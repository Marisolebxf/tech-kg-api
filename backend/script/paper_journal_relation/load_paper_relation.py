"""论文/期刊 实体关系抽取 ETL。

从 gkx_element 的论文关系表抽取「从论文出发」的有向边，INSERT 到 TRSGraph 的 dev 图空间，
把已存在的 Paper 实体（及其它实体）联系起来。期刊在本体中没有出边，故不涉及。

抽取的关系（均为「从论文出发」的有向边，覆盖论文到任意实体类型）：
    Paper → Paper
      - RELATED_TO : dwd_zh_paper_related / dwd_en_paper_related        相关论文
      - CITES      : dwd_zh_paper_reference / dwd_en_paper_reference    参考文献
      - CITED_BY   : dwd_zh_paper_citation / dwd_en_paper_citation      被引论文
    Paper → Keyword
      - HAS_KEYWORD: dwd_zh_paper_classification / dwd_en_paper_classification  关键词
    Paper → Report
      - REFERENCED_BY : dwd_zh_report_paper   论文被报告引用

未抽取：dwd_zh/en_paper_funding 的 `funds` 为自由文本致谢，无结构化资助方 id，
本体亦无 Paper→资助方 边，按「先直接抽、不对齐消歧」暂不处理（见 README 已知限制）。

VID 与属性约定（与 dev 空间已存在数据保持一致）：
    - 源端 vid = `paper_{id}`，id 去掉关系表行号后缀 `__N`，连到真实 Paper 顶点。
    - Paper→Paper 目标桩：`paper_{ref|cit|rel}_{md5(doi)[:16]}`，属性 doi + source。
    - Keyword vid：`keyword_{md5(keyword)}`（与已有 Keyword 一致），属性 keyword。
    - Paper→Report 源桩：`paper_rp_{paper_id}`（report_paper 的 paper_id 是 md5 哈希，
      与真实论文 `paper_{numeric_id}` 命名空间隔离），属性 doi + source；目标 report_{uuid} 已存在不触碰。
    - 边属性只写该边类型 schema 中已存在的列，不 ALTER 已有边；REFERENCED_BY 为新建边类型。

安全约束（重要）：
    1. 只 INSERT / UPSERT / CREATE，绝不 DELETE 或 ALTER 已有点边。
    2. 建桩前先 MATCH 查出已存在的目标 vid 集合，只对「不存在」的顶点做 INSERT VERTEX，
       已有顶点一律跳过（连属性都不覆盖），彻底避免修改既有数据。
    3. 边用多值 INSERT EDGE（rank@0），同 (src,dst,@0) 重复插入为幂等覆盖，属性值相同不丢数据。

用法：
    cd backend && PYTHONPATH=. .venv/bin/python script/paper_journal_relation/load_paper_relation.py

可选环境变量：
    PAPER_LIMIT     限制每张表抽取的行数（调试用，空=全量）
    BATCH_SIZE      单条 nGQL 多值 INSERT 的批量（默认 500）
    MAX_WORKERS     并发线程数（默认 8）
    RELATION_TYPES  逗号分隔：related,cites,cited_by,has_keyword,paper_report（默认全跑）
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote_plus

from sqlalchemy import text

from infra.graph_db import TRSGraphClient
from infra.graph_db.config import TRSGraphSettings
from infra.mysql import MySQLClient

logging.basicConfig(level=logging.INFO, format="%(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

SPACE = "dev"
_SUFFIX_RE = re.compile(r"__\d+$")
INGEST_BATCH = "paper_relation_0725"
INGEST_TIME = "2026-07-26"

# Paper→Paper 关系配置：边名 / 目标 vid 前缀 / 桩 source 值 / 边属性列
PAPER_PAPER_CONFIG = {
    "related": {
        "edge": "RELATED_TO",
        "prefix": "paper_rel",
        "source": "related",
        "field": None,
    },
    "cites": {
        "edge": "CITES",
        "prefix": "paper_ref",
        "source": "reference",
        "field": "reference_identifier",
    },
    "cited_by": {
        "edge": "CITED_BY",
        "prefix": "paper_cit",
        "source": "citation",
        "field": "citation_identifier",
    },
}
PAPER_PAPER_TABLES = {
    "related": ["dwd_zh_paper_related", "dwd_en_paper_related"],
    "cites": ["dwd_zh_paper_reference", "dwd_en_paper_reference"],
    "cited_by": ["dwd_zh_paper_citation", "dwd_en_paper_citation"],
}


# ---------- 连接 ----------


def get_graph_client() -> TRSGraphClient:
    """构造指向 dev 空间的 TRSGraphClient（按任务要求使用 infra.graph_db 封装）。"""
    settings = TRSGraphSettings(
        base_url=os.getenv("TRS_GRAPH_BASE_URL", "http://localhost:8090"),
        space=SPACE,
        api_key=os.getenv("TRS_GRAPH_API_KEY"),
        timeout=int(os.getenv("TRS_GRAPH_TIMEOUT", "60")),
    )
    client = TRSGraphClient(settings)
    client.connect()
    return client


def get_mysql_client() -> MySQLClient:
    """连接 gkx_element 要素库（论文关系源表所在库）。"""
    url = (
        f"mysql+pymysql://{quote_plus(os.getenv('MYSQL_USERNAME', 'root'))}:"
        f"{quote_plus(os.getenv('MYSQL_PASSWORD', '123456789'))}"
        f"@{os.getenv('MYSQL_HOST', '127.0.0.1')}:{os.getenv('MYSQL_PORT', '3306')}"
        f"/gkx_element?charset=utf8mb4"
    )
    return MySQLClient(url=url)


# ---------- 工具 ----------


def esc(v) -> str:
    """转义 nGQL 字符串字面量。None → NULL。"""
    if v is None:
        return "NULL"
    s = str(v).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ").replace("\r", " ")
    return f'"{s}"'


def source_paper_id(raw_id: str) -> str:
    """关系表 id 形如 `1002153099575427075__0`，去掉 `__N` 后缀得到真实论文 id。"""
    if not raw_id:
        return ""
    return _SUFFIX_RE.sub("", str(raw_id))


def md5_vid(prefix: str, key: str, short: bool = False) -> str:
    """vid：`{prefix}_{md5(key)}`。

    short=True 取 md5 前 16 位，与 dev 已有 CITES/CITED_BY 桩（`paper_ref_{md5[:16]}`）一致，
    保证幂等；Keyword 仍用 32 位（与已有 Keyword 顶点一致）。
    """
    h = hashlib.md5(key.encode()).hexdigest()
    return f"{prefix}_{h[:16] if short else h}"


def fetch_existing_vids(client: TRSGraphClient, prefix: str) -> set[str]:
    """查出 dev 中已存在的某前缀顶点 vid，建桩时跳过这些、绝不覆盖。"""
    existing: set[str] = set()
    try:
        r = client.execute_read(
            f'USE {SPACE}; MATCH (v) WHERE id(v) STARTS WITH "{prefix}_" RETURN id(v) AS vid;'
        )
        for rec in r.records:
            vid = rec.get("vid")
            if vid:
                existing.add(str(vid))
    except Exception as exc:
        logger.warning(f"  查询已有 {prefix}_ 顶点失败（按空集处理）: {str(exc)[:120]}")
    return existing


def batch_insert_vertex(
    client: TRSGraphClient, tag: str, fields: list[str], rows: list[tuple]
) -> bool:
    """多值 INSERT VERTEX。rows=[(vid, val1, val2, ...)]。仅用于「新」顶点。"""
    if not rows:
        return True
    field_list = ",".join(fields)
    values = ",".join(f"{esc(vid)}:({','.join(esc(v) for v in vals)})" for vid, *vals in rows)
    ngql = f"USE {SPACE}; INSERT VERTEX {tag}({field_list}) VALUES {values};"
    try:
        client.execute_write(ngql)
        return True
    except Exception as exc:
        logger.warning(f"  批量建顶点失败 {tag} ({len(rows)} 条): {str(exc)[:160]}")
        return False


def batch_insert_edge(
    client: TRSGraphClient, edge: str, fields: list[str], rows: list[tuple]
) -> bool:
    """多值 INSERT EDGE（rank@0，幂等）。rows=[(src, dst, *vals)]。"""
    if not rows:
        return True
    field_part = f"({','.join(fields)})" if fields else ""
    if fields:
        values = ",".join(
            f"{esc(src)}->{esc(dst)}:({','.join(esc(v) for v in vals)})" for src, dst, *vals in rows
        )
    else:
        values = ",".join(f"{esc(src)}->{esc(dst)}:()" for src, dst, *_ in rows)
    ngql = f"USE {SPACE}; INSERT EDGE {edge}{field_part} VALUES {values};"
    try:
        client.execute_write(ngql)
        return True
    except Exception as exc:
        logger.warning(f"  批量写边失败 {edge} ({len(rows)} 条): {str(exc)[:160]}")
        return False


def run_batches(items, worker, label: str, batch_size: int, max_workers: int) -> int:
    """把 items 切成 batch，并发执行 worker(batch)，返回成功批数。"""
    batches = [items[i : i + batch_size] for i in range(0, len(items), batch_size)]
    ok = 0
    total = len(batches)
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(worker, b): b for b in batches}
        for i, fut in enumerate(as_completed(futures), 1):
            if fut.result():
                ok += 1
            if i % 10 == 0 or i == total:
                done_rows = sum(len(futures[f]) for f in futures if f.done())
                logger.info(f"  {label}: {i}/{total} 批, 约 {done_rows} 行已提交")
    return ok


def ensure_edge_type(client: TRSGraphClient, edge: str, fields_sql: str = "") -> None:
    """若边类型不存在则 CREATE EDGE（不 ALTER 已有边）。新建后等待 schema 传播。"""
    try:
        client.execute_read(f"USE {SPACE}; DESCRIBE EDGE {edge};")
        logger.info(f"  边类型 {edge} 已存在，跳过建表")
        return
    except Exception:
        pass
    ddl = f"USE {SPACE}; CREATE EDGE {edge}({fields_sql});"
    client.execute_write(ddl)
    logger.info(f"  已 CREATE EDGE {edge}，等待 schema 传播 15s ...")
    time.sleep(15)


# ---------- ETL: Paper → Paper ----------


def load_paper_paper(
    client: TRSGraphClient, session, kind: str, limit: int, batch_size: int, max_workers: int
) -> int:
    """RELATED_TO / CITES / CITED_BY：Paper → Paper。"""
    cfg = PAPER_PAPER_CONFIG[kind]
    tables = PAPER_PAPER_TABLES[kind]
    edge = cfg["edge"]
    prefix = cfg["prefix"]
    source = cfg["source"]
    field = cfg["field"]

    edges: list[tuple[str, str, str]] = []
    for tbl in tables:
        sql = f"SELECT id, doi FROM {tbl} WHERE doi IS NOT NULL AND doi != ''"
        if limit:
            sql += f" LIMIT {int(limit)}"
        for r in session.execute(text(sql)).all():
            src_id = source_paper_id(r[0])
            doi = r[1]
            if not src_id or not doi:
                continue
            edges.append((f"paper_{src_id}", md5_vid(prefix, doi, short=True), doi))
    logger.info(f"  {edge} 待写边: {len(edges)} 条")

    existing = fetch_existing_vids(client, prefix)
    logger.info(f"  {edge} 已有 {prefix}_ 桩: {len(existing)} 个")
    new_stubs: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for _src, dst, doi in edges:
        if dst in existing or dst in seen:
            continue
        seen.add(dst)
        new_stubs.append((dst, doi, source))
    logger.info(f"  {edge} 需新建桩: {len(new_stubs)} 个")
    if new_stubs:
        run_batches(
            new_stubs,
            lambda b: batch_insert_vertex(client, "Paper", ["doi", "source"], b),
            f"{edge}-stub",
            batch_size,
            max_workers,
        )

    run_batches(
        edges,
        lambda b: batch_insert_edge(client, edge, [field] if field else [], b),
        f"{edge}-edge",
        batch_size,
        max_workers,
    )
    logger.info(f"  {edge} 完成, 边总数: {len(edges)}")
    return len(edges)


# ---------- ETL: Paper → Keyword (HAS_KEYWORD) ----------


def parse_keywords(raw: str, lang: str) -> list[str]:
    """zh: 逗号分隔；en: JSON 数组。返回去空、去重的关键词列表。"""
    if not raw:
        return []
    kws: list[str] = []
    if lang == "en":
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                kws = [str(x).strip() for x in data if x]
            elif isinstance(data, str):
                kws = [data.strip()]
        except (json.JSONDecodeError, TypeError):
            kws = [s.strip() for s in raw.split(",") if s.strip()]
    else:
        kws = [s.strip() for s in raw.split(",") if s.strip()]
    # 去重保序
    seen: set[str] = set()
    out: list[str] = []
    for k in kws:
        if k and k not in seen:
            seen.add(k)
            out.append(k)
    return out


def load_has_keyword(
    client: TRSGraphClient, session, limit: int, batch_size: int, max_workers: int
) -> int:
    """HAS_KEYWORD：Paper → Keyword。"""
    # 1) 读源数据，展开成 (paper_vid, keyword, keyword_vid, source_table, source_record_id)
    edges: list[tuple[str, str, str, str, str]] = []
    for tbl, lang in [
        ("dwd_zh_paper_classification", "zh"),
        ("dwd_en_paper_classification", "en"),
    ]:
        sql = f"SELECT id, keywords FROM {tbl} WHERE keywords IS NOT NULL AND keywords != ''"
        if limit:
            sql += f" LIMIT {int(limit)}"
        for r in session.execute(text(sql)).all():
            src_id = source_paper_id(r[0])
            if not src_id:
                continue
            for kw in parse_keywords(r[1], lang):
                edges.append((f"paper_{src_id}", kw, md5_vid("keyword", kw), tbl, str(r[0])))
    logger.info(f"  HAS_KEYWORD 待写边: {len(edges)} 条")

    # 2) 建新 Keyword 桩（跳过已存在，绝不覆盖）
    existing = fetch_existing_vids(client, "keyword")
    logger.info(f"  已有 keyword_ 顶点: {len(existing)} 个")
    new_kw: list[tuple[str, str]] = []
    seen: set[str] = set()
    for _src, kw, kw_vid, _t, _r in edges:
        if kw_vid in existing or kw_vid in seen:
            continue
        seen.add(kw_vid)
        new_kw.append((kw_vid, kw))
    logger.info(f"  需新建 Keyword 桩: {len(new_kw)} 个")
    if new_kw:
        run_batches(
            new_kw,
            lambda b: batch_insert_vertex(client, "Keyword", ["keyword"], b),
            "keyword-stub",
            batch_size,
            max_workers,
        )

    # 3) 写 HAS_KEYWORD 边（带溯源属性，与已有 HAS_KEYWORD schema 一致）
    fields = ["source_table", "source_record_id", "ingest_batch", "ingest_time"]
    rows = [
        (src, kw_vid, tbl, rid, INGEST_BATCH, INGEST_TIME) for src, _kw, kw_vid, tbl, rid in edges
    ]
    run_batches(
        rows,
        lambda b: batch_insert_edge(client, "HAS_KEYWORD", fields, b),
        "HAS_KEYWORD-edge",
        batch_size,
        max_workers,
    )
    logger.info(f"  HAS_KEYWORD 完成, 边总数: {len(edges)}")
    return len(edges)


# ---------- ETL: Paper → Report (REFERENCED_BY) ----------


def load_paper_report(
    client: TRSGraphClient, session, limit: int, batch_size: int, max_workers: int
) -> int:
    """REFERENCED_BY：Paper → Report（论文被报告引用）。源 paper 不在库内，建占位桩。"""
    ensure_edge_type(client, "REFERENCED_BY")  # 无属性

    # 1) 读 dwd_zh_report_paper，展开 report_id JSON 数组
    edges: list[tuple[str, str]] = []  # (src_paper_rp_vid, dst_report_vid)
    src_meta: dict[str, tuple[str, str]] = {}  # vid -> (doi, name)
    sql = "SELECT paper_id, paper_doi, paper_name, report_id FROM dwd_zh_report_paper"
    if limit:
        sql += f" LIMIT {int(limit)}"
    for r in session.execute(text(sql)).all():
        pid = r[0]
        if not pid:
            continue
        src_vid = f"paper_rp_{pid}"
        src_meta[src_vid] = (r[1] or "", (r[2] or "")[:200])
        try:
            rids = json.loads(r[3]) if r[3] else []
        except (json.JSONDecodeError, TypeError):
            rids = []
        if isinstance(rids, str):
            rids = [rids]
        for rid in rids:
            if rid:
                edges.append((src_vid, f"report_{rid}"))
    logger.info(f"  REFERENCED_BY 待写边: {len(edges)} 条, 源论文桩: {len(src_meta)} 个")

    # 2) 建新源论文桩（paper_rp_ 命名空间，跳过已存在，绝不覆盖真实 paper_{id}）
    existing = fetch_existing_vids(client, "paper_rp")
    new_stubs = [
        (vid, doi, "report_paper") for vid, (doi, _name) in src_meta.items() if vid not in existing
    ]
    logger.info(f"  需新建 paper_rp_ 源桩: {len(new_stubs)} 个")
    if new_stubs:
        run_batches(
            new_stubs,
            lambda b: batch_insert_vertex(client, "Paper", ["doi", "source"], b),
            "paper_rp-stub",
            batch_size,
            max_workers,
        )

    # 3) 写 REFERENCED_BY 边（无属性）
    run_batches(
        edges,
        lambda b: batch_insert_edge(client, "REFERENCED_BY", [], b),
        "REFERENCED_BY-edge",
        batch_size,
        max_workers,
    )
    logger.info(f"  REFERENCED_BY 完成, 边总数: {len(edges)}")
    return len(edges)


# ---------- 入口 ----------


def main() -> None:
    limit = int(os.getenv("PAPER_LIMIT", "0") or "0")
    batch_size = int(os.getenv("BATCH_SIZE", "500") or "500")
    max_workers = int(os.getenv("MAX_WORKERS", "8") or "8")
    kinds = [t.strip() for t in os.getenv("RELATION_TYPES", "").split(",") if t.strip()] or [
        "related",
        "cites",
        "cited_by",
        "has_keyword",
        "paper_report",
    ]

    logger.info(
        f"=== 论文关系抽取 ETL (space={SPACE}, limit={limit or '全量'}, "
        f"batch={batch_size}, workers={max_workers}, types={kinds}) ==="
    )

    graph = get_graph_client()
    mysql = get_mysql_client()
    with mysql.session_scope() as session:
        step = 0
        for kind in kinds:
            step += 1
            if kind in PAPER_PAPER_CONFIG:
                logger.info(f"\n{step}. {PAPER_PAPER_CONFIG[kind]['edge']} (Paper→Paper)")
                load_paper_paper(graph, session, kind, limit, batch_size, max_workers)
            elif kind == "has_keyword":
                logger.info(f"\n{step}. HAS_KEYWORD (Paper→Keyword)")
                load_has_keyword(graph, session, limit, batch_size, max_workers)
            elif kind == "paper_report":
                logger.info(f"\n{step}. REFERENCED_BY (Paper→Report)")
                load_paper_report(graph, session, limit, batch_size, max_workers)
            else:
                logger.warning(f"  未知关系类型 {kind}，跳过")

    logger.info("\n=== 抽取后 dev 空间边数（MATCH 实测）===")
    for edge in ["RELATED_TO", "CITES", "CITED_BY", "HAS_KEYWORD", "REFERENCED_BY"]:
        try:
            r = graph.execute_read(f"USE {SPACE}; MATCH ()-[e:{edge}]->() RETURN count(e) AS n;")
            n = r.records[0].get("n") if r.records else "?"
            logger.info(f"  {edge}: {n}")
        except Exception as exc:
            logger.warning(f"  {edge}: 统计失败 {str(exc)[:120]}")
    graph.close()


if __name__ == "__main__":
    main()
