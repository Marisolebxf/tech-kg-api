"""科技产业链点 TOP-N 事件关系请求模型输入校验的单元测试。

对齐 0825 任务用例：chain_node_id / event_type 超长字符、异常字符（!@#￥%& 等），
time_range_start / time_range_end 超出当前时间。校验规则与同事关系
(expert_colleague_relation) 的专家标识校验保持一致。
"""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from biz.schemas.industry_node_top_events_business import IndustryNodeTopEventsRequest

# 任务用例中的超长字符串样本。
OVERLONG = "XXADASDDDDDDDDDDDDDDDAXZSSSSSSSSSZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZX"
ABNORMAL = "IC0007007!@#￥%&"


@pytest.mark.parametrize("field", ["chain_node_id", "event_type"])
def test_request_rejects_overlong_and_abnormal(field: str) -> None:
    base = {"chain_node_id": "IC0007007", "event_type": "financing"}
    # 超长字符 → 提示超出字段长度
    payload = {**base, field: OVERLONG}
    with pytest.raises(ValidationError, match="64"):
        IndustryNodeTopEventsRequest.model_validate(payload)

    # 异常字符 → 提示存在异常字符
    payload = {**base, field: ABNORMAL}
    with pytest.raises(ValidationError, match="异常字符"):
        IndustryNodeTopEventsRequest.model_validate(payload)


@pytest.mark.parametrize("field", ["chain_node_id", "event_type"])
def test_request_rejects_whitespace(field: str) -> None:
    base = {"chain_node_id": "IC0007007", "event_type": "financing"}
    payload = {**base, field: "IC 0007007"}
    with pytest.raises(ValidationError, match="空格"):
        IndustryNodeTopEventsRequest.model_validate(payload)


def test_request_rejects_future_time_range() -> None:
    future_year = str(date.today().year + 1)
    with pytest.raises(ValidationError, match="当前时间"):
        IndustryNodeTopEventsRequest.model_validate(
            {"chain_node_id": "IC0007007", "time_range": f"{future_year}-{future_year}"}
        )

    # 仅起始端为未来时间
    with pytest.raises(ValidationError, match="time_range_start 不能晚于当前时间"):
        IndustryNodeTopEventsRequest.model_validate(
            {"chain_node_id": "IC0007007", "time_range": f"{future_year}-"}
        )

    # 仅结束端为未来时间
    with pytest.raises(ValidationError, match="time_range_end 不能晚于当前时间"):
        IndustryNodeTopEventsRequest.model_validate(
            {"chain_node_id": "IC0007007", "time_range": f"-{future_year}"}
        )


def test_request_rejects_time_range_start_after_end() -> None:
    with pytest.raises(ValidationError, match="time_range_start 不能晚于 time_range_end"):
        IndustryNodeTopEventsRequest.model_validate(
            {"chain_node_id": "IC0007007", "time_range": "2025-2024"}
        )


def test_request_accepts_valid_inputs() -> None:
    # 完整年份区间
    req = IndustryNodeTopEventsRequest.model_validate(
        {"chain_node_id": "IC0007007", "event_type": "financing", "time_range": "2024-2025"}
    )
    assert req.chain_node_id == "IC0007007"
    assert req.event_type == "financing"
    assert req.time_range == "2024-2025"

    # event_type 可留空（默认 ""），不触发校验
    req = IndustryNodeTopEventsRequest.model_validate({"chain_node_id": "IC0007007"})
    assert req.event_type == ""

    # 单端开放的年份区间
    req = IndustryNodeTopEventsRequest.model_validate(
        {"chain_node_id": "IC0007007", "time_range": "2024-"}
    )
    assert req.time_range == "2024-"

    # 含中文/连字符的合法标识
    req = IndustryNodeTopEventsRequest.model_validate({"chain_node_id": "节点-IC0007"})
    assert req.chain_node_id == "节点-IC0007"


def test_request_rejects_non_numeric_top_n() -> None:
    """top_n 输入非数字 → 提示必须是数字（0826 任务用例）。"""
    with pytest.raises(ValidationError, match="必须是数字"):
        IndustryNodeTopEventsRequest.model_validate({"chain_node_id": "IC0007007", "top_n": "abc"})
    # 中文字符、小数、布尔均视为非数字
    with pytest.raises(ValidationError, match="必须是数字"):
        IndustryNodeTopEventsRequest.model_validate({"chain_node_id": "IC0007007", "top_n": "十"})
    with pytest.raises(ValidationError, match="必须是数字"):
        IndustryNodeTopEventsRequest.model_validate({"chain_node_id": "IC0007007", "top_n": "1.5"})
    with pytest.raises(ValidationError, match="必须是数字"):
        IndustryNodeTopEventsRequest.model_validate({"chain_node_id": "IC0007007", "top_n": True})


def test_request_rejects_top_n_out_of_range() -> None:
    """top_n 不在 1-50 范围 → 提示取值范围（0826 任务用例）。"""
    for bad in (0, -1, 51, 999):
        with pytest.raises(ValidationError, match="取值范围"):
            IndustryNodeTopEventsRequest.model_validate(
                {"chain_node_id": "IC0007007", "top_n": bad}
            )
    # 字符串数字同样受范围约束
    with pytest.raises(ValidationError, match="取值范围"):
        IndustryNodeTopEventsRequest.model_validate({"chain_node_id": "IC0007007", "top_n": "999"})


def test_request_accepts_valid_top_n() -> None:
    """合法 top_n（int / 数字字符串 / 留空默认 10）应通过。"""
    req = IndustryNodeTopEventsRequest.model_validate({"chain_node_id": "IC0007007", "top_n": 10})
    assert req.top_n == 10
    # 字符串数字也兼容
    req = IndustryNodeTopEventsRequest.model_validate({"chain_node_id": "IC0007007", "top_n": "25"})
    assert req.top_n == 25
    # 边界值 1 与 50 合法
    assert (
        IndustryNodeTopEventsRequest.model_validate(
            {"chain_node_id": "IC0007007", "top_n": 1}
        ).top_n
        == 1
    )
    assert (
        IndustryNodeTopEventsRequest.model_validate(
            {"chain_node_id": "IC0007007", "top_n": 50}
        ).top_n
        == 50
    )
    # 留空取默认 10
    assert IndustryNodeTopEventsRequest.model_validate({"chain_node_id": "IC0007007"}).top_n == 10
