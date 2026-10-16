"""真实请求、权限与模型 HTTP 调用串联，验证业务默认不串用。"""

import asyncio
import json
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime

import httpx
import openai
import pytest
from fastapi import Depends, FastAPI, Request
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from biz.dependencies.auth import require_platform_actor
from biz.handler import common_capability, llm_config
from biz.router.register import require_business_data
from db_model.base import Base
from db_model.business_access import BusinessClient, BusinessGraphSpace, BusinessSpacePolicy
from db_model.config_ownership import ConfigOwnership
from db_model.llm_config import LlmConfig
from db_model.llm_default import BusinessLlmDefault
from infra.mysql import get_session
from service.llm_context import selected_llm_business
from service.platform_access import BusinessMembershipGrant, PlatformActor


@pytest.fixture
def model_api(monkeypatch):
    monkeypatch.setenv("BUSINESS_RBAC_ENABLED", "true")
    engine = create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(
        engine,
        tables=[
            BusinessClient.__table__,
            BusinessGraphSpace.__table__,
            BusinessSpacePolicy.__table__,
            ConfigOwnership.__table__,
            LlmConfig.__table__,
            BusinessLlmDefault.__table__,
        ],
    )
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as session:
        session.add_all([BusinessClient(client_id=b, name=b) for b in ("a", "b")])
        session.flush()
        session.add_all(
            [
                BusinessGraphSpace(space_name="public", is_shared_production=True),
                BusinessGraphSpace(space_name="space_a", client_id="a", is_shared_production=False),
                BusinessGraphSpace(space_name="space_b", client_id="b", is_shared_production=False),
            ]
        )
        for model_id, business in (
            ("public_one", None),
            ("public_two", None),
            ("private_a", "a"),
            ("private_b", "b"),
        ):
            session.add(
                LlmConfig(
                    id=model_id,
                    name=model_id,
                    base_url=f"https://{model_id}.test/v1",
                    api_key=f"test-key-{model_id}",
                    model=model_id,
                    owner="admin",
                    is_default=model_id == "public_one",
                    status="正常",
                    created_at=datetime.now(),
                    updated_at=datetime.now(),
                )
            )
            session.add(
                ConfigOwnership(config_kind="llm", config_id=model_id, business_id=business)
            )
        session.commit()

    @contextmanager
    def session_scope():
        with factory() as session:
            yield session

    monkeypatch.setattr("infra.mysql.session_scope", session_scope)
    monkeypatch.setattr("infra.mysql.create_session", factory)
    monkeypatch.setattr("service.business_access_control.session_scope", session_scope)
    llm_config._config_cache_clear()

    app = FastAPI()

    def actor(request: Request):
        identity = request.headers.get("test-user", "admin")
        business = "a" if identity in ("a", "a_colleague") else "b"
        memberships = (BusinessMembershipGrant(business, "developer"),)
        if identity == "admin":
            memberships = ()
        elif identity == "multi":
            memberships = (BusinessMembershipGrant("a"), BusinessMembershipGrant("b"))
        return replace(
            PlatformActor(
                user_id=identity,
                username=identity,
                display_name=identity,
                email="",
                is_admin=identity == "admin",
                memberships=memberships,
            ),
            context_business_id=request.headers.get("X-Business-Id", ""),
        )

    def db():
        with factory() as session:
            yield session

    app.dependency_overrides[require_platform_actor] = actor
    app.dependency_overrides[get_session] = db
    app.include_router(llm_config.router)
    app.include_router(common_capability.router, dependencies=[Depends(require_business_data)])

    requests = []

    def model_response(request):
        body = json.loads(request.content)
        requests.append((request.url.host, body["model"]))
        return httpx.Response(
            200,
            json={
                "id": "completion-test",
                "object": "chat.completion",
                "created": 1,
                "model": body["model"],
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": '{"entities":[],"relations":[]}',
                        },
                    }
                ],
            },
        )

    original_client = openai.OpenAI

    def mock_client(**kwargs):
        return original_client(
            **kwargs, http_client=httpx.Client(transport=httpx.MockTransport(model_response))
        )

    monkeypatch.setattr("openai.OpenAI", mock_client)
    monkeypatch.setattr("infra.llm.OpenAI", mock_client)
    monkeypatch.setattr("service.common.entity_extraction.OpenAI", mock_client)
    yield app, requests
    engine.dispose()


