"""构建学者领域 Milvus 索引。

集合：``scholar_person``
用途：给 Person 顶点建立文本检索索引（BM25 稀疏 + 稠密语义 + 混合检索）。

数据来源：
  - TRSGraph dev 空间中的 Person 顶点（``person_{scholar_id}``）
  - 每条顶点合成一段文本：
        {name_zh}｜{name_en}｜机构：{scholar_org}｜研究方向：{research_fields}｜简介：{bio_zh[:500]}

索引配置：
  - dense_vec: FLOAT_VECTOR (512d, m3e-small), HNSW / L2
  - sparse_vec: SPARSE_FLOAT_VECTOR, SPARSE_INVERTED_INDEX / BM25 (k1=1.5, b=0.75)

用法::

    # 干跑：只统计与预览，不落 Milvus
    uv run python -m script.build_scholar_milvus_index --dry-run

    # 实际构建（首次会下载 m3e-small 模型 ~100MB）
    MILVUS_URI=http://127.0.0.1:19531 \\
    TRS_GRAPH_BASE_URL=http://127.0.0.1:8090 \\
    TRS_GRAPH_SPACE=dev TRS_GRAPH_API_KEY=ysukeg \\
        uv run python -m script.build_scholar_milvus_index

    # 增量刷新（drop + rebuild）
    uv run python -m script.build_scholar_milvus_index --drop-existing
"""

from __future__ import annotations

import argparse
import logging
import os
from typing import Any

from infra.graph_db import get_trs_graph_client
from infra.milvus import get_milvus_client

logger = logging.getLogger("script.build_scholar_milvus_index")

COLLECTION_NAME = os.environ.get("SCHOLAR_MILVUS_COLLECTION", "scholar_person")
DENSE_DIM = 512  # m3e-small
DENSE_MODEL_NAME = os.environ.get("SCHOLAR_DENSE_MODEL", "moka-ai/m3e-small")
BIO_MAX_CHARS = 500

# 只索引本领域直接抽取的学者顶点：source_table == "dwd_scholar"。
# 其他领域（论文/项目/专利）产生的 person_{md5(name)} 桩节点不入本集合，
# 它们将作为查询方使用本集合来查真实学者。
SCHOLAR_SOURCE_TABLE = "dwd_scholar"


# ---------------------------------------------------------------------------
# 文本拼接
# ---------------------------------------------------------------------------
def _clean(v: Any) -> str:
    if v is None:
        return ""
    s = str(v).strip()
    return s.replace("\n", " ").replace("\r", " ")


def _compose_text(props: dict) -> str:
    name_zh = _clean(props.get("name_zh"))
    name_en = _clean(props.get("name_en"))
    org = _clean(props.get("scholar_org"))
    fields = _clean(props.get("research_fields"))
    bio = _clean(props.get("bio_zh"))[:BIO_MAX_CHARS]
    parts = [
        name_zh or name_en,
        name_en if name_zh and name_en else "",
        f"机构：{org}" if org else "",
        f"研究方向：{fields}" if fields else "",
        f"简介：{bio}" if bio else "",
    ]
    return "｜".join(p for p in parts if p)


# ---------------------------------------------------------------------------
# 从 TRSGraph 拉学者
# ---------------------------------------------------------------------------
def _iter_person_vertices(graph: Any, batch_size: int = 200):
    """按 offset+limit 从 TRSGraph 拉 Person 顶点。

    只保留学者领域直接抽取的顶点（``source_table == "dwd_scholar"``），
    过滤掉其他领域造出的 ``person_{md5(name)}`` 桩节点——那些没有稳定
    ``scholar_id``，也不带业务属性，不该占用学者检索/消歧的候选池。
    """
    offset = 0
    seen = kept = 0
    while True:
        page = graph.get_nodes_by_label("Person", offset=offset, limit=batch_size)
        items = getattr(page, "items", None) or []
        if not items:
            break
        for node in items:
            seen += 1
            props = dict(getattr(node, "properties", None) or {})
            vid = str(getattr(node, "id", "") or "")
            if not vid or not vid.startswith("person_"):
                continue
            if props.get("source_table") != SCHOLAR_SOURCE_TABLE:
                continue
            scholar_id = props.get("source_record_id") or vid.removeprefix("person_")
            kept += 1
            yield {"vid": vid, "scholar_id": scholar_id, "props": props}
        offset += len(items)
        if len(items) < batch_size:
            break
    logger.info(
        "person scan: total=%d kept(source_table=%s)=%d",
        seen,
        SCHOLAR_SOURCE_TABLE,
        kept,
    )


