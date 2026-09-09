from dataclasses import replace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from application.auth import AuthApplication, get_auth_application
from biz.router.register import register_routers
from config.auth import AuthSettings
from infra.redis import MemoryJsonStore


def _fail_closed_app() -> FastAPI:
    settings = replace(
        AuthSettings.from_env(),
        enabled=False,
        allow_insecure_dev_context=False,
        session_backend="memory",
    )
    application = AuthApplication(settings=settings, store=MemoryJsonStore())
    app = FastAPI()
    app.dependency_overrides[get_auth_application] = lambda: application
    register_routers(app)
    return app


@pytest.mark.parametrize(
    ("method", "path", "request_kwargs"),
    [
        ("GET", "/api/v1/auth/me", {}),
        ("GET", "/api/v1/auth/security", {}),
        ("POST", "/api/v1/corrections", {"json": {}}),
        ("POST", "/api/v1/llm-config/llm-configs/config-1/test", {}),
        (
            "POST",
            "/api/v1/workflow-system/definitions/workflow-1/schedules",
            {"json": {}},
        ),
        ("POST", "/api/v1/kg-service/expert-colleague-relation", {"json": {}}),
        (
            "POST",
            "/api/v1/kg-construction/expert-indirect-relations/demo/structured-result",
            {"json": {}},
        ),
        (
            "PUT",
            "/api/v1/schema-management/schemas/schema-1/script",
            {"files": {"file": ("workflow.py", b"def workflow(): pass", "text/x-python")}},
        ),
        ("POST", "/api/v1/manual-reviews/review-1/actions", {"json": {}}),
        ("GET", "/api/v1/workflow-system/definitions", {}),
    ],
)
async def test_reported_routes_reject_anonymous_access_when_auth_is_disabled(
    method: str,
    path: str,
    request_kwargs: dict[str, object],
) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=_fail_closed_app()),
        base_url="http://test",
    ) as client:
        response = await client.request(method, path, **request_kwargs)

    assert response.status_code == 503
    assert response.headers["cache-control"] == "no-store"
