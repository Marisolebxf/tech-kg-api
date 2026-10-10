"""图空间绑定/解绑语义单元测试：旧模式删绑定行，新模式写解绑（隐藏）行。

解绑在两种模式下都只影响当前用户的可见性（工作空间下拉移除、配置页列表
保留且状态为已解绑），不动图空间数据；重新绑定后恢复如初。
"""

from __future__ import annotations

import contextlib
from typing import Any, cast

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import service.business_access_control as bac
from db_model.base import Base
from db_model.platform_governance import (
    GraphSpaceProfile,
    UserGraphSpace,
    UserGraphSpaceHidden,
)
from service.graph_space import GraphSpaceService
from service.platform_access import PlatformActor


class _StubGraphClient:
    """只实现绑定/解绑所需的最小接口。"""

    def __init__(self, spaces: set[str]) -> None:
        self.spaces = spaces

    def list_spaces(self) -> list[str]:
        return sorted(self.spaces)


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(
        engine,
        tables=[
            UserGraphSpace.__table__,
            UserGraphSpaceHidden.__table__,
            GraphSpaceProfile.__table__,
        ],
    )
    with Session(engine) as session:
        yield session


def _admin() -> PlatformActor:
    return PlatformActor(
        user_id="admin1", username="admin", display_name="管理员", email="", is_admin=True
    )


def _service(session: Session, spaces: set[str]) -> GraphSpaceService:
    service = GraphSpaceService(
        session, client=cast(Any, _StubGraphClient(spaces)), milvus_client=object()
    )
    service._ensure_vector_database = lambda space_name: ("ready", "")  # noqa: SLF001
    return service


@contextlib.contextmanager
def _sqlite_scope(session: Session):
    yield session


def _stub_rbac_lists(monkeypatch, session, names: list[str]) -> None:
    """space_items 依赖的三件套替换为 sqlite 本地实现（无业务授权表）。"""
    monkeypatch.setattr(bac, "allowed_space_names", lambda actor, action="read": list(names))
    monkeypatch.setattr(
        bac,
        "space_registrations",
        lambda session: {name: bac.SpaceRegistration(name, None, True) for name in names},
    )
    monkeypatch.setattr(GraphSpaceService, "_all_spaces", lambda self: list(names))
    monkeypatch.setattr(bac, "session_scope", lambda: _sqlite_scope(session))


def _hidden_names(session: Session) -> set[str]:
    return set(session.scalars(select(UserGraphSpaceHidden.space_name)))


def test_rbac_unbind_hides_then_bind_restores(session, monkeypatch):
    monkeypatch.setenv("BUSINESS_RBAC_ENABLED", "true")
    monkeypatch.setattr(GraphSpaceService, "_all_spaces_cache", [])
    monkeypatch.setattr(GraphSpaceService, "_all_spaces_cached_at", 0.0)
    _stub_rbac_lists(monkeypatch, session, ["legacy", "bare"])
    service = _service(session, {"legacy", "bare"})

    # 解绑：写隐藏行；配置页列表仍可见（mine=False），工作空间下拉移除
    assert service.unbind(_admin(), "legacy") is True
    assert _hidden_names(session) == {"legacy"}
    items = {item["name"]: item for item in service.list_spaces_for_actor(_admin())}
    assert set(items) == {"legacy", "bare"}
    assert items["legacy"]["mine"] is False
    assert items["bare"]["mine"] is True
    work = [item["name"] for item in service.list_work_spaces_for_actor(_admin())]
    assert work == ["bare"]

    # 重复解绑幂等
    assert service.unbind(_admin(), "legacy") is True
    assert _hidden_names(session) == {"legacy"}

    # 重新绑定：删隐藏行，工作空间恢复
    service.bind(_admin(), "legacy")
    assert _hidden_names(session) == set()
    work = {item["name"] for item in service.list_work_spaces_for_actor(_admin())}
    assert work == {"bare", "legacy"}


def test_legacy_unbind_deletes_binding_row(session, monkeypatch):
    monkeypatch.setenv("BUSINESS_RBAC_ENABLED", "false")
    monkeypatch.setattr(GraphSpaceService, "_all_spaces_cache", [])
    monkeypatch.setattr(GraphSpaceService, "_all_spaces_cached_at", 0.0)
    service = _service(session, {"legacy"})

    service.bind(_admin(), "legacy")
    assert service.is_bound("admin1", "legacy")
    assert service.unbind(_admin(), "legacy") is True
    assert not service.is_bound("admin1", "legacy")
    assert _hidden_names(session) == set()  # 旧模式不写隐藏表
    # 未绑定再解 → False（接口层 404 语义）
    assert service.unbind(_admin(), "legacy") is False
