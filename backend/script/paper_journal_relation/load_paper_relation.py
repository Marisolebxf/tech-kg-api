"""论文/期刊 实体关系抽取 ETL。

从 gkx_element 的论文关系表抽取「从论文出发」的有向边（Paper → Paper），
INSERT 到 TRSGraph 的 dev 图空间，把已存在的 Paper 实体联系起来。

抽取的关系（均为 Paper → Paper，符合「只做从自己负责业务领域出发的关系」要求）：
    - RELATED_TO : dwd_zh_paper_related / dwd_en_paper_related      相关论文
    - CITES      : dwd_zh_paper_reference / dwd_en_paper_reference  参考文献论文
    - CITED_BY   : dwd_zh_paper_citation / dwd_en_paper_citation    被引论文

VID 与属性约定（与 dev 空间已存在数据保持一致）：
    - 源端 vid = `paper_{id}`，id 去掉关系表行号后缀 `__N`，连到真实 Paper 顶点。
    - 目标端 vid = `paper_{ref|cit|rel}_{md5(doi)[:16]}`，与真实论文 `paper_{id}`
      命名空间隔离；doi 多数不在库内，按本体设计「先直接抽、不对齐消歧」建占位 Paper 桩。
    - 占位桩属性：Paper.doi = doi，Paper.source = reference/citation/related
      （与已有 CITES/CITED_BY 桩的 source 取值一致）。
    - 边属性只写该边类型 schema 中已存在的列：
      CITES.reference_identifier / CITED_BY.citation_identifier；RELATED_TO 无属性。

安全约束（重要）：
    1. 只 INSERT / UPSERT，绝不 DELETE / ALTER 任何已有点边或 schema。
    2. 写边前先查出已存在的目标桩 vid 集合，只对「不存在」的桩做 INSERT VERTEX，
       已有桩一律不触碰（连属性都不覆盖），彻底避免修改既有数据。
    3. 边用多值 INSERT EDGE（rank@0），同 (src,dst,@0) 重复插入为幂等覆盖，属性值相同不丢数据。

用法：
    cd backend && PYTHONPATH=. .venv/bin/python script/paper_journal_relation/load_paper_relation.py

可选环境变量：
    PAPER_LIMIT     限制每张表抽取的行数（调试用，空=全量）
    BATCH_SIZE      单条 nGQL 多值 INSERT 的批量（默认 500）
    MAX_WORKERS     并发线程数（默认 8）
    RELATION_TYPES  逗号分隔，取值 related/cites/cited_by，控制只跑某几类（默认全跑）
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote_plus

from sqlalchemy import text

from infra.graph_db import TRSGraphClient
from infra.graph_db.config import TRSGraphSettings
from infra.mysql import MySQLClient

logging.basicConfig(level=logging.INFO, format="%(message)s")
# 抑制 httpx 逐请求日志，避免刷屏
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

SPACE = "dev"
_SUFFIX_RE = re.compile(r"__\d+$")

# 关系类型配置：边名 / 目标 vid 前缀 / 桩 source 值 / 边属性列
RELATION_CONFIG = {
    "related": {
        "edge": "RELATED_TO",
        "prefix": "paper_rel",
        "source": "related",
        "field": None,  # 无属性
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

# 每个关系类型对应的源表
RELATION_TABLES = {
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


def target_vid(prefix: str, doi: str) -> str:
    """目标占位桩 vid：`{prefix}_{md5(doi)[:16]}`，与 dev 已有 CITES/CITED_BY 桩一致。"""
    return f"{prefix}_{hashlib.md5(doi.encode()).hexdigest()[:16]}"


def fetch_existing_target_vids(client: TRSGraphClient, prefix: str) -> set[str]:
    """查出 dev 中已存在的某前缀目标桩 vid，写边时跳过这些桩、绝不覆盖。"""
    existing: set[str] = set()
    try:
        r = client.execute_read(
            f'USE {SPACE}; MATCH (v:Paper) WHERE id(v) STARTS WITH "{prefix}_" RETURN id(v) AS vid;'
        )
        for rec in r.records:
            vid = rec.get("vid")
            if vid:
                existing.add(str(vid))
    except Exception as exc:
        logger.warning(f"  查询已有 {prefix}_ 桩失败（按空集处理）: {exc}")
    return existing


def batch_insert_vertex(
    client: TRSGraphClient, rows: list[tuple[str, str, str]], source: str
) -> bool:
    """多值 INSERT VERTEX Paper(doi,source)。rows=[(vid, doi, source)]。仅用于「新」桩。"""
    if not rows:
        return True
    values = ",".join(f"{esc(vid)}:({esc(doi)},{esc(source)})" for vid, doi, _ in rows)
    ngql = f"USE {SPACE}; INSERT VERTEX Paper(doi,source) VALUES {values};"
    try:
        client.execute_write(ngql)
        return True
    except Exception as exc:
        logger.warning(f"  批量建桩失败 ({len(rows)} 条): {str(exc)[:160]}")
        return False


def batch_insert_edge(
    client: TRSGraphClient, edge: str, field: str | None, rows: list[tuple]
) -> bool:
    """多值 INSERT EDGE（rank@0，幂等）。rows=[(src, dst, doi)]，doi 仅在有 field 时用。"""
    if not rows:
        return True
    field_part = f"({field})" if field else ""
    if field:
        values = ",".join(f"{esc(src)}->{esc(dst)}:({esc(doi)})" for src, dst, doi in rows)
    else:
        values = ",".join(f"{esc(src)}->{esc(dst)}:()" for src, dst, _ in rows)
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


# ---------- ETL 各步骤 ----------


def load_relation(
    client: TRSGraphClient, session, kind: str, limit: int, batch_size: int, max_workers: int
) -> int:
    """抽取一类关系：建新桩 + 写边。返回写入边数。"""
    cfg = RELATION_CONFIG[kind]
    tables = RELATION_TABLES[kind]
    edge = cfg["edge"]
    prefix = cfg["prefix"]
    source = cfg["source"]
    field = cfg["field"]

    # 1) 读源数据
    edges: list[tuple[str, str, str]] = []  # (src_vid, dst_vid, doi)
    for tbl in tables:
        sql = f"SELECT id, doi FROM {tbl} WHERE doi IS NOT NULL AND doi != ''"
        if limit:
            sql += f" LIMIT {int(limit)}"
        rows = session.execute(text(sql)).all()
        for r in rows:
            src_id = source_paper_id(r[0])
            doi = r[1]
            if not src_id or not doi:
                continue
            edges.append((f"paper_{src_id}", target_vid(prefix, doi), doi))
    logger.info(f"  {edge} 待写边: {len(edges)} 条")

    # 2) 建新桩（跳过已存在的，绝不覆盖已有数据）
    existing = fetch_existing_target_vids(client, prefix)
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
        stub_ok = run_batches(
            new_stubs,
            lambda b: batch_insert_vertex(client, b, source),
            f"{edge}-stub",
            batch_size,
            max_workers,
        )
        logger.info(f"  {edge} 建桩批成功: {stub_ok}")

    # 3) 写边（多值 INSERT EDGE，幂等）
    edge_ok = run_batches(
        edges,
        lambda b: batch_insert_edge(client, edge, field, b),
        f"{edge}-edge",
        batch_size,
        max_workers,
    )
    logger.info(f"  {edge} 写边批成功: {edge_ok}, 边总数: {len(edges)}")
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
    ]

    logger.info(
        f"=== 论文关系抽取 ETL (space={SPACE}, limit={limit or '全量'}, "
        f"batch={batch_size}, workers={max_workers}, types={kinds}) ==="
    )

    graph = get_graph_client()
    mysql = get_mysql_client()
    with mysql.session_scope() as session:
        for idx, kind in enumerate(kinds, 1):
            logger.info(f"\n{idx}. {RELATION_CONFIG[kind]['edge']}")
            load_relation(graph, session, kind, limit, batch_size, max_workers)

    logger.info("\n=== 抽取后 dev 空间边数（FETCH 实测，非 stats 缓存）===")
    for kind in kinds:
        edge = RELATION_CONFIG[kind]["edge"]
        try:
            r = graph.execute_read(f"USE {SPACE}; MATCH ()-[e:{edge}]->() RETURN count(e) AS n;")
            n = r.records[0].get("n") if r.records else "?"
            logger.info(f"  {edge}: {n}")
        except Exception as exc:
            logger.warning(f"  {edge}: 统计失败 {str(exc)[:120]}")
    graph.close()


if __name__ == "__main__":
    main()
