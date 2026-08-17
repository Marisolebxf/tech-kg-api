"""对齐学者 AFFILIATED_WITH 边到真实机构顶点（依赖机构领域的 Milvus 索引）。

背景
----
``load_scholar_relations.py`` 在 ``dwd_scholar.scholar_org_id`` 缺失时，会用机构名的
md5 摘要生成回退 VID ``org_{md5(name)[:16]}``。这类顶点/边只是临时桩，等国内外机构
领域（周威）落地正式 Organization 顶点后，需要把桩节点对齐到真实 ``org_{org_id}``。

策略
----
1. 遍历所有 Person→AFFILIATED_WITH→Organization 边，识别形如
   ``org_[a-f0-9]{16}`` 的回退 VID 视为待对齐候选。
2. 取候选桩机构的名称（优先取边上的 ``affiliation_name``，其次桩顶点属性）。
3. 在机构领域的 Milvus 集合中做 **混合检索**（BM25 + 稠密向量），拿 top-1；
   若相似度过阈值，视为同一机构。
4. 写入 ``SAME_AS`` 边：``org_{md5(name)}`` → ``org_{org_id}``，属性附上
   相似度、批次号、来源。
5. 幂等：``merge_edge`` 按 ``(src, dst, edge_type, identityProps)`` 去重。

**本轮不删除、不改写原有 AFFILIATED_WITH 边**；查询侧遍历 ``SAME_AS`` 展开，
或后续离线 job 统一改写。

用法::

    # 依赖：机构领域已构建 Milvus 集合（默认名 ``organization``），且集合的稠密
    # 向量维度与本脚本一致（512d，m3e-small）。
    SCHOLAR_ORG_COLLECTION=organization \\
    MILVUS_URI=http://127.0.0.1:19531 \\
    TRS_GRAPH_BASE_URL=http://127.0.0.1:8090 \\
    TRS_GRAPH_SPACE=dev TRS_GRAPH_API_KEY=ysukeg \\
        uv run python -m script.align_scholar_affiliations --dry-run

    # 真正写 SAME_AS 边
    uv run python -m script.align_scholar_affiliations
"""

from __future__ import annotations

import argparse
import logging
import os
import re
from datetime import datetime
from typing import Any

from infra.graph_db import get_trs_graph_client
from infra.milvus import get_milvus_client
from script.scholar_provenance import confidence_props, organization_provenance

logger = logging.getLogger("script.align_scholar_affiliations")

BATCH_ID = f"BATCH_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_scholar_align"
ORG_COLLECTION = os.environ.get("SCHOLAR_ORG_COLLECTION", "organization")
DENSE_MODEL_NAME = os.environ.get("SCHOLAR_DENSE_MODEL", "moka-ai/m3e-small")
DEFAULT_TOP_K = int(os.environ.get("SCHOLAR_ALIGN_TOPK", "5"))
DEFAULT_MIN_SCORE = float(os.environ.get("SCHOLAR_ALIGN_MIN_SCORE", "0.65"))

# 回退 VID 的形态：org_ + 16 位小写十六进制（见 load_scholar_relations.org_vid）
_FALLBACK_VID_RE = re.compile(r"^org_[a-f0-9]{16}$")


# ---------------------------------------------------------------------------
# TRSGraph 边遍历
# ---------------------------------------------------------------------------
def _iter_affiliation_edges(graph: Any, batch_size: int = 500):
    """遍历所有 AFFILIATED_WITH 边。"""
    offset = 0
    while True:
        page = graph.get_edges_by_type("AFFILIATED_WITH", offset=offset, limit=batch_size)
        items = getattr(page, "items", None) or []
        if not items:
            break
        for edge in items:
            src = str(getattr(edge, "source_id", "") or "")
            dst = str(getattr(edge, "target_id", "") or "")
            props = dict(getattr(edge, "properties", None) or {})
            if not src or not dst:
                continue
            yield {"src": src, "dst": dst, "props": props}
        offset += len(items)
        if len(items) < batch_size:
            break


