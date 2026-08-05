"""论文/期刊/产业链 图谱构建工作流脚本。

通过工作流平台提交执行：
  POST /api/v1/workflow-system/definitions/python  (上传此文件, function_name="workflow")
  POST /api/v1/workflow-system/definitions/{id}/execute  (payload 控制模式)

支持全量和增量更新：
  payload = {} 或 {"mode": "full"}             → 全量
  payload = {"mode": "incremental", "since": "2026-07-01"} → 只处理 updated_time > since 的数据

封装内容：
  1. 论文实体（dwd_zh/en_paper → Paper 顶点）
  2. 论文关系（reference/citation/related → CITES/CITED_BY/RELATED_TO 边）
  3. 产业链图谱（dwd_industry_chain_info → IndustryNode + HAS_NODE/CHILD_OF；
     dwd_org_industry_chain_dtl → BELONGS_TO_NODE）

图写入用多值 INSERT VERTEX/EDGE（rank@0 幂等），只插入不删除。
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sys

# 工作流平台子进程只设 PYTHONPATH=脚本目录，需手动加 backend 到 path + load .env
BACKEND_DIR = os.getenv("BACKEND_DIR", "/data1/huyatao/tech-kg-api/backend")
sys.path.insert(0, BACKEND_DIR)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(BACKEND_DIR, ".env"))

from sqlalchemy import text  # noqa: E402

from infra.graph_db import TRSGraphClient  # noqa: E402
from infra.graph_db.config import TRSGraphSettings  # noqa: E402
from infra.mysql import MySQLClient  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

SPACE = "dev"
BATCH = 500
INGEST_BATCH = "workflow_etl"
_SUFFIX_RE = re.compile(r"__\d+$")


# ---------- 工具 ----------


def _esc(v) -> str:
    if v is None:
        return "NULL"
    s = str(v).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ").replace("\r", " ")
    return f'"{s}"'


def _vid(raw) -> str:
    s = str(raw).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{s}"'


def _source_paper_id(raw_id: str) -> str:
    if not raw_id:
        return ""
    return _SUFFIX_RE.sub("", str(raw_id))


def _md5_vid(prefix: str, key: str, short: bool = True) -> str:
    h = hashlib.md5(key.encode()).hexdigest()
    return f"{prefix}_{h[:16] if short else h}"


def _batch_v(client, tag, fields, rows):
    if not rows:
        return 0
    fl = ",".join(fields)
    vals = ",".join(f"{_vid(vid)}:({','.join(_esc(v) for v in vals)})" for vid, *vals in rows)
    try:
        client.execute_write(f"USE {SPACE}; INSERT VERTEX {tag}({fl}) VALUES {vals};")
        return len(rows)
    except Exception as exc:
        logger.warning("  INSERT VERTEX %s 失败 (%d): %s", tag, len(rows), str(exc)[:120])
        return 0


def _batch_e(client, edge, fields, rows, double_first=False):
    if not rows:
        return 0
    fl = f"({','.join(fields)})" if fields else "()"
    parts = []
    for row in rows:
        s, t = row[0], row[1]
        vals = row[2:]
        if fields:
            vstrs = []
            for i, v in enumerate(vals):
                if double_first and i == 0:
                    try:
                        vstrs.append(str(float(v)))
                    except (TypeError, ValueError):
                        vstrs.append("0.0")
                else:
                    vstrs.append(_esc(v))
            parts.append(f"{_vid(s)}->{_vid(t)}:({','.join(vstrs)})")
        else:
            parts.append(f"{_vid(s)}->{_vid(t)}:()")
    try:
        client.execute_write(f"USE {SPACE}; INSERT EDGE {edge}{fl} VALUES {','.join(parts)};")
        return len(rows)
    except Exception as exc:
        logger.warning("  INSERT EDGE %s 失败 (%d): %s", edge, len(rows), str(exc)[:120])
        return 0


# ---------- ETL 步骤 ----------


def _load_papers(mysql, graph, since):
    """论文实体 → Paper 顶点（全量或增量）。"""
    total = 0
    with mysql.engine.connect() as conn:
        for tbl in ["dwd_zh_paper", "dwd_en_paper"]:
            sql = f"SELECT id, doi, zh_name, en_name, publication_year FROM {tbl}"
            if since:
                sql += f" WHERE updated_time > '{since}'"
            rows = conn.execute(text(sql)).all()
            verts = []
            for r in rows:
                verts.append(
                    (
                        f"paper_{r[0]}",
                        r[1] or "",
                        r[2] or "",
                        r[3] or "",
                        str(r[4]) if r[4] else "",
                    )
                )
            for i in range(0, len(verts), BATCH):
                _batch_v(
                    graph,
                    "Paper",
                    ["doi", "title_zh", "title_en", "publication_year", "source"],
                    [(v[0], v[1], v[2], v[3], v[4], "gkx") for v in verts[i : i + BATCH]],
                )
            total += len(verts)
            logger.info("  %s: %d 篇论文", tbl, len(verts))
    return {"papers": total}


def _load_paper_relations(mysql, graph, since):
    """论文关系 → CITES/CITED_BY/RELATED_TO 边（全量或增量）。"""
    total = 0
    with mysql.engine.connect() as conn:
        configs = [
            (
                "dwd_zh_paper_reference",
                "dwd_en_paper_reference",
                "CITES",
                "paper_ref",
                "reference_identifier",
            ),
            (
                "dwd_zh_paper_citation",
                "dwd_en_paper_citation",
                "CITED_BY",
                "paper_cit",
                "citation_identifier",
            ),
            ("dwd_zh_paper_related", "dwd_en_paper_related", "RELATED_TO", "paper_rel", None),
        ]
        for zh_tbl, en_tbl, edge, prefix, field in configs:
            edges = []
            for tbl in [zh_tbl, en_tbl]:
                sql = f"SELECT id, doi FROM {tbl} WHERE doi IS NOT NULL AND doi != ''"
                if since:
                    sql += f" AND updated_time > '{since}'"
                for r in conn.execute(text(sql)).all():
                    src_id = _source_paper_id(r[0])
                    if not src_id:
                        continue
                    dst_vid = _md5_vid(prefix, r[1])
                    if field:
                        edges.append((f"paper_{src_id}", dst_vid, r[1]))
                    else:
                        edges.append((f"paper_{src_id}", dst_vid))
            for i in range(0, len(edges), BATCH):
                _batch_e(graph, edge, [field] if field else [], edges[i : i + BATCH])
            total += len(edges)
            logger.info("  %s: %d 条边", edge, len(edges))
    return {"paper_relations": total}


def _load_industry_chain(mysql, graph, since):
    """产业链节点 + 层级边 + 企业关联（全量或增量）。"""

    total_nodes = 0
    total_edges = 0
    with mysql.engine.connect() as conn:
        # 链节点 + IndustryChain
        sql = "SELECT chain_code, chain_name, node_id, node_name, node_type, level, node_seq, node_imp_level, node_stage, node_path, parent_id, downstream_link_code FROM dwd_industry_chain_info"
        if since:
            sql += f" WHERE updated_time > '{since}'"
        rows = conn.execute(text(sql)).all()
        chains = {}
        nodes = []
        has_node_e = []
        child_e = []
        down_e = []
        for r in rows:
            cc, cn, nid, nn, nt, lv, ns, ni, nst, np_, pid, dn = r
            if cc:
                chains.setdefault(cc, cn)
            if nid:
                nodes.append(
                    (
                        f"node_{nid}",
                        nid,
                        nn or "",
                        str(nt) if nt is not None else "",
                        str(lv) if lv is not None else "",
                        str(ns) if ns is not None else "",
                        str(ni) if ni is not None else "",
                        str(nst) if nst is not None else "",
                        np_ or "",
                        "dwd_industry_chain_info",
                        INGEST_BATCH,
                        "",
                    )
                )
                if cc:
                    has_node_e.append((f"chain_{cc}", f"node_{nid}"))
                if pid:
                    child_e.append((f"node_{nid}", f"node_{pid}"))
                if dn:
                    down_e.append((f"node_{nid}", f"node_{dn}"))
        chain_rows = [
            (f"chain_{cc}", cc, cn or "", "dwd_industry_chain_info", INGEST_BATCH, "")
            for cc, cn in chains.items()
        ]
        for i in range(0, len(chain_rows), BATCH):
            _batch_v(
                graph,
                "IndustryChain",
                ["chain_code", "chain_name", "source_table", "ingest_batch", "ingest_time"],
                chain_rows[i : i + BATCH],
            )
        for i in range(0, len(nodes), BATCH):
            _batch_v(
                graph,
                "IndustryNode",
                [
                    "node_id",
                    "node_name",
                    "node_type",
                    "level",
                    "node_seq",
                    "node_imp_level",
                    "node_stage",
                    "node_path",
                    "source_table",
                    "ingest_batch",
                    "ingest_time",
                ],
                nodes[i : i + BATCH],
            )
        for i in range(0, len(has_node_e), BATCH):
            _batch_e(graph, "HAS_NODE", [], has_node_e[i : i + BATCH])
        for i in range(0, len(child_e), BATCH):
            _batch_e(graph, "CHILD_OF", [], child_e[i : i + BATCH])
        for i in range(0, len(down_e), BATCH):
            _batch_e(graph, "DOWNSTREAM_OF", [], down_e[i : i + BATCH])
        total_nodes = len(nodes)
        total_edges = len(has_node_e) + len(child_e) + len(down_e)
        logger.info("  产业链: %d 节点, %d 边", total_nodes, total_edges)

        # 企业→节点 BELONGS_TO_NODE（只连已存在 org）
        existing_orgs = set()
        try:
            r = graph.execute_read(f"USE {SPACE}; MATCH (v:Organization) RETURN id(v) AS vid;")
            existing_orgs = {str(rec.get("vid")) for rec in r.records if rec.get("vid")}
        except Exception:
            pass
        sql2 = "SELECT antitypic, node_id, chain_score FROM dwd_org_industry_chain_dtl WHERE antitypic IS NOT NULL"
        if since:
            sql2 += f" AND updated_time > '{since}'"
        bel = []
        for r in conn.execute(text(sql2)).all():
            org_vid = f"org_{r[0]}"
            if org_vid not in existing_orgs:
                continue
            bel.append(
                (
                    org_vid,
                    f"node_{r[1]}",
                    str(r[2]) if r[2] is not None else "0",
                    "dwd_org_industry_chain_dtl",
                    r[0],
                    INGEST_BATCH,
                    "",
                )
            )
        for i in range(0, len(bel), BATCH):
            _batch_e(
                graph,
                "BELONGS_TO_NODE",
                ["chain_score", "source_table", "source_record_id", "ingest_batch", "ingest_time"],
                bel[i : i + BATCH],
                double_first=True,
            )
        total_edges += len(bel)
        logger.info("  BELONGS_TO_NODE: %d 条", len(bel))

    return {"chain_nodes": total_nodes, "chain_edges": total_edges}


# ---------- 工作流入口 ----------


def workflow(payload: dict) -> dict:
    """工作流平台入口函数。

    payload:
      mode: "full" (默认) 或 "incremental"
      since: 增量模式的起始时间 (如 "2026-07-01")
    """
    mode = payload.get("mode", "full")
    since = payload.get("since") if mode == "incremental" else None

    logger.info("=== 论文/期刊/产业链图谱构建 (mode=%s, since=%s) ===", mode, since)

    settings = TRSGraphSettings.from_env()
    settings.space = SPACE
    graph = TRSGraphClient(settings)
    graph.connect()
    mysql = MySQLClient()

    stats = {}
    logger.info("\n1. 论文实体")
    stats.update(_load_papers(mysql, graph, since))
    logger.info("\n2. 论文关系")
    stats.update(_load_paper_relations(mysql, graph, since))
    logger.info("\n3. 产业链图谱")
    stats.update(_load_industry_chain(mysql, graph, since))

    graph.close()
    logger.info("\n=== 完成: %s ===", json.dumps(stats, ensure_ascii=False))
    return {"status": "success", "mode": mode, "since": since, "stats": stats}
