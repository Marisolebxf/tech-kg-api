"""示例 step pipeline 脚本。

验证 ``kg.custom.steps`` 流水线 mechanics：4 个 step 函数，每步读上一步输出（ctx.prev_outputs）。
manifest 示例：

    {
      "id": "sample-pipeline",
      "name": "示例 step 流水线",
      "workflowType": "kg.custom.steps",
      "sourceKind": "python",
      "scriptPath": ".../sample_step_pipeline.py",
      "steps": [
        {"id": "load",    "name": "加载",  "functionName": "step_load",    "timeoutSeconds": 30, "retryPolicy": {"maximumAttempts": 2}},
        {"id": "extract", "name": "抽取",  "functionName": "step_extract", "timeoutSeconds": 30, "retryPolicy": {"maximumAttempts": 2}},
        {"id": "align",   "name": "对齐",  "functionName": "step_align",    "timeoutSeconds": 30, "retryPolicy": {"maximumAttempts": 2}},
        {"id": "persist", "name": "落库",  "functionName": "step_persist", "timeoutSeconds": 30, "retryPolicy": {"maximumAttempts": 1}}
      ]
    }

payload 字段（均可选）:
  - items: list[int] — 输入数据，默认 [1, 2, 3]
  - fail_at: str — 在指定 step 抛异常（用于测试 reset 重试）；值为 step id 如 "extract"

审核契约（post-hoc 队列模型）：
  step 函数返回值里若有 ``pendingReview`` 字段（list[dict]），activity 会自动 pop 出来
  逐条写入 ReviewCase 队列（template_id=T_DIRECT），pipeline 不暂停、跑到底。
  下游 step 拿到的 ``ctx.prev_outputs[stepId]`` 已经不含 ``pendingReview``。
  审核者用 ``POST /manual-reviews/production/{caseId}/direct-decide`` 决策：
  accept 直接写图（merge_node/create_edge），reject 丢弃。不重启 workflow。

  pendingReview 每条 item 字段：
    - kind: "entity" | "relation"
    - nodeLabel (entity 用): 图标签
    - edgeType/fromId/toId (relation 用)
    - objectId: 候选唯一 id（去重用）
    - objectName: 显示名
    - candidate: 完整可灌图数据 dict
    - reason: str
    - confidence: float | None
    - evidence: list[dict]
    - sourceRecord: dict | None — 源表完整行（审核页「原始记录」段展示）
    - sourceTable: str | None — 源表名
    - sourceRecordId: str | None — 源记录 ID
    - llmInput: {system: str, user: str} | None — 发给 LLM 的 prompt（审核页「抽取推理过程」段展示）
    - llmOutput: str | None — LLM 返回的原始 JSON 字符串

  sourceRecord / llmInput / llmOutput 是可选的——step 没调 LLM / 没读源表时留空，
  审核页对应段显示「暂无数据」占位。

注意：stdout 必须只输出最终 JSON（runner 据此解析结果），日志一律走 stderr。
"""

from __future__ import annotations

import json
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


def _read_source_record(mysql: Any, item_id: int) -> dict[str, Any] | None:
    """从 dwd_sample_source 读 item_id 对应的完整行。表不存在 / 记录缺失 / 查询失败都返回 None。"""
    try:
        from sqlalchemy import text

        with mysql.session_scope() as session:
            row = session.execute(
                text("SELECT * FROM dwd_sample_source WHERE id = :id"),
                {"id": item_id},
            ).mappings().first()
            if row is None:
                logger.warning("dwd_sample_source id=%s not found", item_id)
                return None
            return dict(row)
    except Exception as exc:  # noqa: BLE001
        logger.warning("read dwd_sample_source id=%s failed: %s", item_id, exc)
        return None


SYSTEM_PROMPT = (
    "你是一个知识图谱抽取助手。从源记录中抽取实体和关系，输出 JSON。"
    "每个候选必须包含 confidence 字段（0-1），表示你对这次抽取的把握程度。"
    "低于 0.85 的候选会进入人工审核队列，由人工决定是否写图。"
)


def _build_user_message(item_id: int, source_record: dict[str, Any]) -> str:
    return (
        f"源表: dwd_sample_source\n记录 ID: {item_id}\n\n"
        f"记录内容:\n{json.dumps(source_record, ensure_ascii=False, indent=2)}\n\n"
        f"请抽取 Paper 实体，输出 JSON。"
    )


