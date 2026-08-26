"""平台 MySQL 数据源接口请求模型。"""

from __future__ import annotations

from pydantic import Field

from biz.schemas.schema_management import CamelModel


class MysqlDatasourceCreate(CamelModel):
    name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="", max_length=500)
    host: str = Field(min_length=1, max_length=256)
    port: int = Field(default=3306, ge=1, le=65535)
    default_database: str = Field(default="", max_length=128)
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(default="", max_length=256)
    owner: str = Field(default="", max_length=128)
    is_default: bool = False
    status: str = Field(default="正常")


class MysqlDatasourceUpdate(CamelModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=500)
    host: str | None = Field(default=None, min_length=1, max_length=256)
    port: int | None = Field(default=None, ge=1, le=65535)
    default_database: str | None = Field(default=None, max_length=128)
    username: str | None = Field(default=None, min_length=1, max_length=128)
    password: str | None = Field(default=None, max_length=256)
    owner: str | None = Field(default=None, max_length=128)
    is_default: bool | None = None
    status: str | None = Field(default=None, max_length=32)
