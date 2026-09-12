from __future__ import annotations

import pytest
from pydantic import ValidationError

from biz.schema.industry_chain_panorama import (
    MAX_KEY_ENTITIES,
    IndustryChainPanoramaQueryRequest,
)

OVERLONG = "XXADASDDDDDDDDDDDDDDDAXZSSSSSSSSSZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZX"


def test_request_normalizes_blank_filters_and_clamps_top_k() -> None:
    request = IndustryChainPanoramaQueryRequest(
        industry=" 人工智能 ",
        anchorId="",
        depth=2,
        topK=999,
    )

    assert request.industry == "人工智能"
    assert request.anchorId is None
    assert request.topK == MAX_KEY_ENTITIES


def test_request_rejects_overlong_and_abnormal_industry() -> None:
    with pytest.raises(ValidationError, match="64"):
        IndustryChainPanoramaQueryRequest.model_validate({"industry": OVERLONG})

    with pytest.raises(ValidationError, match="异常字符"):
        IndustryChainPanoramaQueryRequest.model_validate({"industry": "人工智能!@#￥%&"})

    request = IndustryChainPanoramaQueryRequest.model_validate(
        {"industry": "集成电路 / 半导体（材料）"}
    )
    assert request.industry == "集成电路 / 半导体（材料）"


def test_request_rejects_overlong_and_abnormal_anchor_id() -> None:
    with pytest.raises(ValidationError, match="64"):
        IndustryChainPanoramaQueryRequest.model_validate({"anchorId": OVERLONG})

    with pytest.raises(ValidationError, match="异常字符"):
        IndustryChainPanoramaQueryRequest.model_validate({"anchorId": "person_a!@#￥%&"})

    with pytest.raises(ValidationError, match="空格"):
        IndustryChainPanoramaQueryRequest.model_validate({"anchorId": "person a"})

    request = IndustryChainPanoramaQueryRequest.model_validate({"anchorId": "person_4G7t0B0t"})
    assert request.anchorId == "person_4G7t0B0t"


def test_request_rejects_removed_data_source_parameter() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        IndustryChainPanoramaQueryRequest.model_validate({"dataSource": "all"})


def test_request_keeps_internal_refresh_control() -> None:
    request = IndustryChainPanoramaQueryRequest.model_validate({"refresh": True})
    assert request.refresh is True


def test_request_rejects_overlong_top_k() -> None:
    with pytest.raises(ValidationError, match="64"):
        IndustryChainPanoramaQueryRequest.model_validate({"topK": "9" * 65})
