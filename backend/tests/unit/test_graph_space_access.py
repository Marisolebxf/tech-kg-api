"""graph-search 空间绑定校验 + workflow 触发资源选择器校验单测。

不挂完整 router（需要真实图客户端/Temporal），直接测 handler 层的两个校验辅助函数：
- graph_search._ensure_space_access：非管理员访问未绑定空间 → 403
- workflow_system._validate_resource_selectors：跨用户配置 → 403
"""

from __future__ import annotations

from datetime import datetime

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from biz.handler import graph_search, workflow_system
from db_model.base import Base
from db_model.llm_config import LlmConfig
from service.platform_access import PlatformActor

USER_A = "101"
USER_B = "202"


def _actor(user_id: str, is_admin: bool = False) -> PlatformActor:
    return PlatformActor(
        user_id=user_id,
        username=f"user{user_id}",
        display_name=f"用户{user_id}",
        email="",
        is_admin=is_admin,
    )


class _FakeGraphSpaceService:
    def __init__(self, bindings: set[tuple[str, str]]) -> None:
        self._bindings = bindings

    def is_bound(self, user_id: str, space: str) -> bool:
        return (user_id, space) in self._bindings


@pytest.fixture
def session_factory(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine, tables=[LlmConfig.__table__])
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    yield factory
    engine.dispose()


def _seed_llm(session_factory, config_id: str, owner: str) -> None:
    s = session_factory()
    now = datetime.utcnow()
    s.add(
        LlmConfig(
            id=config_id,
            name=f"cfg-{config_id}",
            description="",
            base_url="http://llm",
            api_key="k",
            model="m",
            owner=owner,
            is_default=False,
            status="正常",
            created_at=now,
            updated_at=now,
        )
    )
    s.commit()
    s.close()


class TestEnsureSpaceAccess:
    def test_no_space_passes(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "service.graph_space.GraphSpaceService",
            lambda session: (_ for _ in ()).throw(AssertionError("不应查绑定")),
        )
        graph_search._ensure_space_access(_actor(USER_A), None)

    def test_admin_passes(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "service.graph_space.GraphSpaceService",
            lambda session: (_ for _ in ()).throw(AssertionError("不应查绑定")),
        )
        graph_search._ensure_space_access(_actor("admin", is_admin=True), "any_space")

    def test_bound_space_passes(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "service.graph_space.GraphSpaceService",
            lambda session: _FakeGraphSpaceService({(USER_A, "dev")}),
        )
        monkeypatch.setattr(graph_search, "create_session", lambda: _NullSession())
        graph_search._ensure_space_access(_actor(USER_A), "dev")

    def test_unbound_space_forbidden(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "service.graph_space.GraphSpaceService",
            lambda session: _FakeGraphSpaceService(set()),
        )
        monkeypatch.setattr(graph_search, "create_session", lambda: _NullSession())
        with pytest.raises(HTTPException) as exc_info:
            graph_search._ensure_space_access(_actor(USER_A), "dev")
        assert exc_info.value.status_code == 403


class TestValidateResourceSelectors:
    def test_admin_bypasses(self) -> None:
        workflow_system._validate_resource_selectors(
            _actor("admin", is_admin=True),
            {"llm_config_id": "LLM-B", "graph_space": "any"},
        )

    def test_own_config_passes(self, session_factory, monkeypatch) -> None:
        _seed_llm(session_factory, "LLM-A", USER_A)
        monkeypatch.setattr("infra.mysql.create_session", lambda: session_factory())
        workflow_system._validate_resource_selectors(_actor(USER_A), {"llm_config_id": "LLM-A"})

    def test_other_users_config_forbidden(self, session_factory, monkeypatch) -> None:
        _seed_llm(session_factory, "LLM-B", USER_B)
        monkeypatch.setattr("infra.mysql.create_session", lambda: session_factory())
        with pytest.raises(HTTPException) as exc_info:
            workflow_system._validate_resource_selectors(_actor(USER_A), {"llm_config_id": "LLM-B"})
        assert exc_info.value.status_code == 403

    def test_unbound_space_forbidden(self, monkeypatch) -> None:
        monkeypatch.setattr("infra.mysql.create_session", lambda: _NullSession())
        monkeypatch.setattr(
            "service.graph_space.GraphSpaceService",
            lambda session: _FakeGraphSpaceService(set()),
        )
        with pytest.raises(HTTPException) as exc_info:
            workflow_system._validate_resource_selectors(_actor(USER_A), {"graph_space": "dev"})
        assert exc_info.value.status_code == 403


class _NullSession:
    def close(self) -> None:
        return None
