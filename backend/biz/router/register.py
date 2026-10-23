from fastapi import Depends, FastAPI, Request

from biz.dependencies.auth import (
    CurrentActor,
    require_authenticated_user,
    require_platform_admin,
    require_platform_maintainer,
)
from biz.handler.admin_member import router as admin_member_router
from biz.handler.auth import router as auth_router
from biz.handler.business_access import management_router as business_access_router
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
from biz.handler.kg_open import router as kg_open_router
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


async def require_business_data(request: Request, actor: CurrentActor):
    import asyncio

    from fastapi import HTTPException

    from biz.dependencies.selected_graph_space import read_request_graph_space
    from service.business_access_control import ensure_space_access, rbac_enabled
    from service.graph_space import SPACE_NAME_PATTERN
    from service.graph_space_context import (
        business_data_plane,
        business_space_override,
        get_current_space,
        request_can_write,
        selected_graph_space,
    )

    space = await read_request_graph_space(request) or get_current_space()
    # X-Business-Graph-Space：按请求覆盖九大业务取数空间（测试旋钮，只改空间名，
    # 连接参数仍取业务面/平台面 env）。与 X-Graph-Space 分开解析，避免下拉空间
    # 一致性校验误伤；空间绑定校验仍走请求空间（与 env 钉死同信任级）。
    override_values = request.headers.getlist("X-Business-Graph-Space")
    if len(override_values) > 1:
        raise HTTPException(400, "X-Business-Graph-Space 头只能出现一次")
    override_value = override_values[0].strip() if override_values else ""
    if override_value and not SPACE_NAME_PATTERN.fullmatch(override_value):
        raise HTTPException(
            400, "图空间名称格式不正确（字母/数字/下划线，字母或下划线开头，最长 64）"
        )
    await asyncio.to_thread(ensure_space_access, actor, space, "read")
    can_write = actor.is_admin and not actor.business_only
    if rbac_enabled():
        try:
            await asyncio.to_thread(ensure_space_access, actor, space, "write")
            can_write = True
        except HTTPException as exc:
            if exc.status_code != 403:
                raise
            can_write = False
    from biz.prewarm_business import is_readonly_prewarm

    if is_readonly_prewarm(request):
        can_write = False
    from service.llm_context import (
        request_llm_business,
        request_llm_settings,
        selected_llm_business,
    )

    business = await asyncio.to_thread(request_llm_business, actor, space)
    token = selected_graph_space.set(space)
    # 本依赖即「九大业务」边界：置位后图连接走 TRS_GRAPH_BUSINESS_*（未配置则不变）。
    business_token = business_data_plane.set(True)
    override_token = business_space_override.set(override_value or None)
    write_token = request_can_write.set(can_write)
    llm_token = selected_llm_business.set(business)
    settings_token = request_llm_settings.set({})
    try:
        yield
    finally:
        request_llm_settings.reset(settings_token)
        selected_llm_business.reset(llm_token)
        request_can_write.reset(write_token)
        business_space_override.reset(override_token)
        business_data_plane.reset(business_token)
        selected_graph_space.reset(token)


def require_legacy_admin(actor: CurrentActor) -> None:
    from fastapi import HTTPException

    from service.business_access_control import rbac_enabled

    if rbac_enabled() and not actor.is_admin:
        raise HTTPException(403, "未归属业务的旧管理资源仅管理员可访问")


def register_routers(app: FastAPI) -> None:
    app.include_router(auth_router, prefix=API_V1_PREFIX)
    # 该路由自身执行 API Key / 用户双通道认证，不叠加仅接受用户的依赖。
    app.include_router(project_relation_router, prefix=API_V1_PREFIX)
    # kg-open 对外查询同项目关系接口：自带双通道认证，不叠加仅接受用户的依赖。
    app.include_router(kg_open_router, prefix=API_V1_PREFIX)

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
        graph_space_router,
        business_access_router,
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
    for router in (admin_member_router,):
        app.include_router(router, prefix=API_V1_PREFIX, dependencies=admin_dependencies)
