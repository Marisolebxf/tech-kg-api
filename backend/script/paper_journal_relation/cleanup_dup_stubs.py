"""清除论文域 32 字符 md5 重复桩节点（dev 公共空间，只动论文桩）。

背景（见 paper_journal_relation/README.md「dev 空间当前状态说明」）：一次脚本重写误把
Paper→Paper 目标 vid 改成 32 字符 md5，全量重跑后给 RELATED_TO/CITES/CITED_BY 多建了一套
42 字符桩（前缀 10 + md5 32）+ 重复边。正确集是 26 字符（前缀 10 + md5 16）。

本脚本只删 42 字符重复桩（paper_ref_/paper_cit_/paper_rel_），WITH EDGE 一并删其重复边：
  - 保留 26 字符正确集
  - 保留 paper_rp_（report-paper 源桩，vid 长 41，单集不重复）
  - 保留所有真实 Paper/Person/Journal/Keyword/Report
  - 不碰论文域之外的任何顶点/边（dev 公共空间）

幂等：42 字符桩删完后再跑 MATCH 返回空，DELETE 空集无副作用。

用法：
    cd backend && PYTHONPATH=. .venv/bin/python script/paper_journal_relation/cleanup_dup_stubs.py
"""

from __future__ import annotations

import logging
import os

from infra.graph_db import TRSGraphClient
from infra.graph_db.config import TRSGraphSettings

logging.basicConfig(level=logging.INFO, format="%(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

SPACE = os.getenv("TRS_GRAPH_SPACE", "dev")
# 42 字符重复桩前缀（前缀 10 + md5 32 = 42）
DUP_PREFIXES = ["paper_ref_", "paper_cit_", "paper_rel_"]
DUP_VID_LEN = 42
MATCH_BATCH = 2000
DELETE_BATCH = 500


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


def fetch_dup_vids(client: TRSGraphClient, prefix: str, limit: int) -> list[str]:
    """取一批待删的 42 字符重复桩 vid。"""
    q = (
        f'USE {SPACE}; MATCH (v) WHERE id(v) STARTS WITH "{prefix}" '
        f"AND length(id(v))=={DUP_VID_LEN} RETURN id(v) AS vid LIMIT {limit};"
    )
    r = client.execute_read(q)
    return [str(rec.get("vid")) for rec in r.records if rec.get("vid")]


def delete_vids(client: TRSGraphClient, vids: list[str]) -> None:
    """批量 DELETE VERTEX ... WITH EDGE。"""
    for i in range(0, len(vids), DELETE_BATCH):
        batch = vids[i : i + DELETE_BATCH]
        vid_list = ",".join(f'"{v}"' for v in batch)
        try:
            client.execute_write(f"USE {SPACE}; DELETE VERTEX {vid_list} WITH EDGE;")
        except Exception as exc:
            logger.warning("  DELETE 批失败 (%d): %s", len(batch), str(exc)[:120])


def count_prefix_len(client: TRSGraphClient, prefix: str, vid_len: int) -> int:
    q = (
        f'USE {SPACE}; MATCH (v) WHERE id(v) STARTS WITH "{prefix}" '
        f"AND length(id(v))=={vid_len} RETURN count(*) AS c;"
    )
    r = client.execute_read(q)
    return int(r.records[0].get("c")) if r.records else 0


def main() -> None:
    client = get_client()
    logger.info("=== 清除论文域 42 字符重复桩（dev 空间，只动论文桩）===")
    total_deleted = 0
    for prefix in DUP_PREFIXES:
        before = count_prefix_len(client, prefix, DUP_VID_LEN)
        keep = count_prefix_len(client, prefix, 26)
        logger.info("  %s: 待删 42字符=%d，保留 26字符=%d", prefix, before, keep)
        deleted = 0
        while True:
            vids = fetch_dup_vids(client, prefix, MATCH_BATCH)
            if not vids:
                break
            delete_vids(client, vids)
            deleted += len(vids)
            if deleted % 10000 < MATCH_BATCH:
                logger.info("    %s 进度: %d/%d", prefix, deleted, before)
        after = count_prefix_len(client, prefix, DUP_VID_LEN)
        logger.info("  %s 完成: 删 %d，剩 42字符=%d（应为 0）", prefix, deleted, after)
        total_deleted += deleted

    logger.info("=== 总计删桩 %d 个 ===", total_deleted)
    # 校验论文域边数（应减半，与 26 字符正确集一致）
    for et in ("CITES", "CITED_BY", "RELATED_TO"):
        try:
            r = client.execute_read(f"USE {SPACE}; MATCH ()-[e:{et}]->() RETURN count(*) AS c;")
            logger.info("  边 %s 当前数=%s（删前见基线，应约减半）", et, r.records[0].get("c"))
        except Exception:
            pass
    client.close()


if __name__ == "__main__":
    main()
