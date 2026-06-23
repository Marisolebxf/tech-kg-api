"""Semantic candidate recall for entity binding.

The matcher keeps the original sentence-transformers based recall logic, and
optionally knows how to load real scholar/paper/org samples from MySQL so the
binding demo can be exercised against production-like data.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import numpy as np
try:
    import faiss
except ImportError:  # pragma: no cover - optional dependency
    faiss = None

logger = logging.getLogger(__name__)


class HashingTextEncoder:
    """A lightweight embedding fallback that does not require torch."""

    def __init__(self, dim: int = 768) -> None:
        self.dim = max(64, dim)

    @staticmethod
    def _normalize_text(text: str) -> str:
        text = text.lower().strip()
        return re.sub(r"\s+", " ", text)

    def _iter_ngrams(self, text: str) -> list[str]:
        normalized = self._normalize_text(text)
        if not normalized:
            return []
        chunks = re.findall(r"[\u4e00-\u9fffA-Za-z0-9]+", normalized)
        grams: list[str] = []
        for chunk in chunks:
            if len(chunk) <= 2:
                grams.append(chunk)
                continue
            grams.append(chunk)
            for size in (1, 2, 3):
                if len(chunk) < size:
                    continue
                for index in range(len(chunk) - size + 1):
                    grams.append(chunk[index : index + size])
        if not grams:
            grams.append(normalized)
        return grams

    def encode(self, texts: list[str], normalize_embeddings: bool = True):
        vectors = np.zeros((len(texts), self.dim), dtype=np.float32)
        for row_index, text in enumerate(texts):
            grams = self._iter_ngrams(text)
            if not grams:
                continue
            row = vectors[row_index]
            for gram in grams:
                digest = hashlib.blake2b(gram.encode("utf-8"), digest_size=16).digest()
                slot = int.from_bytes(digest[:4], "big") % self.dim
                sign = 1.0 if digest[4] % 2 == 0 else -1.0
                weight = 1.0 + min(2.0, len(gram) / 4.0)
                row[slot] += sign * weight
        if normalize_embeddings and vectors.size:
            norms = np.linalg.norm(vectors, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            vectors = vectors / norms
        return vectors

try:
    from sentence_transformers import SentenceTransformer
except Exception:  # pragma: no cover - optional dependency / runtime import issues
    SentenceTransformer = None

try:
    from sqlalchemy import create_engine, text
except ImportError:  # pragma: no cover - optional dependency
    create_engine = None
    text = None


class SemanticMatcher:
    """Embedding-based recall for cross-database entity binding."""

    def __init__(self) -> None:
        self.enabled = os.getenv("SEMANTIC_MATCHING_ENABLED", "true").lower() not in {"0", "false", "off", "no"}
        self.model_name = os.getenv("SEMANTIC_MATCHING_MODEL", "moka-ai/m3e-small")
        self.embedding_backend = os.getenv("SEMANTIC_MATCHING_EMBEDDING_BACKEND", "auto").strip().lower()
        self.hashing_dim = max(128, int(os.getenv("SEMANTIC_MATCHING_HASHING_DIM", "768")))
        self.top_k = max(1, int(os.getenv("SEMANTIC_MATCHING_TOP_K", "3")))
        self.min_score = float(os.getenv("SEMANTIC_MATCHING_MIN_SCORE", "0.55"))
        self.faiss_backend = os.getenv("SEMANTIC_MATCHING_FAISS_BACKEND", "hnsw").strip().lower()
        self.faiss_hnsw_m = max(4, int(os.getenv("SEMANTIC_MATCHING_FAISS_HNSW_M", "32")))
        self.faiss_hnsw_ef_construction = max(8, int(os.getenv("SEMANTIC_MATCHING_FAISS_HNSW_EF_CONSTRUCTION", "200")))
        self.faiss_hnsw_ef_search = max(self.top_k, int(os.getenv("SEMANTIC_MATCHING_FAISS_HNSW_EF_SEARCH", "64")))
        self.faiss_oversample = max(1, int(os.getenv("SEMANTIC_MATCHING_FAISS_OVERSAMPLE", "3")))
        self.cache_enabled = os.getenv("SEMANTIC_MATCHING_CACHE_ENABLED", "true").lower() not in {"0", "false", "off", "no"}
        self.cache_dir = Path(os.getenv("SEMANTIC_MATCHING_CACHE_DIR", ".cache/semantic_matcher"))
        self.use_mysql = os.getenv("SEMANTIC_MATCHING_USE_MYSQL", "false").lower() in {"1", "true", "yes", "on"}
        self.mysql_url = os.getenv(
            "SEMANTIC_MATCHING_MYSQL_URL",
            "mysql+pymysql://root:123456789@127.0.0.1:3306/techkg?charset=utf8mb4",
        )
        self.mysql_scholar_table = os.getenv("SEMANTIC_MATCHING_MYSQL_SCHOLAR_TABLE", "scholar")
        self.mysql_paper_table = os.getenv("SEMANTIC_MATCHING_MYSQL_PAPER_TABLE", "paper")
        self.mysql_paper_author_table = os.getenv("SEMANTIC_MATCHING_MYSQL_PAPER_AUTHOR_TABLE", "paper_author")
        self.mysql_coop_table = os.getenv("SEMANTIC_MATCHING_MYSQL_COOP_TABLE", "scholar_paper_cooperation")
        self.mysql_venue_table = os.getenv("SEMANTIC_MATCHING_MYSQL_VENUE_TABLE", "venue")
        self._model = None
        self._model_backend: str | None = None
        self._mysql_engine = None
        self._mysql_cache: dict[str, list[dict[str, Any]]] | None = None
        self._faiss_index_cache: dict[str, dict[str, Any]] = {}
        if self.cache_enabled:
            try:
                self.cache_dir.mkdir(parents=True, exist_ok=True)
            except Exception as exc:  # pragma: no cover - filesystem specific
                logger.warning("Semantic matcher cache directory unavailable, disabling cache: %s", exc)
                self.cache_enabled = False

    def is_available(self) -> bool:
        return self.enabled and self._resolve_embedding_backend() is not None

    def _resolve_embedding_backend(self) -> str | None:
        if not self.enabled:
            return None
        requested = self.embedding_backend
        if requested in {"sentence_transformer", "sentence-transformers", "transformer", "transformers"}:
            if SentenceTransformer is not None:
                return "sentence_transformer"
            return None
        if requested in {"hashing", "hash", "fallback"}:
            return "hashing"
        if SentenceTransformer is not None:
            return "sentence_transformer"
        return "hashing"

    def can_load_mysql(self) -> bool:
        return self.use_mysql and create_engine is not None and text is not None and bool(self.mysql_url)

    def _get_model(self):
        backend = self._resolve_embedding_backend()
        if backend is None:
            return None
        if self._model is not None and self._model_backend == backend:
            return self._model
        if backend == "sentence_transformer":
            try:
                self._model = SentenceTransformer(self.model_name)
                self._model_backend = backend
                return self._model
            except Exception as exc:  # pragma: no cover - runtime model availability
                logger.warning("Failed to load semantic embedding model %s: %s", self.model_name, exc)
                if self.embedding_backend in {"sentence_transformer", "sentence-transformers", "transformer", "transformers"}:
                    return None
                backend = "hashing"
        if backend == "hashing":
            self._model = HashingTextEncoder(dim=self.hashing_dim)
            self._model_backend = backend
            return self._model
        return self._model

    def _get_mysql_engine(self):
        if not self.can_load_mysql():
            return None
        if self._mysql_engine is None:
            self._mysql_engine = create_engine(self.mysql_url, pool_pre_ping=True, future=True)
        return self._mysql_engine

    @staticmethod
    def _json_text(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, (list, tuple, set)):
            return "；".join(str(item).strip() for item in value if str(item).strip())
        if isinstance(value, dict):
            return "；".join(
                f"{str(key).strip()}:{str(val).strip()}"
                for key, val in value.items()
                if str(key).strip() and str(val).strip()
            )
        text_value = str(value).strip()
        if not text_value:
            return ""
        if text_value.startswith("[") or text_value.startswith("{"):
            try:
                parsed = json.loads(text_value)
            except Exception:
                return text_value
            return SemanticMatcher._json_text(parsed)
        return text_value

    @staticmethod
    def _split_text(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, (list, tuple, set)):
            result: list[str] = []
            for item in value:
                text_item = str(item).strip()
                if text_item and text_item not in result:
                    result.append(text_item)
            return result
        text_value = str(value).strip()
        if not text_value:
            return []
        if text_value.startswith("[") or text_value.startswith("{"):
            try:
                parsed = json.loads(text_value)
            except Exception:
                parsed = None
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
        for delimiter in ("；", ";", "、", "|", ","):
            if delimiter in text_value:
                parts = [part.strip() for part in text_value.split(delimiter) if part.strip()]
                if parts:
                    return parts
        return [text_value]

    @staticmethod
    def _first_non_empty(*values: Any) -> str:
        for value in values:
            text_value = str(value).strip()
            if text_value:
                return text_value
        return ""

    def _fetch_mysql_rows(self, sql: str, *, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        engine = self._get_mysql_engine()
        if engine is None:
            return []
        assert text is not None  # for type checkers
        try:
            with engine.connect() as conn:
                result = conn.execute(text(sql), params or {})
                return [dict(row._mapping) for row in result]
        except Exception as exc:  # pragma: no cover - depends on runtime database
            logger.warning("MySQL query failed: %s", exc)
            return []

    @staticmethod
    def _build_keyword_text(raw_value: Any) -> str:
        if raw_value is None:
            return ""
        if isinstance(raw_value, str):
            return raw_value.strip()
        if isinstance(raw_value, (list, tuple, set)):
            return "；".join(str(item).strip() for item in raw_value if str(item).strip())
        return str(raw_value).strip()

    @staticmethod
    def _infer_org_type(org_name: str) -> str:
        if not org_name:
            return ""
        if any(token in org_name for token in ("大学", "学院")):
            return "高校"
        if any(token in org_name for token in ("研究所", "研究院", "实验室")):
            return "科研院所"
        return "机构"

    def _load_mysql_talents(self) -> list[dict[str, Any]]:
        rows = self._fetch_mysql_rows(
            f"""
            SELECT scholar_id, name_zh, name_en, org_name_zh, title,
                   research_direction, paper_nums, citation_nums, h_index
            FROM {self.mysql_scholar_table}
            ORDER BY scholar_id
            """
        )
        talents: list[dict[str, Any]] = []
        for row in rows:
            research_direction = row.get("research_direction")
            fields = self._build_keyword_text(research_direction)
            if not fields:
                fields = self._first_non_empty(row.get("title"), row.get("org_name_zh"))

            scholar_id = self._first_non_empty(row.get("scholar_id"))
            org_name = self._first_non_empty(row.get("org_name_zh"))
            talents.append({
                "id": scholar_id,
                "scholar_id": scholar_id,
                "name_zh": self._first_non_empty(row.get("name_zh")),
                "name_en": self._first_non_empty(row.get("name_en")),
                "scholar_org_name_zh": org_name,
                "scholar_org_name_en": org_name,
                "title": self._first_non_empty(row.get("title")),
                "fields": fields,
                "paper_nums": int(row.get("paper_nums") or 0),
                "citation_nums": int(float(row.get("citation_nums") or 0)),
                "h_index": int(float(row.get("h_index") or 0)),
                "status": 1,
            })
        return talents

    def _load_mysql_papers(self) -> list[dict[str, Any]]:
        papers = self._fetch_mysql_rows(
            f"""
            SELECT paper_id, title, publish_year, publish_date, venue_id, venue_name,
                   venue_type, venue_level, citation_count, keywords, doi, paper_url,
                   abstract_text
            FROM {self.mysql_paper_table}
            ORDER BY paper_id
            """
        )
        authors = self._fetch_mysql_rows(
            f"""
            SELECT paper_id, scholar_id, author_name, author_order, org_name,
                   is_corresponding, author_role
            FROM {self.mysql_paper_author_table}
            ORDER BY paper_id, author_order
            """
        )
        author_map: dict[str, list[dict[str, Any]]] = {}
        for author in authors:
            paper_id = self._first_non_empty(author.get("paper_id"))
            if not paper_id:
                continue
            author_map.setdefault(paper_id, []).append(author)

        paper_nodes: list[dict[str, Any]] = []
        for row in papers:
            paper_id = self._first_non_empty(row.get("paper_id"))
            author_rows = author_map.get(paper_id, [])
            author_names = [self._first_non_empty(author.get("author_name")) for author in author_rows]
            author_names = [name for name in author_names if name]
            institution = self._first_non_empty(
                author_rows[0].get("org_name") if author_rows else "",
                row.get("venue_name"),
            )
            title = self._first_non_empty(row.get("title"))
            keywords = self._build_keyword_text(row.get("keywords"))
            if not keywords:
                keywords = title

            paper_nodes.append({
                "id": paper_id,
                "paper_id": paper_id,
                "zh_name": title,
                "en_name": title,
                "authors": "、".join(dict.fromkeys(author_names)),
                "author_id": self._first_non_empty(author_rows[0].get("scholar_id") if author_rows else ""),
                "institution": institution,
                "cover_date_start": self._first_non_empty(row.get("publish_date"), row.get("publish_year")),
                "keywords": keywords,
                "doi": self._first_non_empty(row.get("doi")),
            })
        return paper_nodes

    def _load_mysql_orgs(self) -> list[dict[str, Any]]:
        rows = self._fetch_mysql_rows(
            f"""
            SELECT DISTINCT org_name_zh
            FROM {self.mysql_scholar_table}
            WHERE org_name_zh IS NOT NULL AND TRIM(org_name_zh) <> ''
            ORDER BY org_name_zh
            """
        )
        orgs: list[dict[str, Any]] = []
        for index, row in enumerate(rows, start=1):
            org_name = self._first_non_empty(row.get("org_name_zh"))
            if not org_name:
                continue
            org_id = f"mysql_org_{index:03d}"
            orgs.append({
                "id": org_id,
                "org_id": org_id,
                "name_cn": org_name,
                "province": "",
                "city": "",
                "org_type": self._infer_org_type(org_name),
            })
        return orgs

    def load_mysql_binding_data(self) -> dict[str, list[dict[str, Any]]]:
        """Load real binding source data from MySQL if enabled.

        Returns an empty dict when the MySQL mode is disabled or unavailable.
        """
        if not self.can_load_mysql():
            return {}
        if self._mysql_cache is not None:
            return self._mysql_cache

        try:
            talents = self._load_mysql_talents()
            papers = self._load_mysql_papers()
            orgs = self._load_mysql_orgs()
            self._mysql_cache = {
                "talents": talents,
                "papers": papers,
                "orgs": orgs,
                "source": "mysql",
            }
            logger.info(
                "Loaded MySQL binding data: talents=%d papers=%d orgs=%d",
                len(talents),
                len(papers),
                len(orgs),
            )
            return self._mysql_cache
        except Exception as exc:  # pragma: no cover - runtime/environment specific
            logger.warning("Failed to load MySQL binding data: %s", exc)
            return {}

    def _encode_texts(self, texts: list[str]) -> np.ndarray | None:
        if not texts:
            return None
        model = self._get_model()
        if model is None:
            return None
        try:
            vectors = model.encode(texts, normalize_embeddings=True)
            return np.asarray(vectors, dtype=np.float32)
        except Exception as exc:  # pragma: no cover - depends on runtime model availability
            logger.warning("Semantic embedding failed: %s", exc)
            return None

    @staticmethod
    def _normalize_text(text: Any) -> str:
        return " ".join(str(text or "").split()).strip()

    @staticmethod
    def _stable_hash(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def _build_text_signature(
        self,
        items: list[dict[str, Any]],
        *,
        text_builder: Callable[[dict[str, Any]], str],
        key_getter: Callable[[dict[str, Any]], str],
    ) -> str:
        hasher = hashlib.sha256()
        for item in items:
            item_key = self._normalize_text(key_getter(item))
            item_text = self._normalize_text(text_builder(item))
            hasher.update(item_key.encode("utf-8"))
            hasher.update(b"\0")
            hasher.update(item_text.encode("utf-8"))
            hasher.update(b"\n")
        return hasher.hexdigest()

    def _cache_key(self, namespace: str, signature: str) -> str:
        cache_token = self._stable_hash(
            f"{self.model_name}|{self.faiss_backend}|{namespace}|{signature}"
        )[:24]
        return f"{namespace}-{cache_token}"

    def _cache_paths(self, cache_key: str) -> tuple[Path, Path]:
        return (
            self.cache_dir / f"{cache_key}.index",
            self.cache_dir / f"{cache_key}.json",
        )

    def _load_cached_index(self, cache_key: str) -> dict[str, Any] | None:
        if not self.cache_enabled or faiss is None:
            return None
        if cache_key in self._faiss_index_cache:
            return self._faiss_index_cache[cache_key]
        index_path, meta_path = self._cache_paths(cache_key)
        if not index_path.exists() or not meta_path.exists():
            return None
        try:
            with meta_path.open("r", encoding="utf-8") as handle:
                meta = json.load(handle)
            index = faiss.read_index(str(index_path))
            if meta.get("backend") == "hnsw" and hasattr(index, "hnsw"):
                index.hnsw.efSearch = self.faiss_hnsw_ef_search
            record = {
                "index": index,
                "score_mode": str(meta.get("score_mode", "ip")),
                "dim": int(meta.get("dim", 0)),
                "count": int(meta.get("count", 0)),
                "signature": str(meta.get("signature", "")),
            }
            self._faiss_index_cache[cache_key] = record
            return record
        except Exception as exc:  # pragma: no cover - cache file/runtime specific
            logger.warning("Load cached FAISS index failed for %s: %s", cache_key, exc)
            return None

    def _store_cached_index(
        self,
        cache_key: str,
        *,
        index: Any,
        score_mode: str,
        dim: int,
        count: int,
        signature: str,
    ) -> None:
        record = {
            "index": index,
            "score_mode": score_mode,
            "dim": dim,
            "count": count,
            "signature": signature,
        }
        self._faiss_index_cache[cache_key] = record
        if not self.cache_enabled or faiss is None:
            return
        try:
            index_path, meta_path = self._cache_paths(cache_key)
            faiss.write_index(index, str(index_path))
            with meta_path.open("w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "cache_key": cache_key,
                        "backend": self.faiss_backend,
                        "score_mode": score_mode,
                        "dim": dim,
                        "count": count,
                        "signature": signature,
                        "model_name": self.model_name,
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    },
                    handle,
                    ensure_ascii=False,
                )
        except Exception as exc:  # pragma: no cover - filesystem specific
            logger.warning("Store cached FAISS index failed for %s: %s", cache_key, exc)

    @staticmethod
    def _normalize_vectors(vectors: np.ndarray) -> np.ndarray:
        normalized = np.ascontiguousarray(vectors, dtype=np.float32)
        if normalized.ndim == 1:
            normalized = normalized.reshape(1, -1)
        if faiss is not None and normalized.size > 0:
            faiss.normalize_L2(normalized)
        return normalized

    @staticmethod
    def _item_identity(item: dict[str, Any]) -> str:
        return str(item.get("id") or item.get("scholar_id") or item.get("paper_id") or item.get("patent_id") or item.get("org_id") or "")

    def _build_faiss_index(self, right_vectors: np.ndarray):
        if faiss is None or right_vectors.size == 0:
            return None, "matrix"

        vectors = self._normalize_vectors(right_vectors)
        dim = int(vectors.shape[1])

        try:
            if self.faiss_backend == "flat":
                base_index = faiss.IndexFlatIP(dim)
                score_mode = "ip"
            else:
                base_index = faiss.IndexHNSWFlat(dim, self.faiss_hnsw_m, faiss.METRIC_INNER_PRODUCT)
                base_index.hnsw.efConstruction = self.faiss_hnsw_ef_construction
                base_index.hnsw.efSearch = self.faiss_hnsw_ef_search
                score_mode = "ip"

            index = base_index
            index.add(vectors)
            return index, score_mode
        except Exception as exc:  # pragma: no cover - depends on runtime faiss support
            logger.warning("Failed to build FAISS index, falling back to matrix search: %s", exc)
            return None, "matrix"

    @staticmethod
    def _faiss_score(distance: float, score_mode: str) -> float:
        if score_mode == "ip":
            return max(0.0, min(1.0, float(distance)))
        return max(0.0, min(1.0, float(distance)))

    def _load_or_build_faiss_index(
        self,
        *,
        namespace: str,
        items: list[dict[str, Any]],
        text_builder: Callable[[dict[str, Any]], str],
        key_getter: Callable[[dict[str, Any]], str] | None = None,
    ) -> tuple[Any | None, str, str]:
        if not self.is_available() or not items:
            return None, "matrix", ""
        if faiss is None:
            return None, "matrix", ""

        key_getter = key_getter or self._item_identity
        signature = self._build_text_signature(items, text_builder=text_builder, key_getter=key_getter)
        cache_key = self._cache_key(namespace, signature)
        cached = self._load_cached_index(cache_key)
        if cached is not None:
            return cached.get("index"), str(cached.get("score_mode", "ip")), cache_key

        texts = [text_builder(item) for item in items]
        vectors = self._encode_texts(texts)
        if vectors is None:
            return None, "matrix", cache_key
        index, score_mode = self._build_faiss_index(vectors)
        if index is not None:
            self._store_cached_index(
                cache_key,
                index=index,
                score_mode=score_mode,
                dim=int(vectors.shape[1]),
                count=len(items),
                signature=signature,
            )
        return index, score_mode, cache_key

    def prewarm_binding_indexes(
        self,
        binding_data: dict[str, list[dict[str, Any]]] | None = None,
    ) -> dict[str, str]:
        """Pre-build and cache the main recall indexes.

        This is a lightweight offline warmup hook used by startup jobs or
        manual data preparation flows. It only builds the right-side indexes
        needed by the matcher and stores them on disk when caching is enabled.
        """
        if not self.is_available() or faiss is None:
            return {}

        binding_data = binding_data or self.load_mysql_binding_data()
        if not binding_data:
            return {}

        warmed: dict[str, str] = {}
        warm_targets: list[tuple[str, list[dict[str, Any]], Callable[[dict[str, Any]], str], str]] = [
            ("talent_to_paper", binding_data.get("papers") or [], self._build_paper_text, "papers"),
            ("talent_to_patent", binding_data.get("patents") or [], self._build_patent_text, "patents"),
            ("org_a_to_org_b", binding_data.get("orgs") or [], self._build_org_text, "orgs"),
        ]
        for namespace, items, builder, label in warm_targets:
            if not items:
                continue
            try:
                _, _, cache_key = self._load_or_build_faiss_index(
                    namespace=namespace,
                    items=items,
                    text_builder=builder,
                )
                if cache_key:
                    warmed[label] = cache_key
            except Exception as exc:  # pragma: no cover - warmup is best effort
                logger.warning("Semantic index warmup failed for %s: %s", namespace, exc)
        return warmed

    def _retrieve_candidates(
        self,
        left_items: list[dict[str, Any]],
        right_items: list[dict[str, Any]],
        *,
        left_text_builder: Callable[[dict[str, Any]], str],
        right_text_builder: Callable[[dict[str, Any]], str],
        left_key: str,
        right_key: str,
        dedupe_same_id: bool = False,
    ) -> list[dict[str, Any]]:
        if not self.is_available() or not left_items or not right_items:
            return []

        left_texts = [left_text_builder(item) for item in left_items]
        left_vectors = self._encode_texts(left_texts)
        if left_vectors is None:
            return []

        candidates: list[dict[str, Any]] = []
        index, score_mode, _cache_key = self._load_or_build_faiss_index(
            namespace=f"{left_key}_to_{right_key}",
            items=right_items,
            text_builder=right_text_builder,
        )
        if index is not None:
            search_k = min(
                len(right_items),
                max(self.top_k, self.top_k * self.faiss_oversample if dedupe_same_id else self.top_k),
            )
            query_vectors = self._normalize_vectors(left_vectors)
            try:
                distances, indices = index.search(query_vectors, search_k)
                for left_index, (row_distances, row_indices) in enumerate(zip(distances, indices)):
                    left_item = left_items[left_index]
                    left_id = self._item_identity(left_item)
                    for distance, right_index in zip(row_distances, row_indices):
                        if int(right_index) < 0:
                            continue
                        right_item = right_items[int(right_index)]
                        right_id = self._item_identity(right_item)
                        if dedupe_same_id and left_id and right_id and left_id == right_id:
                            continue

                        semantic_score = self._faiss_score(float(distance), score_mode)
                        if semantic_score < self.min_score:
                            continue

                        candidates.append({
                            left_key: left_item,
                            right_key: right_item,
                            "semantic_score": round(semantic_score, 4),
                        })
                return candidates
            except Exception as exc:  # pragma: no cover - depends on runtime faiss support
                logger.warning("FAISS search failed, falling back to matrix search: %s", exc)

        right_texts = [right_text_builder(item) for item in right_items]
        right_vectors = self._encode_texts(right_texts)
        if right_vectors is None:
            return []
        score_matrix = left_vectors @ right_vectors.T
        top_k = min(self.top_k, len(right_items))
        ranked_indices = np.argsort(-score_matrix, axis=1)[:, :top_k]

        for left_index, right_indices in enumerate(ranked_indices):
            left_item = left_items[left_index]
            left_id = self._item_identity(left_item)
            for right_index in right_indices:
                right_item = right_items[int(right_index)]
                right_id = self._item_identity(right_item)
                if dedupe_same_id and left_id and right_id and left_id == right_id:
                    continue

                semantic_score = float(score_matrix[left_index][int(right_index)])
                if semantic_score < self.min_score:
                    continue

                candidates.append({
                    left_key: left_item,
                    right_key: right_item,
                    "semantic_score": round(semantic_score, 4),
                })
        return candidates

    @staticmethod
    def _build_talent_text(talent: dict[str, Any]) -> str:
        parts = [
            talent.get("name_zh", ""),
            talent.get("name_en", ""),
            talent.get("scholar_org_name_zh", ""),
            talent.get("scholar_org_name_en", ""),
            talent.get("title", ""),
            talent.get("fields", ""),
            f"论文数:{talent.get('paper_nums', '')}",
            f"引用数:{talent.get('citation_nums', '')}",
            f"h指数:{talent.get('h_index', '')}",
        ]
        return " ".join(part for part in parts if part)

    @staticmethod
    def _build_paper_text(paper: dict[str, Any]) -> str:
        parts = [
            paper.get("authors", ""),
            paper.get("institution", ""),
            paper.get("zh_name", ""),
            paper.get("en_name", ""),
            paper.get("publication_zh_name", ""),
            paper.get("publication_type", ""),
            paper.get("keywords", ""),
            paper.get("zh_abstract", ""),
        ]
        return " ".join(part for part in parts if part)

    @staticmethod
    def _build_patent_text(patent: dict[str, Any]) -> str:
        parts = [
            patent.get("first_inventor_name", ""),
            patent.get("first_applicant_name", ""),
            patent.get("title_zh", ""),
            patent.get("keywords", ""),
        ]
        return " ".join(part for part in parts if part)

    @staticmethod
    def _build_org_text(org: dict[str, Any]) -> str:
        parts = [
            org.get("name_cn", ""),
            org.get("province", ""),
            org.get("city", ""),
            org.get("org_type", ""),
        ]
        return " ".join(part for part in parts if part)

    def match_talent_paper(
        self, talents: list[dict[str, Any]], papers: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        return self._retrieve_candidates(
            talents,
            papers,
            left_text_builder=self._build_talent_text,
            right_text_builder=self._build_paper_text,
            left_key="talent",
            right_key="paper",
        )

    def match_talent_patent(
        self, talents: list[dict[str, Any]], patents: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        return self._retrieve_candidates(
            talents,
            patents,
            left_text_builder=self._build_talent_text,
            right_text_builder=self._build_patent_text,
            left_key="talent",
            right_key="patent",
        )

    def match_org_org(self, orgs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        candidates = self._retrieve_candidates(
            orgs,
            orgs,
            left_text_builder=self._build_org_text,
            right_text_builder=self._build_org_text,
            left_key="org_a",
            right_key="org_b",
            dedupe_same_id=True,
        )
        deduped: dict[tuple[str, str], dict[str, Any]] = {}
        for candidate in candidates:
            left = candidate["org_a"]
            right = candidate["org_b"]
            left_id = str(left.get("id") or left.get("org_id") or "")
            right_id = str(right.get("id") or right.get("org_id") or "")
            ordered = tuple(sorted((left_id, right_id)))
            existing = deduped.get(ordered)
            if existing is None or candidate["semantic_score"] > existing["semantic_score"]:
                deduped[ordered] = candidate
        return list(deduped.values())
