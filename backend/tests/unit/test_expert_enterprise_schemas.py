from __future__ import annotations

import pytest
from pydantic import ValidationError

from biz.schemas.expert_enterprise_relation import ExpertEnterpriseBuildRequest


def test_request_accepts_valid_relation_types():
    req = ExpertEnterpriseBuildRequest(
        scholarId="S001", enterpriseId="E001", relationTypes=["employment", "advisor"]
    )
    assert req.relationTypes == ["employment", "advisor"]


def test_request_rejects_unknown_relation_type():
    with pytest.raises(ValidationError):
        ExpertEnterpriseBuildRequest(
            scholarId="S001", enterpriseId="E001", relationTypes=["employment", "bogus"]
        )


def test_request_rejects_empty_relation_types():
    with pytest.raises(ValidationError):
        ExpertEnterpriseBuildRequest(scholarId="S001", enterpriseId="E001", relationTypes=[])
