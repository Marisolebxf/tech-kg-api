"""构建论文/期刊 Milvus 索引（BM25 稀疏 + m3e-small 稠密 + 混合检索）。

为 dev 图空间中的 Paper、Journal 顶点各建一个 Milvus collection，支撑实体检索与
对齐消歧（align_paper_relations.py 用 paper 集合的 doi→vid 注册表做占位桩对齐，
向量索引供语义检索复用）。

集合
----
- ``paper``   ← Paper 顶点（vid 形如 ``paper_{numeric_id}``，排除 paper_ref_/paper_cit_/
  paper_rel_/paper_rp_ 等占位桩）
- ``journal`` ← Journal 顶点（vid 形如 ``journal_{id}``）

每个集合字段：``vid``(主键) + 业务属性 + ``text``(拼文本) + ``dense_vec``(512d, m3e-small)
+ ``sparse_vec``(BM25)。索引：dense HNSW/COSINE；sparse SPARSE_INVERTED_INDEX/BM25(k1=1.5,b=0.75)。

数据来源：TRSGraph dev 空间顶点属性（标题/doi/期刊名等；摘要未入图，故不纳入）。

用法::

    # 干跑：只统计与预览
    uv run python -m script.paper_milvus.build_paper_journal_milvus_index --dry-run

    # 实际构建（首次下载 m3e-small ~100MB）
    MILVUS_URI=http://127.0.0.1:19530 \\
    TRS_GRAPH_BASE_URL=http://127.0.0.1:8090 TRS_GRAPH_SPACE=dev TRS_GRAPH_API_KEY=ysukeg \\
        uv run python -m script.paper_milvus.build_paper_journal_milvus_index --drop-existing

    # 只建某个实体
    uv run python -m script.paper_milvus.build_paper_journal_milvus_index --entity paper
"""

from __future__ import annotations

import argparse
import logging
import os
from typing import Any

from infra.graph_db import TRSGraphClient
from infra.graph_db.config import TRSGraphSettings
from script.paper_milvus.milvus import get_milvus_client

logger = logging.getLogger("script.build_paper_journal_milvus_index")

SPACE = "dev"
DENSE_DIM = 512  # m3e-small
DENSE_MODEL_NAME = os.environ.get("PAPER_DENSE_MODEL", "moka-ai/m3e-small")


# ---------------------------------------------------------------------------
# 文本拼接
# ---------------------------------------------------------------------------
def _clean(v: Any) -> str:
    if v is None:
        return ""
    s = str(v).strip()
    return s.replace("\n", " ").replace("\r", " ")


def _compose_paper_text(props: dict) -> str:
    title_zh = _clean(props.get("title_zh"))
    title_en = _clean(props.get("title_en"))
    doi = _clean(props.get("doi"))
    pub_name = _clean(props.get("publication_name"))
    year = _clean(props.get("publication_year"))
    parts = [
        title_zh or title_en,
        title_en if title_zh and title_en else "",
        f"doi：{doi}" if doi else "",
        f"期刊：{pub_name}" if pub_name else "",
        f"年份：{year}" if year else "",
    ]
    return "｜".join(p for p in parts if p)


def _compose_journal_text(props: dict) -> str:
    name_zh = _clean(props.get("name_zh"))
    name_en = _clean(props.get("name_en"))
    abbr = _clean(props.get("name_abbr"))
    issn = _clean(props.get("issn"))
    eissn = _clean(props.get("eissn"))
    country = _clean(props.get("country"))
    parts = [
        name_zh or name_en,
        name_en if name_zh and name_en else "",
        abbr if abbr else "",
        f"issn：{issn}" if issn else "",
        f"eissn：{eissn}" if eissn else "",
        f"国家：{country}" if country else "",
    ]
    return "｜".join(p for p in parts if p)


# ---------------------------------------------------------------------------
# 从 TRSGraph 拉顶点
# ---------------------------------------------------------------------------
def _get_graph_client() -> TRSGraphClient:
    settings = TRSGraphSettings.from_env()
    settings.space = "dev"
    client = TRSGraphClient(settings)
    client.connect()
    return client


def _iter_vertices(graph: TRSGraphClient, label: str, vid_pattern: str, batch_size: int = 500):
    """MATCH + 正则分页拉顶点（避开占位桩），返回 (vid, props)。"""
    offset = 0
    while True:
        q = (
            f'USE {SPACE}; MATCH (v:{label}) WHERE id(v) =~ "{vid_pattern}" '
            f"RETURN id(v) AS vid, properties(v) AS p SKIP {offset} LIMIT {batch_size};"
        )
        r = graph.execute_read(q)
        recs = r.records
        if not recs:
            break
        for rec in recs:
            vid = str(rec.get("vid") or "")
            props = rec.get("p") or {}
            if vid:
                yield vid, props
        offset += len(recs)
        if len(recs) < batch_size:
            break


