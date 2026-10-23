"""门户角色与本地业务权限的交集，包含后台执行和失效缓存。"""

from contextlib import contextmanager
from dataclasses import replace
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from application.auth import AuthApplication
from config.auth import AuthSettings
from db_model.base import Base
from db_model.business_access import (
    BusinessClient,
    BusinessGraphSpace,
    BusinessMember,
    BusinessMembership,
    BusinessMembershipState,
    BusinessSpacePolicy,
)
from db_model.platform_governance import PlatformUser, PlatformUserRole
from infra.redis import MemoryJsonStore
from infra.user_center import UserCenterError
from service import business_access_control as acl
from service import platform_access, portal_developer
from service.auth import AuthContext


@pytest.fixture
def workflow_jobs(monkeypatch):
    from infra.workflow_mysql import workflow_mysql_client

    engine = create_engine("sqlite:///:memory:")
    monkeypatch.setattr(workflow_mysql_client, "_engine", engine)
    from service import workflow_jobs

    yield workflow_jobs
    engine.dispose()


@pytest.fixture
def directory(monkeypatch):
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("USER_CENTER_PORTAL_DEVELOPER_ROLE_CODES", "bkg_developer")
    monkeypatch.setenv("BUSINESS_RBAC_ENABLED", "true")
    monkeypatch.setenv("PLATFORM_BOOTSTRAP_FIRST_ADMIN", "false")
    monkeypatch.setenv("PLATFORM_INITIAL_ADMIN_USER_IDS", "")
    clock = SimpleNamespace(now=0)
    state = SimpleNamespace(users={"dev"}, calls=0, failure=False)
    monkeypatch.setattr(portal_developer.time, "monotonic", lambda: clock.now)
    obj = portal_developer.PortalDeveloperDirectory(AuthSettings.from_env())

    def lookup(code):
        state.calls += 1
        assert code == "bkg_developer"
        if state.failure:
            raise UserCenterError("unavailable")
        return frozenset(state.users)

    obj.client.role_user_ids = lookup
    monkeypatch.setattr(portal_developer, "_directory", lambda settings: obj)
    return obj, state, clock


@pytest.fixture
def db(monkeypatch, directory):
    engine = create_engine("sqlite:///:memory:")
    models = [
        BusinessClient,
        BusinessGraphSpace,
        BusinessMember,
        BusinessMembership,
        BusinessMembershipState,
        BusinessSpacePolicy,
        PlatformUser,
        PlatformUserRole,
    ]
    Base.metadata.create_all(engine, tables=[m.__table__ for m in models])
    with Session(engine, expire_on_commit=False) as session:
        session.add_all(
            [BusinessClient(client_id="a", name="A"), BusinessClient(client_id="b", name="B")]
        )
        session.add_all([PlatformUser(user_id=u, username=u) for u in ("dev", "plain", "admin")])
        session.flush()
        session.add(BusinessMember(user_id="dev", client_id="a", role="developer"))
        session.add(
            PlatformUserRole(user_id="admin", role_code="platform_admin", granted_by="test")
        )
        session.commit()

        @contextmanager
        def scope():
            yield session
            session.commit()

        monkeypatch.setattr(acl, "session_scope", scope)
        monkeypatch.setattr(platform_access, "session_scope", scope)
        import infra.mysql

        monkeypatch.setattr(infra.mysql, "session_scope", scope)
        yield session
    engine.dispose()


def profile(user_id):
    app = AuthApplication(settings=AuthSettings.from_env(), store=MemoryJsonStore())
    return app.profile(
        AuthContext(
            "token",
            {
                "userInfo": {"id": user_id, "username": user_id, "nickname": user_id},
            },
            None,
        )
    )


def test_portal_developer_needs_local_business_binding(db, directory):
    _, state, _ = directory
    state.users.add("plain")
    unbound = profile("plain")
    assert unbound.can_develop is False
    assert unbound.developer_business_binding_required is True
    assert unbound.model_dump(by_alias=True)["developerBusinessBindingRequired"] is True
    result = profile("dev")
    assert result.platform_role == "developer"
    assert result.can_develop and not result.is_admin
    assert result.developer_business_ids == ["a"]
    assert "member:manage" not in result.platform_permissions
    assert result.developer_business_binding_required is False


def test_binding_notice_does_not_grant_access_and_clears_after_binding(db, directory):
    _, state, _ = directory
    state.users.add("plain")
    assert profile("plain").developer_business_binding_required
    db.add(BusinessMember(user_id="plain", client_id="a", role="developer"))
    db.commit()
    result = profile("plain")
    assert result.can_develop and not result.developer_business_binding_required


def test_no_binding_notice_for_ordinary_admin_or_capped_account(db, monkeypatch):
    assert not profile("plain").developer_business_binding_required
    assert not profile("admin").developer_business_binding_required
    monkeypatch.setenv("PLATFORM_BUSINESS_ONLY_USER_IDS", "dev")
    assert not profile("dev").developer_business_binding_required


