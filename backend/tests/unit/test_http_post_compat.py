"""仅允许 GET/POST 的入口下，操作接口保留原路由的输入与权限语义。"""

import re
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from biz.dependencies.auth import require_authenticated_user, require_platform_actor
from infra.mysql import get_session
from infra.workflow_mysql import get_workflow_session, workflow_mysql_client
from service.platform_access import PlatformActor

# 显式列出兼容契约，避免新增非 GET/POST 路由时静默漏改。
ROUTES = [
    (
        "PUT",
        "/api/v1/admin/members/{user_id}/admin",
        "/api/v1/admin/members/{user_id}/admin/update",
    ),
    (
        "PUT",
        "/api/v1/business-access/businesses/{client_id}",
        "/api/v1/business-access/businesses/{client_id}/update",
    ),
    (
        "PUT",
        "/api/v1/business-access/members/{user_id}",
        "/api/v1/business-access/members/{user_id}/update",
    ),
    (
        "PUT",
        "/api/v1/business-access/spaces/{space_name}",
        "/api/v1/business-access/spaces/{space_name}/update",
    ),
    ("PATCH", "/api/v1/corrections/{correction_id}", "/api/v1/corrections/{correction_id}/update"),
    ("DELETE", "/api/v1/corrections/{correction_id}", "/api/v1/corrections/{correction_id}/delete"),
    ("PUT", "/api/v1/embedding-config/{config_id}", "/api/v1/embedding-config/{config_id}/update"),
    (
        "DELETE",
        "/api/v1/embedding-config/{config_id}",
        "/api/v1/embedding-config/{config_id}/delete",
    ),
    ("DELETE", "/api/v1/graph-spaces/{space_name}", "/api/v1/graph-spaces/{space_name}/unbind"),
    (
        "PUT",
        "/api/v1/llm-config/llm-configs/{config_id}",
        "/api/v1/llm-config/llm-configs/{config_id}/update",
    ),
    (
        "DELETE",
        "/api/v1/llm-config/llm-configs/{config_id}",
        "/api/v1/llm-config/llm-configs/{config_id}/delete",
    ),
    (
        "PUT",
        "/api/v1/manual-reviews/production/{case_id}/draft",
        "/api/v1/manual-reviews/production/{case_id}/draft/update",
    ),
    (
        "DELETE",
        "/api/v1/manual-reviews/production/{case_id}",
        "/api/v1/manual-reviews/production/{case_id}/delete",
    ),
    ("PUT", "/api/v1/milvus-configs/{config_id}", "/api/v1/milvus-configs/{config_id}/update"),
    ("DELETE", "/api/v1/milvus-configs/{config_id}", "/api/v1/milvus-configs/{config_id}/delete"),
    (
        "PUT",
        "/api/v1/mysql-datasources/{datasource_id}",
        "/api/v1/mysql-datasources/{datasource_id}/update",
    ),
    (
        "DELETE",
        "/api/v1/mysql-datasources/{datasource_id}",
        "/api/v1/mysql-datasources/{datasource_id}/delete",
    ),
    (
        "DELETE",
        "/api/v1/schema-management/schemas/{schema_id}",
        "/api/v1/schema-management/schemas/{schema_id}/delete",
    ),
    (
        "DELETE",
        "/api/v1/schema-management/schemas/{schema_id}/properties/{property_name}",
        "/api/v1/schema-management/schemas/{schema_id}/properties/{property_name}/delete",
    ),
    (
        "PUT",
        "/api/v1/schema-management/schemas/{schema_id}/sources",
        "/api/v1/schema-management/schemas/{schema_id}/sources/update",
    ),
    (
        "PUT",
        "/api/v1/schema-management/schemas/{schema_id}/script",
        "/api/v1/schema-management/schemas/{schema_id}/script/update",
    ),
    ("PUT", "/api/v1/task-center/update-policy", "/api/v1/task-center/update-policy"),
    (
        "PUT",
        "/api/v1/workflow-system/schedules/{schedule_id}/state",
        "/api/v1/workflow-system/schedules/{schedule_id}/state",
    ),
    (
        "DELETE",
        "/api/v1/workflow-system/schedules/{schedule_id}",
        "/api/v1/workflow-system/schedules/{schedule_id}/delete",
    ),
    (
        "PUT",
        "/api/v1/workflow-system/jobs/{job_id}/state",
        "/api/v1/workflow-system/jobs/{job_id}/state",
    ),
    (
        "PUT",
        "/api/v1/workflow-system/jobs/{job_id}",
        "/api/v1/workflow-system/jobs/{job_id}/update",
    ),
    (
        "DELETE",
        "/api/v1/workflow-system/jobs/{job_id}",
        "/api/v1/workflow-system/jobs/{job_id}/delete",
    ),
]


