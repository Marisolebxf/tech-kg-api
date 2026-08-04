"""Declarative router registration for the HTTP application."""

from fastapi import APIRouter, FastAPI

from biz.handler.common_capability import router as common_capability_router
from biz.handler.enterprise_background_analysis import (
    router as enterprise_background_analysis_router,
)
from biz.handler.expert_alumni_relation import router as expert_alumni_relation_router
from biz.handler.expert_colleague_relation import router as expert_colleague_relation_router
from biz.handler.expert_cooperation_achievement import (
    router as expert_cooperation_achievement_router,
)
from biz.handler.expert_direct_relation import router as expert_direct_relation_router
from biz.handler.expert_enterprise_mining import router as expert_enterprise_mining_router
from biz.handler.expert_enterprise_relation import router as expert_enterprise_relation_router
from biz.handler.expert_indirect_relation import router as expert_indirect_relation_router
from biz.handler.expert_paper_cooperation import router as expert_paper_cooperation_router
from biz.handler.graph_search import router as graph_search_router
from biz.handler.industry_chain_panorama import router as industry_chain_panorama_router
from biz.handler.industry_chain_topn_event import router as industry_chain_topn_event_router
from biz.handler.kg_construction import router as kg_construction_router
from biz.handler.manual_review import router as manual_review_router
from biz.handler.operator import internal_router as operator_internal_router
from biz.handler.operator import router as operator_router
from biz.handler.options import router as options_router
from biz.handler.platform_overview import router as platform_overview_router
from biz.handler.relation_detail_annotation import router as relation_detail_annotation_router
from biz.handler.schema_management import router as schema_management_router
from biz.handler.system import router as system_router
from biz.handler.task_center import router as task_center_router
from biz.handler.workflow_system import router as workflow_system_router

API_PREFIX = "/api/v1"

API_ROUTERS: tuple[APIRouter, ...] = (
    common_capability_router,
    kg_construction_router,
    options_router,
    platform_overview_router,
    expert_direct_relation_router,
    expert_indirect_relation_router,
    expert_cooperation_achievement_router,
    expert_colleague_relation_router,
    expert_alumni_relation_router,
    expert_paper_cooperation_router,
    expert_enterprise_relation_router,
    relation_detail_annotation_router,
    enterprise_background_analysis_router,
    expert_enterprise_mining_router,
    industry_chain_topn_event_router,
    industry_chain_panorama_router,
    graph_search_router,
    task_center_router,
    manual_review_router,
    workflow_system_router,
    schema_management_router,
    operator_router,
)

ROOT_ROUTERS: tuple[APIRouter, ...] = (system_router, operator_internal_router)


def register_routers(app: FastAPI) -> None:
    for router in API_ROUTERS:
        app.include_router(router, prefix=API_PREFIX)
    for router in ROOT_ROUTERS:
        app.include_router(router)