def test_unavailable_portal_does_not_mislabel_unbound_user_or_block_public_login(db, directory):
    _, state, _ = directory
    state.failure = True
    result = profile("plain")
    assert not result.developer_business_binding_required and not result.can_develop


def test_local_user_binding_is_not_upgraded_by_portal_role(db, directory):
    db.get(BusinessMember, "dev").role = "user"
    db.commit()
    assert profile("dev").can_develop is False
    assert profile("dev").developer_business_binding_required is True


def test_new_team_has_public_read_only_until_spaces_are_assigned(db):
    from service.platform_access import PlatformActor

    db.add_all(
        [
            BusinessGraphSpace(space_name="public", is_shared_production=True),
            BusinessGraphSpace(space_name="other", client_id="b"),
        ]
    )
    db.commit()
    actor = acl.with_memberships(PlatformActor("dev", "dev", "dev", "", False))
    assert actor.is_developer
    assert acl.allowed_space_names(actor) == ["public"]
    assert acl.allowed_space_names(actor, "write") == []
    acl.ensure_space_access(actor, "public", "read")
    for space, action in [("public", "write"), ("public", "review"), ("other", "read")]:
        with pytest.raises(HTTPException) as exc:
            acl.ensure_space_access(actor, space, action)
        assert exc.value.status_code == 403


def test_revocation_removes_api_development_and_keeps_binding(db, directory):
    _, state, clock = directory
    assert profile("dev").can_develop
    state.users.clear()
    clock.now = 30
    assert profile("dev").can_develop
    clock.now = 61
    assert profile("dev").can_develop is False
    assert profile("dev").business_ids == ["a"]
    assert db.get(BusinessMember, "dev").role == "developer"
    assert state.calls == 2


def test_background_execution_rechecks_portal_role(db, directory, monkeypatch, workflow_jobs):
    _, state, clock = directory
    monkeypatch.setattr(workflow_jobs, "authorize_workflow_resource", lambda *args: None)
    payload = {"actorUserId": "dev", "clientId": "a", "graphSpace": "a_space"}
    assert workflow_jobs.authorize_background_execution(payload).is_developer
    state.users.clear()
    clock.now = 61
    with pytest.raises(HTTPException) as exc:
        workflow_jobs.authorize_background_execution(
            {**payload, "isAdmin": True, "role": "developer"}
        )
    assert exc.value.status_code == 403


def test_background_foreign_business_rejected(db, monkeypatch, workflow_jobs):
    monkeypatch.setattr(workflow_jobs, "authorize_workflow_resource", lambda *args: None)
    with pytest.raises(HTTPException) as exc:
        workflow_jobs.authorize_background_execution({"actorUserId": "dev", "clientId": "b"})
    assert exc.value.status_code == 403


def test_local_admin_and_business_only_scope_preserved(db, directory, monkeypatch):
    _, state, _ = directory
    state.users.clear()
    assert profile("admin").is_admin
    monkeypatch.setenv("PLATFORM_BUSINESS_ONLY_USER_IDS", "admin")
    capped = profile("admin")
    assert not capped.is_admin and not capped.can_develop


def test_local_revocation_and_disabled_business_still_block(db):
    db.add(BusinessMembershipState(user_id="dev"))
    db.commit()
    assert not profile("dev").can_develop
    db.add(BusinessMembership(user_id="dev", client_id="a", role="developer"))
    db.commit()
    assert profile("dev").can_develop
    db.get(BusinessClient, "a").enabled = False
    db.commit()
    assert not profile("dev").can_develop


def test_expired_directory_error_does_not_reuse_admin_or_developer(directory):
    obj, state, clock = directory
    assert obj.contains("dev")
    state.failure = True
    clock.now = 61
    with pytest.raises(HTTPException) as exc:
        portal_developer.portal_allows_development("dev")
    assert exc.value.status_code == 503


def test_unconfigured_environment_preserves_local_developers(db, monkeypatch):
    monkeypatch.setenv("USER_CENTER_PORTAL_DEVELOPER_ROLE_CODES", "")
    assert profile("dev").can_develop
    assert not profile("plain").developer_business_binding_required


def test_role_configuration_is_normalized_and_opt_in(monkeypatch):
    monkeypatch.delenv("USER_CENTER_PORTAL_DEVELOPER_ROLE_CODES", raising=False)
    assert AuthSettings.from_env().portal_developer_role_codes == ()
    monkeypatch.setenv("USER_CENTER_PORTAL_DEVELOPER_ROLE_CODES", " bkg_developer, bkg_developer, ")
    assert AuthSettings.from_env().portal_developer_role_codes == ("bkg_developer",)


def test_policy_cache_is_distinct_for_different_environments():
    settings = AuthSettings.from_env()
    edu = replace(settings, client_id="edu")
    assert portal_developer._directory(edu) is portal_developer._directory(edu)
    assert portal_developer._directory(edu) is not portal_developer._directory(
        replace(edu, client_id="supercompute")
    )
    assert portal_developer._directory(edu) is not portal_developer._directory(
        replace(edu, portal_developer_role_codes=("other",))
    )
