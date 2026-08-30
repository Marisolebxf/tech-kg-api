"""把 worker 输出的 stages 归一化为前端可渲染的 ProcessStep 列表。

真实 worker 返回的 ``output.stages`` 是 dict(以 stage 名为 key,如
``{"schema": {"status": "ok"}, "load": {...}, ...}``),不是 list。
``_sync_task_from_execution`` 历史上用 ``isinstance(stages, list)`` 判断,
导致 dict 形式的真实阶段数据永远流不进 ``task["steps"]``。

归一化规则:
- 已知 stage key 走 ``_STAGE_CATALOG`` 拿规范 name/phase/description
- 未知 key 用 raw key 作为 id 和 name,phase 默认"图谱构建"
- 每个字段(status/count/abnormal/duration)从 worker dict 取,缺省填 "-"——不编造
- 输入 None / 非 dict / 无 stages key / 空 stages → 返回 []
"""

from __future__ import annotations

from typing import Any

# 已知 stage key → (canonical_id, name, phase, description)
_STAGE_CATALOG: dict[str, tuple[str, str, str, str]] = {
    # 数据处理
    "source": ("source", "数据接入", "数据处理", "读取业务域增量数据"),
    "normalize": ("normalize", "清洗标准化", "数据处理", "执行字段、枚举和字典标准化"),
    # 图谱构建 canonical 7 步
    "schema": ("schema", "Schema 映射", "图谱构建", "映射实体、关系与属性 Schema"),
    "extract": ("extract", "实体关系抽取", "图谱构建", "运行领域专属实体/关系工作流"),
    "align": ("align", "实体对齐消歧", "图谱构建", "候选实体与存量图谱召回、消歧与合并"),
    "validate": ("validate", "质量校验", "图谱构建", "执行置信度、证据与唯一性校验"),
    "persist": ("persist", "图谱入库", "图谱构建", "幂等写入实体、关系和属性"),
    # worker 实际使用但不在 canonical 7 步内的 key
    "load": ("load", "节点入库", "图谱构建", "将实体节点写入图数据库"),
    "cleanup": ("cleanup", "冗余清理", "图谱构建", "清理无主节点和冗余数据"),
    "backfill_confidence": (
        "backfill_confidence",
        "置信度回填",
        "图谱构建",
        "回填现有节点 confidence 字段",
    ),
}

_DEFAULT_PHASE = "图谱构建"
_DASH = "-"


def _step_from_dict(key: str, value: dict[str, Any]) -> dict[str, Any]:
    catalog_entry = _STAGE_CATALOG.get(key)
    if catalog_entry:
        step_id, name, phase, description = catalog_entry
    else:
        step_id, name, phase, description = key, key, _DEFAULT_PHASE, ""
    return {
        "id": step_id,
        "name": name,
        "phase": phase,
        "description": description,
        "status": value.get("status", _DASH),
        "count": value.get("count", _DASH),
        "abnormal": value.get("abnormal", _DASH),
        "duration": value.get("duration", _DASH),
    }


def normalize_stages(output: dict[str, Any] | None) -> list[dict[str, Any]]:
    """把 worker output 中的 stages(dict 或 list)归一化为 ProcessStep 列表。

    返回 ``[]`` 表示无可用 stages,调用方应保留 task 已有的 steps
    (可能是任务创建时塞的静态模板),不要清空。
    """
    if not isinstance(output, dict):
        return []
    stages = output.get("stages")
    if stages is None:
        return []
    if isinstance(stages, list):
        # 旧 list 形式:透传已经是 ProcessStep 形状的 dict,跳过非 dict 项
        return [s for s in stages if isinstance(s, dict)]
    if isinstance(stages, dict):
        return [
            _step_from_dict(key, value) for key, value in stages.items() if isinstance(value, dict)
        ]
    return []


_STEP_STATUS_LABELS = {
    "COMPLETED": "成功",
    "FAILED": "需人工处理",
}


def pipeline_steps(output: dict[str, Any] | None) -> list[dict[str, Any]]:
    """把 steps/chain 工作流的 ``output.steps`` 映射为保留输入输出的步骤列表。

    与 ``normalize_stages`` 不同：每个步骤原样保留 input/output/error/access JSON
    （任务详情页展示每个 activity step 的真实输入输出）。
    返回 ``[]`` 表示 output 里没有 steps（如 kg.custom.python 单脚本）。
    """
    if not isinstance(output, dict):
        return []
    steps = output.get("steps")
    if not isinstance(steps, dict) or not steps:
        return []
    result = []
    for step_id, state in steps.items():
        if not isinstance(state, dict):
            continue
        raw_status = str(state.get("status", "-"))
        result.append(
            {
                "id": step_id,
                "name": state.get("name") or step_id,
                "phase": "图谱构建",
                "description": "脚本 activity step",
                "status": _STEP_STATUS_LABELS.get(raw_status, "运行中"),
                "rawStatus": raw_status,
                "count": state.get("attempt", "-"),
                "abnormal": "-",
                "duration": "-",
                "input": state.get("input"),
                "output": state.get("output"),
                "error": state.get("error"),
                "access": state.get("access"),
            }
        )
    return result
