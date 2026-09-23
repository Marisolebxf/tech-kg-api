"""间接关系标注 请求/响应模型。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

from biz.schemas.text_rules import (
    IDENTIFIER_TEXT_PATTERN,
    MAX_TEXT_LENGTH,
    check_text,
)

# 节点 VID 主键长度上限（含 person_ 等前缀，宽于普通文本框 64 字限制）。
VID_MAX_LENGTH = 256


def check_vid(value: str | None, *, label: str) -> str | None:
    """节点 VID 校验：不允许空格与异常字符，长度上限放宽到 VID 主键列宽。"""
    if value is None or value == "":
        return value
    value = str(value).strip()
    if len(value) > VID_MAX_LENGTH:
        raise ValueError(f"{label}长度不能超过 {VID_MAX_LENGTH} 个字符")
    if not IDENTIFIER_TEXT_PATTERN.fullmatch(value):
        raise ValueError(f"{label}不能包含空格或 !@#￥%& 等异常字符")
    return value


class IndirectRelationAnnotationRequest(BaseModel):
    """保存（upsert）一条关系标注。"""

    sourceVid: str = Field(..., min_length=1, description="边起点节点 VID")
    targetVid: str = Field(..., min_length=1, description="边终点节点 VID")
    annotation: str = Field(
        default="",
        max_length=MAX_TEXT_LENGTH,
        description="关系标注文本；留空表示清除标注。",
    )

    @field_validator("sourceVid", "targetVid", mode="before")
    @classmethod
    def _validate_vid(cls, v: str) -> str:
        return check_vid(v, label="节点 VID")

    @field_validator("annotation", mode="before")
    @classmethod
    def _validate_annotation(cls, v: str | None) -> str:
        if v is None:
            return v
        return check_text(str(v), label="关系标注", allow_space=True)


class IndirectRelationAnnotationItem(BaseModel):
    sourceVid: str
    targetVid: str
    annotation: str = ""
    updateTime: str | None = None


class IndirectRelationAnnotationList(BaseModel):
    items: list[IndirectRelationAnnotationItem] = Field(default_factory=list)


def annotation_item(data: dict[str, Any]) -> IndirectRelationAnnotationItem:
    return IndirectRelationAnnotationItem(**data)
