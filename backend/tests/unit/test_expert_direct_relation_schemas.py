from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from biz.schema.expert_direct_relation import (
    MAX_QUERY_LIMIT,
    ExpertDirectRelationQueryRequest,
)

OVERLONG = "XXADASDDDDDDDDDDDDDDDAXZSSSSSSSSSZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZX"


def _future_month() -> str:
    today = date.today()
    year = today.year + (1 if today.month == 12 else 0)
    month = 1 if today.month == 12 else today.month + 1
    return f"{year}-{month:02d}"


def test_request_normalizes_blank_filters() -> None:
    request = ExpertDirectRelationQueryRequest(
        expertAId=" 007Rb117 ",
        expertBId="",
        institution="  ",
        startTime="",
        endTime="",
        limit=MAX_QUERY_LIMIT,
    )

    assert request.expertAId == "007Rb117"
    assert request.expertBId is None
    assert request.institution is None
    assert request.startTime is None
    assert request.limit == MAX_QUERY_LIMIT


@pytest.mark.parametrize("limit", [1, MAX_QUERY_LIMIT])
def test_request_accepts_limit_boundaries(limit: int) -> None:
    request = ExpertDirectRelationQueryRequest(expertAId="007Rb117", limit=limit)
    assert request.limit == limit


@pytest.mark.parametrize("limit", [0, 101, -1, 1.5, "10", True, None])
def test_request_rejects_invalid_limit(limit: object) -> None:
    with pytest.raises(ValidationError):
        ExpertDirectRelationQueryRequest.model_validate({"expertAId": "007Rb117", "limit": limit})


@pytest.mark.parametrize("field", ["expertAId", "expertBId"])
def test_request_rejects_overlong_and_abnormal_expert_ids(field: str) -> None:
    with pytest.raises(ValidationError, match="64"):
        ExpertDirectRelationQueryRequest.model_validate({field: OVERLONG})

    with pytest.raises(ValidationError, match="异常字符"):
        ExpertDirectRelationQueryRequest.model_validate({field: "person_a!@#￥%&"})

    with pytest.raises(ValidationError, match="空格"):
        ExpertDirectRelationQueryRequest.model_validate({field: "person a"})


def test_request_rejects_overlong_and_abnormal_institution() -> None:
    with pytest.raises(ValidationError, match="64"):
        ExpertDirectRelationQueryRequest.model_validate(
            {"expertAId": "王祎", "institution": OVERLONG}
        )

    with pytest.raises(ValidationError, match="异常字符"):
        ExpertDirectRelationQueryRequest.model_validate(
            {"expertAId": "王祎", "institution": "清华大学!@#￥%&"}
        )

    # 机构名允许空格和括号
    request = ExpertDirectRelationQueryRequest.model_validate(
        {"expertAId": "王祎", "institution": "National University of Singapore（NUS）"}
    )
    assert request.institution == "National University of Singapore（NUS）"


def test_request_rejects_future_and_reversed_time_range() -> None:
    with pytest.raises(ValidationError, match="不能晚于当前时间"):
        ExpertDirectRelationQueryRequest.model_validate(
            {"expertAId": "王祎", "startTime": _future_month()}
        )

    with pytest.raises(ValidationError, match="不能晚于当前时间"):
        ExpertDirectRelationQueryRequest.model_validate({"expertAId": "王祎", "endTime": "2027-01"})

    with pytest.raises(ValidationError, match="不能晚于结束时间"):
        ExpertDirectRelationQueryRequest.model_validate(
            {"expertAId": "王祎", "startTime": "2023-01", "endTime": "2022-12"}
        )

    with pytest.raises(ValidationError, match="YYYY-MM"):
        ExpertDirectRelationQueryRequest.model_validate(
            {"expertAId": "王祎", "startTime": "2023/01"}
        )

    request = ExpertDirectRelationQueryRequest.model_validate(
        {"expertAId": "王祎", "startTime": "2020-01", "endTime": "2021-06-30"}
    )
    assert request.startTime == "2020-01"
    assert request.endTime == "2021-06-30"
