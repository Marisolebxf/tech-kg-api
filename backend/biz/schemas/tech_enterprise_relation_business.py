"""重点关注科技企业关系业务（九大业务之一）请求/响应模型。

对齐前端 service-modules.ts 的 enterprise-relation 契约：
端点 POST /api/v1/kg-service/key-enterprise-relation，请求 {expert_id, enterprise_name,
role_type, industry}，响应 data={enterprises, roles, cooperation_fields, relations}。
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field, field_validator

# 标识类字段允许的字符：字母数字下划线、中文、间隔号、点、连字符。
_ID_LIKE_PATTERN = re.compile(r"[\w一-鿿·.\-]+")
# 关键词类筛选字段（企业名称/角色/行业）允许的字符：标识字符 + 空格、中英文括号、
# 顿号、逗号、斜杠（兼容「（集团）」「高端装备/智能制造」等合法输入）。
_KEYWORD_PATTERN = re.compile(r"[\w一-鿿·.\-()（）、，,/\s]+")


class BusinessPeriod(BaseModel):
    start: str | None = None
    end: str | None = None


class EntityProvenance(BaseModel):
    """实体溯源信息（来自图节点 properties，与同事关系 _entity_data 同源同口径）。

    前端 getNodeProvenance 读取节点的 sourceTable/sourceField/sourceValue/ingestBatch/ingestTime，
    缺失时回退 nodeSourceMap 静态映射；这里填真实值后即展示真实源数据表/英文字段名。
    """

    sourceTable: str | None = None
    sourceField: str | None = None
    sourceValue: str | None = None
    ingestBatch: str | None = None
    ingestTime: str | None = None


class KeyEnterpriseRelationRequest(BaseModel):
    expert_id: str = Field(..., max_length=64, description="科技专家/人才唯一标识 VID")
    enterprise_name: str = Field("", max_length=64, description="企业名称筛选（模糊，可留空）")
    role_type: str = Field("", max_length=64, description="专家企业角色筛选（可留空）")
    industry: str = Field("", max_length=64, description="企业行业方向筛选（可留空）")
    key_tech_enterprise_only: bool = Field(
        True, description="只保留重点科技企业（已上市/公司类），排除高校/研究院/MOCK"
    )

    @field_validator("expert_id", mode="before")
    @classmethod
    def normalize_expert_id(cls, value: str | None) -> str | None:
        """专家标识：拒绝超长、空格与 !@#￥%& 等异常字符。

        与同事关系 (expert_colleague_relation) 的专家标识校验保持一致，覆盖测试用例：
        超长字符 / 异常字符。
        """
        if value is None:
            return None
        if not isinstance(value, str):
            value = str(value)
        if re.search(r"\s", value):
            raise ValueError("专家标识不能包含空格或 !@#￥%& 等异常字符")
        value = value.strip()
        if not value:
            raise ValueError("expert_id 不能为空")
        if len(value) > 64:
            raise ValueError("专家标识长度不能超过 64 个字符")
        if not _ID_LIKE_PATTERN.fullmatch(value):
            raise ValueError("专家标识不能包含空格或 !@#￥%& 等异常字符")
        return value

    @field_validator("key_tech_enterprise_only", mode="before")
    @classmethod
    def _coerce_bool(cls, v: object) -> object:
        """只接受布尔 true/false（字符串 'true'/'false' 大小写不敏感）。

        不再兼容 '是'/'否'/'1'/'0'/'yes'/'no' 等旧值——前端面板按 field.type=boolean
        转真布尔提交，其余脏输入一律拒绝并提示用 true/false。
        """
        if isinstance(v, bool):
            return v
        if v is None:
            return True
        s = str(v).strip().lower()
        if s == "true":
            return True
        if s == "false":
            return False
        raise ValueError("key_tech_enterprise_only 只接受 true/false")

    @field_validator("enterprise_name", "role_type", "industry", mode="before")
    @classmethod
    def _validate_filter_text(cls, value: str | None) -> str | None:
        """企业名称/角色/行业筛选：拒绝超长与 !@#￥%& 等异常字符，可留空。

        与前端 keywordError 同口径（关键词类字段允许空格、括号、顿号、斜杠），
        覆盖 0826 任务用例：enterprise_name / industry 超长字符、异常字符。留空跳过校验。
        """
        if value is None:
            return None
        if not isinstance(value, str):
            value = str(value)
        value = value.strip()
        if value == "":
            return ""
        if len(value) > 64:
            raise ValueError("输入长度不能超过 64 个字符")
        if not _KEYWORD_PATTERN.fullmatch(value):
            raise ValueError("不能包含 !@#￥%& 等异常字符")
        return value


class EnterpriseRelationItem(BaseModel):
    enterprise_id: str
    enterprise_name: str | None = None
    cooperation_type: str = ""  # governance / project_cooperation / patent_cooperation
    cooperation_mode: str = ""  # 高管任职/法人代表/项目合作/专利合作/任职/...
    role_label: str | None = None
    role_level: str | None = None
    tech_field: str | None = None
    period: BusinessPeriod = Field(default_factory=BusinessPeriod)
    enterprise_background: dict[str, Any] = Field(default_factory=dict)
    source: str = ""  # 来源边类型或 project_id/patent_id
    risk_summary: str = ""  # 首要企业风险事件摘要（标书「经营状况」之风险提示）
    confidence: float = 0.0  # 关系置信度（标书「企业关联置信度」）


class KeyEnterpriseRelationResponse(BaseModel):
    expert_id: str
    expert_name: str | None = None
    enterprises: int = 0  # 关联企业数
    roles: int = 0  # 角色类型数
    cooperation_fields: list[str] = Field(default_factory=list)
    relations: list[EnterpriseRelationItem] = Field(default_factory=list)
    confidence: float = 0.0  # 综合置信度（取关系置信度最大值）
    evidence: list[str] = Field(default_factory=list)
    # 实体溯源：vid -> 源数据表/英文字段名/源记录值/入图批次/入图时间，供前端溯源栏展示。
    # 字段名特意不用 provenance，避免被前端 liveProvenance(data.provenance) 当成响应级溯源误匹配。
    entity_provenance: dict[str, EntityProvenance] = Field(default_factory=dict)