def headers(user, space="public", business=None):
    values = {"test-user": user, "X-Graph-Space": space}
    if business:
        values["X-Business-Id"] = business
    return values


async def choose(client, user, model):
    response = await client.post(
        f"/llm-config/llm-configs/{model}/set-default", headers=headers(user)
    )
    assert response.status_code == 200, response.text


async def call_model(client, user, **kwargs):
    return await client.post(
        "/common-capabilities/relation-extraction",
        headers=headers(user, **kwargs),
        json={"text": "甲公司收购乙公司", "method": "llm"},
    )


async def test_real_calls_follow_public_until_business_pins_its_own_default(model_api):
    app, requests = model_api
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://test"
    ) as client:
        assert (await call_model(client, "a")).status_code == 200
        assert requests[-1] == ("public_one.test", "public_one")
        await choose(client, "a", "public_one")
        await choose(client, "admin", "public_two")
        for user, model in (
            ("a_colleague", "public_one"),
            ("b", "public_two"),
            ("admin", "public_two"),
        ):
            assert (await call_model(client, user)).status_code == 200
            assert requests[-1] == (f"{model}.test", model)
        await choose(client, "a", "private_a")
        await choose(client, "b", "private_b")
        responses = await asyncio.gather(call_model(client, "a"), call_model(client, "b"))
        assert all(response.status_code == 200 for response in responses)
        assert set(requests[-2:]) == {
            ("private_a.test", "private_a"),
            ("private_b.test", "private_b"),
        }
        # 管理员执行业务图空间操作，也必须使用该空间所属业务的默认。
        assert (await call_model(client, "admin", space="space_a")).status_code == 200
        assert requests[-1] == ("private_a.test", "private_a")
        assert (await call_model(client, "admin")).status_code == 200
        assert requests[-1] == ("public_two.test", "public_two")
    assert selected_llm_business.get() is None


async def test_entity_extraction_uses_selected_endpoint_without_shared_client(model_api):
    app, requests = model_api
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://test"
    ) as client:
        await choose(client, "a", "private_a")
        await choose(client, "b", "private_b")
        for user in ("a", "b", "a_colleague"):
            response = await client.post(
                "/common-capabilities/entity-extraction",
                headers=headers(user),
                json={"text": "清华大学计算机系教授", "source_type": "work"},
            )
            assert response.status_code == 200, response.text
            model = "private_b" if user == "b" else "private_a"
            assert requests[-1] == (f"{model}.test", model)


async def test_foreign_business_header_rejected_and_admin_pins_business_default(
    model_api,
):
    app, requests = model_api
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://test"
    ) as client:
        response = await call_model(client, "a", business="b")
        assert response.status_code == 403
        response = await client.post(
            "/llm-config/llm-configs/private_b/set-default", headers=headers("a")
        )
        assert response.status_code == 403
        assert requests == []
        # 管理员拨业务归属模型的开关＝给该业务设业务默认，公共默认与其他业务不受影响
        response = await client.post(
            "/llm-config/llm-configs/private_a/set-default", headers=headers("admin")
        )
        assert response.status_code == 200, response.text
        assert (await call_model(client, "a")).status_code == 200
        assert requests[-1] == ("private_a.test", "private_a")
        assert (await call_model(client, "b")).status_code == 200
        assert requests[-1] == ("public_one.test", "public_one")
    assert selected_llm_business.get() is None


async def test_multi_business_reader_keeps_public_routes_and_uses_public_model(model_api):
    app, requests = model_api
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://test"
    ) as client:
        await choose(client, "a", "private_a")
        await choose(client, "b", "private_b")
        response = await client.get("/common-capabilities/metadata", headers=headers("multi"))
        assert response.status_code == 200
        assert requests == []
        assert (await call_model(client, "multi")).status_code == 200
        assert requests[-1] == ("public_one.test", "public_one")
