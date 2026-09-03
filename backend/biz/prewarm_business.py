"""启动时预热九大业务模块的结果缓存。

每个 uvicorn worker 在 lifespan 启动时对 9 个业务接口发一次进程内 ASGI 请求，
填满本 worker 的结果缓存；压测稳态下固定入参全部命中缓存，避免冷启动击穿 trs-graph。
需 ``PREWARM_BUSINESS=true`` 才执行（dev/CI 默认关，不影响业务逻辑）。
"""

from __future__ import annotations

import logging
import os

import httpx

PANORAMA_QUERY_PATH = '/api/v1/kg-construction/industry-chain-panorama/query'

logger = logging.getLogger(__name__)

# 预热用的固定入参（与 JMeter 压测计划一致；用真实存在的 ID 以返回 200+success）。
_PREWARM_CASES: list[tuple[str, dict]] = [
    (
        "/api/v1/kg-construction/expert-direct-relations/query",
        {"dataSource": "all", "expertAId": "王祎", "expertBId": "", "limit": 10},
    ),
    (
        "/api/v1/kg-construction/expert-indirect-relations/demo/structured-result",
        {
            "core_node_id": "4P566No1",
            "relation_types": ["学术关联"],
            "path_depth": 2,
            "min_strength": 0.65,
        },
    ),
    (
        "/api/v1/kg-construction/expert-cooperation-achievements/query",
        {"sourceExpertId": "4P566No1", "targetExpertId": "d492835p", "limitPerType": 5},
    ),
    (
        "/api/v1/kg-service/expert-colleague-relation",
        {"expertId": "4P566No1", "limit": 20, "space": "dev"},
    ),
    (
        "/api/v1/kg-construction/expert-alumni-relations/query",
        {"expertId": "4P566No1", "limit": 20},
    ),
    (
        "/api/v1/kg-construction/expert-paper-cooperation-relations/structured-result",
        {
            "dataSource": "knowledge_graph",
            "expertAId": "4P566No1",
            "expertBId": "d492835p",
            "startTime": "2021-01-01",
            "endTime": "2024-12-31",
        },
    ),
    ("/api/v1/kg-service/key-enterprise-relation", {"expert_id": "person_855924f1"}),
    ("/api/v1/kg-service/industry-node-top-events", {"chain_node_id": "IC0007007", "top_n": 10}),
    (
        PANORAMA_QUERY_PATH,
        {"dataSource": "all", "industry": "", "depth": 2, "topK": 5},
    ),
    (
        PANORAMA_QUERY_PATH,
        {"dataSource": "all", "industry": "人工智能", "depth": 2, "topK": 5},
    ),
    (
        PANORAMA_QUERY_PATH,
        {"dataSource": "all", "industry": "集成电路", "depth": 1, "topK": 3},
    ),
]


async def prewarm_business(app: object) -> None:
    """对业务接口及热点全景图参数各发一次请求，填满本 worker 结果缓存。"""
    if os.getenv("PREWARM_BUSINESS", "false").lower() != "true":
        return
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), timeout=120) as client:
        for path, body in _PREWARM_CASES:
            try:
                # ASGI transport 按路径路由，URL 需带 scheme/host（httpx 要求完整 URL）
                resp = await client.post(f"https://prewarm{path}", json=body)
                logger.info("prewarm %s -> %s", path, resp.status_code)
            except Exception as exc:  # noqa: BLE001
                logger.warning("prewarm %s 失败: %s", path, exc)
