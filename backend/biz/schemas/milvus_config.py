"""平台 Milvus 配置接口请求模型。"""

from __future__ import annotations

from pydantic import Field

from biz.schemas.schema_management import CamelModel


class MilvusConfigCreate(CamelModel):
    name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="", max_length=500)
    uri: str = Field(default="", max_length=256)
    token: str = Field(default="", max_length=256)
    default_db: str = Field(default="default", max_length=128)
    owner: str = Field(default="", max_length=128)
    is_default: bool = False
    status: str = Field(default="正常")


class MilvusConfigUpdate(CamelModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=500)
    uri: str | None = Field(default=None, max_length=256)
    token: str | None = Field(default=None, max_length=256)
    default_db: str | None = Field(default=None, max_length=128)
    owner: str | None = Field(default=None, max_length=128)
    is_default: bool | None = None
    status: str | None = Field(default=None, max_length=32)
