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
    """昨日新增明细行（2026-10-14 起聚合格式）：一行 = 一个写入块
    （统计日 × 空间 × kind × Schema × 执行 × 来源），数量列给该块的
    written 精确计数；页面按「数据类型/数量/来源/识别时间」展示，
    不再逐对象列出（对象级明细链路保留在 service，未接线）。"""

    type: str
    count: int = 0
    source: str
    time: str
    # 真实工作流任务 ID；旧执行未记录任务时留空，不按来源名称猜测任务。
    task_id: str | None = None
    # 同一条执行所属的图谱构建任务（job-xxx）；与 task_id 同源（同一条执行记录），
    # 旧执行未记录时留空。
    job_id: str | None = None
    # 该行写入块归属的执行 ID（EXEC-xxx）：行级跳转据此直达任务详情页的
    # 那一次执行——任务可多次运行，只落任务页会默认展示最新执行、数字对不上。
    exec_id: str | None = None
    object_id: str | None = None
    # 写图执行的终态（COMPLETED/ABNORMAL/TERMINATED/CANCELED/FAILED）：中断执行
    # 也计入昨日新增（已落图批次是真实写入），页面据此对中断行标注「已中断/失败」。
    exec_status: str | None = None
    # 逐对象时代的展示字段：聚合格式下不再随接口序列化，仅供反查链路内部
    # 与单测使用（object=对象名/「Schema · N 条」，change=「新增 schemaKey」）。
    object: str = Field(default="", exclude=True)
    change: str = Field(default="", exclude=True)
    is_aggregate: bool = Field(default=False, exclude=True)


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
    # 统计日（日窗口时区自然日，YYYY-MM-DD）：昨日新增实际归属的日子，页面直接
    # 展示它，不再自行推算「昨天」——多 worker 缓存异常时用户一眼可辨
    stats_day: str = ""
    asset_overview_groups: list[AssetOverviewGroup]
    asset_change_rows: dict[AssetOverviewKey, list[AssetChangeRow]]
    # 与逐对象明细同源：完整读取时，徽标、合计和实际记录数一致。
    asset_change_totals: dict[AssetOverviewKey, int] = Field(default_factory=dict)
    asset_change_errors: dict[AssetOverviewKey, str] = Field(default_factory=dict)
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
