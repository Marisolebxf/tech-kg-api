"""只把 dev 图中的 Patent 实体同步为 Milvus BM25、向量及混合索引。"""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from infra.graph_db import get_trs_graph_client
from script.patent_indexing import HashedBM25, compose_search_text, truncate_utf8


@dataclass(frozen=True)
class EntitySpec:
    tag: str
    dense_fields: tuple[str, ...]
    sparse_fields: tuple[str, ...]


PATENT_SPEC = EntitySpec(
    "Patent",
    (
        "title_zh",
        "title_en",
        "title_original",
        "abstract_zh",
        "keywords",
    ),
    (
        "patent_id",
        "publication_number",
        "application_number",
        "granted_number",
        "title_zh",
        "title_en",
        "title_original",
        "abstract_zh",
        "keywords",
        "main_ipcr",
        "main_cpc",
    ),
)
SCALAR_INDEXES = (
    ("publication_number", "publication_number_inverted"),
    ("application_number", "application_number_inverted"),
    ("granted_number", "granted_number_inverted"),
    ("simple_family_number", "family_number_inverted"),
    ("country_code", "country_code_inverted"),
    ("organization_base", "organization_base_inverted"),
)


def persist_bm25_state(model: HashedBM25, path: Path, *, resume: bool) -> None:
    """保证断点续跑期间语料统计不变，避免新旧稀疏向量使用不同IDF。"""
    current = model.to_dict()
    if resume:
        if not path.exists():
            raise RuntimeError("--resume 缺少既有BM25状态文件；请使用原state-dir或--rebuild")
        previous = json.loads(path.read_text(encoding="utf-8"))
        if previous != current:
            raise RuntimeError("Patent语料已变化，BM25统计不一致；请使用--rebuild重建全部向量")
    path.write_text(json.dumps(current), encoding="utf-8")


def graph_rows(graph: Any, spec: EntitySpec, page_size: int) -> Iterator[dict[str, Any]]:
    offset = 0
    while True:
        query = f"MATCH (v:`{spec.tag}`) RETURN id(v) AS graph_vid, properties(v) AS properties SKIP {offset} LIMIT {page_size}"
        rows = graph.execute_read(query).records
        if not rows:
            return
        yield from rows
        if len(rows) < page_size:
            return
        offset += len(rows)


def openai_embedder() -> tuple[int, Any]:
    from openai import OpenAI

    model = os.getenv("PATENT_EMBEDDING_MODEL")
    if not model:
        raise RuntimeError("缺少 PATENT_EMBEDDING_MODEL，不允许以伪向量替代语义向量")
    dim = int(os.getenv("PATENT_EMBEDDING_DIM", "384"))
    client = OpenAI(
        api_key=os.getenv("PATENT_EMBEDDING_API_KEY") or os.getenv("OPENAI_API_KEY"),
        base_url=os.getenv("PATENT_EMBEDDING_BASE_URL") or None,
    )

    def encode(texts: list[str]) -> list[list[float]]:
        response = client.embeddings.create(model=model, input=texts, dimensions=dim)
        vectors = [item.embedding for item in response.data]
        if any(len(vector) != dim for vector in vectors):
            raise ValueError(f"Embedding服务返回维度与 PATENT_EMBEDDING_DIM={dim} 不一致")
        return vectors

    return dim, encode


