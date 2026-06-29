from __future__ import annotations

import pytest
from pydantic import ValidationError

from biz.schemas.relation_detail_annotation import RelationDetailAnnotationRequest


def test_request_accepts_valid_role():
    req = RelationDetailAnnotationRequest(
        relationId="S001->E001@0",
        roleType="chief_scientist",
        techField="人工智能",
        period={"start": "2021-01-01", "end": "2024-12-31"},
    )
    assert req.roleType == "chief_scientist"
    assert req.period.start == "2021-01-01"


def test_request_rejects_unknown_role():
    with pytest.raises(ValidationError):
        RelationDetailAnnotationRequest(relationId="S001->E001@0", roleType="ceo")