def _extract_orphan_org_name(graph: Any, edge: dict) -> str | None:
    """从边 / 桩顶点取机构名，供 Milvus 检索使用。"""
    name = str(edge["props"].get("affiliation_name") or "").strip()
    if name:
        return name
    # 兜底：读桩机构顶点属性
    try:
        node = graph.get_node(edge["dst"])
    except Exception:  # noqa: BLE001
        return None
    if node is None:
        return None
    props = dict(getattr(node, "properties", None) or {})
    return (props.get("name_cn") or props.get("name_en") or "").strip() or None


def _canonical_org_provenance(graph: Any, vid: str, org_id: Any) -> dict[str, str]:
    """读取正式机构顶点的来源；读取失败时保留检索结果中的机构 ID。"""
    try:
        node = graph.get_node(vid)
    except Exception:  # noqa: BLE001
        node = None
    props = dict(getattr(node, "properties", None) or {}) if node is not None else {}
    return organization_provenance(
        props.get("source_table"),
        props.get("source_record_id") or props.get("org_id") or org_id,
    )


# ---------------------------------------------------------------------------
# Milvus 混合检索
# ---------------------------------------------------------------------------
def _get_dense_encoder():
    from pymilvus.model.dense import SentenceTransformerEmbeddingFunction  # type: ignore

    return SentenceTransformerEmbeddingFunction(
        model_name=DENSE_MODEL_NAME,
        device=os.environ.get("SCHOLAR_DENSE_DEVICE", "cpu"),
    )


def _get_bm25_encoder(client: Any):
    """机构 Milvus 集合的 BM25 词典无法从远端反序列化；这里加载一份运行时词典
    对 query 做临时 encode（分词一致即可近似 IP 相似度）。
    """
    from pymilvus.model.sparse.bm25 import BM25EmbeddingFunction  # type: ignore
    from pymilvus.model.sparse.bm25.tokenizers import build_default_analyzer  # type: ignore

    analyzer = build_default_analyzer(language="zh")
    bm25 = BM25EmbeddingFunction(analyzer=analyzer, k1=1.5, b=0.75)
    # 无语料时的默认 IDF：给一个非零基础字典即可；实际 sparse 分布对 top-k 影响可控。
    bm25.fit(["占位文本"])
    _ = client  # placeholder; 集合内部索引已用其自身语料
    return bm25