def _parse_llm_entity(llm_output: str | None) -> dict[str, Any]:
    """从 LLM 输出里抽取实体 properties（title/authors/etc，不含 confidence）。

    兼容格式：bare array / {entities:[...]} / {entity:{type,id,properties},confidence} / bare dict。
    不带 confidence——保留 step 硬编码值作为审核触发置信度。
    """
    if not llm_output:
        return {}
    raw = llm_output.strip()
    if raw.startswith("```"):
        first_nl = raw.find("\n")
        raw = raw[first_nl + 1 :] if first_nl > 0 else raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3]
        raw = raw.strip()
    try:
        parsed = json.loads(raw)
    except Exception:  # noqa: BLE001
        return {}

    entities: list[dict] = []
    if isinstance(parsed, list):
        entities = [e for e in parsed if isinstance(e, dict)]
    elif isinstance(parsed, dict):
        if isinstance(parsed.get("entities"), list):
            entities = [e for e in parsed["entities"] if isinstance(e, dict)]
        elif isinstance(parsed.get("entity"), dict):
            entities = [parsed["entity"]]
        else:
            entities = [parsed]

    for entity in entities:
        props = entity.get("properties")
        if isinstance(props, dict) and props:
            return {k: v for k, v in props.items() if k != "confidence"}

    for entity in entities:
        if isinstance(entity, dict) and any(k for k in entity if not k.startswith("_")):
            return {k: v for k, v in entity.items() if k != "confidence"}

    return {}


def step_load(payload: dict[str, Any], ctx: Any) -> dict[str, Any]:
    _configure_logging()
    logger.info("step_load start attempt=%s", ctx.attempt)
    _fail_if_requested(payload, "load")
    items = payload.get("items", [1, 2, 3])
    return {"loaded": list(items), "count": len(items)}


def step_extract(payload: dict[str, Any], ctx: Any) -> dict[str, Any]:
    """抽取候选实体；item == 2 模拟低置信度，抛到 pendingReview 队列。

    如果 ctx.mysql + ctx.llm 可用，读真实源记录 + 调真实 LLM，pendingReview item 带
    sourceRecord / llmInput / llmOutput，审核页能展示完整推理链。
    否则降级到硬编码 candidate（无推理链字段，审核页显示占位）。
    """
    _configure_logging()
    logger.info("step_extract start attempt=%s prev=%s", ctx.attempt, list(ctx.prev_outputs))
    _fail_if_requested(payload, "extract")
    prev = ctx.prev_outputs.get("load", {})
    items = prev.get("loaded", [])
    extracted, pending = [], []

    mysql = ctx.mysql
    llm = ctx.llm

    for item_id in items:
        # item == 2 演示低置信度候选：不进入下游，抛到审核队列
        confidence = 0.78 if item_id == 2 else 0.95
        candidate = {"id": item_id, "name": f"entity-{item_id}", "confidence": confidence}
        if confidence >= 0.85:
            extracted.append(candidate)
            continue

        item: dict[str, Any] = {
            "kind": "entity",
            "nodeLabel": "Paper",
            "objectId": f"P-{item_id}",
            "objectName": f"entity-{item_id}",
            "candidate": candidate,
            "reason": f"置信度 {confidence} < 0.85，需人工确认",
            "confidence": confidence,
            "evidence": [
                {
                    "table": "dwd_sample_source",
                    "record_id": str(item_id),
                    "field": "confidence",
                    "raw": str(confidence),
                }
            ],
        }

        # 有 MySQL + LLM 时读真实源记录 + 调 LLM，填充推理链字段供审核页展示
        if mysql is not None and llm is not None:
            source_record = _read_source_record(mysql, item_id)
            if source_record is not None:
                user_message = _build_user_message(item_id, source_record)
                llm_output = llm.synthesize(f"{SYSTEM_PROMPT}\n\n{user_message}")
                item["sourceRecord"] = source_record
                item["sourceTable"] = "dwd_sample_source"
                item["sourceRecordId"] = str(item_id)
                item["llmInput"] = {"system": SYSTEM_PROMPT, "user": user_message}
                item["llmOutput"] = llm_output
                # 用 LLM 抽取的 properties 覆盖硬编码 candidate，让审核页 ③ 段显示真实实体字段
                props = _parse_llm_entity(llm_output)
                if props:
                    candidate = {**candidate, **props}
                    item["candidate"] = candidate
                    if props.get("title"):
                        item["objectName"] = props["title"]
                logger.info("step_extract enriched item %s with source_record + llm I/O", item_id)

        pending.append(item)

    logger.info("step_extract done: %d approved, %d pending review", len(extracted), len(pending))
    return {"extracted": extracted, "count": len(extracted), "pendingReview": pending}


def step_align(payload: dict[str, Any], ctx: Any) -> dict[str, Any]:
    _configure_logging()
    logger.info("step_align start attempt=%s prev=%s", ctx.attempt, list(ctx.prev_outputs))
    _fail_if_requested(payload, "align")
    prev = ctx.prev_outputs.get("extract", {})
    extracted = prev.get("extracted", [])
    aligned = [{"id": e["id"], "name": e["name"], "aligned": True} for e in extracted]
    return {"aligned": aligned, "skipped": 0}


def step_persist(payload: dict[str, Any], ctx: Any) -> dict[str, Any]:
    _configure_logging()
    logger.info("step_persist start attempt=%s prev=%s", ctx.attempt, list(ctx.prev_outputs))
    _fail_if_requested(payload, "persist")
    prev = ctx.prev_outputs.get("align", {})
    aligned = prev.get("aligned", [])
    return {"persisted": len(aligned), "status": "ok"}
