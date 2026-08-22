from fastapi import Depends, FastAPI

from biz.dependencies.auth import require_authenticated_user
from biz.handler.auth import router as auth_router
from biz.handler.common_capability import router as common_capability_router
from biz.handler.enterprise_background_analysis import (
    router as enterprise_background_analysis_router,
)
from biz.handler.expert_alumni_relation import legacy_router as expert_alumni_relation_legacy_router
from biz.handler.expert_alumni_relation import router as expert_alumni_relation_router
from biz.handler.expert_colleague_relation import router as expert_colleague_relation_router
from biz.handler.expert_colleague_relation import service_router as expert_colleague_service_router
from biz.handler.expert_cooperation_achievement import (
    legacy_router as expert_cooperation_achievement_legacy_router,
)
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
from biz.handler.industry_node_top_events_business import (
    router as industry_node_top_events_business_router,
)
from biz.handler.kg_construction import router as kg_construction_router
from biz.handler.llm_config import router as llm_config_router
from biz.handler.manual_review import router as manual_review_router
from biz.handler.manual_review_internal import router as manual_review_internal_router
from biz.handler.operator import internal_router as operator_internal_router
from biz.handler.operator import router as operator_router
from biz.handler.options import router as options_router
from biz.handler.platform_overview import router as platform_overview_router
from biz.handler.relation_detail_annotation import router as relation_detail_annotation_router
from biz.handler.schema_management import router as schema_management_router
from biz.handler.task_center import router as task_center_router
from biz.handler.tech_enterprise_relation_business import (
    router as tech_enterprise_relation_business_router,
)
from biz.handler.workflow_system import router as workflow_system_router


def register_routers(app: FastAPI) -> None:
    app.include_router(common_capability_router, prefix="/api/v1")
    app.include_router(kg_construction_router, prefix="/api/v1")
    app.include_router(options_router, prefix="/api/v1")
    app.include_router(platform_overview_router, prefix="/api/v1")
    app.include_router(expert_direct_relation_router, prefix="/api/v1")
    app.include_router(expert_indirect_relation_router, prefix="/api/v1")
    app.include_router(expert_cooperation_achievement_router, prefix="/api/v1")
    app.include_router(expert_colleague_relation_router, prefix="/api/v1")
    app.include_router(expert_colleague_service_router, prefix="/api/v1")
    app.include_router(expert_alumni_relation_router, prefix="/api/v1")
    app.include_router(expert_paper_cooperation_router, prefix="/api/v1")
    app.include_router(expert_enterprise_relation_router, prefix="/api/v1")
    app.include_router(relation_detail_annotation_router, prefix="/api/v1")
    app.include_router(enterprise_background_analysis_router, prefix="/api/v1")
    app.include_router(expert_enterprise_mining_router, prefix="/api/v1")
    app.include_router(industry_chain_topn_event_router, prefix="/api/v1")
    app.include_router(industry_chain_panorama_router, prefix="/api/v1")
    app.include_router(graph_search_router, prefix="/api/v1")
    app.include_router(task_center_router, prefix="/api/v1")
    app.include_router(manual_review_router, prefix="/api/v1")
    app.include_router(workflow_system_router, prefix="/api/v1")
    app.include_router(schema_management_router, prefix="/api/v1")
    app.include_router(llm_config_router, prefix="/api/v1")
    app.include_router(operator_router, prefix="/api/v1")
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(manual_review_internal_router, prefix="/api/v1")

    protected_dependencies = [Depends(require_authenticated_user)]
    protected_routers = (
        common_capability_router,
        kg_construction_router,
        options_router,
        platform_overview_router,
        expert_direct_relation_router,
        expert_indirect_relation_router,
        expert_cooperation_achievement_router,
        expert_cooperation_achievement_legacy_router,
        expert_colleague_relation_router,
        expert_alumni_relation_router,
        expert_alumni_relation_legacy_router,
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
        llm_config_router,
        tech_enterprise_relation_business_router,
        industry_node_top_events_business_router,
        operator_router,
    )
    for router in protected_routers:
        app.include_router(
            router,
            prefix="/api/v1",
            dependencies=protected_dependencies,
        )
    app.include_router(operator_internal_router)
