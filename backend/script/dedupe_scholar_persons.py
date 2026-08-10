"""学者领域同域消歧：识别 ``scholar_person`` 集合中"疑似同一人"的顶点对。

背景
----
``scholar_id`` 是 ``dwd_scholar`` 主键，不等同于自然人全局 ID。同一位学者可能：
  * 在不同数据源批次录入为多条记录，得到不同 ``scholar_id``；
  * 中英文姓名拼写差异（``Wei Li`` / ``W. Li`` / ``李伟``）；
  * 换机构后被重新登记。

反之，同名不同人（``张伟``、``Wang Fang`` 之类）也可能被误认。本脚本用 Milvus
``scholar_person`` 集合的混合检索做候选生成（blocking），再叠加多信号打分做判定。

信号
----
1. **Milvus 混合检索分数**（BM25 + m3e-small dense，RRF 融合，占比 0.40）
2. **姓名相似度**（rapidfuzz.WRatio，中/英均计算取最大值，占比 0.30）
3. **机构相似度**（rapidfuzz.token_set_ratio，占比 0.20）
4. **研究方向 Jaccard**（按 ``；,、`` 切词，占比 0.10）

综合分区间：
  * ``>= 0.75``  高置信 → 建议直接写 ``SAME_AS`` 边
  * ``0.55~0.75`` 疑似 → 记入报表，等人工/LLM 复核
  * ``< 0.55``   忽略

用法
----
::

    # 干跑：只出报表 (JSON)，不写图
    MILVUS_URI=http://127.0.0.1:19531 \\
    TRS_GRAPH_BASE_URL=http://127.0.0.1:8090 \\
    TRS_GRAPH_SPACE=dev TRS_GRAPH_API_KEY=ysukeg \\
        uv run python -m script.dedupe_scholar_persons --dry-run --report /tmp/dedupe.json

    # 写高置信 SAME_AS 边（不动 AFFILIATED_WITH / COAUTHOR_WITH）
    uv run python -m script.dedupe_scholar_persons --write

    # 调阈值：只处理综合分 >= 0.80 的
    uv run python -m script.dedupe_scholar_persons --write --high-threshold 0.80

依赖
----
* ``build_scholar_milvus_index.py`` 已构建 ``scholar_person`` 集合。
* ``rapidfuzz`` 已在 pyproject 依赖中。
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
from datetime import datetime
from typing import Any

from rapidfuzz import fuzz

from infra.graph_db import get_trs_graph_client
from infra.milvus import get_milvus_client

logger = logging.getLogger("script.dedupe_scholar_persons")

BATCH_ID = f"BATCH_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_scholar_dedupe"
COLLECTION_NAME = "scholar_person"
DENSE_MODEL_NAME = os.environ.get("SCHOLAR_DENSE_MODEL", "moka-ai/m3e-small")
BIO_MAX_CHARS = 500

DEFAULT_TOP_K = int(os.environ.get("SCHOLAR_DEDUPE_TOPK", "5"))
DEFAULT_HIGH = float(os.environ.get("SCHOLAR_DEDUPE_HIGH", "0.75"))
DEFAULT_MID = float(os.environ.get("SCHOLAR_DEDUPE_MID", "0.55"))

# 权重配置
_W_MILVUS = 0.40
_W_NAME = 0.30
_W_ORG = 0.20
_W_FIELDS = 0.10

_FIELDS_SPLIT = re.compile(r"[；;、,，/\|]+")


# ---------------------------------------------------------------------------
# 文本 / 分词工具
# ---------------------------------------------------------------------------
def _clean(v: Any) -> str:
    if v is None:
        return ""
    return str(v).strip().replace("\n", " ").replace("\r", " ")


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


def _fields_set(v: str) -> set[str]:
    if not v:
        return set()
    return {t.strip() for t in _FIELDS_SPLIT.split(v) if t.strip()}


def _name_similarity(a: dict, b: dict) -> float:
    """中英文姓名各自计算相似度，取最大。范围 0-100 → 归一 0-1。"""
    ns_zh = (
        fuzz.WRatio(_clean(a.get("name_zh")), _clean(b.get("name_zh")))
        if (a.get("name_zh") and b.get("name_zh"))
        else 0.0
    )
    ns_en = (
        fuzz.WRatio(_clean(a.get("name_en")), _clean(b.get("name_en")))
        if (a.get("name_en") and b.get("name_en"))
        else 0.0
    )
    return max(ns_zh, ns_en) / 100.0


def _org_similarity(a: dict, b: dict) -> float:
    oa, ob = _clean(a.get("scholar_org")), _clean(b.get("scholar_org"))
    if not oa or not ob:
        return 0.0
    return fuzz.token_set_ratio(oa, ob) / 100.0


def _fields_jaccard(a: dict, b: dict) -> float:
    fa = _fields_set(_clean(a.get("research_fields")))
    fb = _fields_set(_clean(b.get("research_fields")))
    if not fa or not fb:
        return 0.0
    inter = fa & fb
    union = fa | fb
    return len(inter) / len(union) if union else 0.0


# ---------------------------------------------------------------------------
# 拉全量学者 + 编码
# ---------------------------------------------------------------------------
def _fetch_persons(graph: Any, batch_size: int = 200) -> list[dict]:
    """从 TRSGraph 拉所有 Person 顶点，保留对齐用属性。"""
    persons: list[dict] = []
    offset = 0
    while True:
        page = graph.get_nodes_by_label("Person", offset=offset, limit=batch_size)
        items = getattr(page, "items", None) or []
        if not items:
            break
        for node in items:
            vid = str(getattr(node, "id", "") or "")
            props = dict(getattr(node, "properties", None) or {})
            if not vid or not vid.startswith("person_"):
                continue
            persons.append({"vid": vid, "props": props})
        offset += len(items)
        if len(items) < batch_size:
            break
    return persons


def _get_dense_encoder():
    from pymilvus.model.dense import SentenceTransformerEmbeddingFunction  # type: ignore

    return SentenceTransformerEmbeddingFunction(
        model_name=DENSE_MODEL_NAME,
        device=os.environ.get("SCHOLAR_DENSE_DEVICE", "cpu"),
    )


def _get_bm25_fitted(corpus: list[str]):
    from pymilvus.model.sparse.bm25 import BM25EmbeddingFunction  # type: ignore
    from pymilvus.model.sparse.bm25.tokenizers import build_default_analyzer  # type: ignore

    analyzer = build_default_analyzer(language="zh")
    bm25 = BM25EmbeddingFunction(analyzer=analyzer, k1=1.5, b=0.75)
    bm25.fit(corpus)
    return bm25


# ---------------------------------------------------------------------------
# Milvus 混合检索
# ---------------------------------------------------------------------------
def _hybrid_search(milvus: Any, dense_vec, sparse_vec, top_k: int) -> list[dict]:
    from pymilvus import AnnSearchRequest, RRFRanker  # type: ignore

    dense_req = AnnSearchRequest(
        data=[dense_vec.tolist() if hasattr(dense_vec, "tolist") else list(dense_vec)],
        anns_field="dense_vec",
        param={"metric_type": "COSINE", "params": {"ef": 128}},
        limit=top_k,
    )
    sparse_req = AnnSearchRequest(
        data=[sparse_vec],
        anns_field="sparse_vec",
        param={"metric_type": "IP", "params": {"drop_ratio_search": 0.2}},
        limit=top_k,
    )
    resp = milvus.hybrid_search(
        collection_name=COLLECTION_NAME,
        reqs=[dense_req, sparse_req],
        ranker=RRFRanker(k=60),
        limit=top_k,
        output_fields=["vid", "name_zh", "name_en", "scholar_org", "research_fields"],
    )
    out: list[dict] = []
    if not resp or not resp[0]:
        return out
    for hit in resp[0]:
        entity = getattr(hit, "entity", None) or {}

        def _g(entity_ref, k, d=None):
            if hasattr(entity_ref, "get"):
                return entity_ref.get(k, d)
            return getattr(entity_ref, k, d)

        out.append(
            {
                "vid": _g(entity, "vid") or getattr(hit, "id", ""),
                "name_zh": _g(entity, "name_zh") or "",
                "name_en": _g(entity, "name_en") or "",
                "scholar_org": _g(entity, "scholar_org") or "",
                "research_fields": _g(entity, "research_fields") or "",
                "milvus_score": float(getattr(hit, "score", 0.0) or 0.0),
            }
        )
    return out


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def _combined_score(milvus_score: float, name_s: float, org_s: float, fields_s: float) -> float:
    """把 Milvus 分（RRF 分数近似 0.5~1.0）归一到 0-1，然后加权。"""
    # RRF 分数一般在 0~1；直接采用，若超出剪裁。
    m = max(0.0, min(1.0, milvus_score))
    return _W_MILVUS * m + _W_NAME * name_s + _W_ORG * org_s + _W_FIELDS * fields_s


def _canonical_pair(a: str, b: str) -> tuple[str, str]:
    """规范化 pair 顺序，避免 (A,B) 和 (B,A) 重复。"""
    return (a, b) if a < b else (b, a)


def run(
    *,
    dry_run: bool,
    write: bool,
    top_k: int,
    high_threshold: float,
    mid_threshold: float,
    report_path: str | None,
    preview: int = 8,
) -> dict:
    graph = get_trs_graph_client()
    milvus = get_milvus_client()

    if not milvus.has_collection(COLLECTION_NAME):
        logger.error(
            "Milvus collection %r not found — run build_scholar_milvus_index.py first",
            COLLECTION_NAME,
        )
        return {"error": "collection_missing"}

    try:
        milvus.load_collection(COLLECTION_NAME)
    except Exception:  # noqa: BLE001
        pass

    persons = _fetch_persons(graph)
    logger.info("loaded %d Person vertices", len(persons))
    if not persons:
        return {"error": "no_persons"}

    texts = [_compose_text(p["props"]) for p in persons]

    logger.info("loading dense encoder %s ...", DENSE_MODEL_NAME)
    dense_encoder = _get_dense_encoder()
    dense_vecs = dense_encoder.encode_documents(texts)

    logger.info("fitting BM25 on %d docs ...", len(texts))
    bm25 = _get_bm25_fitted(texts)
    sparse_vecs = bm25.encode_documents(texts)

    high_pairs: list[dict] = []
    mid_pairs: list[dict] = []
    seen_pairs: set[tuple[str, str]] = set()

    for i, person in enumerate(persons):
        hits = _hybrid_search(milvus, dense_vecs[i], sparse_vecs[i], top_k=top_k + 1)
        for h in hits:
            if not h["vid"] or h["vid"] == person["vid"]:
                continue
            pair = _canonical_pair(person["vid"], h["vid"])
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)

            a_props = person["props"]
            b_props = h  # search 返回的字段就是 b 的稀疏投影
            name_s = _name_similarity(a_props, b_props)
            org_s = _org_similarity(a_props, b_props)
            fields_s = _fields_jaccard(a_props, b_props)
            combined = _combined_score(h["milvus_score"], name_s, org_s, fields_s)

            entry = {
                "a": {
                    "vid": person["vid"],
                    "name_zh": a_props.get("name_zh"),
                    "name_en": a_props.get("name_en"),
                    "scholar_org": a_props.get("scholar_org"),
                    "research_fields": a_props.get("research_fields"),
                },
                "b": {
                    "vid": h["vid"],
                    "name_zh": h.get("name_zh"),
                    "name_en": h.get("name_en"),
                    "scholar_org": h.get("scholar_org"),
                    "research_fields": h.get("research_fields"),
                },
                "signals": {
                    "milvus": round(h["milvus_score"], 4),
                    "name": round(name_s, 4),
                    "org": round(org_s, 4),
                    "fields": round(fields_s, 4),
                },
                "combined": round(combined, 4),
            }
            if combined >= high_threshold:
                high_pairs.append(entry)
            elif combined >= mid_threshold:
                mid_pairs.append(entry)

    logger.info(
        "candidates: high(>=%.2f)=%d  mid(%.2f-%.2f)=%d",
        high_threshold,
        len(high_pairs),
        mid_threshold,
        high_threshold,
        len(mid_pairs),
    )

    # 预览
    for entry in sorted(high_pairs, key=lambda e: -e["combined"])[:preview]:
        logger.info(
            "[high %.3f] %s <-> %s  name=%.2f org=%.2f fields=%.2f milvus=%.2f",
            entry["combined"],
            entry["a"]["vid"],
            entry["b"]["vid"],
            entry["signals"]["name"],
            entry["signals"]["org"],
            entry["signals"]["fields"],
            entry["signals"]["milvus"],
        )

    # 报表
    if report_path:
        payload = {
            "batch": BATCH_ID,
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "collection": COLLECTION_NAME,
            "counts": {"high": len(high_pairs), "mid": len(mid_pairs), "persons": len(persons)},
            "thresholds": {"high": high_threshold, "mid": mid_threshold},
            "high": high_pairs,
            "mid": mid_pairs,
        }
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        logger.info("report written to %s", report_path)

    # 落 SAME_AS 边
    written = 0
    failed = 0
    if write and not dry_run:
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        for entry in high_pairs:
            a_vid, b_vid = entry["a"]["vid"], entry["b"]["vid"]
            props = {
                "match_source": "scholar_dedupe",
                "match_score": entry["combined"],
                "signal_name": entry["signals"]["name"],
                "signal_org": entry["signals"]["org"],
                "signal_fields": entry["signals"]["fields"],
                "signal_milvus": entry["signals"]["milvus"],
                "source_table": "scholar_dedupe",
                "source_record_id": f"{a_vid}__{b_vid}",
                "ingest_batch": BATCH_ID,
                "ingest_time": now,
            }
            # 单条失败不能中断整批：merge_edge 是幂等的，重跑只补未写成功的边。
            try:
                graph.merge_edge(
                    a_vid,
                    b_vid,
                    "SAME_AS",
                    {"source_record_id": f"{a_vid}__{b_vid}"},
                    props,
                )
            except Exception:
                failed += 1
                logger.exception("failed to write SAME_AS edge %s -> %s", a_vid, b_vid)
                continue
            written += 1
        logger.info("wrote %d SAME_AS edges (%d failed)", written, failed)

    return {
        "persons": len(persons),
        "high": len(high_pairs),
        "mid": len(mid_pairs),
        "written": written,
        "failed": failed,
        "batch": BATCH_ID,
    }


def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="不写图；默认即 dry-run")
    ap.add_argument("--write", action="store_true", help="真的写 SAME_AS 边（高置信区间）")
    ap.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    ap.add_argument("--high-threshold", type=float, default=DEFAULT_HIGH)
    ap.add_argument("--mid-threshold", type=float, default=DEFAULT_MID)
    ap.add_argument("--report", type=str, default=None, help="报表 JSON 输出路径")
    return ap.parse_args()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    args = _parse_args()
    dry_run = args.dry_run or not args.write
    result = run(
        dry_run=dry_run,
        write=args.write,
        top_k=args.top_k,
        high_threshold=args.high_threshold,
        mid_threshold=args.mid_threshold,
        report_path=args.report,
    )
    logger.info("result: %s", result)
