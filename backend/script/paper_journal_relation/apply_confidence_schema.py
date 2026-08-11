"""论文边补 confidence 字段（dev 空间，只动论文域边 schema）。

CITES / HAS_KEYWORD 已有 confidence；本脚本对其余 5 条论文边 ALTER EDGE ADD confidence double。
幂等：DESCRIBE EDGE 先判断字段是否已存在，已有则跳过。

dev 公共空间安全：只 ALTER 论文域边（AUTHORED_BY/PUBLISHED_IN/CITED_BY/RELATED_TO/REFERENCED_BY），
不碰其它域边 schema。ALTER EDGE ADD 是加 nullable 列，不改变现有边数据。

用法：
    cd backend && PYTHONPATH=. .venv/bin/python script/paper_journal_relation/apply_confidence_schema.py
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
# 需要补 confidence 的论文边（CITES/HAS_KEYWORD 已有，跳过）
EDGES_NEED_CONFIDENCE = [
    "AUTHORED_BY",
    "PUBLISHED_IN",
    "CITED_BY",
    "RELATED_TO",
    "REFERENCED_BY",
]


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


def has_confidence(client: TRSGraphClient, edge: str) -> bool:
    try:
        r = client.execute_read(f"USE {SPACE}; DESCRIBE EDGE {edge};")
        return any(rec.get("Field") == "confidence" for rec in r.records)
    except Exception as exc:
        logger.warning("  DESCRIBE EDGE %s 失败: %s", edge, str(exc)[:100])
        return False


def main() -> None:
    client = get_client()
    logger.info("=== 论文边补 confidence 字段（dev，只动论文域边 schema）===")
    for edge in EDGES_NEED_CONFIDENCE:
        if has_confidence(client, edge):
            logger.info("  %s: 已有 confidence，跳过", edge)
            continue
        try:
            client.execute_write(f"USE {SPACE}; ALTER EDGE {edge} ADD (confidence double);")
            logger.info("  %s: ✅ ALTER EDGE ADD confidence", edge)
        except Exception as exc:
            logger.warning("  %s: ALTER 失败: %s", edge, str(exc)[:120])
    # 校验
    logger.info("--- 校验 ---")
    for edge in EDGES_NEED_CONFIDENCE + ["CITES", "HAS_KEYWORD"]:
        logger.info(
            "  %s confidence 字段: %s", edge, "✅" if has_confidence(client, edge) else "❌"
        )
    client.close()


if __name__ == "__main__":
    main()
