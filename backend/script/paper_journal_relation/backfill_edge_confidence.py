"""回填论文域边 confidence 值（dev 公共空间，只动论文域边）。

置信度规则：
  AUTHORED_BY / PUBLISHED_IN / HAS_KEYWORD = 1.0（直接关系）
  CITES / CITED_BY：目标真实 Paper=1.0；指向桩(paper_ref_/paper_cit_)=0.5
  RELATED_TO = 0.7（相关非直接引用）
  REFERENCED_BY = 0.8（报告引用）

实现：MATCH 边 (src,dst) 批量取，UPDATE EDGE ON <type> "src"->"dst"@0 SET confidence=x。
UPDATE EDGE 只改 confidence 不动其它属性。批量 200 条 UPDATE 拼一个 execute_write。

dev 公共空间安全：只 MATCH/UPDATE 论文域边类型，不碰其它域边。
幂等：同值 UPDATE 可重跑。

用法：
    cd backend && PYTHONPATH=. .venv/bin/python script/paper_journal_relation/backfill_edge_confidence.py
"""

from __future__ import annotations

import logging
import os

from infra.graph_db import TRSGraphClient
from infra.graph_db.config import TRSGraphSettings

logging.basicConfig(level=logging.INFO, format="%(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

SPACE = "dev"
MATCH_BATCH = 5000
WRITE_BATCH = 200  # 每个 execute_write 拼 200 条 UPDATE EDGE


def get_client() -> TRSGraphClient:
    s = TRSGraphSettings(
        base_url=os.getenv("TRS_GRAPH_BASE_URL", "http://localhost:8090"),
        space=SPACE,
        api_key=os.getenv("TRS_GRAPH_API_KEY"),
        timeout=int(os.getenv("TRS_GRAPH_TIMEOUT", "120")),
    )
    c = TRSGraphClient(s)
    c.connect()
    return c


def fetch_edges(
    client: TRSGraphClient, edge_type: str, limit: int, offset: int = 0
) -> list[tuple[str, str]]:
    """分页取边 (src, dst)。用 STARTS WITH 谓词避免 OFFSET 大时变慢：按 src 前缀分段不现实，这里用 LIMIT+OFFSET。"""
    q = (
        f"USE {SPACE}; MATCH (s)-[e:{edge_type}]->(d) "
        f"RETURN id(s) AS src, id(d) AS dst SKIP {offset} LIMIT {limit};"
    )
    r = client.execute_read(q)
    return [
        (str(rec.get("src")), str(rec.get("dst")))
        for rec in r.records
        if rec.get("src") and rec.get("dst")
    ]


def update_confidence(
    client: TRSGraphClient,
    edge_type: str,
    edges: list[tuple[str, str]],
    confidence_of,
) -> int:
    """批量 UPDATE EDGE SET confidence。confidence_of(src,dst)->float。"""
    done = 0
    for i in range(0, len(edges), WRITE_BATCH):
        chunk = edges[i : i + WRITE_BATCH]
        stmts = []
        for src, dst in chunk:
            conf = confidence_of(src, dst)
            stmts.append(f'UPDATE EDGE ON {edge_type} "{src}"->"{dst}"@0 SET confidence={conf};')
        try:
            client.execute_write(f"USE {SPACE}; " + " ".join(stmts))
            done += len(chunk)
        except Exception as exc:
            # 整批失败则逐条重试，跳过坏边
            logger.warning("  %s 批失败 (%d)，逐条重试: %s", edge_type, len(chunk), str(exc)[:100])
            for src, dst in chunk:
                conf = confidence_of(src, dst)
                try:
                    client.execute_write(
                        f'USE {SPACE}; UPDATE EDGE ON {edge_type} "{src}"->"{dst}"@0 SET confidence={conf};'
                    )
                    done += 1
                except Exception:
                    pass
        if done % 20000 < WRITE_BATCH:
            logger.info("    %s 进度 %d", edge_type, done)
    return done


def count_edges(client: TRSGraphClient, edge_type: str) -> int:
    try:
        r = client.execute_read(f"USE {SPACE}; MATCH ()-[e:{edge_type}]->() RETURN count(*) AS c;")
        return int(r.records[0].get("c")) if r.records else 0
    except Exception:
        return 0


def main() -> None:
    client = get_client()
    logger.info("=== 回填论文域边 confidence（dev，只动论文域边）===")

    # (edge_type, confidence_of)
    rules = [
        ("AUTHORED_BY", lambda s, d: 1.0),
        ("PUBLISHED_IN", lambda s, d: 1.0),
        ("HAS_KEYWORD", lambda s, d: 1.0),
        ("RELATED_TO", lambda s, d: 0.7),
        ("REFERENCED_BY", lambda s, d: 0.8),
        ("CITES", lambda s, d: 0.5 if d.startswith("paper_ref_") else 1.0),
        ("CITED_BY", lambda s, d: 0.5 if d.startswith("paper_cit_") else 1.0),
    ]

    for edge_type, conf_of in rules:
        total = count_edges(client, edge_type)
        logger.info("  %s: 共 %d 条", edge_type, total)
        done = 0
        offset = 0
        while True:
            edges = fetch_edges(client, edge_type, MATCH_BATCH, offset)
            if not edges:
                break
            done += update_confidence(client, edge_type, edges, conf_of)
            offset += len(edges)
            if len(edges) < MATCH_BATCH:
                break
        logger.info("  %s 完成: 回填 %d", edge_type, done)

    client.close()
    logger.info("=== 边 confidence 回填完成 ===")


if __name__ == "__main__":
    main()
