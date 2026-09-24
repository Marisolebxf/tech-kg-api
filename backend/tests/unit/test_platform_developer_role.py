"""业务开发维护不等于管理员；旧平台标记和个人绑定不得扩大授权。"""

from contextlib import contextmanager
from dataclasses import replace
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from biz.dependencies.auth import require_platform_admin, require_platform_maintainer
from biz.handler.graph_space import GraphSpaceCreateRequest, create_graph_space
from db_model.base import Base
from db_model.business_access import BusinessClient, BusinessGraphSpace, BusinessMember
from db_model.platform_governance import PlatformUser, PlatformUserRole, UserGraphSpace
from service import business_access_control as acl
from service import platform_access
from service.graph_space import GraphSpaceService


@pytest.fixture
def scope(monkeypatch):
    monkeypatch.setenv("BUSINESS_RBAC_ENABLED", "true")
    engine = create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(
        engine,
        tables=[
            m.__table__
            for m in (
                BusinessClient,
                BusinessMember,
                BusinessGraphSpace,
                PlatformUser,
                PlatformUserRole,
                UserGraphSpace,
            )
        ],
    )
    factory = sessionmaker(engine, expire_on_commit=False)

    @contextmanager
    def sessions():
        with factory.begin() as session:
            yield session

    monkeypatch.setattr(platform_access, "session_scope", sessions)
    monkeypatch.setattr(acl, "session_scope", sessions)
    monkeypatch.setattr(
        GraphSpaceService, "_all_spaces", lambda self: ["dev", "dev2", "gaoxing_test", "foreign"]
    )
    with sessions() as session:
        session.add_all(
            [
                BusinessClient(client_id="engine", name="Engine"),
                BusinessClient(client_id="other", name="Other"),
            ]
        )
        session.add_all(
            [PlatformUser(user_id=u, username=u) for u in ("developer", "user", "admin", "legacy")]
        )
        session.flush()
        session.add_all(
            [
                BusinessMember(user_id="developer", client_id="engine", role="developer"),
                BusinessMember(user_id="user", client_id="engine", role="user"),
                BusinessGraphSpace(
                    space_name="dev", is_shared_production=True, shared_key="production"
                ),
                BusinessGraphSpace(space_name="dev2", client_id="engine"),
                BusinessGraphSpace(space_name="gaoxing_test", client_id="engine"),
                BusinessGraphSpace(space_name="foreign", client_id="other"),
                PlatformUserRole(user_id="admin", role_code="platform_admin", granted_by="test"),
                PlatformUserRole(
                    user_id="admin", role_code="platform_developer", granted_by="test"
                ),
                PlatformUserRole(
                    user_id="developer", role_code="platform_developer", granted_by="test"
                ),
                PlatformUserRole(
                    user_id="legacy", role_code="platform_developer", granted_by="test"
                ),
                UserGraphSpace(user_id="developer", space_name="foreign"),
            ]
        )
    yield sessions
    engine.dispose()


def resolve(user):
    profile = SimpleNamespace(user=SimpleNamespace(id=user, username=user, nickname=user, email=""))
    actor = platform_access.actor_from_profile(profile, initial_admin_ids=(), auth_enabled=True)
    business, role = acl.resolve_membership(user)
    return replace(actor, business_id=business, business_role=role)


def test_developer_is_not_admin_and_cannot_use_admin_dependencies(scope):
    actor = resolve("developer")
    assert actor.can_develop and actor.is_developer
    assert not actor.is_admin
    assert require_platform_maintainer(actor) is actor
    with pytest.raises(HTTPException) as caught:
        require_platform_admin(actor)
    assert caught.value.status_code == 403
    assert "member:manage" not in actor.permissions


@pytest.mark.parametrize("action", ["read", "write", "review"])
def test_personal_binding_does_not_grant_foreign_access(scope, action):
    with pytest.raises(HTTPException) as caught:
        acl.ensure_space_access(resolve("developer"), "foreign", action)
    assert caught.value.status_code == 403


def test_ordinary_and_developer_share_business_spaces_but_not_write_or_public_review(scope):
    user, developer = resolve("user"), resolve("developer")
    assert (
        acl.allowed_space_names(user)
        == acl.allowed_space_names(developer)
        == ["dev", "dev2", "gaoxing_test"]
    )
    assert acl.allowed_space_names(developer, "review") == ["dev2", "gaoxing_test"]
    assert acl.allowed_space_names(user, "review") == []
    for space in ("dev", "dev2", "gaoxing_test"):
        acl.ensure_space_access(developer, space, "write")
        with pytest.raises(HTTPException):
            acl.ensure_space_access(user, space, "write")
    with pytest.raises(HTTPException):
        acl.ensure_space_access(developer, "dev", "review")


def test_admin_without_business_sees_all_despite_legacy_developer_marker(scope):
    actor = resolve("admin")
    assert actor.is_admin and not actor.is_developer and not actor.business_id
    assert acl.allowed_space_names(actor) == ["dev", "dev2", "gaoxing_test", "foreign"]
    acl.ensure_space_access(actor, "dev", "review")


def test_legacy_developer_marker_alone_has_no_maintenance_authority(scope, monkeypatch):
    for enabled in ("true", "false"):
        monkeypatch.setenv("BUSINESS_RBAC_ENABLED", enabled)
        actor = resolve("legacy")
        assert not actor.is_admin and not actor.can_develop and not actor.is_developer
        with pytest.raises(HTTPException):
            require_platform_maintainer(actor)


def test_sql_membership_change_takes_effect_without_personal_binding(scope):
    assert resolve("developer").can_develop
    with scope() as session:
        row = session.get(BusinessMember, "developer")
        row.role = "user"
        row.client_id = "other"
    actor = resolve("developer")
    assert not actor.can_develop
    assert acl.allowed_space_names(actor) == ["dev", "foreign"]


def test_existing_config_list_displays_all_authorized_rows(scope):
    for user in ("user", "developer", "admin"):
        actor = resolve(user)
        items = acl.space_items(actor)
        assert sorted(row["name"] for row in items if row["mine"]) == sorted(
            acl.allowed_space_names(actor)
        )


def test_admin_creation_does_not_require_online_approval(scope, monkeypatch):
    monkeypatch.setattr(GraphSpaceService, "create_space", lambda self, actor, name: {"name": name})
    with scope() as session:
        result = create_graph_space(
            GraphSpaceCreateRequest(name="new_space"), resolve("admin"), session
        )
    assert result.data == {"name": "new_space"}


def test_domain_creation_rejects_developer_before_graph_call(scope):
    with scope() as session:
        with pytest.raises(HTTPException) as caught:
            GraphSpaceService(session, client=object()).create_space(
                resolve("developer"), "new_space"
            )
    assert caught.value.status_code == 403
