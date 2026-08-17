"""产业链图谱 ETL：从 gkx_element 灌产业链节点/边到 TRSGraph dev 空间。

dev 现状：无 IndustryChain/IndustryNode tag，无 HAS_NODE/CHILD_OF/DOWNSTREAM_OF/COVERS_CHAIN 边
（BELONGS_TO_NODE/PRODUCES/HAS_NEWS 已有但 BELONGS_TO_NODE 0 条数据）。

本脚本建缺失 schema 并加载：
  - dwd_industry_chain_info → IndustryChain 节点(chain_{chain_code}) + IndustryNode 节点(node_{node_id})
    + HAS_NODE(chain→node) + CHILD_OF(node→parent) + DOWNSTREAM_OF(node→downstream)
  - dwd_org_industry_chain_dtl → BELONGS_TO_NODE(org_{antitypic}→node_{node_id}, chain_score)
    只连 dev 中已存在的 org，避免悬挂。
  - dwd_industry_chain_news_info → News 节点(news_{news_id}) + COVERS_CHAIN(news→chain)

VID 约定：chain_{chain_code} / node_{node_id} / news_{news_id} / org_{antitypic}(已有)。

安全约束：只 CREATE/INSERT，绝不 DELETE/ALTER 已有数据；多值 INSERT 幂等(rank@0)。
使用 infra.graph_db.TRSGraphClient。

用法：
    cd backend && PYTHONPATH=. .venv/bin/python script/industry_chain_etl/load_industry_chain_graph.py
"""

from __future__ import annotations

import logging
import os
import time
from urllib.parse import quote_plus

from sqlalchemy import select, text

from db_model.industry_chain import (
    DwdIndustryChainNewsInfo,
    DwdOrgIndustryChainDtl,
)
from infra.graph_db import TRSGraphClient
from infra.graph_db.config import TRSGraphSettings
from infra.mysql import MySQLClient

