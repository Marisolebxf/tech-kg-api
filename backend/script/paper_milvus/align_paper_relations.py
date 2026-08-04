"""实体对齐补关系：把 0725 因「不对齐」连到占位桩的边，用 doi 精确对齐到真实 Paper。

0725 任务对 CITES/CITED_BY/RELATED_TO 的目标论文未做对齐，目标不在库内时建了占位桩
（paper_ref_/paper_cit_/paper_rel_）。本脚本用 Milvus `paper` 集合（真实 Paper 的 doi→vid
注册表）做精确 doi 对齐：桩的 Paper.doi 命中某真实 Paper 的 doi → 建 SAME_AS 边
（桩 → 真实 Paper），把占位桩与真实实体对齐，补齐需要对齐才能建立的关系。

为何用 doi 精确匹配而非 m3e 语义检索：占位桩只存了 doi、没有 title 文本，m3e 语义检索
无法作用于桩；doi 精确匹配是桩→真实论文唯一可靠的对齐信号，只放行真同一篇。
（曾尝试用 m3e 语义对齐 OUTPUT_OF 的项目产出论文标题，但项目产出论文与论文库几乎不重叠、
语义 top-1 命中的是「主题相近的不同篇」，误对齐，故不建；见 README「已知限制」。）

流程：
  1. 从 Milvus `paper` 集合查全量 (doi, vid) 建 doi→vid 对齐注册表
  2. 从 dev 图空间按前缀拉占位桩 (vid, doi)：paper_ref_ / paper_cit_ / paper_rel_
  3. 桩 doi 命中注册表 → 建 SAME_AS 边 桩 -> 真实 Paper（带 source/confidence/溯源）
  4. 使用 infra.graph_db.TRSGraphClient 写边（多值 INSERT EDGE, rank@0 幂等）

安全约束：只 CREATE EDGE / INSERT EDGE，绝不 DELETE/ALTER 已有数据；SAME_AS 为新建边类型。

用法::
    MILVUS_URI=http://127.0.0.1:19530 \\
    TRS_GRAPH_BASE_URL=http://127.0.0.1:8090 TRS_GRAPH_SPACE=dev TRS_GRAPH_API_KEY=ysukeg \\
        uv run python -m script.paper_milvus.align_paper_relations --dry-run
    # 真正写边去掉 --dry-run
"""

from __future__ import annotations

import argparse
import logging
import time

from infra.graph_db import TRSGraphClient
from infra.graph_db.config import TRSGraphSettings
from script.paper_milvus.milvus import get_milvus_client

logger = logging.getLogger("script.align_paper_relations")

SPACE = "dev"
COLLECTION = "paper"
STUB_PREFIXES = ["paper_ref", "paper_cit", "paper_rel"]
INGEST_BATCH = "paper_milvus_align_0730"
INGEST_TIME = "2026-07-31"


# ---------------------------------------------------------------------------
# 连接
# ---------------------------------------------------------------------------
def _get_graph_client() -> TRSGraphClient:
    settings = TRSGraphSettings.from_env()
    settings.space = SPACE
    client = TRSGraphClient(settings)
    client.connect()
    return client


# ---------------------------------------------------------------------------
# 1) Milvus paper 集合 → doi→vid 对齐注册表
# ---------------------------------------------------------------------------
def _build_doi_registry(milvus) -> dict[str, str]:
    """从 Milvus paper 集合查全量 (doi, vid)，返回 doi -> vid。"""
    # Milvus query 单次 offset+limit 上限 16384，分页拉全量
    registry: dict[str, str] = {}
    offset = 0
    while True:
        res = milvus.query(
            collection_name=COLLECTION,
            filter="doi != ''",
            output_fields=["vid", "doi"],
            limit=16384,
            offset=offset,
        )
        if not res:
            break
        for row in res:
            doi = (row.get("doi") or "").strip()
            vid = row.get("vid")
            if doi and vid:
                registry[doi] = vid
        offset += len(res)
        if len(res) < 16384:
            break
    logger.info("milvus paper doi registry: %d entries", len(registry))
    return registry


# ---------------------------------------------------------------------------
# 2) 从 dev 拉占位桩 (vid, doi)
# ---------------------------------------------------------------------------
def _find_stub_matches(
    graph: TRSGraphClient, prefix: str, doi_to_vid: dict[str, str], in_batch: int = 200
) -> list[tuple[str, str, str]]:
    """对某前缀桩，用 doi IN [batch] 批量查命中真实论文的 (stub_vid, real_vid, prefix)。"""
    matches: list[tuple[str, str, str]] = []
    dois = list(doi_to_vid.keys())
    for i in range(0, len(dois), in_batch):
        batch = dois[i : i + in_batch]
        doi_list = ",".join(_esc(d) for d in batch)
        q = (
            f'USE {SPACE}; MATCH (v:Paper) WHERE id(v) STARTS WITH "{prefix}_" '
            f"AND v.Paper.doi IN [{doi_list}] RETURN id(v) AS vid, v.Paper.doi AS doi;"
        )
        r = graph.execute_read(q)
        for rec in r.records:
            stub_vid = str(rec.get("vid") or "")
            doi = (rec.get("doi") or "").strip()
            real_vid = doi_to_vid.get(doi)
            if stub_vid and real_vid and real_vid != stub_vid:
                matches.append((stub_vid, real_vid, prefix))
    return matches


