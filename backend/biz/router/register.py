from fastapi import FastAPI

from biz.handler.binding import router as binding_router
from biz.handler.enterprise_background_analysis import (
    router as enterprise_background_analysis_router,
)
from biz.handler.expert_alumni_relation import router as expert_alumni_relation_router
from biz.handler.expert_colleague_relation import router as expert_colleague_relation_router
from biz.handler.expert_cooperation_achievement import (
    router as expert_cooperation_achievement_router,
)
from biz.handler.expert_direct_relation import router as expert_direct_relation_router
from biz.handler.expert_enterprise_relation import router as expert_enterprise_relation_router
from biz.handler.expert_indirect_relation import router as expert_indirect_relation_router
from biz.handler.expert_paper_cooperation import router as expert_paper_cooperation_router
from biz.handler.industry_chain_panorama import router as industry_chain_panorama_router
from biz.handler.industry_chain_topn_event import router as industry_chain_topn_event_router
from biz.handler.kg_construction import router as kg_construction_router
from biz.handler.options import router as options_router
from biz.handler.relation_detail_annotation import router as relation_detail_annotation_router
from integration.legacy_mount import register_legacy_routers


def register_routers(app: FastAPI) -> None:
    app.include_router(binding_router, prefix="/api/v1")
    app.include_router(kg_construction_router, prefix="/api/v1")
    app.include_router(options_router, prefix="/api/v1")
    app.include_router(expert_direct_relation_router, prefix="/api/v1")
    app.include_router(expert_indirect_relation_router, prefix="/api/v1")
    app.include_router(expert_cooperation_achievement_router, prefix="/api/v1")
    app.include_router(expert_colleague_relation_router, prefix="/api/v1")
    app.include_router(expert_alumni_relation_router, prefix="/api/v1")
    app.include_router(expert_paper_cooperation_router, prefix="/api/v1")
    app.include_router(expert_enterprise_relation_router, prefix="/api/v1")
    app.include_router(relation_detail_annotation_router, prefix="/api/v1")
    app.include_router(enterprise_background_analysis_router, prefix="/api/v1")
    app.include_router(industry_chain_topn_event_router, prefix="/api/v1")
    app.include_router(industry_chain_panorama_router, prefix="/api/v1")
    register_legacy_routers(app)