def _iter_paper_vertices(graph: TRSGraphClient):
    # vid 形如 paper_{numeric_id}，正则排除 paper_ref_/paper_cit_/paper_rel_/paper_rp_ 占位桩
    for vid, props in _iter_vertices(graph, "Paper", "paper_[0-9]+"):
        text = _compose_paper_text(props)
        if not text:
            continue
        yield {"vid": vid, "paper_id": vid.removeprefix("paper_"), "props": props, "text": text}


def _iter_journal_vertices(graph: TRSGraphClient):
    for vid, props in _iter_vertices(graph, "Journal", "journal_.+"):
        text = _compose_journal_text(props)
        if not text:
            continue
        yield {"vid": vid, "journal_id": vid.removeprefix("journal_"), "props": props, "text": text}


# ---------------------------------------------------------------------------
# 集合定义
# ---------------------------------------------------------------------------
def _paper_schema(client: Any):
    from pymilvus import DataType  # type: ignore

    schema = client.create_schema(auto_id=False, enable_dynamic_field=True)
    schema.add_field("vid", DataType.VARCHAR, is_primary=True, max_length=128)
    schema.add_field("paper_id", DataType.VARCHAR, max_length=64)
    schema.add_field("title_zh", DataType.VARCHAR, max_length=512)
    schema.add_field("title_en", DataType.VARCHAR, max_length=512)
    schema.add_field("doi", DataType.VARCHAR, max_length=128)
    schema.add_field("text", DataType.VARCHAR, max_length=4096)
    schema.add_field("dense_vec", DataType.FLOAT_VECTOR, dim=DENSE_DIM)
    schema.add_field("sparse_vec", DataType.SPARSE_FLOAT_VECTOR)
    return schema


def _journal_schema(client: Any):
    from pymilvus import DataType  # type: ignore

    schema = client.create_schema(auto_id=False, enable_dynamic_field=True)
    schema.add_field("vid", DataType.VARCHAR, is_primary=True, max_length=128)
    schema.add_field("journal_id", DataType.VARCHAR, max_length=64)
    schema.add_field("name_zh", DataType.VARCHAR, max_length=256)
    schema.add_field("name_en", DataType.VARCHAR, max_length=256)
    schema.add_field("issn", DataType.VARCHAR, max_length=64)
    schema.add_field("text", DataType.VARCHAR, max_length=4096)
    schema.add_field("dense_vec", DataType.FLOAT_VECTOR, dim=DENSE_DIM)
    schema.add_field("sparse_vec", DataType.SPARSE_FLOAT_VECTOR)
    return schema


def _index_params(client: Any):
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


def _ensure_collection(client: Any, name: str, schema_fn, drop_existing: bool):
    has = client.has_collection(name)
    if has and drop_existing:
        logger.info("dropping existing collection %s", name)
        client.drop_collection(name)
        has = False
    if not has:
        logger.info("creating collection %s", name)
        client.create_collection(
            collection_name=name,
            schema=schema_fn(client),
            index_params=_index_params(client),
        )
    else:
        logger.info("collection %s already exists (will upsert)", name)


def _sparse_to_dict(row) -> dict:
    """CSR 行 → {col_index: value} dict，供 pymilvus upsert 稀疏向量。"""
    coo = row.tocoo()
    return {int(k): float(v) for k, v in zip(coo.col, coo.data, strict=False) if v != 0}


# ---------------------------------------------------------------------------
# 编码器
# ---------------------------------------------------------------------------
def _get_dense_encoder():
    from pymilvus.model.dense import SentenceTransformerEmbeddingFunction  # type: ignore

    return SentenceTransformerEmbeddingFunction(
        model_name=DENSE_MODEL_NAME,
        device=os.environ.get("PAPER_DENSE_DEVICE", "cpu"),
    )


def _get_bm25_encoder(corpus: list[str]):
    """fit BM25 稀疏编码器。用 jieba 做中文分词分析器（不依赖 nltk 语料数据）。"""
    import jieba  # type: ignore
    from pymilvus.model.sparse.bm25 import BM25EmbeddingFunction  # type: ignore

    def zh_analyzer(text: str) -> list[str]:
        return [t for t in jieba.cut(text) if t.strip()]

    bm25 = BM25EmbeddingFunction(analyzer=zh_analyzer, k1=1.5, b=0.75)
    bm25.fit(corpus)
    return bm25