class GetPostOnly:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["method"] not in {"GET", "POST"}:
            await JSONResponse({"detail": "HTTP method blocked"}, status_code=405)(
                scope, receive, send
            )
            return
        await self.app(scope, receive, send)


@pytest.fixture
def registered_app(monkeypatch):
    # 路由导入会初始化控制面仓库；只注入测试内存库，不接触部署数据库。
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    monkeypatch.setattr(workflow_mysql_client, "_engine", engine)
    monkeypatch.setattr(workflow_mysql_client, "_session_factory", sessionmaker(bind=engine))
    from biz.router.register import register_routers

    app = FastAPI()
    register_routers(app)
    yield app
    engine.dispose()


def _fields(fields):
    return [(f.name, f.alias, f.type_, f.required, f.default) for f in fields]


def _dependency_contract(dependant):
    return (
        dependant.call,
        dependant.use_cache,
        tuple(dependant.security_scopes or []),
        [
            _fields(getattr(dependant, kind))
            for kind in (
                "path_params",
                "query_params",
                "header_params",
                "cookie_params",
                "body_params",
            )
        ],
        [_dependency_contract(child) for child in dependant.dependencies],
    )


def test_all_legacy_operations_have_equivalent_public_post_routes(registered_app):
    routes = {
        (method, route.path): route
        for route in registered_app.routes
        if isinstance(route, APIRoute)
        for method in route.methods
    }
    assert {(method, path) for method, path in routes if method not in {"GET", "POST"}} == {
        (method, path) for method, path, _ in ROUTES
    }
    schema = registered_app.openapi()["paths"]
    for method, old_path, post_path in ROUTES:
        old = routes[method, old_path]
        new = routes["POST", post_path]
        assert new.endpoint is old.endpoint
        assert _dependency_contract(new.dependant) == _dependency_contract(old.dependant)
        assert new.response_model is old.response_model
        assert new.status_code == old.status_code
        assert new.responses == old.responses
        assert old.deprecated and not old.include_in_schema
        assert new.include_in_schema and not new.deprecated
        assert "post" in schema[post_path]
        assert method.lower() not in schema.get(old_path, {})


@pytest.mark.parametrize("method,old_path,post_path", ROUTES)
async def test_post_aliases_still_require_authentication(
    registered_app, method, old_path, post_path
):
    def reject_anonymous():
        raise HTTPException(401, "authentication required")

    registered_app.dependency_overrides[require_authenticated_user] = reject_anonymous

    def resolve(path):
        return re.sub(r"\{[^}]+\}", "sample", path)

    async with AsyncClient(
        transport=ASGITransport(app=GetPostOnly(registered_app)), base_url="http://test"
    ) as client:
        blocked = await client.request(method, resolve(old_path))
        response = await client.post(resolve(post_path))
    assert blocked.status_code == 405
    assert response.status_code == 401
    assert response.json()["detail"] == "authentication required"


@pytest.fixture
def admin_app(registered_app, monkeypatch):
    actor = PlatformActor("admin", "admin", "管理员", "", True)
    registered_app.dependency_overrides[require_authenticated_user] = lambda: object()
    registered_app.dependency_overrides[require_platform_actor] = lambda: actor
    registered_app.dependency_overrides[get_session] = lambda: None
    registered_app.dependency_overrides[get_workflow_session] = lambda: None
    monkeypatch.setattr("service.business_access_control.rbac_enabled", lambda: False)
    return registered_app


async def test_post_update_delete_and_validation_through_restricted_gateway(admin_app, monkeypatch):
    from biz.handler import milvus_config

    records = {"config-1": {"id": "config-1", "name": "before", "owner": "admin"}}
    updates = []

    def update(config_id, data, **kwargs):
        updates.append(data)
        records[config_id].update(data)
        return records[config_id]

    service = SimpleNamespace(
        get_config=lambda config_id: records.get(config_id),
        update_config=update,
        delete_config=lambda config_id: records.pop(config_id, None) is not None,
    )
    monkeypatch.setattr(milvus_config, "_application", lambda session: service)
    async with AsyncClient(
        transport=ASGITransport(app=GetPostOnly(admin_app)), base_url="http://test"
    ) as client:
        invalid = await client.post("/api/v1/milvus-configs/config-1/update", json={"name": ""})
        assert invalid.status_code == 422
        assert updates == []
        changed = await client.post(
            "/api/v1/milvus-configs/config-1/update", json={"name": "after", "defaultDb": "test"}
        )
        assert changed.status_code == 200
        assert changed.json()["data"]["name"] == "after"
        assert updates == [{"name": "after", "default_db": "test"}]
        deleted = await client.post("/api/v1/milvus-configs/config-1/delete")
        assert deleted.status_code == 200
        assert deleted.json()["data"] == {"deleted": True}
        assert records == {}
        missing = await client.post("/api/v1/milvus-configs/config-1/delete")
        assert missing.status_code == 404


