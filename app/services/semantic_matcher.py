"""Semantic candidate recall for entity binding using sentence-transformers."""

from __future__ import annotations

import logging
import os
from typing import Any, Callable

import numpy as np

logger = logging.getLogger(__name__)

try:
    from sentence_transformers import SentenceTransformer
except ImportError:  # pragma: no cover - optional dependency
    SentenceTransformer = None


class SemanticMatcher:
    """Embedding-based recall for cross-database entity binding."""

    def __init__(self) -> None:
        self.enabled = os.getenv("SEMANTIC_MATCHING_ENABLED", "true").lower() not in {"0", "false", "off", "no"}
        self.model_name = os.getenv("SEMANTIC_MATCHING_MODEL", "moka-ai/m3e-small")
        self.top_k = max(1, int(os.getenv("SEMANTIC_MATCHING_TOP_K", "3")))
        self.min_score = float(os.getenv("SEMANTIC_MATCHING_MIN_SCORE", "0.55"))
        self._model = None

    def is_available(self) -> bool:
        return self.enabled and SentenceTransformer is not None

    def _get_model(self):
        if not self.is_available():
            return None
        if self._model is None:
            self._model = SentenceTransformer(self.model_name)
        return self._model

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
        right_texts = [right_text_builder(item) for item in right_items]
        left_vectors = self._encode_texts(left_texts)
        right_vectors = self._encode_texts(right_texts)
        if left_vectors is None or right_vectors is None:
            return []

        score_matrix = left_vectors @ right_vectors.T
        top_k = min(self.top_k, len(right_items))
        ranked_indices = np.argsort(-score_matrix, axis=1)[:, :top_k]

        candidates: list[dict[str, Any]] = []
        for left_index, right_indices in enumerate(ranked_indices):
            left_item = left_items[left_index]
            left_id = str(left_item.get("id") or left_item.get("scholar_id") or left_item.get("org_id") or "")
            for right_index in right_indices:
                right_item = right_items[int(right_index)]
                right_id = str(right_item.get("id") or right_item.get("paper_id") or right_item.get("patent_id") or right_item.get("org_id") or "")
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
            talent.get("fields", ""),
        ]
        return " ".join(part for part in parts if part)

    @staticmethod
    def _build_paper_text(paper: dict[str, Any]) -> str:
        parts = [
            paper.get("authors", ""),
            paper.get("institution", ""),
            paper.get("zh_name", ""),
            paper.get("en_name", ""),
            paper.get("keywords", ""),
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