logging.basicConfig(level=logging.INFO, format="%(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

SPACE = "dev"
BATCH = 500
INGEST_BATCH = "industry_chain_etl_20260805"
INGEST_TIME = "2026-08-05"


def get_graph_client() -> TRSGraphClient:
    s = TRSGraphSettings.from_env()
    s.space = SPACE
    c = TRSGraphClient(s)
    c.connect()
    return c


def get_mysql_client() -> MySQLClient:
    url = (
        f"mysql+pymysql://{quote_plus(os.getenv('MYSQL_USERNAME', 'root'))}:"
        f"{quote_plus(os.getenv('MYSQL_PASSWORD', '123456789'))}"
        f"@{os.getenv('MYSQL_HOST', '127.0.0.1')}:{os.getenv('MYSQL_PORT', '3306')}"
        f"/gkx_element?charset=utf8mb4"
    )
    return MySQLClient(url=url)


def esc(v) -> str:
    if v is None:
        return "NULL"
    s = str(v).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ").replace("\r", " ")
    return f'"{s}"'


def _write(client: TRSGraphClient, ngql: str, label: str) -> bool:
    try:
        client.execute_write(ngql)
        return True
    except Exception as exc:
        logger.warning("  %s 失败: %s", label, str(exc)[:160])
        return False


def ensure_schema(client: TRSGraphClient) -> None:
    """建缺失的 tag/edge（不 ALTER 已有）。CREATE 后等 schema 传播。"""
    defs = [
        (
            "TAG",
            "IndustryChain",
            "CREATE TAG IndustryChain(chain_code string, chain_name string, source_table string, ingest_batch string, ingest_time string);",
        ),
        (
            "TAG",
            "IndustryNode",
            "CREATE TAG IndustryNode(node_id string, node_name string, node_type string, level string, node_seq string, node_imp_level string, node_stage string, node_path string, source_table string, ingest_batch string, ingest_time string);",
        ),
        ("EDGE", "HAS_NODE", "CREATE EDGE HAS_NODE();"),
        ("EDGE", "CHILD_OF", "CREATE EDGE CHILD_OF();"),
        ("EDGE", "DOWNSTREAM_OF", "CREATE EDGE DOWNSTREAM_OF();"),
        (
            "EDGE",
            "COVERS_CHAIN",
            "CREATE EDGE COVERS_CHAIN(source_table string, ingest_batch string, ingest_time string);",
        ),
    ]
    for kind, name, ddl in defs:
        # 检查是否已存在
        try:
            client.execute_read(f"USE {SPACE}; DESCRIBE {kind} {name};")
            logger.info("  %s %s 已存在", kind, name)
            continue
        except Exception:
            pass
        logger.info("  CREATE %s %s ...", kind, name)
        client.execute_write(f"USE {SPACE}; {ddl}")
        time.sleep(15)


def batch_insert_vertex(client, tag, fields, rows, label):
    if not rows:
        return 0
    fl = ",".join(fields)
    vals = ",".join(f"{esc(vid)}:({','.join(esc(v) for v in vals)})" for vid, *vals in rows)
    _write(client, f"USE {SPACE}; INSERT VERTEX {tag}({fl}) VALUES {vals};", label)
    return len(rows)


def batch_insert_edge(client, edge, fields, rows, label):
    if not rows:
        return 0
    fl = f"({','.join(fields)})" if fields else "()"
    if fields:
        vals = ",".join(
            f"{esc(s)}->{esc(t)}:({','.join(esc(v) for v in vals)})" for s, t, *vals in rows
        )
    else:
        vals = ",".join(f"{esc(s)}->{esc(t)}:()" for s, t, *vals in rows)
    _write(client, f"USE {SPACE}; INSERT EDGE {edge}{fl} VALUES {vals};", label)
    return len(rows)


def main() -> None:
    graph = get_graph_client()
    mysql = get_mysql_client()

    logger.info("=== 1. 确保 schema ===")
    ensure_schema(graph)

    with mysql.session_scope() as session:
        logger.info(
            "\n=== 2. 加载 dwd_industry_chain_info → IndustryChain/IndustryNode + 层级边 ==="
        )
        # raw SQL 避开 ORM 里 downstream_lin 与实际列 downstream_link_code 不一致的 bug
        rows = session.execute(
            text(
                "SELECT chain_code, chain_name, node_id, node_name, node_type, level, "
                "node_seq, node_imp_level, node_stage, node_path, parent_id, downstream_link_code "
                "FROM dwd_industry_chain_info"
            )
        ).all()

        chains = {}
        nodes = []
        has_node_edges = []
        child_edges = []
        down_edges = []
        for r in rows:
            (
                chain_code,
                chain_name,
                node_id,
                node_name,
                ntype,
                level,
                nseq,
                nimp,
                nstage,
                npath,
                parent_id,
                downstream,
            ) = r
            if chain_code:
                chains.setdefault(chain_code, chain_name)
            if node_id:
                nodes.append(
                    (
                        f"node_{node_id}",
                        node_id,
                        node_name,
                        str(ntype) if ntype is not None else "",
                        str(level) if level is not None else "",
                        str(nseq) if nseq is not None else "",
                        str(nimp) if nimp is not None else "",
                        str(nstage) if nstage is not None else "",
                        npath or "",
                        "dwd_industry_chain_info",
                        INGEST_BATCH,
                        INGEST_TIME,
                    )
                )
                if chain_code:
                    has_node_edges.append((f"chain_{chain_code}", f"node_{node_id}"))
                if parent_id:
                    child_edges.append((f"node_{node_id}", f"node_{parent_id}"))
                if downstream:
                    down_edges.append((f"node_{node_id}", f"node_{downstream}"))

        chain_rows = [
            (f"chain_{cc}", cc, cn or "", "dwd_industry_chain_info", INGEST_BATCH, INGEST_TIME)
            for cc, cn in chains.items()
        ]
        logger.info(
            "  IndustryChain %d, IndustryNode %d, HAS_NODE %d, CHILD_OF %d, DOWNSTREAM_OF %d",
            len(chain_rows),
            len(nodes),
            len(has_node_edges),
            len(child_edges),
            len(down_edges),
        )

        for i in range(0, len(chain_rows), BATCH):
            batch_insert_vertex(
                graph,
                "IndustryChain",
                ["chain_code", "chain_name", "source_table", "ingest_batch", "ingest_time"],
                chain_rows[i : i + BATCH],
                "IndustryChain",
            )
        for i in range(0, len(nodes), BATCH):
            batch_insert_vertex(
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
                "IndustryNode",
            )
        for i in range(0, len(has_node_edges), BATCH):
            batch_insert_edge(graph, "HAS_NODE", [], has_node_edges[i : i + BATCH], "HAS_NODE")
        for i in range(0, len(child_edges), BATCH):
            batch_insert_edge(graph, "CHILD_OF", [], child_edges[i : i + BATCH], "CHILD_OF")
        for i in range(0, len(down_edges), BATCH):
            batch_insert_edge(
                graph, "DOWNSTREAM_OF", [], down_edges[i : i + BATCH], "DOWNSTREAM_OF"
            )

        logger.info(
            "\n=== 3. 加载 dwd_org_industry_chain_dtl → BELONGS_TO_NODE（只连已存在 org）==="
        )
        # 预取 dev 中已有 org vid
        existing_orgs = set()
        try:
            r = graph.execute_read(f"USE {SPACE}; MATCH (v:Organization) RETURN id(v) AS vid;")
            existing_orgs = {str(rec.get("vid")) for rec in r.records if rec.get("vid")}
        except Exception as exc:
            logger.warning("  取已有 org 失败: %s", exc)
        logger.info("  dev 已有 org %d 个", len(existing_orgs))

        dtl_rows = session.execute(
            select(
                DwdOrgIndustryChainDtl.antitypic,
                DwdOrgIndustryChainDtl.node_id,
                DwdOrgIndustryChainDtl.chain_score,
            )
        ).all()
        bel_edges = []
        for r in dtl_rows:
            antitypic, node_id, chain_score = r
            if not antitypic or not node_id:
                continue
            org_vid = f"org_{antitypic}"
            if org_vid not in existing_orgs:
                continue
            bel_edges.append(
                (
                    org_vid,
                    f"node_{node_id}",
                    str(chain_score) if chain_score is not None else "",
                    "dwd_org_industry_chain_dtl",
                    antitypic,
                    INGEST_BATCH,
                    INGEST_TIME,
                )
            )
        logger.info("  BELONGS_TO_NODE 待写 %d 条（跳过不存在 org）", len(bel_edges))

        def _insert_belongs(rows):
            # chain_score 是 double，不能加引号；其余 string 正常转义
            if not rows:
                return
            parts = []
            for org_vid, node_vid, cs, st, srid, ib, it in rows:
                try:
                    cs_val = str(float(cs)) if cs not in (None, "", "None") else "0.0"
                except (TypeError, ValueError):
                    cs_val = "0.0"
                parts.append(
                    f"{esc(org_vid)}->{esc(node_vid)}:({cs_val},{esc(st)},{esc(srid)},{esc(ib)},{esc(it)})"
                )
            _write(
                graph,
                f"USE {SPACE}; INSERT EDGE BELONGS_TO_NODE(chain_score,source_table,source_record_id,ingest_batch,ingest_time) "
                f"VALUES {','.join(parts)};",
                "BELONGS_TO_NODE",
            )

        for i in range(0, len(bel_edges), BATCH):
            _insert_belongs(bel_edges[i : i + BATCH])

        logger.info("\n=== 4. 加载 dwd_industry_chain_news_info → News + COVERS_CHAIN ===")
        news_rows = session.execute(
            select(
                DwdIndustryChainNewsInfo.news_id,
                DwdIndustryChainNewsInfo.title,
                DwdIndustryChainNewsInfo.summary,
                DwdIndustryChainNewsInfo.relaese_date,
                DwdIndustryChainNewsInfo.source,
                DwdIndustryChainNewsInfo.chain_code,
            )
        ).all()
        news_nodes = []
        cover_edges = []
        for r in news_rows:
            news_id, title, summary, rdate, source, chain_code = r
            if not news_id:
                continue
            news_nodes.append(
                (
                    f"news_{news_id}",
                    title or "",
                    summary or "",
                    str(rdate) if rdate else "",
                    "",
                    "",
                    "dwd_industry_chain_news_info",
                    news_id,
                    "",
                    "dwd_industry_chain_news_info",
                    INGEST_BATCH,
                    INGEST_TIME,
                    "",
                )
            )
            if chain_code:
                cover_edges.append(
                    (
                        f"news_{news_id}",
                        f"chain_{chain_code}",
                        "dwd_industry_chain_news_info",
                        INGEST_BATCH,
                        INGEST_TIME,
                    )
                )
        logger.info("  News %d, COVERS_CHAIN %d", len(news_nodes), len(cover_edges))
        for i in range(0, len(news_nodes), BATCH):
            batch_insert_vertex(
                graph,
                "News",
                [
                    "title",
                    "content",
                    "release_date",
                    "original_url",
                    "extra_json",
                    "source_system",
                    "source_table",
                    "source_record_id",
                    "source_url",
                    "ingest_batch",
                    "ingest_time",
                    "source_update_time",
                ],
                news_nodes[i : i + BATCH],
                "News(chain)",
            )
        for i in range(0, len(cover_edges), BATCH):
            batch_insert_edge(
                graph,
                "COVERS_CHAIN",
                ["source_table", "ingest_batch", "ingest_time"],
                cover_edges[i : i + BATCH],
                "COVERS_CHAIN",
            )

    logger.info("\n=== 5. 统计 ===")
    for t in ["IndustryChain", "IndustryNode"]:
        try:
            logger.info("  %s: %s", t, graph.node_count(t))
        except Exception:
            pass
    for e in ["HAS_NODE", "CHILD_OF", "DOWNSTREAM_OF", "BELONGS_TO_NODE", "COVERS_CHAIN"]:
        try:
            logger.info("  %s: %s", e, graph.edge_count(e))
        except Exception:
            pass
    graph.close()


if __name__ == "__main__":
    main()
