"""平台 LLM 配置接口请求/响应模型。"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, field_validator

from biz.schemas.schema_management import CamelModel
from biz.schemas.text_rules import SECRET_TEXT_PATTERN, URL_TEXT_PATTERN, check_text


class LlmConfigCreate(CamelModel):
    name: str = Field(min_length=1, max_length=64)
    description: str = Field(default="", max_length=64)
    base_url: str = Field(min_length=1, max_length=64)
    api_key: str = Field(default="", max_length=64)
    model: str = Field(min_length=1, max_length=64)
    owner: str = Field(default="", max_length=64)
    is_default: bool = False
    status: str = Field(default="正常")

    @field_validator("name", "description", "model", "owner", mode="before")
    @classmethod
    def _validate_text(cls, v: str) -> str:
        if v is None:
            return v
        return check_text(str(v), label="配置文本", allow_space=True)

    @field_validator("base_url", mode="before")
    @classmethod
    def _validate_base_url(cls, v: str) -> str:
        if v is None:
            return v
        return check_text(str(v), label="Base URL", pattern=URL_TEXT_PATTERN)

    @field_validator("api_key", mode="before")
    @classmethod
    def _validate_api_key(cls, v: str) -> str:
        if v is None:
            return v
        return check_text(str(v), label="API Key", pattern=SECRET_TEXT_PATTERN)


class LlmConfigUpdate(CamelModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=64)
    base_url: str | None = Field(default=None, min_length=1, max_length=64)
    api_key: str | None = Field(default=None, max_length=64)
    model: str | None = Field(default=None, min_length=1, max_length=64)
    owner: str | None = Field(default=None, max_length=64)
    is_default: bool | None = None
    status: str | None = Field(default=None, max_length=32)

    @field_validator("name", "description", "model", "owner", mode="before")
    @classmethod
    def _validate_text(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return check_text(str(v), label="配置文本", allow_space=True)

    @field_validator("base_url", mode="before")
    @classmethod
    def _validate_base_url(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return check_text(str(v), label="Base URL", pattern=URL_TEXT_PATTERN)

    @field_validator("api_key", mode="before")
    @classmethod
    def _validate_api_key(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return check_text(str(v), label="API Key", pattern=SECRET_TEXT_PATTERN)


class LlmConfigOut(CamelModel):
    id: str
    name: str
    description: str
    base_url: str
    model: str
    owner: str
    is_default: bool
    status: str
    has_api_key: bool
    api_key_masked: str
    created_at: datetime
    updated_at: datetime


class TestConnectionResult(CamelModel):
    ok: bool
    latency_ms: int | None = None
    error: str | None = None