# ---------------------------------------------------------------------------
# 3) SAME_AS 边类型
# ---------------------------------------------------------------------------
def _ensure_same_as_edge(graph: TRSGraphClient) -> None:
    try:
        graph.execute_read(f"USE {SPACE}; DESCRIBE EDGE SAME_AS;")
        logger.info("SAME_AS 边类型已存在")
        return
    except Exception:
        pass
    graph.execute_write(
        f"USE {SPACE}; CREATE EDGE SAME_AS(source_table string, source_record_id string, ingest_batch string, ingest_time string, confidence string, match_method string);"
    )
    logger.info("已 CREATE EDGE SAME_AS，等待 schema 传播 15s ...")
    time.sleep(15)


# ---------------------------------------------------------------------------
# 4) 写 SAME_AS 边
# ---------------------------------------------------------------------------
def _esc(v) -> str:
    if v is None:
        return "NULL"
    s = str(v).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ").replace("\r", " ")
    return f'"{s}"'


_SAME_AS_FIELDS = [
    "source_table",
    "source_record_id",
    "ingest_batch",
    "ingest_time",
    "confidence",
    "match_method",
]


def _insert_same_as_edges(graph: TRSGraphClient, rows: list[tuple[str, str, str]]) -> int:
    """多值 INSERT EDGE SAME_AS。rows=[(stub_vid, real_vid, stub_prefix)]。"""
    if not rows:
        return 0
    vals = ",".join(
        f"{_esc(stub)}->{_esc(real)}:"
        f"({_esc('stub_doi_align')},{_esc(stub_prefix)},{_esc(INGEST_BATCH)},{_esc(INGEST_TIME)},{_esc('1.0000')},{_esc('doi_exact')})"
        for stub, real, stub_prefix in rows
    )
    ngql = f"USE {SPACE}; INSERT EDGE SAME_AS({','.join(_SAME_AS_FIELDS)}) VALUES {vals};"
    try:
        graph.execute_write(ngql)
        return len(rows)
    except Exception as exc:
        logger.warning("批量写 SAME_AS 失败 (%d 条): %s", len(rows), str(exc)[:160])
        return 0


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def run(*, dry_run: bool, batch_size: int, preview: int) -> dict:
    graph = _get_graph_client()
    milvus = get_milvus_client()

    if not milvus.has_collection(COLLECTION):
        logger.error("milvus 集合 %s 不存在，请先运行 build_paper_journal_milvus_index", COLLECTION)
        return {"written": 0, "reason": "collection missing"}

    registry = _build_doi_registry(milvus)
    if not registry:
        return {"written": 0, "reason": "empty registry"}

    if not dry_run:
        _ensure_same_as_edge(graph)

    stats = {"matched": 0, "by_prefix": {}}
    for prefix in STUB_PREFIXES:
        matches = _find_stub_matches(graph, prefix, registry)
        stats["by_prefix"][prefix] = len(matches)
        stats["matched"] += len(matches)
        logger.info("[%s] doi 对齐命中: %d", prefix, len(matches))
        for idx, (stub_vid, real_vid, _p) in enumerate(matches):
            if idx < preview:
                logger.info("[match] %s -> %s", stub_vid, real_vid)
        if not dry_run:
            for i in range(0, len(matches), batch_size):
                _insert_same_as_edges(graph, matches[i : i + batch_size])

    if dry_run:
        logger.info("[dry-run] 未写边，共匹配 %d 个桩", stats["matched"])
    else:
        try:
            r = graph.execute_read(f"USE {SPACE}; MATCH ()-[e:SAME_AS]->() RETURN count(e) AS n;")
            logger.info("dev SAME_AS 边数: %s", r.records[0].get("n") if r.records else "?")
        except Exception as exc:
            logger.warning("统计失败: %s", str(exc)[:120])
    return {"written": stats["matched"], "stats": stats, "dry_run": dry_run}


def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--batch-size", type=int, default=200)
    ap.add_argument("--preview", type=int, default=10)
    return ap.parse_args()


def main() -> None:
    args = _parse_args()
    result = run(dry_run=args.dry_run, batch_size=args.batch_size, preview=args.preview)
    logger.info("result: %s", result)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    main()