@pytest.mark.parametrize("action", ["update", "delete"])
async def test_post_operations_do_not_bypass_maintainer_role(admin_app, action):
    admin_app.dependency_overrides[require_platform_actor] = lambda: PlatformActor(
        "reader", "reader", "普通用户", "", False
    )
    async with AsyncClient(
        transport=ASGITransport(app=GetPostOnly(admin_app)), base_url="http://test"
    ) as client:
        response = await client.post(
            f"/api/v1/milvus-configs/config-1/{action}", json={"name": "forbidden"}
        )
    assert response.status_code == 403
    assert response.json()["detail"] == "仅开发维护或管理员可以执行该操作"


async def test_post_script_update_preserves_multipart_upload(admin_app, monkeypatch):
    from biz.handler import schema_management

    saved = []

    def replace_script(**kwargs):
        saved.append(kwargs)
        return {"id": kwargs["schema_id"]}

    monkeypatch.setattr(schema_management, "_schema_access", lambda *args: None)
    monkeypatch.setattr(
        schema_management,
        "_application",
        lambda session: SimpleNamespace(replace_script=replace_script),
    )
    script = b"def transform(payload): return payload\n"
    async with AsyncClient(
        transport=ASGITransport(app=GetPostOnly(admin_app)), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/schema-management/schemas/schema-1/script/update",
            files={"script": ("script.py", script, "text/x-python")},
        )
    assert response.status_code == 200
    assert saved == [
        {
            "schema_id": "schema-1",
            "user_id": "admin",
            "is_platform_admin": True,
            "filename": "script.py",
            "content_type": "text/x-python",
            "script_data": script,
        }
    ]


@pytest.mark.parametrize("action", ["update", "delete"])
async def test_post_operations_keep_cross_business_resource_checks(admin_app, monkeypatch, action):
    from biz.handler import milvus_config

    monkeypatch.setattr("service.business_access_control.rbac_enabled", lambda: True)
    admin_app.dependency_overrides[require_platform_actor] = lambda: PlatformActor(
        "developer",
        "developer",
        "开发人员",
        "",
        False,
        business_id="a",
        business_role="developer",
    )
    monkeypatch.setattr(
        milvus_config,
        "_application",
        lambda session: SimpleNamespace(get_config=lambda config_id: {"owner": "business:b"}),
    )
    async with AsyncClient(
        transport=ASGITransport(app=GetPostOnly(admin_app)), base_url="http://test"
    ) as client:
        response = await client.post(
            f"/api/v1/milvus-configs/other-business/{action}", json={"name": "forbidden"}
        )
    assert response.status_code == 403
    assert response.json()["detail"] == "无权访问其他业务配置"


async def test_post_job_state_preserves_false_and_invalid_body(admin_app, monkeypatch):
    from biz.handler import workflow_system

    saved = []

    async def set_state(actor, job_id, active):
        saved.append((actor.user_id, job_id, active))
        return {"id": job_id, "active": active}

    monkeypatch.setattr(workflow_system, "job_service", SimpleNamespace(set_job_state=set_state))
    async with AsyncClient(
        transport=ASGITransport(app=GetPostOnly(admin_app)), base_url="http://test"
    ) as client:
        missing = await client.post("/api/v1/workflow-system/jobs/job-1/state", json={})
        assert missing.status_code == 422
        assert saved == []
        changed = await client.post(
            "/api/v1/workflow-system/jobs/job-1/state", json={"active": False}
        )
    assert changed.status_code == 200
    assert changed.json()["data"] == {"id": "job-1", "active": False}
    assert saved == [("admin", "job-1", False)]


async def test_post_graph_space_unbind_keeps_unbind_response(admin_app, monkeypatch):
    from biz.handler import graph_space

    calls = []

    def unbind(actor, space_name):
        calls.append((actor.user_id, space_name))
        return True

    monkeypatch.setattr(graph_space, "_service", lambda session: SimpleNamespace(unbind=unbind))
    async with AsyncClient(
        transport=ASGITransport(app=GetPostOnly(admin_app)), base_url="http://test"
    ) as client:
        response = await client.post("/api/v1/graph-spaces/test_space/unbind")
    assert response.status_code == 200
    assert response.json()["data"] == {"unbound": True}
    assert calls == [("admin", "test_space")]
