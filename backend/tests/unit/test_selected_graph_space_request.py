"""验证空间选择与实际请求一致，并且并发请求不会串上下文。"""

import asyncio

import pytest
from fastapi import Depends, FastAPI, HTTPException, Request
from httpx import ASGITransport, AsyncClient

from biz.dependencies.auth import require_platform_actor
from biz.dependencies.selected_graph_space import bind_selected_graph_space, resolve_selected_space
from service.graph_space_context import selected_graph_space
from service.platform_access import PlatformActor


@pytest.fixture
def app(monkeypatch):
    actor = PlatformActor("reader", "reader", "reader", "", False)

    def authorize(_actor, space):
        if space == "forbidden":
            raise HTTPException(403, "无权访问")

    monkeypatch.setattr("biz.handler.graph_search._ensure_space_access", authorize)
    application = FastAPI()
    application.dependency_overrides[require_platform_actor] = lambda: actor

    @application.api_route(
        "/probe", methods=["GET", "POST"], dependencies=[Depends(bind_selected_graph_space)]
    )
    async def probe(request: Request):
        before = resolve_selected_space()
        await asyncio.sleep(0.01)
        return {"before": before, "after": resolve_selected_space()}

    @application.get("/graph-search/spaces", dependencies=[Depends(bind_selected_graph_space)])
    async def directory():
        return {"space": selected_graph_space.get()}

    return application


async def test_parallel_requests_have_separate_space_contexts(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        responses = await asyncio.gather(
            *(
                client.get("/probe", headers={"X-Graph-Space": space})
                for space in ("dev", "business_a", "business_b")
            )
        )
    assert [r.json() for r in responses] == [
        {"before": space, "after": space} for space in ("dev", "business_a", "business_b")
    ]
    assert selected_graph_space.get() is None


@pytest.mark.parametrize(
    "params,body",
    [({"space": "other"}, {}), ({}, {"space": "other"}), ({}, {"graphSpace": "other"})],
)
async def test_conflicting_header_and_payload_rejected(app, params, body):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/probe", params=params, json=body, headers={"X-Graph-Space": "dev"}
        )
    assert response.status_code == 400
    assert selected_graph_space.get() is None


async def test_header_is_authorized_before_handler_and_directory_can_recover(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/probe", headers={"X-Graph-Space": "forbidden"})
        directory = await client.get("/graph-search/spaces", headers={"X-Graph-Space": "forbidden"})
    assert response.status_code == 403
    assert directory.status_code == 200
    assert directory.json() == {"space": None}


async def test_explicit_legacy_query_and_body_are_preserved(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        query = await client.get("/probe", params={"space": "business_a"})
        body = await client.post("/probe", json={"space": "business_b"})
    assert query.json()["after"] == "business_a"
    assert body.json()["after"] == "business_b"