def dense_embedder() -> tuple[int, Any]:
    provider = os.getenv("PATENT_EMBEDDING_PROVIDER", "local").casefold()
    if provider == "openai":
        return openai_embedder()
    if provider != "local":
        raise ValueError(f"不支持的 PATENT_EMBEDDING_PROVIDER: {provider}")
    from sentence_transformers import SentenceTransformer

    model_name = os.getenv("PATENT_LOCAL_EMBEDDING_MODEL", "moka-ai/m3e-small")
    dim = int(os.getenv("PATENT_EMBEDDING_DIM", "512"))
    model = SentenceTransformer(model_name, device=os.getenv("PATENT_EMBEDDING_DEVICE", "cpu"))
    dimension_getter = getattr(model, "get_embedding_dimension", None)
    if dimension_getter is None:
        dimension_getter = model.get_sentence_embedding_dimension
    actual_dim = dimension_getter()
    if actual_dim != dim:
        raise ValueError(
            f"本地模型 {model_name} 输出维度为{actual_dim}，与 PATENT_EMBEDDING_DIM={dim} 不一致"
        )

    def encode(texts: list[str]) -> list[list[float]]:
        vectors = model.encode(
            texts,
            batch_size=int(os.getenv("PATENT_EMBEDDING_BATCH_SIZE", "8")),
            normalize_embeddings=True,
            show_progress_bar=False,
        ).tolist()
        if any(len(vector) != dim for vector in vectors):
            raise ValueError(f"本地模型返回维度与 PATENT_EMBEDDING_DIM={dim} 不一致")
        return vectors

    return dim, encode


def create_collection(
    client: Any, name: str, dim: int, *, rebuild: bool = False, resume: bool = False
) -> None:
    from pymilvus import DataType

    if client.has_collection(name):
        if resume:
            return
        if not rebuild:
            raise RuntimeError(f"Collection {name} 已存在；为防止误删，请显式传入 --rebuild")
        client.drop_collection(name)
    schema = client.create_schema(auto_id=False, enable_dynamic_field=False)
    schema.add_field("vid", DataType.VARCHAR, is_primary=True, max_length=512)
    schema.add_field("entity_type", DataType.VARCHAR, max_length=64)
    for field in (
        "patent_id",
        "publication_number",
        "application_number",
        "granted_number",
        "simple_family_number",
    ):
        schema.add_field(field, DataType.VARCHAR, max_length=128)
    schema.add_field("country_code", DataType.VARCHAR, max_length=32)
    schema.add_field("organization_base", DataType.VARCHAR, max_length=256)
    schema.add_field("semantic_text", DataType.VARCHAR, max_length=16384)
    schema.add_field("search_text", DataType.VARCHAR, max_length=16384)
    schema.add_field("dense_vector", DataType.FLOAT_VECTOR, dim=dim)
    schema.add_field("sparse_vector", DataType.SPARSE_FLOAT_VECTOR)
    indexes = client.prepare_index_params()
    indexes.add_index(
        "dense_vector",
        index_name="dense_hnsw",
        index_type="HNSW",
        metric_type="COSINE",
        params={"M": 16, "efConstruction": 200},
    )
    indexes.add_index(
        "sparse_vector",
        index_name="bm25_sparse_inverted",
        index_type="SPARSE_INVERTED_INDEX",
        metric_type="IP",
        params={"drop_ratio_build": 0.0},
    )
    for field, index_name in SCALAR_INDEXES:
        indexes.add_index(field, index_name=index_name, index_type="INVERTED")
    client.create_collection(name, schema=schema, index_params=indexes)


