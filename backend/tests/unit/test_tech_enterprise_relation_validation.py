"""重点关注科技企业关系请求模型输入校验的单元测试。

对齐 0825 任务用例（重点科技企业可能存在与同事关系类似的输入问题）：
expert_id 超长字符、异常字符（!@#￥%& 等）。校验规则与同事关系
(expert_colleague_relation) 的专家标识校验保持一致。
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from biz.schemas.tech_enterprise_relation_business import KeyEnterpriseRelationRequest

# 任务用例中的超长字符串样本。
OVERLONG = "XXADASDDDDDDDDDDDDDDDAXZSSSSSSSSSZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZX"
ABNORMAL = "person_855924f1!@#￥%&"


def test_request_rejects_overlong_expert_id() -> None:
    with pytest.raises(ValidationError, match="64"):
        KeyEnterpriseRelationRequest.model_validate({"expert_id": OVERLONG})


def test_request_rejects_abnormal_expert_id() -> None:
    with pytest.raises(ValidationError, match="异常字符"):
        KeyEnterpriseRelationRequest.model_validate({"expert_id": ABNORMAL})


def test_request_rejects_whitespace_expert_id() -> None:
    with pytest.raises(ValidationError, match="空格"):
        KeyEnterpriseRelationRequest.model_validate({"expert_id": "person 855924f1"})


def test_request_accepts_valid_expert_id() -> None:
    req = KeyEnterpriseRelationRequest.model_validate({"expert_id": "person_855924f1"})
    assert req.expert_id == "person_855924f1"

    # 含连字符/下划线的合法标识
    req = KeyEnterpriseRelationRequest.model_validate({"expert_id": "person_left-jing"})
    assert req.expert_id == "person_left-jing"


@pytest.mark.parametrize("field", ["enterprise_name", "role_type", "industry"])
def test_request_rejects_overlong_filter(field: str) -> None:
    """企业名称/角色/行业筛选超长字符 → 提示超出字段长度（0826 任务用例）。"""
    with pytest.raises(ValidationError, match="64"):
        KeyEnterpriseRelationRequest.model_validate(
            {"expert_id": "person_855924f1", field: OVERLONG}
        )


@pytest.mark.parametrize("field", ["enterprise_name", "role_type", "industry"])
def test_request_rejects_abnormal_filter(field: str) -> None:
    """企业名称/角色/行业筛选异常字符 → 提示存在异常字符（0826 任务用例）。"""
    with pytest.raises(ValidationError, match="异常字符"):
        KeyEnterpriseRelationRequest.model_validate(
            {"expert_id": "person_855924f1", field: "！#@！@#"}
        )


def test_request_accepts_valid_filter_text() -> None:
    """合法的企业名称/行业筛选（含中文、括号、斜杠）应通过，留空也应通过。"""
    req = KeyEnterpriseRelationRequest.model_validate(
        {
            "expert_id": "person_855924f1",
            "enterprise_name": "苏州绿的谐波传动科技股份有限公司",
            "role_type": "副董事长",
            "industry": "高端装备/智能制造",
        }
    )
    assert req.enterprise_name == "苏州绿的谐波传动科技股份有限公司"
    assert req.role_type == "副董事长"
    assert req.industry == "高端装备/智能制造"
    # 留空合法（默认 ""）
    req2 = KeyEnterpriseRelationRequest.model_validate({"expert_id": "person_855924f1"})
    assert req2.enterprise_name == ""
    assert req2.industry == ""
