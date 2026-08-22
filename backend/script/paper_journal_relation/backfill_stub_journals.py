"""补 PUBLISHED_IN 缺口：为论文引用但未入库的期刊建 stub Journal 节点 + 边。

对账发现 en_paper 有 126 个 distinct publication_id 不在 dwd_en_journal（被 1724 篇论文引用），
导致 1724 条 PUBLISHED_IN 边因 journal 端点不存在被 skip。本脚本：
  1. 取这 126 个 publication_id + 论文 publication_en_name（作 journal name_en）
  2. 建 stub Journal 节点 journal_{publication_id}（name_en + source=stub_from_paper）
  3. 挂 organization_base（confidence=0.5 推断期刊，organization_id=publication_id）
  4. 建 1724 条 PUBLISHED_IN 边 paper_{id} -> journal_{publication_id}（confidence=1.0）

dev 公共空间安全：只新增 stub journal 节点 + PUBLISHED_IN 边，不删改现有节点/边。
幂等：INSERT VERTEX/EDGE rank@0 覆盖，可重跑。

用法：
    cd backend && PYTHONPATH=. .venv/bin/python script/paper_journal_relation/backfill_stub_journals.py
"""

from __future__ import annotations

import logging
import os
from urllib.parse import quote_plus

from sqlalchemy import create_engine, text

from infra.graph_db import TRSGraphClient
from infra.graph_db.config import TRSGraphSettings

logging.basicConfig(level=logging.INFO, format="%(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

SPACE = os.getenv("TRS_GRAPH_SPACE", "dev")
BATCH = 200
INGEST_BATCH = "stub_journal_20260812"
INGEST_TIME = "2026-08-12T00:00:00Z"


def get_graph() -> TRSGraphClient:
    s = TRSGraphSettings(
        base_url=os.getenv("TRS_GRAPH_BASE_URL", "http://localhost:8090"),
        space=SPACE,
        api_key=os.getenv("TRS_GRAPH_API_KEY"),
        timeout=int(os.getenv("TRS_GRAPH_TIMEOUT", "120")),
    )
    c = TRSGraphClient(s)
    c.connect()
    return c


def get_mysql_engine():
    url = (
        f"mysql+pymysql://{quote_plus(os.getenv('MYSQL_USERNAME', 'root'))}:"
        f"{quote_plus(os.getenv('MYSQL_PASSWORD', '123456789'))}"
        f"@{os.getenv('MYSQL_HOST', '127.0.0.1')}:{os.getenv('MYSQL_PORT', '3306')}"
        f"/gkx_element?charset=utf8mb4"
    )
    return create_engine(url)


def esc(v) -> str:
    if v is None:
        return '""'
    s = str(v).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ").replace("\r", " ")
    return f'"{s}"'


def main() -> None:
    eng = get_mysql_engine()
    with eng.connect() as c:
        # en_paper publication_id 不在 dwd_en_journal 的 distinct 集合
        rows = c.execute(
            text(
                "SELECT DISTINCT p.publication_id, p.publication_en_name "
                "FROM dwd_en_paper p LEFT JOIN (SELECT DISTINCT publication_id FROM dwd_en_journal) j "
                "ON p.publication_id=j.publication_id "
                "WHERE p.publication_id IS NOT NULL AND j.publication_id IS NULL"
            )
        ).all()
        stubs = [(str(r[0]), r[1] or "") for r in rows if r[0]]
        # 每篇论文的 (paper_id, publication_id) 用于建边
        pubs = c.execute(
            text(
                "SELECT p.id, p.publication_id FROM dwd_en_paper p LEFT JOIN "
                "(SELECT DISTINCT publication_id FROM dwd_en_journal) j ON p.publication_id=j.publication_id "
                "WHERE p.publication_id IS NOT NULL AND j.publication_id IS NULL"
            )
        ).all()
        edges = [(str(r[0]), str(r[1])) for r in pubs if r[0] and r[1]]
    eng.dispose()
    logger.info("待建 stub journal: %d 个，PUBLISHED_IN 边: %d 条", len(stubs), len(edges))

    g = get_graph()

    # 1. stub Journal 节点 + organization_base mixin
    for i in range(0, len(stubs), BATCH):
        chunk = stubs[i : i + BATCH]
        vvals = ",".join(f'"journal_{pid}":({esc(name)}, "stub_from_paper")' for pid, name in chunk)
        try:
            g.execute_write(f"USE {SPACE}; INSERT VERTEX Journal(name_en, source) VALUES {vvals};")
        except Exception as exc:
            logger.warning("  INSERT Journal 失败 (%d): %s", len(chunk), str(exc)[:100])
        # organization_base
        ovals = ",".join(
            f'"journal_{pid}":({esc(pid)},0.5,"gkx_element","dwd_en_paper_inferred",'
            f"{esc(pid)},{esc(INGEST_BATCH)},{esc(INGEST_TIME)})"
            for pid, _ in chunk
        )
        try:
            g.execute_write(
                f"USE {SPACE}; INSERT VERTEX organization_base(organization_id, confidence, "
                f"source_system, source_table, source_record_id, ingest_batch, ingest_time) VALUES {ovals};"
            )
        except Exception as exc:
            logger.warning("  INSERT org_base 失败 (%d): %s", len(chunk), str(exc)[:100])
    logger.info("stub Journal 节点 + org_base 完成")

    # 2. PUBLISHED_IN 边
    for i in range(0, len(edges), BATCH):
        chunk = edges[i : i + BATCH]
        evals = ",".join(f'"paper_{pid}"->"journal_{jid}":(1.0)' for pid, jid in chunk)
        try:
            g.execute_write(f"USE {SPACE}; INSERT EDGE PUBLISHED_IN(confidence) VALUES {evals};")
        except Exception as exc:
            logger.warning("  INSERT PUBLISHED_IN 失败 (%d): %s", len(chunk), str(exc)[:100])
    logger.info("PUBLISHED_IN 边完成")

    # 校验
    r = g.execute_read(f"USE {SPACE}; MATCH ()-[e:PUBLISHED_IN]->() RETURN count(*) AS c;")
    logger.info("PUBLISHED_IN 总边数: %s", r.records[0].get("c"))
    g.close()


if __name__ == "__main__":
    main()
