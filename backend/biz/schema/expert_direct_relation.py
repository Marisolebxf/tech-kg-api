from __future__ import annotations

import re
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

DataSource = Literal["all"]
MAX_QUERY_LIMIT = 100
MAX_TEXT_LENGTH = 64

# 专家标识：字母数字下划线、中文、间隔号、点、连字符；不允许空格与 !@#￥%& 等符号
EXPERT_ID_PATTERN = re.compile(r"[\w\u4e00-\u9fff·.\-]+")
# 机构关键词：在专家标识基础上额外允许空格、括号、顿号和斜杠
INSTITUTION_PATTERN = re.compile(r"[\w\u4e00-\u9fff·.\-()（）、，,/\s]+")
# 时间：YYYY-MM 或 YYYY-MM-DD
TIME_PATTERN = re.compile(r"(?:19|20)\d{2}-(?:0[1-9]|1[0-2])(?:-(?:0[1-9]|[12]\d|3[01]))?")


class ExpertDirectRelationQueryRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "dataSource": "all",
                "expertAId": "王祎",
                "expertBId": "",
                "institution": "",
                "startTime": "",
                "endTime": "",
                "limit": 10,
            }
        }
    )

    dataSource: DataSource = Field(default="all", description="数据来源，固定为 all。")
    expertAId: str = Field(
        ...,
        description=f"专家A scholar_id 或姓名关键词，必填，最多 {MAX_TEXT_LENGTH} 个字符。",
    )
    expertBId: str | None = Field(
        default=None,
        description=(
            f"专家B scholar_id 或姓名关键词，可选；为空时仅返回专家A节点，"
            f"最多 {MAX_TEXT_LENGTH} 个字符。"
        ),
    )
    institution: str | None = Field(
        default=None, description=f"机构关键词，最多 {MAX_TEXT_LENGTH} 个字符。"
    )
    startTime: str | None = Field(default=None, description="开始日期 YYYY-MM 或 YYYY-MM-DD。")
    endTime: str | None = Field(default=None, description="结束日期 YYYY-MM 或 YYYY-MM-DD。")
    limit: int = Field(default=10, ge=1, description=f"返回结果数，最大 {MAX_QUERY_LIMIT}。")

    @field_validator("limit")
    @classmethod
    def clamp_limit(cls, value: int) -> int:
        return min(value, MAX_QUERY_LIMIT)

    @field_validator("expertAId", mode="before")
    @classmethod
    def normalize_expert_a_id(cls, value: Any) -> str:
        if value is None or (isinstance(value, str) and not value.strip()):
            raise ValueError("专家A标识不能为空")
        return cls._normalize_expert_id_value(value)

    @field_validator("expertBId", mode="before")
    @classmethod
    def normalize_expert_b_id(cls, value: Any) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("专家标识必须是字符串")
        if not value.strip():
            return None
        return cls._normalize_expert_id_value(value)

    @staticmethod
    def _normalize_expert_id_value(value: Any) -> str:
        if not isinstance(value, str):
            raise ValueError("专家标识必须是字符串")
        value = value.strip()
        if not value:
            raise ValueError("专家标识不能为空")
        if len(value) > MAX_TEXT_LENGTH:
            raise ValueError(f"专家标识长度不能超过 {MAX_TEXT_LENGTH} 个字符")
        if re.search(r"\s", value):
            raise ValueError("专家标识不能包含空格或 !@#￥%& 等异常字符")
        if not EXPERT_ID_PATTERN.fullmatch(value):
            raise ValueError("专家标识不能包含空格或 !@#￥%& 等异常字符")
        return value

    @field_validator("institution", mode="before")
    @classmethod
    def normalize_institution(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("机构关键词必须是字符串")
        value = value.strip()
        if not value:
            return None
        if len(value) > MAX_TEXT_LENGTH:
            raise ValueError(f"机构关键词长度不能超过 {MAX_TEXT_LENGTH} 个字符")
        if not INSTITUTION_PATTERN.fullmatch(value):
            raise ValueError("机构关键词不能包含 !@#￥%& 等异常字符")
        return value

    @field_validator("startTime", "endTime", mode="before")
    @classmethod
    def normalize_time(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("时间必须是字符串")
        value = value.strip()
        if not value:
            return None
        if not TIME_PATTERN.fullmatch(value):
            raise ValueError("时间必须使用 YYYY-MM 或 YYYY-MM-DD 格式")
        return value

    @model_validator(mode="after")
    def validate_time_range(self) -> ExpertDirectRelationQueryRequest:
        today = date.today().isoformat()
        if self.startTime and self.startTime > today[: len(self.startTime)]:
            raise ValueError("开始时间不能晚于当前时间")
        if self.endTime and self.endTime > today[: len(self.endTime)]:
            raise ValueError("结束时间不能晚于当前时间")
        if self.startTime and self.endTime and self.startTime[:7] > self.endTime[:7]:
            raise ValueError("开始时间不能晚于结束时间")
        return self


class DirectRelationExpert(BaseModel):
    expertId: str
    name: str
    organization: str | None = None
    title: str = "专家"
    paperCount: int = 0
    citationCount: int = 0
    hIndex: int = 0


class DirectRelationItem(BaseModel):
    key: str
    relationType: str = "直接关系"
    expertA: DirectRelationExpert
    expertB: DirectRelationExpert
    institution: str | None = None
    coPaperCount: int = 0
    relationStrength: int = 0
    reasonTags: list[str] = Field(default_factory=list)
    relationSummary: str = ""
    lastUpdatedAt: str | None = None
    detailRows: list[list[Any]] = Field(default_factory=list)


class DirectRelationGraphNode(BaseModel):
    id: str
    type: str
    label: str
    subtitle: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class DirectRelationGraphEdge(BaseModel):
    source: str
    target: str
    label: str
    data: dict[str, Any] = Field(default_factory=dict)


class ExpertDirectRelationQueryResponse(BaseModel):
    taskName: str
    input: dict[str, Any]
    total: int
    items: list[DirectRelationItem]
    graph: dict[str, list[Any]]
    source: dict[str, Any]
    provenance: dict[str, Any] | None = None
    apiResultExample: dict[str, Any]