def build_one(
    graph: Any,
    client: Any,
    spec: EntitySpec,
    page_size: int,
    collection_name: str,
    state_dir: Path,
    *,
    rebuild: bool = False,
    resume: bool = False,
    max_rows: int | None = None,
) -> int:
    if resume and rebuild:
        raise ValueError("--resume 与 --rebuild 不能同时使用")
    if client.has_collection(collection_name) and not (resume or rebuild):
        raise RuntimeError(f"Collection {collection_name} 已存在；请选择--resume或--rebuild")
    bm25 = HashedBM25(int(os.getenv("PATENT_BM25_DIM", "262144")))
    for row in graph_rows(graph, spec, page_size):
        bm25.observe(compose_search_text(row.get("properties") or {}, spec.sparse_fields))
    if not bm25.document_count:
        raise RuntimeError("dev 图空间中没有 Patent 实体，拒绝创建空索引")
    state_dir.mkdir(parents=True, exist_ok=True)
    persist_bm25_state(bm25, state_dir / "patent_bm25.json", resume=resume)
    dim, embed = dense_embedder()
    create_collection(client, collection_name, dim, rebuild=rebuild, resume=resume)
    existing = set()
    if resume:
        iterator = client.query_iterator(
            collection_name, batch_size=5000, filter="", output_fields=["vid"]
        )
        try:
            while rows := iterator.next():
                existing.update(str(row["vid"]) for row in rows)
        finally:
            iterator.close()
    initial_count = len(existing)
    total = initial_count
    batch = []

    def flush() -> None:
        nonlocal total, batch
        if not batch:
            return
        vectors = embed([item["semantic_text"] for item in batch])
        for item, vector in zip(batch, vectors, strict=True):
            item["dense_vector"] = vector
        client.insert(collection_name, batch)
        print(f"Milvus Patent 写入进度: {total + len(batch)}", flush=True)
        total += len(batch)
        batch = []

    for row in graph_rows(graph, spec, page_size):
        if str(row["graph_vid"]) in existing:
            continue
        if max_rows is not None and total - initial_count >= max_rows:
            break
        props = row.get("properties") or {}
        semantic_text = compose_search_text(props, spec.dense_fields)
        search_text = compose_search_text(props, spec.sparse_fields)
        batch.append(
            {
                "vid": str(row["graph_vid"]),
                "entity_type": "Patent",
                "patent_id": str(props.get("patent_id") or ""),
                "publication_number": str(props.get("publication_number") or ""),
                "application_number": str(props.get("application_number") or ""),
                "granted_number": str(props.get("granted_number") or ""),
                "simple_family_number": str(props.get("simple_family_number") or ""),
                "country_code": str(props.get("country_code") or ""),
                "organization_base": str(props.get("organization_base") or ""),
                "semantic_text": truncate_utf8(semantic_text, 16000),
                "search_text": truncate_utf8(search_text, 16000),
                "sparse_vector": bm25.encode(search_text),
            }
        )
        if len(batch) >= 32:
            flush()
    flush()
    client.flush(collection_name)
    indexed = int(client.get_collection_stats(collection_name).get("row_count", 0))
    expected_complete = bm25.document_count
    if max_rows is None and indexed != expected_complete:
        raise RuntimeError(f"Milvus行数校验失败：期望{expected_complete}，实际{indexed}")
    return total


def main() -> None:
    parser = argparse.ArgumentParser(description="为 dev 中的 Patent 建立 Milvus 八类索引")
    parser.add_argument("--page-size", type=int, default=1000)
    parser.add_argument("--collection", default="patent")
    parser.add_argument("--state-dir", type=Path, default=Path("var/patent_indexes"))
    parser.add_argument(
        "--rebuild", action="store_true", help="允许删除并重建已存在的 Patent Collection"
    )
    parser.add_argument("--resume", action="store_true", help="复用既有Collection并跳过已写入的VID")
    parser.add_argument(
        "--max-rows", type=int, default=None, help="仅用于小批验证；默认索引全部Patent"
    )
    args = parser.parse_args()
    if args.resume and args.rebuild:
        parser.error("--resume 与 --rebuild 不能同时使用")
    load_dotenv()
    os.environ["TRS_GRAPH_SPACE"] = "dev"
    from pymilvus import MilvusClient

    uri = (
        os.getenv("MILVUS_URI")
        or f"http://{os.getenv('MILVUS_HOST', '127.0.0.1')}:{os.getenv('MILVUS_PORT', '19530')}"
    )
    client = MilvusClient(uri=uri, token=os.getenv("MILVUS_TOKEN") or None)
    graph = get_trs_graph_client()
    count = build_one(
        graph,
        client,
        PATENT_SPEC,
        args.page_size,
        args.collection,
        args.state_dir,
        rebuild=args.rebuild,
        resume=args.resume,
        max_rows=args.max_rows,
    )
    print(
        json.dumps(
            {"collection": args.collection, "Patent": count, "indexes": 8}, ensure_ascii=False
        )
    )


if __name__ == "__main__":
    main()