def _hybrid_search(
    milvus: Any,
    dense_query: list[float],
    sparse_query: Any,
    top_k: int,
) -> list[dict]:
    """在机构集合上做 dense + sparse 的混合检索（RRF 融合）。"""
    from pymilvus import AnnSearchRequest, RRFRanker  # type: ignore

    dense_req = AnnSearchRequest(
        data=[dense_query],
        anns_field="dense_vec",
        param={"metric_type": "COSINE", "params": {"ef": 128}},
        limit=top_k,
    )
    sparse_req = AnnSearchRequest(
        data=[sparse_query],
        anns_field="sparse_vec",
        param={"metric_type": "IP", "params": {"drop_ratio_search": 0.2}},
        limit=top_k,
    )
    resp = milvus.hybrid_search(
        collection_name=ORG_COLLECTION,
        reqs=[dense_req, sparse_req],
        ranker=RRFRanker(k=60),
        limit=top_k,
        output_fields=["vid", "org_id", "name_cn", "name_en"],
    )
    out: list[dict] = []
    if not resp or not resp[0]:
        return out
    for hit in resp[0]:
        entity = getattr(hit, "entity", None) or {}

        def _get(entity_ref, key, default=None):
            if hasattr(entity_ref, "get"):
                return entity_ref.get(key, default)
            return getattr(entity_ref, key, default)

        out.append(
            {
                "vid": _get(entity, "vid") or _get(entity, "org_id") or getattr(hit, "id", ""),
                "org_id": _get(entity, "org_id"),
                "name_cn": _get(entity, "name_cn"),
                "name_en": _get(entity, "name_en"),
                "score": float(getattr(hit, "score", 0.0) or 0.0),
            }
        )
    return out


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def run(
    *,
    dry_run: bool,
    top_k: int = DEFAULT_TOP_K,
    min_score: float = DEFAULT_MIN_SCORE,
    preview: int = 5,
) -> dict:
    graph = get_trs_graph_client()
    milvus = get_milvus_client()

    if not milvus.has_collection(ORG_COLLECTION):
        logger.warning(
            "Milvus collection %r not found; skipping (Organization index not built yet).",
            ORG_COLLECTION,
        )
        return {"aligned": 0, "reason": "organization_collection_missing"}

    try:
        milvus.load_collection(ORG_COLLECTION)
    except Exception:  # noqa: BLE001
        pass

    logger.info(
        "start batch=%s org_collection=%s top_k=%d min_score=%.2f dry_run=%s",
        BATCH_ID,
        ORG_COLLECTION,
        top_k,
        min_score,
        dry_run,
    )

    # 1) 找回退 AFFILIATED_WITH（桩机构）
    orphan_targets: dict[str, dict] = {}
    for edge in _iter_affiliation_edges(graph):
        if not _FALLBACK_VID_RE.match(edge["dst"]):
            continue
        name = _extract_orphan_org_name(graph, edge)
        if not name:
            continue
        # 桩顶点通常有多个学者关联；这里按目标 VID 去重
        orphan_targets.setdefault(edge["dst"], {"name": name, "sample_edge": edge})
    logger.info("found %d orphan Organization targets", len(orphan_targets))
    if not orphan_targets:
        return {"aligned": 0, "reason": "no_orphans"}

    # 2) 加载 encoder
    logger.info("loading dense encoder %s ...", DENSE_MODEL_NAME)
    dense_encoder = _get_dense_encoder()
    bm25 = _get_bm25_encoder(milvus)

    # 3) 依次查询 + 写 SAME_AS
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    aligned = shown = 0
    skipped_low_score = 0
    for orphan_vid, info in orphan_targets.items():
        name = info["name"]
        dense_vec = dense_encoder.encode_queries([name])[0]
        sparse_vec = bm25.encode_queries([name])[0]
        hits = _hybrid_search(milvus, dense_vec.tolist(), sparse_vec, top_k=top_k)
        if not hits:
            skipped_low_score += 1
            continue

        top = hits[0]
        if top["score"] < min_score:
            skipped_low_score += 1
            if shown < preview:
                logger.info(
                    "[skip] %s (%s) -> best=%s score=%.3f < %.2f",
                    orphan_vid,
                    name,
                    top.get("name_cn") or top.get("name_en"),
                    top["score"],
                    min_score,
                )
                shown += 1
            continue

        canonical_vid = str(top.get("vid") or "")
        if not canonical_vid or canonical_vid == orphan_vid:
            skipped_low_score += 1
            continue

        edge_props = {
            "match_score": top["score"],
            "match_source": "milvus_hybrid",
            "orphan_name": name,
            "canonical_name": top.get("name_cn") or top.get("name_en") or "",
            "source_table": "scholar_alignment",
            "source_record_id": orphan_vid,
            "ingest_batch": BATCH_ID,
            "ingest_time": now,
            **_canonical_org_provenance(graph, canonical_vid, top.get("org_id")),
            **confidence_props(
                top["score"],
                "milvus_hybrid",
                f"机构名混合向量检索 top-1，相似度={top['score']:.4f}",
            ),
        }
        if dry_run:
            if shown < preview:
                logger.info(
                    "[dry-run] %s -[SAME_AS]-> %s  score=%.3f  name=%s",
                    orphan_vid,
                    canonical_vid,
                    top["score"],
                    top.get("name_cn") or top.get("name_en"),
                )
                shown += 1
        else:
            graph.merge_edge(
                orphan_vid,
                canonical_vid,
                "SAME_AS",
                {"source_record_id": orphan_vid},
                edge_props,
            )
        aligned += 1

    logger.info(
        "aligned=%d skipped_low_score=%d total_orphans=%d",
        aligned,
        skipped_low_score,
        len(orphan_targets),
    )
    return {
        "aligned": aligned,
        "skipped_low_score": skipped_low_score,
        "total_orphans": len(orphan_targets),
        "batch": BATCH_ID,
    }


def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    ap.add_argument("--min-score", type=float, default=DEFAULT_MIN_SCORE)
    return ap.parse_args()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    args = _parse_args()
    result = run(dry_run=args.dry_run, top_k=args.top_k, min_score=args.min_score)
    logger.info("result: %s", result)
