"""专家-企业关系共享目录：关系类型码表 + 角色目录 + 校验。"""

from __future__ import annotations

RELATION_TYPES: dict[str, str] = {
    "employment": "任职",
    "advisor": "顾问",
    "rd_cooperation": "研发合作",
    "project_cooperation": "项目合作",
    "tech_cooperation": "技术合作",
}

ROLE_CATALOG: dict[str, tuple[str, str]] = {
    "chief_scientist": ("首席科学家", "L1"),
    "cto": ("技术总监", "L1"),
    "technical_advisor": ("技术顾问", "L2"),
    "rd_lead": ("研发负责人", "L2"),
    "engineer": ("工程师", "L3"),
}


class InvalidRelationTypeError(ValueError):
    """关系类型码非法。"""


class InvalidRoleTypeError(ValueError):
    """角色类型码非法。"""


def validate_relation_types(codes: list[str]) -> list[str]:
    bad = [c for c in codes if c not in RELATION_TYPES]
    if bad:
        raise InvalidRelationTypeError(f"非法关系类型: {bad}")
    return codes


def relation_label(codes: list[str]) -> str:
    """英文码列表 → 中文标签（/ 拼接）。

    对不在码表中的值（例如图里已存的中文标签或未知码）原样保留，避免
    真实数据混入历史中文标签时抛 KeyError。
    """
    return "/".join(RELATION_TYPES.get(c, c) for c in codes)


def role_info(role_type: str) -> tuple[str, str]:
    """roleType → (中文标签, 等级)。非法抛 InvalidRoleTypeError。"""
    if role_type not in ROLE_CATALOG:
        raise InvalidRoleTypeError(f"非法角色类型: {role_type}")
    return ROLE_CATALOG[role_type]
