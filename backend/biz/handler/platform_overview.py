"""平台首页总览路由。"""

import asyncio
from typing import Annotated

from fastapi import APIRouter, Query

from application.platform_overview import PlatformOverviewApplication
from biz.schemas.platform_overview import (
    AssetOverviewKey,
    PlatformActivityData,
    PlatformActivityResponse,
    PlatformAssetChangesData,
    PlatformAssetChangesResponse,
    PlatformAssetSummaryData,
    PlatformAssetSummaryResponse,
    PlatformOverviewData,
    PlatformOverviewResponse,
    PlatformRiskData,
    PlatformRiskResponse,
    PlatformStructureData,
    PlatformStructureResponse,
)

router = APIRouter(prefix="/platform/overview", tags=["platform-overview"])
application = PlatformOverviewApplication()


async def _get_overview(space: str | None = None) -> PlatformOverviewData:
    # TRSGraph 客户端为同步实现，放在线程中避免阻塞 FastAPI 事件循环。
    # space：全局图空间选择器当前空间（缺省回落 env 默认空间，兼容旧调用方）。
    return await asyncio.to_thread(application.get_overview, space)


@router.get("")
async def get_platform_overview(
    space: Annotated[str | None, Query(max_length=64)] = None,
) -> PlatformOverviewResponse:
    return PlatformOverviewResponse(data=await _get_overview(space))


@router.get("/assets")
async def get_platform_assets(
    space: Annotated[str | None, Query(max_length=64)] = None,
) -> PlatformAssetSummaryResponse:
    overview = await _get_overview(space)
    return PlatformAssetSummaryResponse(
        data=PlatformAssetSummaryData(
            platform_status=overview.platform_status,
            pending_batch_count=overview.pending_batch_count,
            updated_at=overview.updated_at,
            data_mode=overview.data_mode,
            data_sources=overview.data_sources,
            warnings=overview.warnings,
            items=overview.asset_overview_groups,
        )
    )


@router.get("/changes")
async def get_platform_asset_changes(
    asset_type: Annotated[AssetOverviewKey, Query(alias="assetType")] = "entity",
    space: Annotated[str | None, Query(max_length=64)] = None,
) -> PlatformAssetChangesResponse:
    overview = await _get_overview(space)
    return PlatformAssetChangesResponse(
        data=PlatformAssetChangesData(
            asset_type=asset_type,
            rows=overview.asset_change_rows[asset_type],
            data_source=overview.data_sources.get("todayChanges", "unknown"),
        )
    )


@router.get("/activity")
async def get_platform_activity(
    space: Annotated[str | None, Query(max_length=64)] = None,
) -> PlatformActivityResponse:
    overview = await _get_overview(space)
    return PlatformActivityResponse(
        data=PlatformActivityData(
            items=overview.latest_changes,
            data_source=overview.data_sources.get("todayChanges", "unknown"),
        )
    )


@router.get("/risks")
async def get_platform_risks(
    space: Annotated[str | None, Query(max_length=64)] = None,
) -> PlatformRiskResponse:
    overview = await _get_overview(space)
    return PlatformRiskResponse(
        data=PlatformRiskData(
            items=overview.management_risks,
            data_source=overview.data_sources.get("managementRisks", "unknown"),
        )
    )


@router.get("/structures")
async def get_platform_structures(
    space: Annotated[str | None, Query(max_length=64)] = None,
) -> PlatformStructureResponse:
    overview = await _get_overview(space)
    return PlatformStructureResponse(
        data=PlatformStructureData(
            entity=overview.entity_structure,
            relation=overview.relation_structure,
            data_source=overview.data_sources.get("graphAssets", "unknown"),
        )
    )
