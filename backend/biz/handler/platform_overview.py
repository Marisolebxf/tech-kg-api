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


async def _get_overview() -> PlatformOverviewData:
    # TRSGraph 客户端为同步实现，放在线程中避免阻塞 FastAPI 事件循环。
    return await asyncio.to_thread(application.get_overview)


@router.get("", response_model=PlatformOverviewResponse)
async def get_platform_overview() -> PlatformOverviewResponse:
    return PlatformOverviewResponse(data=await _get_overview())


@router.get("/assets", response_model=PlatformAssetSummaryResponse)
async def get_platform_assets() -> PlatformAssetSummaryResponse:
    overview = await _get_overview()
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


@router.get("/changes", response_model=PlatformAssetChangesResponse)
async def get_platform_asset_changes(
    asset_type: Annotated[AssetOverviewKey, Query(alias="assetType")] = "entity",
) -> PlatformAssetChangesResponse:
    overview = await _get_overview()
    return PlatformAssetChangesResponse(
        data=PlatformAssetChangesData(
            asset_type=asset_type,
            rows=overview.asset_change_rows[asset_type],
            data_source=overview.data_sources.get("todayChanges", "unknown"),
        )
    )


@router.get("/activity", response_model=PlatformActivityResponse)
async def get_platform_activity() -> PlatformActivityResponse:
    overview = await _get_overview()
    return PlatformActivityResponse(
        data=PlatformActivityData(
            items=overview.latest_changes,
            data_source=overview.data_sources.get("todayChanges", "unknown"),
        )
    )


@router.get("/risks", response_model=PlatformRiskResponse)
async def get_platform_risks() -> PlatformRiskResponse:
    overview = await _get_overview()
    return PlatformRiskResponse(
        data=PlatformRiskData(
            items=overview.management_risks,
            data_source=overview.data_sources.get("managementRisks", "unknown"),
        )
    )


@router.get("/structures", response_model=PlatformStructureResponse)
async def get_platform_structures() -> PlatformStructureResponse:
    overview = await _get_overview()
    return PlatformStructureResponse(
        data=PlatformStructureData(
            entity=overview.entity_structure,
            relation=overview.relation_structure,
            data_source=overview.data_sources.get("graphAssets", "unknown"),
        )
    )
