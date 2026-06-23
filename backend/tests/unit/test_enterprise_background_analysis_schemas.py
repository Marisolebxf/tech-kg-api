from __future__ import annotations

import pytest
from pydantic import ValidationError

from biz.schemas.enterprise_background_analysis import EnterpriseBackgroundAnalysisRequest


def test_request_accepts_valid_dimensions():
    req = EnterpriseBackgroundAnalysisRequest(
        enterpriseId="E001",
        analysisDimensions=["industry_status", "core_tech"],
        patentCPC=["G06N"],
    )
    assert req.analysisDimensions == ["industry_status", "core_tech"]


def test_request_rejects_unknown_dimension():
    with pytest.raises(ValidationError):
        EnterpriseBackgroundAnalysisRequest(enterpriseId="E001", analysisDimensions=["bogus"])


def test_request_rejects_empty_dimensions():
    with pytest.raises(ValidationError):
        EnterpriseBackgroundAnalysisRequest(enterpriseId="E001", analysisDimensions=[])
