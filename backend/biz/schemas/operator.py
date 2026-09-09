"""算子注册与调用 API 模型。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from biz.schemas.text_rules import check_text
from service.operator_registry import OperatorKind


class OperatorUploadRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "user.add_score",
                "version": "1.0.0",
                "kind": "data_processing",
                "description": "给每条记录增加分数",
                "source": (
                    "def operator(data, ctx):\n"
                    "    score = ctx.get('score', 1)\n"
                    "    return [{**item, 'score': score} for item in data]\n"
                ),
            }
        }
    )

    name: str = Field(min_length=1, max_length=64)
    version: str = Field(min_length=1, max_length=64)
    kind: OperatorKind
    source: str = Field(min_length=1, max_length=262_144)
    description: str = Field(default="", max_length=64)

    @field_validator("name", mode="before")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        if v is None or v == "":
            return v
        return check_text(str(v).strip(), label="算子名称")

    @field_validator("description", mode="before")
    @classmethod
    def _validate_description(cls, v: str) -> str:
        if v is None or v == "":
            return v
        return check_text(str(v).strip(), label="算子描述", allow_space=True)


class OperatorUpdateRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "version": "1.1.0",
                "kind": "data_processing",
                "description": "热更新后的实现",
                "source": "def operator(data, ctx):\n    return [{**x, 'v': 2} for x in data]\n",
            }
        }
    )

    version: str = Field(min_length=1, max_length=64)
    kind: OperatorKind
    source: str = Field(min_length=1, max_length=262_144)
    description: str = Field(default="", max_length=64)

    @field_validator("description", mode="before")
    @classmethod
    def _validate_description(cls, v: str) -> str:
        if v is None or v == "":
            return v
        return check_text(str(v).strip(), label="算子描述", allow_space=True)


class OperatorInvokeRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"example": {"data": [{"name": " Alice  "}], "ctx": {}}}
    )

    data: list[dict[str, Any]]
    ctx: dict[str, Any] = Field(default_factory=dict)


class OperatorManifestResponse(BaseModel):
    name: str
    version: str
    kind: OperatorKind
    description: str
    builtin: bool
    updated_at: str


class OperatorListResponse(BaseModel):
    items: list[OperatorManifestResponse]


class OperatorInvokeResponse(BaseModel):
    operator: OperatorManifestResponse
    data: list[dict[str, Any]]
    count: int


class OperatorReloadResponse(BaseModel):
    loaded: list[str]
    count: int


class OperatorBundle(BaseModel):
    manifest: OperatorManifestResponse
    source: str = Field(max_length=262_144)


class OperatorSyncRequest(BaseModel):
    operators: list[OperatorBundle] = Field(default_factory=list)
    replace: bool = True
