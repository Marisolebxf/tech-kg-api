"""platform_developer 角色单测：与管理员同权（is_admin 直通）+ 图空间按绑定收敛
+ 空间自助操作（创建/绑定/解绑）拦截。

背景：开发维护账号不启用业务 RBAC，直接写 kg_platform_user_role 授权；
与管理员看到的页面与接口完全一致，唯一差异是图空间范围（默认空间+管理员绑定）。
"""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from biz.handler.graph_space import _reject_developer
from db_model.base import Base
from db_model.platform_governance import (
    GraphSpaceVectorDatabase,
    PlatformUser,
    PlatformUserRole,
    UserGraphSpace,
)
from service import platform_access
from service.graph_space import GraphSpaceService
from service.platform_access import PlatformActor

DEV_USER = "dev-1"
ADMIN_USER = "admin-1"


class FakeGraphClient:
    def __init__(self, spaces: list[str]) -> None:
        self.spaces = list(spaces)

    def list_spaces(self) -> list[str]:
        return list(self.spaces)


class FakeMilvusClient:
    def list_databases(self) -> list[str]:
        return ["default"]

    def create_database(self, db_name: str) -> None:  # noqa: ARG002
        return None


@pytest.fixture
def session_factory():
    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(
        engine,
        tables=[
            PlatformUser.__table__,
            PlatformUserRole.__table__,
            UserGraphSpace.__table__,
            GraphSpaceVectorDatabase.__table__,
        ],
    )
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    yield factory
    engine.dispose()


@pytest.fixture(autouse=True)
def _reset_all_spaces_cache():
    # _all_spaces 的 30s 进程内缓存跨测试泄漏，逐用例归零
    GraphSpaceService._all_spaces_cached_at = 0.0
    GraphSpaceService._all_spaces_cache = []
    yield


def _profile(user_id: str) -> SimpleNamespace:
    return SimpleNamespace(
        user=SimpleNamespace(id=user_id, username=user_id, nickname=user_id, email="")
    )


def _patched_scope(session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    @contextmanager
    def test_session_scope():
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise

    monkeypatch.setattr(platform_access, "session_scope", test_session_scope)


def _add_role(session: Session, user_id: str, role_code: str) -> None:
    session.add(PlatformUserRole(user_id=user_id, role_code=role_code, granted_by="test"))
    session.flush()


def test_developer_role_is_admin_with_restricted_spaces_marker(
    session_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """角色表写入 platform_developer → is_admin 直通 + is_developer 标记。"""
    with session_factory() as session:
        session.add(PlatformUser(user_id=DEV_USER, username=DEV_USER))
        _add_role(session, DEV_USER, platform_access.DEVELOPER_ROLE)
        _patched_scope(session, monkeypatch)

        actor = platform_access.actor_from_profile(
            _profile(DEV_USER), initial_admin_ids=(), auth_enabled=True
        )

    assert actor.is_admin is True  # 与管理员同权：全部页面/接口/审核权限
    assert actor.is_developer is True  # 仅图空间范围收敛用


def test_plain_admin_and_regular_user_unmarked(
    session_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    with session_factory() as session:
        session.add(PlatformUser(user_id=ADMIN_USER, username=ADMIN_USER))
        _add_role(session, ADMIN_USER, platform_access.ADMIN_ROLE)
        session.add(PlatformUser(user_id="u-9", username="u-9"))
        _patched_scope(session, monkeypatch)

        admin = platform_access.actor_from_profile(
            _profile(ADMIN_USER), initial_admin_ids=(), auth_enabled=True
        )
        regular = platform_access.actor_from_profile(
            _profile("u-9"), initial_admin_ids=(), auth_enabled=True
        )

    assert admin.is_admin is True and admin.is_developer is False
    assert regular.is_admin is False and regular.is_developer is False


def _actor(user_id: str, *, is_admin: bool, is_developer: bool = False) -> PlatformActor:
    return PlatformActor(
        user_id=user_id,
        username=user_id,
        display_name=user_id,
        email="",
        is_admin=is_admin,
        is_developer=is_developer,
    )


def _seed_binding(session_factory, user_id: str, space: str) -> None:
    with session_factory() as session:
        session.add(UserGraphSpace(user_id=user_id, space_name=space))
        session.commit()


def test_config_page_space_list_collapsed_for_developer(
    session_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """配置页绑定入口（list_spaces_for_actor）：开发者只见 默认+本人绑定，
    纯管理员看全量。"""
    monkeypatch.setenv("TRS_GRAPH_SPACE", "dev")
    _seed_binding(session_factory, DEV_USER, "dev2")
    client = FakeGraphClient(["dev", "dev2", "gaoxing_test", "other_space"])

    developer = _actor(DEV_USER, is_admin=True, is_developer=True)
    admin = _actor(ADMIN_USER, is_admin=True)

    with session_factory() as session:
        service = GraphSpaceService(session, client=client, milvus_client=FakeMilvusClient())
        dev_items = service.list_spaces_for_actor(developer)
        admin_items = service.list_spaces_for_actor(admin)

    assert sorted(item["name"] for item in dev_items) == ["dev", "dev2"]
    assert {item["name"]: item["mine"] for item in dev_items}["dev2"] is True
    assert sorted(item["name"] for item in admin_items) == [
        "dev",
        "dev2",
        "gaoxing_test",
        "other_space",
    ]


def test_selector_space_list_unchanged_default_plus_bound(
    session_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """可工作空间（list_work_spaces_for_actor，全局选择器来源）对所有用户口径
    不变：默认空间+本人绑定——开发者与管理员一致，不看全量。"""
    monkeypatch.setenv("TRS_GRAPH_SPACE", "dev")
    _seed_binding(session_factory, DEV_USER, "dev2")
    service = GraphSpaceService(
        session_factory(),
        client=FakeGraphClient(["dev", "dev2", "gaoxing_test"]),
        milvus_client=FakeMilvusClient(),
    )

    dev_items = service.list_work_spaces_for_actor(
        _actor(DEV_USER, is_admin=True, is_developer=True)
    )
    admin_items = service.list_work_spaces_for_actor(_actor(ADMIN_USER, is_admin=True))

    assert sorted(item["name"] for item in dev_items) == ["dev", "dev2"]
    assert [item["name"] for item in admin_items] == ["dev"]


def test_developer_cannot_self_manage_spaces() -> None:
    """创建/绑定/解绑入口对开发者 403；纯管理员放行。"""
    developer = _actor(DEV_USER, is_admin=True, is_developer=True)
    with pytest.raises(HTTPException) as exc:
        _reject_developer(developer)
    assert exc.value.status_code == 403

    admin = _actor(ADMIN_USER, is_admin=True)
    assert _reject_developer(admin) is None