# ---------------------------------------------------------------------------
# 单实体构建
# ---------------------------------------------------------------------------
def _build_entity(
    client: Any,
    name: str,
    schema_fn,
    records: list[dict],
    texts: list[str],
    *,
    dry_run: bool,
    drop_existing: bool,
    row_builder,
    preview: int,
) -> dict:
    logger.info("[%s] collected %d vertices", name, len(records))
    if not records:
        return {"collection": name, "written": 0, "reason": "no vertices"}

    if dry_run:
        for rec, t in zip(records[:preview], texts[:preview], strict=False):
            logger.info("[dry-run][%s] %s -> %s", name, rec["vid"], t[:120])
        return {"collection": name, "written": 0, "candidates": len(records), "dry_run": True}

    logger.info("[%s] loading dense encoder (%s)...", name, DENSE_MODEL_NAME)
    dense_encoder = _get_dense_encoder()
    dense_vecs = dense_encoder.encode_documents(texts)

    logger.info("[%s] fitting BM25 on %d docs...", name, len(texts))
    bm25 = _get_bm25_encoder(texts)
    sparse_vecs = bm25.encode_documents(texts)

    _ensure_collection(client, name, schema_fn, drop_existing=drop_existing)

    rows = [row_builder(rec, texts, dense_vecs, sparse_vecs, i) for i, rec in enumerate(records)]
    batch = 200
    written = 0
    for i in range(0, len(rows), batch):
        chunk = rows[i : i + batch]
        client.upsert(collection_name=name, data=chunk)
        written += len(chunk)
        logger.info("[%s] upserted %d/%d", name, written, len(rows))
    client.flush(collection_name=name)
    logger.info("[%s] done written=%d", name, written)
    return {"collection": name, "written": written, "candidates": len(records)}


def _build_paper(client, graph, *, dry_run, drop_existing, preview):
    records, texts = [], []
    for rec in _iter_paper_vertices(graph):
        records.append(rec)
        texts.append(rec["text"])

    def row_builder(rec, texts, dense_vecs, sparse_vecs, i):
        props = rec["props"]
        return {
            "vid": rec["vid"],
            "paper_id": rec["paper_id"],
            "title_zh": _clean(props.get("title_zh"))[:500],
            "title_en": _clean(props.get("title_en"))[:500],
            "doi": _clean(props.get("doi"))[:120],
            "text": texts[i][:4000],
            "dense_vec": dense_vecs[i].tolist()
            if hasattr(dense_vecs[i], "tolist")
            else list(dense_vecs[i]),
            "sparse_vec": _sparse_to_dict(sparse_vecs[i]),
        }

    return _build_entity(
        client,
        "paper",
        _paper_schema,
        records,
        texts,
        dry_run=dry_run,
        drop_existing=drop_existing,
        row_builder=row_builder,
        preview=preview,
    )


def _build_journal(client, graph, *, dry_run, drop_existing, preview):
    records, texts = [], []
    for rec in _iter_journal_vertices(graph):
        records.append(rec)
        texts.append(rec["text"])

    def row_builder(rec, texts, dense_vecs, sparse_vecs, i):
        props = rec["props"]
        return {
            "vid": rec["vid"],
            "journal_id": rec["journal_id"],
            "name_zh": _clean(props.get("name_zh"))[:250],
            "name_en": _clean(props.get("name_en"))[:250],
            "issn": _clean(props.get("issn"))[:60],
            "text": texts[i][:4000],
            "dense_vec": dense_vecs[i].tolist()
            if hasattr(dense_vecs[i], "tolist")
            else list(dense_vecs[i]),
            "sparse_vec": _sparse_to_dict(sparse_vecs[i]),
        }

    return _build_entity(
        client,
        "journal",
        _journal_schema,
        records,
        texts,
        dry_run=dry_run,
        drop_existing=drop_existing,
        row_builder=row_builder,
        preview=preview,
    )


def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--drop-existing", action="store_true")
    ap.add_argument("--entity", choices=["paper", "journal", "both"], default="both")
    ap.add_argument("--preview", type=int, default=5)
    return ap.parse_args()


def main() -> None:
    args = _parse_args()
    graph = _get_graph_client()
    client = get_milvus_client()
    results = []
    if args.entity in ("paper", "both"):
        results.append(
            _build_paper(
                client,
                graph,
                dry_run=args.dry_run,
                drop_existing=args.drop_existing,
                preview=args.preview,
            )
        )
    if args.entity in ("journal", "both"):
        results.append(
            _build_journal(
                client,
                graph,
                dry_run=args.dry_run,
                drop_existing=args.drop_existing,
                preview=args.preview,
            )
        )
    for r in results:
        logger.info("result: %s", r)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    main()
