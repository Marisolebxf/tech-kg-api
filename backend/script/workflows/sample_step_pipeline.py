"""示例 step pipeline 脚本。

验证 ``kg.custom.steps`` 流水线 mechanics：4 个 step 函数，每步读上一步输出（ctx.prevOutputs），
不依赖任何外部基础设施。manifest 示例：

    {
      "id": "sample-pipeline",
      "name": "示例 step 流水线",
      "workflowType": "kg.custom.steps",
      "sourceKind": "python",
      "scriptPath": ".../sample_step_pipeline.py",
      "steps": [
        {"id": "load",    "name": "加载",  "functionName": "step_load",    "timeoutSeconds": 30, "retryPolicy": {"maximumAttempts": 2}},
        {"id": "extract", "name": "抽取",  "functionName": "step_extract", "timeoutSeconds": 30, "retryPolicy": {"maximumAttempts": 2}},
        {"id": "align",   "name": "对齐",  "functionName": "step_align",    "timeoutSeconds": 30, "retryPolicy": {"maximumAttempts": 2}, "requireReview": true},
        {"id": "persist", "name": "落库",  "functionName": "step_persist", "timeoutSeconds": 30, "retryPolicy": {"maximumAttempts": 1}}
      ]
    }

payload 字段（均可选）:
  - items: list[int] — 输入数据，默认 [1, 2, 3]
  - fail_at: str — 在指定 step 抛异常（用于测试 reset 重试）；值为 step id 如 "extract"

注意：stdout 必须只输出最终 JSON（runner 据此解析结果），日志一律走 stderr。
"""

from __future__ import annotations

import logging
import sys
from typing import Any

logger = logging.getLogger("workflow.sample_step_pipeline")


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def _fail_if_requested(payload: dict[str, Any], step_id: str) -> None:
    fail_at = payload.get("fail_at")
    if fail_at == step_id:
        raise RuntimeError(f"模拟失败：step {step_id} 按 payload.fail_at 抛异常")


def step_load(payload: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    _configure_logging()
    logger.info("step_load start attempt=%s", ctx.get("attempt"))
    _fail_if_requested(payload, "load")
    items = payload.get("items", [1, 2, 3])
    return {"loaded": list(items), "count": len(items)}


def step_extract(payload: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    _configure_logging()
    logger.info(
        "step_extract start attempt=%s prev=%s",
        ctx.get("attempt"),
        list(ctx.get("prevOutputs", {})),
    )
    _fail_if_requested(payload, "extract")
    prev = ctx.get("prevOutputs", {}).get("load", {})
    items = prev.get("loaded", [])
    extracted = [{"id": i, "name": f"entity-{i}"} for i in items]
    return {"extracted": extracted, "count": len(extracted)}


def step_align(payload: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    _configure_logging()
    logger.info(
        "step_align start attempt=%s prev=%s", ctx.get("attempt"), list(ctx.get("prevOutputs", {}))
    )
    _fail_if_requested(payload, "align")
    prev = ctx.get("prevOutputs", {}).get("extract", {})
    extracted = prev.get("extracted", [])
    aligned = [{"id": e["id"], "name": e["name"], "aligned": True} for e in extracted]
    return {"aligned": aligned, "skipped": 0}


def step_persist(payload: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    _configure_logging()
    logger.info(
        "step_persist start attempt=%s prev=%s",
        ctx.get("attempt"),
        list(ctx.get("prevOutputs", {})),
    )
    _fail_if_requested(payload, "persist")
    prev = ctx.get("prevOutputs", {}).get("align", {})
    aligned = prev.get("aligned", [])
    return {"persisted": len(aligned), "status": "ok"}
