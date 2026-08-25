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
