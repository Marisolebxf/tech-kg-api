"""Manual-review pipeline contract, dynamic templates, state rules and RBAC."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any


class ReviewConflictError(RuntimeError):
    pass


class ReviewForbiddenError(PermissionError):
    pass


class ReviewValidationError(ValueError):
    pass


@dataclass(frozen=True)
class ReviewIdentity:
    user_id: str
    user_name: str
    roles: frozenset[str]
    domains: frozenset[str]
    organization: str
    request_id: str

    def has_any(self, *roles: str) -> bool:
        return bool(self.roles.intersection(roles))


PIPELINE_STEPS = {
    "source": {"name": "数据接入", "phase": "数据处理", "templates": {"T_RUNTIME"}},
    "normalize": {
        "name": "清洗标准化",
        "phase": "数据处理",
        "templates": {"T_MAP", "T_DQ_FILL", "T_DQ_MERGE", "T_RUNTIME"},
    },
    "schema": {"name": "Schema 映射", "phase": "图谱构建", "templates": {"T_MAP", "T_RUNTIME"}},
    "extract": {"name": "实体关系抽取", "phase": "图谱构建", "templates": {"T_RUNTIME"}},
    "align": {"name": "实体对齐消歧", "phase": "图谱构建", "templates": {"T_LINK", "T_RUNTIME"}},
    "validate": {
        "name": "规则与证据校验",
        "phase": "图谱构建",
        "templates": {"T_EVIDENCE", "T_ATTR", "T_RUNTIME"},
    },
    "persist": {"name": "图谱入库", "phase": "图谱构建", "templates": {"T_RUNTIME"}},
}
TEMPLATE_ALIASES = {"T_ENTITY": "T_LINK", "T_RELATION": "T_EVIDENCE"}
TEMPLATES: dict[str, dict[str, Any]] = {
    "T_MAP": {
        "title": "选值映射",
        "actions": {"save-map-rerun", "confirm-type", "rollback-dict", "reject-upstream"},
        "adapter": "mapping",
        "components": [{"type": "mapping-table", "source": "data.candidate.mappings"}],
    },
    "T_DQ_FILL": {
        "title": "必填补全",
        "actions": {"save-fill-rerun", "discard-record", "reject-upstream"},
        "adapter": "data-quality-fill",
        "components": [{"type": "field-editor", "source": "data.candidate.missingFields"}],
    },
    "T_DQ_MERGE": {
        "title": "重复定主",
        "actions": {"merge-rerun", "isolate-dup", "reject-upstream"},
        "adapter": "data-quality-merge",
        "components": [{"type": "record-merge", "source": "data.candidate.records"}],
    },
    "T_LINK": {
        "title": "实体对齐裁决",
        "actions": {"entity-confirm", "reject-candidate"},
        "adapter": "entity-link",
        "components": [
            {
                "type": "entity-comparison",
                "source": "data.candidate",
                "target": "data.candidate.existingCandidates",
            }
        ],
    },
    "T_EVIDENCE": {
        "title": "关系证据审核",
        "actions": {"pass-rerun", "keep-isolated", "reject-extract", "force-pass"},
        "adapter": "relation-evidence",
        "components": [{"type": "evidence-list", "source": "data.evidence"}],
    },
    "T_ATTR": {
        "title": "属性对照",
        "actions": {"confirm-attr", "reject-upstream"},
        "adapter": "attribute",
        "components": [{"type": "attribute-comparison", "source": "data.candidate.conflicts"}],
    },
    "T_RUNTIME": {
        "title": "运行处置",
        "actions": {"rerun-batch", "retry-task", "skip-task", "escalate"},
        "adapter": "runtime",
        "components": [{"type": "runtime-config", "source": "data.candidate.runtime"}],
    },
}
RESULT_SCHEMAS: dict[str, dict[str, Any]] = {
    "T_MAP": {
        "type": "object",
        "properties": {"mappings": {"type": "array"}, "entityType": {"type": "string"}},
    },
    "T_DQ_FILL": {"type": "object", "properties": {"fields": {"type": "object"}}},
    "T_DQ_MERGE": {
        "type": "object",
        "required": ["mergeMaster"],
        "properties": {"mergeMaster": {"type": ["string", "integer"]}},
    },
    "T_LINK": {
        "type": "object",
        "required": ["entityVerdict"],
        "properties": {
            "entityVerdict": {"enum": ["merge", "create", "retype"]},
            "targetEntityId": {"type": "string"},
        },
    },
    "T_EVIDENCE": {"type": "object", "properties": {"evidence": {"type": "array"}}},
    "T_ATTR": {
        "type": "object",
        "properties": {"fields": {"type": "object"}, "attrVerdict": {"type": "string"}},
    },
    "T_RUNTIME": {
        "type": "object",
        "properties": {"runtimeConfig": {"type": ["object", "string"]}},
    },
}

HIGH_RISK_ACTIONS = {"force-pass", "rollback-dict", "skip-task"}
TERMINAL_STATUSES = {"RESOLVED", "REJECTED", "CANCELLED", "EXPIRED"}
EDITABLE_STATUSES = {"CLAIMED", "IN_REVIEW"}
EVENT_STAGE = {
    "CORRECTION_ACCEPTED": 1,
    "RERUN_STARTED": 2,
    "RERUN_PROGRESS": 2,
    "RERUN_SUCCEEDED": 3,
    "RERUN_FAILED": 3,
    "VERIFICATION_SUCCEEDED": 4,
    "VERIFICATION_FAILED": 4,
}


def canonical_template(value: str) -> str:
    return TEMPLATE_ALIASES.get(value, value)


def choose_template(error_type: str, node_id: str = "", object_type: str = "") -> str:
    text = f"{error_type} {node_id} {object_type}"
    if "映射" in text or "类型判断" in text or "标准化失败" in text:
        return "T_MAP"
    if any(x in text for x in ("实体重复", "实体类型", "实体置信", "实体对齐", "对齐歧义")):
        return "T_LINK"
    if "关系" in text and any(x in text for x in ("证据", "置信", "类型")):
        return "T_EVIDENCE"
    if "属性冲突" in text:
        return "T_ATTR"
    if "缺失" in text:
        return "T_DQ_FILL"
    if "唯一性" in text or "重复记录" in text:
        return "T_DQ_MERGE"
    return "T_RUNTIME"


def validate_step_template(step_id: str, template_id: str) -> str:
    if step_id not in PIPELINE_STEPS:
        raise ReviewValidationError(f"非法 pipeline stepId: {step_id}")
    template_id = canonical_template(template_id)
    if template_id not in TEMPLATES:
        raise ReviewValidationError(f"未知审核模板: {template_id}")
    if template_id not in PIPELINE_STEPS[step_id]["templates"]:
        raise ReviewValidationError(f"模板 {template_id} 不适用于节点 {step_id}")
    return template_id


def risk_policy(error_type: str, scope_hint: str | None = None, severity: str | None = None):
    t = datetime.now(UTC).replace(tzinfo=None)
    scope = "批次级" if scope_hint in ("batch", "BATCH", "REVIEW_BATCH") else "任务级"
    risk = (
        severity
        if severity in ("P0", "P1", "P2")
        else (
            "P0"
            if scope == "批次级"
            else "P1"
            if any(x in error_type for x in ("冲突", "不足", "缺失", "失败", "超时"))
            else "P2"
        )
    )
    if risk == "P0":
        return risk, scope, t + timedelta(minutes=15), t + timedelta(minutes=30)
    if risk == "P1":
        return risk, scope, t + timedelta(hours=1), t + timedelta(hours=4)
    return risk, scope, t + timedelta(hours=4), t + timedelta(days=1)


def validate_action(template_id: str, action_id: str, result: dict[str, Any]) -> None:
    tid = canonical_template(template_id)
    template = TEMPLATES.get(tid)
    if not template or action_id not in template["actions"]:
        raise ReviewValidationError(f"动作 {action_id} 不适用于模板 {tid}")
    if action_id in {"save-map-rerun", "rollback-dict"} and not result.get("mappings"):
        raise ReviewValidationError("映射修复必须包含 mappings")
    if action_id == "confirm-type" and not result.get("entityType"):
        raise ReviewValidationError("类型修正必须包含 entityType")
    if action_id == "entity-confirm":
        verdict = result.get("entityVerdict")
        if verdict not in {"merge", "create", "retype"}:
            raise ReviewValidationError("实体裁决必须指定 merge/create/retype")
        if verdict == "merge" and not result.get("targetEntityId"):
            raise ReviewValidationError("实体合并必须指定 targetEntityId")
    if (
        action_id == "pass-rerun"
        and len([x for x in result.get("evidence", []) if x.get("checked", True)]) < 2
    ):
        raise ReviewValidationError("关系确认至少需要两个独立证据")
    if action_id == "save-fill-rerun" and not (result.get("titleZh") or result.get("fields")):
        raise ReviewValidationError("补录必须包含修正字段")
    if action_id == "merge-rerun" and not str(result.get("mergeMaster", "")).strip():
        raise ReviewValidationError("重复记录合并必须指定主记录")
    if action_id == "confirm-attr" and not (result.get("fields") or result.get("attrVerdict")):
        raise ReviewValidationError("属性裁决必须包含选值或人工值")
    if result.get("rerunStepId"):
        raise ReviewValidationError("rerunStepId 由服务端决定，客户端不得覆盖")


def template_contract(template_id: str) -> dict[str, Any]:
    tid = canonical_template(template_id)
    t = TEMPLATES[tid]
    return {
        "id": tid,
        "version": "1.0",
        "title": t["title"],
        "displaySchema": {"sections": t["components"]},
        "resultSchema": RESULT_SCHEMAS[tid],
        "allowedActions": sorted(t["actions"]),
    }


def rerun_step(step_id: str, action_id: str) -> str:
    return "extract" if action_id == "reject-extract" else step_id


def write_target(template_id: str) -> str:
    return {
        "T_MAP": "Schema 映射/标准字典 correction 层",
        "T_DQ_FILL": "字段补全 correction 层",
        "T_DQ_MERGE": "去重 correction 层",
        "T_LINK": "实体对齐 correction 层",
        "T_EVIDENCE": "候选关系 correction 层",
        "T_ATTR": "属性融合 correction 层",
        "T_RUNTIME": "任务配置 correction 层",
    }[canonical_template(template_id)]


def requires_approval(risk_level: str, action_id: str, result: dict[str, Any]) -> bool:
    return (
        risk_level == "P0" or action_id in HIGH_RISK_ACTIONS or bool(result.get("highValueEntity"))
    )


def require_domain_access(i: ReviewIdentity, d: str) -> None:
    if (
        not i.has_any("review_admin", "auditor", "approver")
        and i.domains
        and "*" not in i.domains
        and d not in i.domains
    ):
        raise ReviewForbiddenError("无权访问该业务域")


def require_role(i: ReviewIdentity, *roles: str) -> None:
    if not i.has_any(*roles, "review_admin"):
        raise ReviewForbiddenError("当前角色无权执行此操作")


def role_can_review(i: ReviewIdentity, phase: str) -> bool:
    return (
        i.has_any("reviewer", "review_admin")
        or (phase == "数据处理" and i.has_any("data_quality_reviewer"))
        or (phase == "图谱构建" and i.has_any("graph_governance_reviewer"))
    )
