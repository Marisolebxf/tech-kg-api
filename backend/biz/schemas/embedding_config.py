"""平台 embedding 模型配置接口请求模型。"""

from __future__ import annotations

from pydantic import Field

from biz.schemas.schema_management import CamelModel


class EmbeddingConfigCreate(CamelModel):
    name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="", max_length=500)
    base_url: str = Field(min_length=1, max_length=256)
    api_key: str = Field(default="", max_length=256)
    model: str = Field(min_length=1, max_length=128)
    dimensions: int | None = Field(default=None, ge=1, le=8192)
    owner: str = Field(default="", max_length=128)
    is_default: bool = False
    status: str = Field(default="正常")


class EmbeddingConfigUpdate(CamelModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=500)
    base_url: str | None = Field(default=None, min_length=1, max_length=256)
    api_key: str | None = Field(default=None, max_length=256)
    model: str | None = Field(default=None, min_length=1, max_length=128)
    dimensions: int | None = Field(default=None, ge=1, le=8192)
    owner: str | None = Field(default=None, max_length=128)
    is_default: bool | None = None
    status: str | None = Field(default=None, max_length=32)
