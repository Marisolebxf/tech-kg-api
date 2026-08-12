"""论文/期刊/产业链 图谱构建工作流脚本。

通过工作流平台提交执行：
  POST /api/v1/workflow-system/definitions/python  (上传此文件, function_name="workflow")
  POST /api/v1/workflow-system/definitions/{id}/execute  (payload 控制模式)

支持全量和增量更新：
  payload = {} 或 {"mode": "full"}             → 全量
  payload = {"mode": "incremental", "since": "2026-07-01"} → 只处理 updated_time > since 的数据

封装内容（完整覆盖三个原脚本的所有点边）：
  论文实体：Paper 顶点（dwd_zh/en_paper）
  论文作者：Person 顶点 + AUTHORED_BY 边（dwd_zh/en_paper_author）
  期刊：Journal 顶点 + PUBLISHED_IN 边（dwd_zh/en_journal + paper.journal_id）
  论文关系：CITES / CITED_BY / RELATED_TO 边（reference / citation / related 表）
  关键词：Keyword 顶点 + HAS_KEYWORD 边（dwd_zh/en_paper_classification）
  报告：Report 顶点 + REFERENCED_BY 边（dwd_zh_report_paper）
  产业链：IndustryChain / IndustryNode 顶点 + HAS_NODE / CHILD_OF / DOWNSTREAM_OF 边
         + BELONGS_TO_NODE 边（org→node）
         + News 顶点 + COVERS_CHAIN 边（dwd_industry_chain_news_info）

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
INGEST_TIME = "2026-08-11T00:00:00Z"
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


def _batch_e(client, edge, fields, rows, double_first=False, fixed_confidence=None):
    """INSERT EDGE。fixed_confidence 非 None 时追加 confidence double 字段（不加引号）。"""
    if not rows:
        return 0
    if fixed_confidence is not None:
        fields = [*fields, "confidence"]
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
            if fixed_confidence is not None:
                vstrs.append(str(float(fixed_confidence)))
            parts.append(f"{_vid(s)}->{_vid(t)}:({','.join(vstrs)})")
        else:
            if fixed_confidence is not None:
                parts.append(f"{_vid(s)}->{_vid(t)}:({str(float(fixed_confidence))})")
            else:
                parts.append(f"{_vid(s)}->{_vid(t)}:()")
    try:
        client.execute_write(f"USE {SPACE}; INSERT EDGE {edge}{fl} VALUES {','.join(parts)};")
        return len(rows)
    except Exception as exc:
        logger.warning("  INSERT EDGE %s 失败 (%d): %s", edge, len(rows), str(exc)[:120])
        return 0


def _attach_org_base(client, vids, confidence, source_table):
    """给实体 vid 批量挂 organization_base mixin tag（confidence + 溯源四件套）。"""
    if not vids:
        return 0
    fields = (
        "organization_id, confidence, source_system, source_table, source_record_id, "
        "ingest_batch, ingest_time"
    )
    done = 0
    for i in range(0, len(vids), BATCH):
        chunk = vids[i : i + BATCH]
        vals = ",".join(
            f'{_vid(v)}:("",{float(confidence)},"gkx_element","{source_table}",'
            f'"{v}","{INGEST_BATCH}","{INGEST_TIME}")'
            for v in chunk
        )
        try:
            client.execute_write(
                f"USE {SPACE}; INSERT VERTEX organization_base({fields}) VALUES {vals};"
            )
            done += len(chunk)
        except Exception as exc:
            logger.warning(
                "  INSERT VERTEX organization_base 失败 (%d): %s", len(chunk), str(exc)[:120]
            )
    return done


def _since(sql, since, col="updated_time"):
    """给 SQL 追加增量条件。"""
    if since:
        sql += f" WHERE {col} > '{since}'"
    return sql


# ---------- ETL 步骤 ----------


def _load_papers(mysql, graph, since):
    """论文实体 → Paper 顶点。"""
    total = 0
    with mysql.engine.connect() as conn:
        for tbl in ["dwd_zh_paper", "dwd_en_paper"]:
            sql = f"SELECT id, doi, zh_name, en_name, publication_year, publication_id FROM {tbl}"
            sql = _since(sql, since)
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
                        str(r[5]) if r[5] else "",
                        "gkx",
                    )
                )
            for i in range(0, len(verts), BATCH):
                _batch_v(
                    graph,
                    "Paper",
                    [
                        "doi",
                        "title_zh",
                        "title_en",
                        "publication_year",
                        "publication_name",
                        "source",
                    ],
                    verts[i : i + BATCH],
                )
            # 挂 organization_base 溯源+置信度 mixin（confidence=1.0 真实实体）
            _attach_org_base(graph, [v[0] for v in verts], 1.0, tbl)
            total += len(verts)
            logger.info("  %s: %d 篇论文", tbl, len(verts))
    return {"papers": total}


def _load_authors(mysql, graph, since):
    """论文作者 → Person 顶点 + AUTHORED_BY 边。"""
    total_p = total_e = 0
    with mysql.engine.connect() as conn:
        for tbl in ["dwd_zh_author", "dwd_en_author"]:
            sql = f"SELECT paper_id, author_id, en_name, zh_name, email, author_sequence, correspond FROM {tbl}"
            sql = _since(sql, since)
            persons = {}
            edges = []
            for r in conn.execute(text(sql)).all():
                pid = _source_paper_id(r[0])
                aid = str(r[1]) if r[1] else ""
                if not pid or not aid:
                    continue
                if aid not in persons:
                    # r[2]=en_name, r[3]=zh_name（与 SELECT 顺序一致）
                    persons[aid] = (f"person_{aid}", r[3] or "", r[2] or "")
                edges.append(
                    (
                        f"paper_{pid}",
                        f"person_{aid}",
                        str(r[5]) if r[5] is not None else "",
                        str(r[6]) if r[6] is not None else "",
                    )
                )
            prows = list(persons.values())
            for i in range(0, len(prows), BATCH):
                _batch_v(
                    graph,
                    "Person",
                    ["name_zh", "name_en"],
                    [(p[0], p[1], p[2]) for p in prows[i : i + BATCH]],
                )
            _attach_org_base(graph, [p[0] for p in prows], 1.0, tbl)
            for i in range(0, len(edges), BATCH):
                _batch_e(
                    graph,
                    "AUTHORED_BY",
                    ["author_order", "is_corresponding"],
                    edges[i : i + BATCH],
                    fixed_confidence=1.0,
                )
            total_p += len(persons)
            total_e += len(edges)
            logger.info("  %s: %d 作者, %d AUTHORED_BY", tbl, len(persons), len(edges))
    return {"persons": total_p, "authored_by": total_e}


def _load_journals(mysql, graph, since):
    """期刊 → Journal 顶点 + PUBLISHED_IN 边。"""
    total_j = total_e = 0
    with mysql.engine.connect() as conn:
        # Journal 顶点
        for tbl in ["dwd_zh_journal", "dwd_en_journal"]:
            sql = f"SELECT journal_id, journal_en_name, journal_zh_name, issn, country FROM {tbl}"
            sql = _since(sql, since)
            verts = []
            for r in conn.execute(text(sql)).all():
                jid = str(r[0]) if r[0] else ""
                if not jid:
                    continue
                verts.append((f"journal_{jid}", r[1] or "", r[2] or "", r[3] or "", r[4] or ""))
            for i in range(0, len(verts), BATCH):
                _batch_v(
                    graph,
                    "Journal",
                    ["name_en", "name_zh", "issn", "country"],
                    verts[i : i + BATCH],
                )
            _attach_org_base(graph, [v[0] for v in verts], 1.0, tbl)
            total_j += len(verts)
            logger.info("  %s: %d 期刊", tbl, len(verts))

        # PUBLISHED_IN 边（从 paper 表的 publication_id）
        for tbl in ["dwd_zh_paper", "dwd_en_paper"]:
            sql = f"SELECT id, publication_id FROM {tbl} WHERE publication_id IS NOT NULL AND publication_id != ''"
            if since:
                sql += f" AND updated_time > '{since}'"
            edges = []
            for r in conn.execute(text(sql)).all():
                pid = _source_paper_id(r[0])
                jid = str(r[1]) if r[1] else ""
                if pid and jid:
                    edges.append((f"paper_{pid}", f"journal_{jid}"))
            for i in range(0, len(edges), BATCH):
                _batch_e(graph, "PUBLISHED_IN", [], edges[i : i + BATCH], fixed_confidence=1.0)
            total_e += len(edges)
            logger.info("  %s PUBLISHED_IN: %d", tbl, len(edges))
    return {"journals": total_j, "published_in": total_e}


def _load_paper_relations(mysql, graph, since):
    """论文关系 → CITES / CITED_BY / RELATED_TO 边。"""
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
                # CITES/CITED_BY 目标是桩(paper_ref_/cit_) → 0.5；RELATED_TO → 0.7
                _rel_conf = 0.7 if edge == "RELATED_TO" else 0.5
                _batch_e(
                    graph,
                    edge,
                    [field] if field else [],
                    edges[i : i + BATCH],
                    fixed_confidence=_rel_conf,
                )
            total += len(edges)
            logger.info("  %s: %d 条边", edge, len(edges))
    return {"paper_relations": total}


def _load_keywords(mysql, graph, since):
    """关键词 → Keyword 顶点 + HAS_KEYWORD 边。"""
    total_kw = total_e = 0
    with mysql.engine.connect() as conn:
        for tbl, lang in [
            ("dwd_zh_paper_classification", "zh"),
            ("dwd_en_paper_classification", "en"),
        ]:
            sql = f"SELECT id, keywords FROM {tbl} WHERE keywords IS NOT NULL AND keywords != ''"
            if since:
                sql += f" AND updated_time > '{since}'"
            kw_set = {}
            edges = []
            for r in conn.execute(text(sql)).all():
                pid = _source_paper_id(r[0])
                if not pid:
                    continue
                raw = r[1]
                # 中文逗号分割 / 英文 JSON 数组
                kws = []
                if lang == "en":
                    try:
                        kws = [str(x).strip() for x in json.loads(raw) if x]
                    except (json.JSONDecodeError, TypeError):
                        kws = [s.strip() for s in raw.split(",") if s.strip()]
                else:
                    kws = [s.strip() for s in raw.split(",") if s.strip()]
                for kw in kws:
                    if not kw:
                        continue
                    kw_vid = _md5_vid("keyword", kw, short=False)
                    if kw_vid not in kw_set:
                        kw_set[kw_vid] = (kw_vid, kw)
                    edges.append((f"paper_{pid}", kw_vid))
            krows = list(kw_set.values())
            for i in range(0, len(krows), BATCH):
                _batch_v(graph, "Keyword", ["keyword"], krows[i : i + BATCH])
            _attach_org_base(graph, [k[0] for k in krows], 1.0, tbl)
            for i in range(0, len(edges), BATCH):
                _batch_e(graph, "HAS_KEYWORD", [], edges[i : i + BATCH], fixed_confidence=1.0)
            total_kw += len(kw_set)
            total_e += len(edges)
            logger.info("  %s: %d 关键词, %d HAS_KEYWORD", tbl, len(kw_set), len(edges))
    return {"keywords": total_kw, "has_keyword": total_e}


def _load_reports(mysql, graph, since):
    """报告 → Report 顶点 + REFERENCED_BY 边（Paper→Report）。"""
    total_r = total_e = 0
    with mysql.engine.connect() as conn:
        # Report 顶点
        for tbl, _lang in [("dwd_zh_report", "zh"), ("dwd_en_report", "en")]:
            sql = f"SELECT report_id, title_cn, title_en, abstract_cn FROM {tbl}"
            sql = _since(sql, since)
            verts = []
            for r in conn.execute(text(sql)).all():
                rid = str(r[0]) if r[0] else ""
                if not rid:
                    continue
                verts.append((f"report_{rid}", r[1] or r[2] or "", r[3] or ""))
            for i in range(0, len(verts), BATCH):
                _batch_v(graph, "Report", ["title", "abstract"], verts[i : i + BATCH])
            _attach_org_base(graph, [v[0] for v in verts], 1.0, tbl)
            total_r += len(verts)
            logger.info("  %s: %d 报告", tbl, len(verts))

        # REFERENCED_BY 边（dwd_zh_report_paper: paper→report）
        sql = "SELECT paper_id, paper_doi, report_id FROM dwd_zh_report_paper"
        if since:
            sql += f" WHERE updated_time > '{since}'"
        edges = []
        for r in conn.execute(text(sql)).all():
            pid = r[0] or ""
            rids = r[2] or ""
            if not pid or not rids:
                continue
            import json as _json

            try:
                rid_list = _json.loads(rids) if rids.startswith("[") else [rids]
            except (ValueError, TypeError):
                rid_list = [rids]
            for rid in rid_list:
                if rid:
                    edges.append((f"paper_rp_{pid}", f"report_{rid}"))
        for i in range(0, len(edges), BATCH):
            _batch_e(graph, "REFERENCED_BY", [], edges[i : i + BATCH], fixed_confidence=0.8)
        total_e = len(edges)
        logger.info("  REFERENCED_BY: %d", total_e)
    return {"reports": total_r, "referenced_by": total_e}


def _load_industry_chain(mysql, graph, since):
    """产业链节点 + 层级边 + 企业关联 + 产业资讯。"""
    total_nodes = 0
    total_edges = 0
    with mysql.engine.connect() as conn:
        # 链节点 + IndustryChain + IndustryNode + HAS_NODE/CHILD_OF/DOWNSTREAM_OF
        sql = (
            "SELECT chain_code, chain_name, node_id, node_name, node_type, level, "
            "node_seq, node_imp_level, node_stage, node_path, parent_id, downstream_link_code "
            "FROM dwd_industry_chain_info"
        )
        sql = _since(sql, since)
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
                        INGEST_TIME,
                    )
                )
                if cc:
                    has_node_e.append((f"chain_{cc}", f"node_{nid}"))
                if pid:
                    child_e.append((f"node_{nid}", f"node_{pid}"))
                if dn:
                    down_e.append((f"node_{nid}", f"node_{dn}"))
        chain_rows = [
            (f"chain_{cc}", cc, cn or "", "dwd_industry_chain_info", INGEST_BATCH, INGEST_TIME)
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
        logger.info("  产业链: %d 节点, %d 层级边", total_nodes, total_edges)

        # BELONGS_TO_NODE（只连已存在 org）
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
                    INGEST_TIME,
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
        logger.info("  BELONGS_TO_NODE: %d", len(bel))

        # News 顶点 + COVERS_CHAIN 边
        sql3 = "SELECT news_id, title, summary, relaese_date, chain_code FROM dwd_industry_chain_news_info"
        if since:
            sql3 += f" WHERE updated_time > '{since}'"
        news_verts = []
        cover_edges = []
        for r in conn.execute(text(sql3)).all():
            nid = str(r[0]) if r[0] else ""
            if not nid:
                continue
            news_verts.append(
                (
                    f"news_{nid}",
                    r[1] or "",
                    r[2] or "",
                    str(r[3]) if r[3] else "",
                    "",
                    "",
                    "dwd_industry_chain_news_info",
                    nid,
                    "",
                    "dwd_industry_chain_news_info",
                    INGEST_BATCH,
                    INGEST_TIME,
                    "",
                )
            )
            if r[4]:
                cover_edges.append(
                    (
                        f"news_{nid}",
                        f"chain_{r[4]}",
                        "dwd_industry_chain_news_info",
                        INGEST_BATCH,
                        INGEST_TIME,
                    )
                )
        for i in range(0, len(news_verts), BATCH):
            _batch_v(
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
                news_verts[i : i + BATCH],
            )
        for i in range(0, len(cover_edges), BATCH):
            _batch_e(
                graph,
                "COVERS_CHAIN",
                ["source_table", "ingest_batch", "ingest_time"],
                cover_edges[i : i + BATCH],
            )
        total_edges += len(cover_edges)
        logger.info("  News: %d, COVERS_CHAIN: %d", len(news_verts), len(cover_edges))

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
    steps = [
        ("1. 论文实体", _load_papers),
        ("2. 论文作者 Person + AUTHORED_BY", _load_authors),
        ("3. 期刊 Journal + PUBLISHED_IN", _load_journals),
        ("4. 论文关系 CITES/CITED_BY/RELATED_TO", _load_paper_relations),
        ("5. 关键词 Keyword + HAS_KEYWORD", _load_keywords),
        ("6. 报告 Report + REFERENCED_BY", _load_reports),
        ("7. 产业链图谱", _load_industry_chain),
    ]
    for label, fn in steps:
        logger.info("\n%s", label)
        stats.update(fn(mysql, graph, since))

    graph.close()
    logger.info("\n=== 完成: %s ===", json.dumps(stats, ensure_ascii=False))
    return {"status": "success", "mode": mode, "since": since, "stats": stats}
