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


def test_request_maps_chinese_relation_labels_to_edge_codes() -> None:
    # 中文文案（含"+"拼接的下拉折叠标签）自动转英文边类型码
    request = IndustryChainPanoramaQueryRequest.model_validate(
        {"industry": "集成电路", "relationTypes": ["产业链归属+论文合作"]}
    )
    assert request.relationTypes == ["BELONGS_TO_NODE", "COAUTHOR_WITH"]

    # 中文、小写英文码混传均规整为大写码
    request = IndustryChainPanoramaQueryRequest.model_validate(
        {"industry": "集成电路", "relationTypes": ["机构任职", "belongs_to_node"]}
    )
    assert request.relationTypes == ["AFFILIATED_WITH", "BELONGS_TO_NODE"]

    # 中文与英文码同义去重
    request = IndustryChainPanoramaQueryRequest.model_validate(
        {"industry": "集成电路", "relationTypes": "产业链归属,BELONGS_TO_NODE"}
    )
    assert request.relationTypes == ["BELONGS_TO_NODE"]


def test_request_rejects_unknown_relation_labels() -> None:
    # 映射表之外的中文文案仍按非法关系类型拒绝
    with pytest.raises(ValidationError, match="关系类型只能包含字母、数字和下划线"):
        IndustryChainPanoramaQueryRequest.model_validate(
            {"industry": "集成电路", "relationTypes": ["不存在的关系"]}
        )


def test_request_rejects_overlong_and_abnormal_industry() -> None:
    with pytest.raises(ValidationError, match="64"):
        IndustryChainPanoramaQueryRequest.model_validate({"industry": OVERLONG})

    with pytest.raises(ValidationError, match="异常字符"):
        IndustryChainPanoramaQueryRequest.model_validate({"industry": "人工智能!@#￥%&"})

    request = IndustryChainPanoramaQueryRequest.model_validate(
        {"industry": "集成电路 / 半导体（材料）"}
    )
    assert request.industry == "集成电路 / 半导体（材料）"


def test_request_requires_industry() -> None:
    # industry 为必填：缺失、None、空串、纯空白都要拒绝
    with pytest.raises(ValidationError, match="Field required"):
        IndustryChainPanoramaQueryRequest.model_validate({"anchorId": "person_4G7t0B0t"})

    with pytest.raises(ValidationError, match="不能为空"):
        IndustryChainPanoramaQueryRequest.model_validate({"industry": None})

    with pytest.raises(ValidationError, match="不能为空"):
        IndustryChainPanoramaQueryRequest.model_validate({"industry": ""})

    with pytest.raises(ValidationError, match="不能为空"):
        IndustryChainPanoramaQueryRequest.model_validate({"industry": "   "})


def test_request_rejects_overlong_and_abnormal_anchor_id() -> None:
    with pytest.raises(ValidationError, match="64"):
        IndustryChainPanoramaQueryRequest.model_validate(
            {"industry": "人工智能", "anchorId": OVERLONG}
        )

    with pytest.raises(ValidationError, match="异常字符"):
        IndustryChainPanoramaQueryRequest.model_validate(
            {"industry": "人工智能", "anchorId": "person_a!@#￥%&"}
        )

    with pytest.raises(ValidationError, match="空格"):
        IndustryChainPanoramaQueryRequest.model_validate(
            {"industry": "人工智能", "anchorId": "person a"}
        )

    request = IndustryChainPanoramaQueryRequest.model_validate(
        {"industry": "人工智能", "anchorId": "person_4G7t0B0t"}
    )
    assert request.anchorId == "person_4G7t0B0t"


def test_request_rejects_removed_data_source_parameter() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        IndustryChainPanoramaQueryRequest.model_validate(
            {"industry": "人工智能", "dataSource": "all"}
        )


def test_request_keeps_internal_refresh_control() -> None:
    request = IndustryChainPanoramaQueryRequest.model_validate(
        {"industry": "人工智能", "refresh": True}
    )
    assert request.refresh is True


def test_request_rejects_overlong_top_k() -> None:
    with pytest.raises(ValidationError, match="64"):
        IndustryChainPanoramaQueryRequest.model_validate({"industry": "人工智能", "topK": "9" * 65})