# ---------------------------------------------------------------------------
# 集合定义
# ---------------------------------------------------------------------------
def _build_schema(client: Any):
    from pymilvus import DataType  # type: ignore

    schema = client.create_schema(auto_id=False, enable_dynamic_field=True)
    schema.add_field("vid", DataType.VARCHAR, is_primary=True, max_length=128)
    schema.add_field("scholar_id", DataType.VARCHAR, max_length=64)
    schema.add_field("name_zh", DataType.VARCHAR, max_length=256)
    schema.add_field("name_en", DataType.VARCHAR, max_length=256)
    schema.add_field("scholar_org", DataType.VARCHAR, max_length=1024)
    schema.add_field("research_fields", DataType.VARCHAR, max_length=1024)
    schema.add_field("text", DataType.VARCHAR, max_length=4096)
    schema.add_field("dense_vec", DataType.FLOAT_VECTOR, dim=DENSE_DIM)
    schema.add_field("sparse_vec", DataType.SPARSE_FLOAT_VECTOR)
    return schema


def _build_index_params(client: Any):
    index_params = client.prepare_index_params()
    index_params.add_index(
        field_name="dense_vec",
        index_type="HNSW",
        metric_type="COSINE",
        params={"M": 16, "efConstruction": 200},
    )
    index_params.add_index(
        field_name="sparse_vec",
        index_type="SPARSE_INVERTED_INDEX",
        metric_type="IP",
        params={"drop_ratio_build": 0.0},
    )
    return index_params


def _ensure_collection(client: Any, drop_existing: bool):
    has = client.has_collection(COLLECTION_NAME)
    if has and drop_existing:
        logger.info("dropping existing collection %s", COLLECTION_NAME)
        client.drop_collection(COLLECTION_NAME)
        has = False
    if not has:
        logger.info("creating collection %s", COLLECTION_NAME)
        client.create_collection(
            collection_name=COLLECTION_NAME,
            schema=_build_schema(client),
            index_params=_build_index_params(client),
        )
    else:
        logger.info("collection %s already exists (will upsert)", COLLECTION_NAME)


# ---------------------------------------------------------------------------
# Embedders
# ---------------------------------------------------------------------------
def _get_dense_encoder():
    """加载 m3e-small 稠密编码器。"""
    from pymilvus.model.dense import SentenceTransformerEmbeddingFunction  # type: ignore

    return SentenceTransformerEmbeddingFunction(
        model_name=DENSE_MODEL_NAME,
        device=os.environ.get("SCHOLAR_DENSE_DEVICE", "cpu"),
    )


def _get_bm25_encoder(corpus: list[str]):
    """构建并 fit BM25 稀疏编码器。"""
    from pymilvus.model.sparse.bm25 import BM25EmbeddingFunction  # type: ignore
    from pymilvus.model.sparse.bm25.tokenizers import build_default_analyzer  # type: ignore

    analyzer = build_default_analyzer(language="zh")
    bm25 = BM25EmbeddingFunction(analyzer=analyzer, k1=1.5, b=0.75)
    bm25.fit(corpus)
    return bm25


