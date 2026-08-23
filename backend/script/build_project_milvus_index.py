"""构建项目域 Milvus 索引（BM25 稀疏 + m3e-small 稠密 + RRF 混合检索）。

集合：``project``
数据源：TRSGraph ``dev`` 中的 Project 顶点；可选从 MySQL 补齐资助机构/负责人/关键词。

用法::

    cd backend
    uv sync --extra milvus
    MILVUS_URI=http://127.0.0.1:19530 TRS_GRAPH_SPACE=dev \\
      uv run python -m script.build_project_milvus_index --dry-run
    MILVUS_URI=http://127.0.0.1:19530 TRS_GRAPH_SPACE=dev \\
      uv run python -m script.build_project_milvus_index --drop-existing
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from infra.graph_db import get_trs_graph_client
from infra.milvus import get_milvus_client
from script.project_graph_utils import parse_list
from service.project_milvus import (
    COLLECTION_NAME,
    DENSE_DIM,
    DENSE_MODEL_NAME,
    DENSE_TEXT_MAX_CHARS,
    RRF_K,
    STORED_TEXT_MAX_CHARS,
    build_project_index_params,
    build_project_schema,
    clean_text,
    compose_project_text,
    sparse_to_dict,
    truncate_text,
)

logger = logging.getLogger("script.build_project_milvus_index")

GRAPH_SPACE = os.getenv("TRS_GRAPH_SPACE", "dev")
ARTIFACT_DIR = Path(os.environ.get("PROJECT_MILVUS_ARTIFACT_DIR", ".milvus_artifacts/project"))


def _require_dev_space() -> None:
    space = os.getenv("TRS_GRAPH_SPACE")
    if space != GRAPH_SPACE:
        raise RuntimeError(f"Project Milvus index requires TRS_GRAPH_SPACE=dev, got {space!r}")


def _iter_project_vertices(graph: Any, batch_size: int = 200):
    """Page Project vertices via nGQL (more reliable than label REST on some TRSGraph builds)."""
    offset = 0
    while True:
        query = (
            f"USE {GRAPH_SPACE}; MATCH (v:Project) "
            f"RETURN id(v) AS vid, properties(v) AS p "
            f"SKIP {offset} LIMIT {batch_size};"
        )
        result = graph.execute_read(query)
        records = getattr(result, "records", None) or []
        if not records:
            break
        for row in records:
            vid = str(row.get("vid") or "")
            props = dict(row.get("p") or {})
            if not vid.startswith("project_"):
                continue
            yield {"vid": vid, "props": props}
        offset += len(records)
        if len(records) < batch_size:
            break


def _load_mysql_enrichment(record_ids: set[str]) -> dict[str, dict[str, str]]:
    """Optional MySQL enrichment for fields not stored on the Project Tag."""
    if not record_ids:
        return {}
    try:
        from dao.project import ProjectDAO
        from infra.mysql import get_mysql_client
    except Exception as exc:  # noqa: BLE001
        logger.warning("MySQL enrichment unavailable: %s", exc)
        return {}

    enrichment: dict[str, dict[str, str]] = {}
    mysql = get_mysql_client()
    session = mysql.session()
    try:
        dao = ProjectDAO(session)
        for list_fn in (dao.list_zh, dao.list_en):
            offset = 0
            while True:
                rows = list_fn(offset=offset, limit=200)
                if not rows:
                    break
                for row in rows:
                    rid = str(row.id)
                    if rid not in record_ids:
                        continue
                    keywords = "；".join(parse_list(row.keywords))
                    enrichment[rid] = {
                        "funded_institution": clean_text(row.funded_institution),
                        "project_host": clean_text(row.project_host),
                        "keywords": keywords,
                    }
                offset += len(rows)
                if len(rows) < 200:
                    break
    except Exception as exc:  # noqa: BLE001
        logger.warning("MySQL enrichment failed: %s", exc)
        return {}
    finally:
        session.close()
    return enrichment


def _get_dense_encoder():
    from pymilvus.model.dense import SentenceTransformerEmbeddingFunction  # type: ignore

    return SentenceTransformerEmbeddingFunction(
        model_name=DENSE_MODEL_NAME,
        device=os.environ.get("PROJECT_DENSE_DEVICE", "cpu"),
    )


def _get_bm25_encoder(corpus: list[str]) -> Any:
    """Fit project BM25 with jieba analyzer (same approach as paper domain; no org reuse)."""
    import jieba  # type: ignore[import-not-found]
    from pymilvus.model.sparse.bm25 import BM25EmbeddingFunction  # type: ignore[import-not-found]

    def zh_analyzer(text: str) -> list[str]:
        return [token for token in jieba.cut(text) if token.strip()]

    bm25 = BM25EmbeddingFunction(analyzer=zh_analyzer, k1=1.5, b=0.75)
    bm25.fit(corpus)
    return bm25


def _ensure_collection(client: Any, *, drop_existing: bool) -> None:
    has = client.has_collection(COLLECTION_NAME)
    if has and drop_existing:
        logger.info("dropping existing collection %s", COLLECTION_NAME)
        client.drop_collection(COLLECTION_NAME)
        has = False
    if not has:
        logger.info("creating collection %s", COLLECTION_NAME)
        client.create_collection(
            collection_name=COLLECTION_NAME,
            schema=build_project_schema(client),
            index_params=build_project_index_params(client),
        )
    else:
        logger.info("collection %s already exists (will upsert)", COLLECTION_NAME)


def _write_artifacts(
    *,
    corpus: list[str],
    written: int,
) -> Path:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    corpus_sha = hashlib.sha256("\n".join(corpus).encode("utf-8")).hexdigest()
    bm25_path = ARTIFACT_DIR / "bm25.json"
    bm25_path.write_text(
        json.dumps(
            {
                "analyzer": "jieba",
                "k1": 1.5,
                "b": 0.75,
                "document_count": len(corpus),
                "note": "BM25 fit in-process via milvus-model BM25EmbeddingFunction; not org BM25SparseEncoder",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    bm25_sha = hashlib.sha256(bm25_path.read_bytes()).hexdigest()
    manifest = {
        "alias": COLLECTION_NAME,
        "collection_name": COLLECTION_NAME,
        "entity_type": "Project",
        "graph_space": GRAPH_SPACE,
        "row_count": written,
        "dense_dim": DENSE_DIM,
        "dense_model": DENSE_MODEL_NAME,
        "dense_text_max_chars": DENSE_TEXT_MAX_CHARS,
        "text_max_bytes": STORED_TEXT_MAX_CHARS,
        "hybrid": {"ranker": "RRF", "k": RRF_K, "component_top_k": 20},
        "bm25": {
            "analyzer": "jieba",
            "language": "zh",
            "k1": 1.5,
            "b": 0.75,
            "library": "pymilvus.model.sparse.bm25.BM25EmbeddingFunction",
            "state_file": "bm25.json",
            "sha256": bm25_sha,
        },
        "indexes": {
            "dense_vec": {
                "index_type": "HNSW",
                "metric_type": "COSINE",
                "params": {"M": 16, "efConstruction": 200, "search_ef": 128},
            },
            "sparse_vec": {
                "index_type": "SPARSE_INVERTED_INDEX",
                "metric_type": "IP",
                "params": {"drop_ratio_build": 0.0},
            },
        },
        "corpus_sha256": corpus_sha,
        "created_at": datetime.now(UTC).isoformat(),
        "schema_version": 1,
    }
    path = ARTIFACT_DIR / "manifest.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def collect_project_records(graph: Any, *, enrich_mysql: bool = True) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for item in _iter_project_vertices(graph):
        props = dict(item["props"])
        props.setdefault("source_record_id", item["vid"].removeprefix("project_"))
        records.append({"vid": item["vid"], "props": props})
    if enrich_mysql and records:
        ids = {str(rec["props"].get("source_record_id") or "") for rec in records}
        enrichment = _load_mysql_enrichment({i for i in ids if i})
        for rec in records:
            rid = str(rec["props"].get("source_record_id") or "")
            if rid in enrichment:
                rec["props"].update(enrichment[rid])
    for rec in records:
        text = compose_project_text(rec["props"])
        rec["text"] = text
    return [rec for rec in records if rec["text"]]


def run(
    *,
    dry_run: bool,
    drop_existing: bool,
    enrich_mysql: bool = True,
    preview: int = 5,
) -> dict[str, Any]:
    _require_dev_space()
    graph = get_trs_graph_client()
    logger.info(
        "start collection=%s dry_run=%s drop_existing=%s dense_model=%s",
        COLLECTION_NAME,
        dry_run,
        drop_existing,
        DENSE_MODEL_NAME,
    )
    records = collect_project_records(graph, enrich_mysql=enrich_mysql)
    texts = [rec["text"] for rec in records]
    logger.info("collected %d Project vertices with text", len(records))
    if not records:
        return {"collection": COLLECTION_NAME, "written": 0, "reason": "no projects"}

    if dry_run:
        for rec in records[:preview]:
            logger.info("[dry-run] %s -> %s", rec["vid"], rec["text"][:120])
        _write_artifacts(corpus=texts, written=0)
        return {
            "collection": COLLECTION_NAME,
            "written": 0,
            "candidates": len(records),
            "dry_run": True,
        }

    logger.info("loading dense encoder (%s)...", DENSE_MODEL_NAME)
    dense_encoder = _get_dense_encoder()
    dense_vecs = dense_encoder.encode_documents(
        [truncate_text(text, DENSE_TEXT_MAX_CHARS) for text in texts]
    )
    logger.info("fitting BM25 (jieba) on %d docs...", len(texts))
    bm25 = _get_bm25_encoder(texts)
    sparse_vecs = bm25.encode_documents(texts)

    client = get_milvus_client()
    _ensure_collection(client, drop_existing=drop_existing)

    rows: list[dict[str, Any]] = []
    for i, rec in enumerate(records):
        props = rec["props"]
        dense = dense_vecs[i]
        rows.append(
            {
                "vid": rec["vid"],
                "project_number": clean_text(props.get("project_number"))[:120],
                "title": clean_text(props.get("title"))[:1000],
                "source": clean_text(props.get("source"))[:60],
                "source_table": clean_text(props.get("source_table"))[:120],
                "source_record_id": clean_text(props.get("source_record_id"))[:120],
                "approval_year": clean_text(props.get("approval_year"))[:30],
                "text": truncate_text(texts[i], STORED_TEXT_MAX_CHARS),
                "dense_vec": dense.tolist() if hasattr(dense, "tolist") else list(dense),
                "sparse_vec": sparse_to_dict(sparse_vecs[i]),
            }
        )

    batch = 200
    written = 0
    for i in range(0, len(rows), batch):
        chunk = rows[i : i + batch]
        client.upsert(collection_name=COLLECTION_NAME, data=chunk)
        written += len(chunk)
        logger.info("upserted %d/%d", written, len(rows))
    client.flush(collection_name=COLLECTION_NAME)
    manifest = _write_artifacts(corpus=texts, written=written)
    logger.info("done collection=%s written=%d manifest=%s", COLLECTION_NAME, written, manifest)
    return {"collection": COLLECTION_NAME, "written": written, "candidates": len(records)}


def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--drop-existing", action="store_true")
    ap.add_argument(
        "--no-mysql-enrich",
        action="store_true",
        help="only use graph Project properties (skip MySQL funded_institution/host/keywords)",
    )
    ap.add_argument("--preview", type=int, default=5)
    return ap.parse_args()


def main() -> None:
    load_dotenv()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    args = _parse_args()
    result = run(
        dry_run=args.dry_run,
        drop_existing=args.drop_existing,
        enrich_mysql=not args.no_mysql_enrich,
        preview=args.preview,
    )
    logger.info("result: %s", result)


if __name__ == "__main__":
    main()
