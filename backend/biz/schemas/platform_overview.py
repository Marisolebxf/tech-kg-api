"""平台首页总览接口模型。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from biz.schemas.common import ApiResponse

AssetOverviewKey = Literal["entity", "relation", "property"]


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


class LatestChange(CamelCaseModel):
    time: str
    type: str
    domain: str
    title: str
    detail: str
    impact: str
    to: str


class ManagementRisk(CamelCaseModel):
    title: str
    detail: str
    detail_to: str
    review_to: str


class StructureItem(CamelCaseModel):
    label: str
    schema_name: str = Field(alias="schema")
    count: str
    ratio: int
    tone: str


class PlatformOverviewData(CamelCaseModel):
    platform_status: str
    pending_batch_count: int
    updated_at: str
    asset_overview_groups: list[AssetOverviewGroup]
    asset_change_rows: dict[AssetOverviewKey, list[AssetChangeRow]]
    latest_changes: list[LatestChange]
    management_risks: list[ManagementRisk]
    entity_structure: list[StructureItem]
    relation_structure: list[StructureItem]


class PlatformOverviewResponse(ApiResponse):
    data: PlatformOverviewData