def _sparse_row_to_dict(sparse_vec, index: int) -> dict[int, float]:
    """把 BM25 ``encode_documents`` 返回的 csr/coo 行转成 ``{token_id: weight}``。

    ``pymilvus.model.sparse.BM25EmbeddingFunction.encode_documents`` 返回
    ``scipy.sparse.csr_array`` (shape (n_docs, vocab))，``[i]`` 出来的是 1D
    ``coo_array``。Milvus 2.4 的 upsert 期望每条稀疏向量是 dict 或 1×N csr，
    这里统一转 dict 最稳。
    """
    row = sparse_vec.getrow(index) if hasattr(sparse_vec, "getrow") else sparse_vec[index]
    coo = row.tocoo() if hasattr(row, "tocoo") else row
    if hasattr(coo, "col"):
        keys = coo.col
    else:
        # 1D coo_array: coords 是 (indices,)
        keys = coo.coords[0]
    return {int(k): float(v) for k, v in zip(keys, coo.data, strict=False)}


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def run(*, dry_run: bool, drop_existing: bool, preview: int = 5, limit: int | None = None) -> dict:
    graph = get_trs_graph_client()
    logger.info(
        "start collection=%s dry_run=%s drop_existing=%s dense_model=%s limit=%s",
        COLLECTION_NAME,
        dry_run,
        drop_existing,
        DENSE_MODEL_NAME,
        limit,
    )

    # 1) 拉学者顶点 + 拼文本
    records: list[dict] = []
    texts: list[str] = []
    for rec in _iter_person_vertices(graph):
        text = _compose_text(rec["props"])
        if not text:
            continue
        records.append(rec)
        texts.append(text)
        if limit is not None and len(records) >= limit:
            break
    logger.info("collected %d Person vertices", len(records))
    if not records:
        return {"collection": COLLECTION_NAME, "written": 0, "reason": "no persons"}

    if dry_run:
        for rec, t in zip(records[:preview], texts[:preview], strict=False):
            logger.info("[dry-run] %s -> %s", rec["vid"], t[:120])
        logger.info("[dry-run] would insert %d rows into %s", len(records), COLLECTION_NAME)
        return {
            "collection": COLLECTION_NAME,
            "written": 0,
            "candidates": len(records),
            "dry_run": True,
        }

    # 2) 编码：稠密 + BM25 稀疏
    logger.info("loading dense encoder (%s)...", DENSE_MODEL_NAME)
    dense_encoder = _get_dense_encoder()
    dense_vecs = dense_encoder.encode_documents(texts)
    logger.info("dense encoded shape=%s", getattr(dense_vecs, "shape", None))

    logger.info("fitting BM25 on %d docs...", len(texts))
    bm25 = _get_bm25_encoder(texts)
    sparse_vecs = bm25.encode_documents(texts)
    logger.info("BM25 encoded, shape=%s", getattr(sparse_vecs, "shape", None))

    # 3) 建集合（或复用）
    client = get_milvus_client()
    _ensure_collection(client, drop_existing=drop_existing)

    # 4) 组装并 upsert
    rows: list[dict] = []
    for i, rec in enumerate(records):
        props = rec["props"]
        rows.append(
            {
                "vid": rec["vid"],
                "scholar_id": rec["scholar_id"],
                "name_zh": _clean(props.get("name_zh"))[:250],
                "name_en": _clean(props.get("name_en"))[:250],
                "scholar_org": _clean(props.get("scholar_org"))[:1000],
                "research_fields": _clean(props.get("research_fields"))[:1000],
                "text": texts[i][:4000],
                "dense_vec": dense_vecs[i].tolist()
                if hasattr(dense_vecs[i], "tolist")
                else list(dense_vecs[i]),
                "sparse_vec": _sparse_row_to_dict(sparse_vecs, i),
            }
        )

    # upsert 分批
    BATCH = 200
    written = 0
    for i in range(0, len(rows), BATCH):
        chunk = rows[i : i + BATCH]
        client.upsert(collection_name=COLLECTION_NAME, data=chunk)
        written += len(chunk)
        logger.info("upserted %d/%d", written, len(rows))

    client.flush(collection_name=COLLECTION_NAME)
    logger.info("done collection=%s written=%d", COLLECTION_NAME, written)
    return {"collection": COLLECTION_NAME, "written": written, "candidates": len(records)}


def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument(
        "--drop-existing",
        action="store_true",
        help="drop the collection before re-creating it (default: upsert onto existing collection).",
    )
    ap.add_argument(
        "--limit",
        type=int,
        default=None,
        help="only index the first N scholar vertices (for small-scale testing).",
    )
    return ap.parse_args()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    args = _parse_args()
    result = run(dry_run=args.dry_run, drop_existing=args.drop_existing, limit=args.limit)
    logger.info("result: %s", result)
