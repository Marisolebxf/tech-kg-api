"""实体检索接口请求模型。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class EntitySearchRequest(BaseModel):
    """实体混合检索请求。"""

    keyword: str = Field(min_length=1, max_length=256, description="搜索关键词")
    space: str | None = Field(default=None, max_length=64, description="图空间，缺省当前空间")
    entityType: str | None = Field(default=None, max_length=64, description="实体类型过滤")
    limit: int = Field(default=10, ge=1, le=100)
    offset: int = Field(default=0, ge=0, le=400)


class EntityReindexRequest(BaseModel):
    """重建实体索引请求。"""

    space: str | None = Field(default=None, max_length=64, description="图空间，缺省当前空间")
    entityTypes: list[str] | None = Field(
        default=None,
        max_length=64,
        description="兼容校验实体类型；为保证 BM25 快照一致，当前始终重建空间全部类型",
    )
