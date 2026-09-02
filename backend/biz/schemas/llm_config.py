"""平台 LLM 配置接口请求/响应模型。"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from biz.schemas.schema_management import CamelModel


class LlmConfigCreate(CamelModel):
    name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="", max_length=500)
    base_url: str = Field(min_length=1, max_length=256)
    api_key: str = Field(default="", max_length=256)
    model: str = Field(min_length=1, max_length=128)
    owner: str = Field(default="", max_length=128)
    is_default: bool = False
    status: str = Field(default="正常")


class LlmConfigUpdate(CamelModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=500)
    base_url: str | None = Field(default=None, min_length=1, max_length=256)
    api_key: str | None = Field(default=None, max_length=256)
    model: str | None = Field(default=None, min_length=1, max_length=128)
    owner: str | None = Field(default=None, max_length=128)
    is_default: bool | None = None
    status: str | None = Field(default=None, max_length=32)


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


class LlmConfigVerifyRequest(CamelModel):
    """未保存前的连通性验证：直接用弹窗里的原始参数。"""

    base_url: str = Field(min_length=1, max_length=256)
    model: str = Field(min_length=1, max_length=128)
    api_key: str = Field(min_length=1, max_length=256)
