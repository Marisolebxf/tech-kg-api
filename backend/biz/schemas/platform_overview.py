"""平台首页总览接口模型。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from biz.schemas.common import ApiResponse

AssetOverviewKey = Literal["entity", "relation"]


def _to_camel(value: str) -> str:
    first, *rest = value.split("_")
    return first + "".join(part.capitalize() for part in rest)


class CamelCaseModel(BaseModel):
    """Python 使用 snake_case，接口响应序列化为前端习惯的 camelCase。"""

    model_config = ConfigDict(alias_generator=_to_camel, populate_by_name=True)


class AssetOverviewGroup(CamelCaseModel):
    key: AssetOverviewKey
    title: str
    total: str
    total_label: str
    added: str
    added_label: str


class AssetChangeRow(CamelCaseModel):
    type: str
    object: str
    change: str
    source: str
    time: str


class StructureMember(CamelCaseModel):
    """分段成员（图内真实标签/边类型）及其计数，供前端悬停浮窗展示。"""

    name: str
    count: int


class StructureItem(CamelCaseModel):
    label: str
    schema_name: str = Field(alias="schema")
    # 全部非零成员（按计数降序，展示名=Schema 目录中文名）；降级空态无成员
    members: list[StructureMember] = []
    count: str
    ratio: int
    tone: str
    # 「其他实体/其他关系」聚合段：前端只对它开悬浮（浮窗列成员 Schema 清单）
    is_other: bool = False


class PlatformOverviewData(CamelCaseModel):
    platform_status: str
    pending_batch_count: int
    updated_at: str
    asset_overview_groups: list[AssetOverviewGroup]
    asset_change_rows: dict[AssetOverviewKey, list[AssetChangeRow]]
    # 昨日新增真实计数（Σwritten，与资产卡徽标同源）：抽屉明细行有单执行
    # 50 条上限，行数 ≠ 徽标数时前端用它展示「共 N 条 · 展示前 n 条」
    asset_change_totals: dict[AssetOverviewKey, int] = Field(default_factory=dict)
    entity_structure: list[StructureItem]
    relation_structure: list[StructureItem]
    data_mode: Literal["partial", "mock"] = "mock"
    data_sources: dict[str, str] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class PlatformAssetSummaryData(CamelCaseModel):
    platform_status: str
    pending_batch_count: int
    updated_at: str
    data_mode: Literal["partial", "mock"]
    data_sources: dict[str, str]
    warnings: list[str]
    items: list[AssetOverviewGroup]


class PlatformAssetChangesData(CamelCaseModel):
    asset_type: AssetOverviewKey
    rows: list[AssetChangeRow]
    data_source: str


class PlatformStructureData(CamelCaseModel):
    entity: list[StructureItem]
    relation: list[StructureItem]
    data_source: str


class PlatformOverviewResponse(ApiResponse):
    data: PlatformOverviewData


class PlatformAssetSummaryResponse(ApiResponse):
    data: PlatformAssetSummaryData


class PlatformAssetChangesResponse(ApiResponse):
    data: PlatformAssetChangesData


class PlatformStructureResponse(ApiResponse):
    data: PlatformStructureData
