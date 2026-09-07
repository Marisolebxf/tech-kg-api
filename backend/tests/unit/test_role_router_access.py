"""运行真实注册器和 FastAPI 鉴权依赖；用无业务副作用的探针替代各领域 handler。"""

import ast
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest
from fastapi import APIRouter, FastAPI
from httpx import ASGITransport, AsyncClient

from biz.dependencies.auth import require_authenticated_user, require_platform_actor
from service.auth import AuthContext
from service.platform_access import PlatformActor

ADMIN_ROUTERS = [
    "platform_overview_router",
    "schema_management_router",
    "task_center_router",
    "workflow_system_router",
    "manual_review_router",
    "operator_router",
    "admin_member_router",
    "llm_config_router",
    "mysql_datasource_router",
    "milvus_config_router",
    "embedding_config_router",
    "graph_space_router",
]
USER_ROUTERS = [
    "graph_search_router",
    "graph_console_router",
    "entity_search_router",
    "expert_direct_relation_router",
    "expert_indirect_relation_router",
    "expert_cooperation_achievement_router",
    "expert_colleague_relation_router",
    "expert_alumni_relation_router",
    "expert_paper_cooperation_router",
    "tech_enterprise_relation_business_router",
    "industry_node_top_events_business_router",
    "industry_chain_panorama_router",
    "options_router",
    "correction_router",
]


@pytest.fixture
def app(monkeypatch):
    source = Path(__file__).resolve().parents[2] / "biz" / "router" / "register.py"
    for node in ast.parse(source.read_text(encoding="utf-8")).body:
        if not isinstance(node, ast.ImportFrom) or not (node.module or "").startswith(
            "biz.handler."
        ):
            continue
        handler = sys.modules.get(node.module)
        if handler is None or getattr(handler, "_role_probe", False) is False:
            handler = ModuleType(node.module)
            handler._role_probe = True
            monkeypatch.setitem(sys.modules, node.module, handler)
        for imported in node.names:
            router = APIRouter()

            async def probe():
                return {"ok": True}

            router.add_api_route(f"/probe/{imported.asname}", probe, methods=["GET", "POST"])
            setattr(handler, imported.name, router)
    spec = importlib.util.spec_from_file_location("_role_registration_under_test", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    app = FastAPI()
    module.register_routers(app)
    app.dependency_overrides[require_authenticated_user] = lambda: AuthContext("token", {}, None)
    return app


@pytest.mark.parametrize("router_name", ADMIN_ROUTERS)
@pytest.mark.parametrize("is_admin", [False, True])
async def test_management_api_rejects_ordinary_user_before_handler(app, router_name, is_admin):
    app.dependency_overrides[require_platform_actor] = lambda: PlatformActor(
        "user", "user", "user", "", is_admin
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for method in ("GET", "POST"):
            response = await client.request(method, f"/api/v1/probe/{router_name}")
            assert response.status_code == (200 if is_admin else 403)


@pytest.mark.parametrize("router_name", USER_ROUTERS)
async def test_query_and_business_routers_remain_available_to_ordinary_user(app, router_name):
    app.dependency_overrides[require_platform_actor] = lambda: PlatformActor(
        "user", "user", "user", "", False
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(f"/api/v1/probe/{router_name}")
        assert response.status_code == 200
