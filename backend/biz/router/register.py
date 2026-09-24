from fastapi import Depends, FastAPI

from biz.dependencies.auth import (
    CurrentActor,
    require_authenticated_user,
    require_platform_admin,
    require_platform_maintainer,
)
from biz.handler.admin_member import router as admin_member_router
from biz.handler.auth import router as auth_router
from biz.handler.common_capability import router as common_capability_router
from biz.handler.correction import router as correction_router
from biz.handler.embedding_config import router as embedding_config_router
from biz.handler.enterprise_background_analysis import (
    router as enterprise_background_analysis_router,
)
from biz.handler.entity_search import router as entity_search_router
from biz.handler.expert_alumni_relation import router as expert_alumni_relation_router
from biz.handler.expert_colleague_relation import router as expert_colleague_relation_router
from biz.handler.expert_colleague_relation import service_router as expert_colleague_service_router
from biz.handler.expert_cooperation_achievement import (
    router as expert_cooperation_achievement_router,
)
from biz.handler.expert_direct_relation import router as expert_direct_relation_router
from biz.handler.expert_enterprise_mining import router as expert_enterprise_mining_router
from biz.handler.expert_enterprise_relation import router as expert_enterprise_relation_router
from biz.handler.expert_indirect_relation import router as expert_indirect_relation_router
from biz.handler.expert_paper_cooperation import router as expert_paper_cooperation_router
from biz.handler.graph_algorithm import router as graph_algorithm_router
from biz.handler.graph_console import router as graph_console_router
from biz.handler.graph_search import router as graph_search_router
from biz.handler.graph_space import readonly_router as graph_space_readonly_router
from biz.handler.graph_space import router as graph_space_router
from biz.handler.industry_chain_panorama import router as industry_chain_panorama_router
from biz.handler.industry_chain_topn_event import router as industry_chain_topn_event_router
from biz.handler.industry_node_top_events_business import (
    router as industry_node_top_events_business_router,
)
from biz.handler.kg_construction import router as kg_construction_router
from biz.handler.llm_config import router as llm_config_router
from biz.handler.manual_review import readonly_router as manual_review_readonly_router
from biz.handler.manual_review import router as manual_review_router
from biz.handler.milvus_config import router as milvus_config_router
from biz.handler.mysql_datasource import router as mysql_datasource_router
from biz.handler.options import router as options_router
from biz.handler.platform_overview import router as platform_overview_router
from biz.handler.project_relation import router as project_relation_router
from biz.handler.relation_detail_annotation import router as relation_detail_annotation_router
from biz.handler.schema_management import router as schema_management_router
from biz.handler.task_center import router as task_center_router
from biz.handler.tech_enterprise_relation_business import (
    router as tech_enterprise_relation_business_router,
)
from biz.handler.workflow_system import readonly_router as workflow_system_readonly_router
from biz.handler.workflow_system import router as workflow_system_router

API_V1_PREFIX = "/api/v1"


def require_business_data(actor: CurrentActor) -> None:
    from service.business_access_control import ensure_space_access, rbac_enabled

    if rbac_enabled():
        ensure_space_access(actor, None, "read")


def require_legacy_admin(actor: CurrentActor) -> None:
    from fastapi import HTTPException

    from service.business_access_control import rbac_enabled

    if rbac_enabled() and not actor.is_admin:
        raise HTTPException(403, "未归属业务的旧管理资源仅管理员可访问")


def register_routers(app: FastAPI) -> None:
    app.include_router(auth_router, prefix=API_V1_PREFIX)
    # 该路由自身执行 API Key / 用户双通道认证，不叠加仅接受用户的依赖。
    app.include_router(project_relation_router, prefix=API_V1_PREFIX)

    protected_dependencies = [Depends(require_authenticated_user)]
    business_routers = (
        common_capability_router,
        kg_construction_router,
        options_router,
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
        expert_colleague_service_router,
        tech_enterprise_relation_business_router,
        industry_node_top_events_business_router,
    )
    protected_routers = (
        common_capability_router,
        kg_construction_router,
        options_router,
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
        graph_console_router,
        graph_algorithm_router,
        entity_search_router,
        correction_router,
        expert_colleague_service_router,
        tech_enterprise_relation_business_router,
        industry_node_top_events_business_router,
        # 平台总览页数据对所有登录用户只读开放（页面卡片对普通用户不可点击）：
        platform_overview_router,
        workflow_system_readonly_router,
        manual_review_readonly_router,
        graph_space_readonly_router,
    )
    for router in protected_routers:
        dependencies = list(protected_dependencies)
        if any(router is business_router for business_router in business_routers):
            dependencies.append(Depends(require_business_data))
        if router is correction_router:
            dependencies.append(Depends(require_legacy_admin))
        app.include_router(
            router,
            prefix=API_V1_PREFIX,
            dependencies=dependencies,
        )
    admin_dependencies = [Depends(require_authenticated_user), Depends(require_platform_admin)]
    maintainer_dependencies = [
        Depends(require_authenticated_user),
        Depends(require_platform_maintainer),
    ]
    maintainer_routers = (
        task_center_router,
        workflow_system_router,
        schema_management_router,
        llm_config_router,
        mysql_datasource_router,
        milvus_config_router,
        embedding_config_router,
        manual_review_router,
    )
    for router in maintainer_routers:
        app.include_router(router, prefix=API_V1_PREFIX, dependencies=maintainer_dependencies)
    for router in (admin_member_router, graph_space_router):
        app.include_router(router, prefix=API_V1_PREFIX, dependencies=admin_dependencies)
