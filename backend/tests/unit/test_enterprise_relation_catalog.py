from __future__ import annotations

import pytest

from service.enterprise_relation_catalog import (
    RELATION_TYPES,
    ROLE_CATALOG,
    InvalidRelationTypeError,
    relation_label,
    role_info,
    validate_relation_types,
)


def test_validate_relation_types_accepts_known():
    assert validate_relation_types(["employment", "advisor"]) == ["employment", "advisor"]


def test_validate_relation_types_rejects_unknown():
    with pytest.raises(InvalidRelationTypeError):
        validate_relation_types(["employment", "bogus"])


def test_relation_label_joins_chinese():
    assert relation_label(["employment", "rd_cooperation"]) == "任职/研发合作"


def test_relation_label_tolerates_unknown_codes():
    # 真实图数据可能混入历史中文标签（如「合作」），不应抛 KeyError。
    assert relation_label(["employment", "合作"]) == "任职/合作"
    assert relation_label(["合作", "研发合作"]) == "合作/研发合作"


def test_role_info_returns_label_and_level():
    assert role_info("chief_scientist") == ("首席科学家", "L1")
    assert role_info("engineer") == ("工程师", "L3")


def test_role_info_tolerates_unknown():
    # 非码表角色（如挖掘抽取的真实职位）原样保留、等级置空，不再抛错
    assert role_info("ceo") == ("ceo", "")
    assert role_info("博士后") == ("博士后", "")


def test_catalog_contents():
    assert RELATION_TYPES["employment"] == "任职"
    assert ROLE_CATALOG["cto"] == ("技术总监", "L1")
