"""Manual-review pipeline contract, templates, state rules and RBAC."""

from __future__ import annotations

from dataclasses import dataclass
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


# 流水线节点契约（case_dict 的 pipelineStepName 渲染用）。
# 2026-09-15 移交外部 graph-build 服务的通道删除后，只在产活模板的节点标注 templates；
# 其余节点保留名称映射供存量 case 展示。
PIPELINE_STEPS = {
    "source": {"name": "数据接入", "phase": "数据处理", "templates": set()},
    "normalize": {"name": "清洗标准化", "phase": "数据处理", "templates": set()},
    "schema": {"name": "Schema 映射", "phase": "图谱构建", "templates": set()},
    "extract": {
        "name": "实体关系抽取",
        "phase": "图谱构建",
        "templates": {"T_EXTRACT_FAIL"},
    },
    "align": {"name": "实体对齐消歧", "phase": "图谱构建", "templates": {"T_LINK"}},
    "validate": {"name": "规则与证据校验", "phase": "图谱构建", "templates": set()},
    "persist": {"name": "图谱入库", "phase": "图谱构建", "templates": set()},
}
TEMPLATE_ALIASES = {"T_ENTITY": "T_LINK"}
TEMPLATES: dict[str, dict[str, Any]] = {
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
    "T_DIRECT": {
        "title": "kg.custom.steps 候选审核",
        "actions": {"accept", "reject"},
        "adapter": "direct",
        "components": [{"type": "candidate-detail", "source": "data.candidate"}],
    },
    "T_EXTRACT_FAIL": {
        "title": "抽取失败重跑",
        "actions": {"rerun-record", "discard-record"},
        "adapter": "extract-fail",
        "components": [{"type": "record-error", "source": "data.candidate"}],
    },
}
RESULT_SCHEMAS: dict[str, dict[str, Any]] = {
    "T_LINK": {
        "type": "object",
        "required": ["entityVerdict"],
        "properties": {
            "entityVerdict": {"enum": ["merge", "create", "retype"]},
            "targetEntityId": {"type": "string"},
        },
    },
    "T_DIRECT": {
        "type": "object",
        "properties": {"accepted": {"type": "boolean"}, "note": {"type": "string"}},
    },
    "T_EXTRACT_FAIL": {
        "type": "object",
        "properties": {"rerun": {"type": "boolean"}, "note": {"type": "string"}},
    },
}

TERMINAL_STATUSES = {"RESOLVED", "REJECTED", "CANCELLED", "EXPIRED"}
EDITABLE_STATUSES = {"CLAIMED", "IN_REVIEW"}
# 直审模式：submit 可从 OPEN 直接提交（领取为可选，不再强制）
SUBMITTABLE_STATUSES = {"OPEN", "CLAIMED", "IN_REVIEW"}


def canonical_template(value: str) -> str:
    return TEMPLATE_ALIASES.get(value, value)


def validate_action(template_id: str, action_id: str, result: dict[str, Any]) -> None:
    tid = canonical_template(template_id)
    template = TEMPLATES.get(tid)
    if not template or action_id not in template["actions"]:
        raise ReviewValidationError(f"动作 {action_id} 不适用于模板 {tid}")
    if action_id == "entity-confirm":
        verdict = result.get("entityVerdict")
        if verdict not in {"merge", "create", "retype"}:
            raise ReviewValidationError("实体裁决必须指定 merge/create/retype")
        if verdict == "merge" and not result.get("targetEntityId"):
            raise ReviewValidationError("实体合并必须指定 targetEntityId")
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


def write_target(template_id: str) -> str:
    return {
        "T_LINK": "实体对齐决议（merge 并入所选实体 / create 新建入库，裁决即写图）",
        "T_DIRECT": "图数据库直写（accept 时 merge_node/create_edge）",
        "T_EXTRACT_FAIL": "失败记录重跑（重新执行抽取）",
    }[canonical_template(template_id)]


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
