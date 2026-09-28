"""Exercise business isolation against real ownership rows, including cached reads."""

from contextlib import contextmanager
from dataclasses import replace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db_model.base import Base
from db_model.business_access import BusinessClient, BusinessGraphSpace, BusinessMember
from service import business_access_control as acl
from service.platform_access import PlatformActor


def actor(role="user", business="a", business_only=False):
    return PlatformActor(
        user_id="alice",
        username="alice",
        display_name="Alice",
        email="",
        is_admin=role == "admin",
        business_id=business,
        business_role="developer" if role == "developer" else "user",
        business_only=business_only,
    )


@pytest.fixture
def business_db(monkeypatch):
    monkeypatch.setenv("BUSINESS_RBAC_ENABLED", "true")
    engine = create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(
        engine,
        tables=[BusinessClient.__table__, BusinessMember.__table__, BusinessGraphSpace.__table__],
    )
    factory = sessionmaker(engine, expire_on_commit=False)

    @contextmanager
    def scope():
        with factory.begin() as session:
            yield session

    monkeypatch.setattr(acl, "session_scope", scope)
    with scope() as session:
        session.add_all(
            [BusinessClient(client_id="a", name="A"), BusinessClient(client_id="b", name="B")]
        )
        session.flush()
        session.add_all(
            [
                BusinessMember(user_id="alice", client_id="a", role="developer"),
                BusinessMember(user_id="bob", client_id="a", role="user"),
                BusinessMember(user_id="other", client_id="b", role="developer"),
                BusinessGraphSpace(space_name="private_a", client_id="a"),
                BusinessGraphSpace(space_name="private_b", client_id="b"),
                BusinessGraphSpace(
                    space_name="production", is_shared_production=True, shared_key="production"
                ),
            ]
        )
    yield scope
    engine.dispose()


@pytest.mark.parametrize(
    "role,space,action,allowed",
    [
        ("user", "private_a", "read", True),
        ("user", "private_a", "write", False),
        ("user", "private_a", "review", False),
        ("user", "private_a", "review_view", False),
        ("user", "private_b", "read", False),
        ("user", "production", "read", True),
        ("user", "production", "write", False),
        ("user", "production", "review_view", False),
        ("developer", "private_a", "read", True),
        ("developer", "private_a", "write", True),
        ("developer", "private_a", "review", True),
        ("developer", "private_a", "review_view", True),
        ("developer", "private_b", "read", False),
        ("developer", "private_b", "write", False),
        ("developer", "private_b", "review", False),
        ("developer", "private_b", "review_view", False),
        ("developer", "production", "read", True),
        ("developer", "production", "write", True),
        ("developer", "production", "review", False),
        ("developer", "production", "review_view", True),
        ("developer", "unregistered", "read", False),
        ("developer", "unregistered", "review_view", False),
        ("admin", "private_b", "write", True),
        ("admin", "production", "review", True),
        ("admin", "production", "review_view", True),
    ],
)
def test_role_space_matrix(business_db, role, space, action, allowed):
    if allowed:
        acl.ensure_space_access(actor(role), space, action)
    else:
        with pytest.raises(HTTPException) as caught:
            acl.ensure_space_access(actor(role), space, action)
        assert caught.value.status_code == 403


def test_company_test_scope_caps_even_admin(business_db):
    limited = actor("admin", business_only=True)
    assert not limited.can_develop
    acl.ensure_space_access(limited, "production", "read")
    for space, action in [("private_b", "read"), ("private_a", "write"), ("production", "review")]:
        with pytest.raises(HTTPException):
            acl.ensure_space_access(limited, space, action)


def test_unbound_only_explicit_shared_space(business_db):
    unbound = actor(business="")
    assert acl.allowed_space_names(unbound) == ["production"]
    with pytest.raises(HTTPException):
        acl.ensure_space_access(unbound, "private_a")


def test_direct_database_changes_apply_without_session_refresh(business_db):
    assert acl.resolve_membership("alice") == ("a", "developer")
    with business_db() as session:
        session.get(BusinessMember, "alice").role = "user"
    assert acl.resolve_membership("alice") == ("a", "user")
    with business_db() as session:
        session.get(BusinessClient, "a").enabled = False
    assert acl.resolve_membership("alice") == ("", "user")


def test_space_transfer_revokes_access_even_with_warm_console_cache(business_db, monkeypatch):
    from service import graph_console

    statement = "MATCH (n) RETURN n LIMIT 1"
    monkeypatch.setattr(graph_console, "_ngql_payload_cache", {})
    graph_console._ngql_cache_put(graph_console.ngql_cache_key("private_a", statement), "cached")
    assert graph_console.run_statement_cached_payload(actor(), "private_a", statement) == "cached"
    with business_db() as session:
        session.get(BusinessGraphSpace, "private_a").client_id = "b"
    with pytest.raises(HTTPException) as caught:
        graph_console.run_statement_cached_payload(actor(), "private_a", statement)
    assert caught.value.status_code == 403


@pytest.mark.parametrize(
    "statement", ["SHOW SPACES", "SHOW HOSTS", "SHOW USERS", "DESC SPACE private_b"]
)
def test_console_cannot_enumerate_other_businesses(business_db, statement):
    from service.graph_console import GraphConsoleError, run_statement_cached_payload

    with pytest.raises(GraphConsoleError) as caught:
        run_statement_cached_payload(actor("developer"), "private_a", statement)
    assert caught.value.status_code == 403


def test_configuration_owner_stable_across_member_transfer(business_db):
    from biz.dependencies.resources import assigned_resource_owner, ensure_owner_access

    developer = actor("developer")
    assert assigned_resource_owner(developer, "business:b") == "business:a"
    ensure_owner_access(developer, "business:a")
    for invalid in ("business:b", "alice", ""):
        with pytest.raises(HTTPException):
            ensure_owner_access(developer, invalid)
    with pytest.raises(HTTPException):
        ensure_owner_access(replace(developer, business_id="b"), "business:a")


def test_legacy_personal_bind_mutations_disabled(business_db):
    from biz.handler.graph_space import _require_legacy_binding

    with pytest.raises(HTTPException) as caught:
        _require_legacy_binding()
    assert caught.value.status_code == 409


def test_legacy_mode_does_not_read_new_tables(monkeypatch):
    monkeypatch.setenv("BUSINESS_RBAC_ENABLED", "false")
    monkeypatch.setattr(acl, "session_scope", lambda: pytest.fail("must not query new tables"))
    assert acl.resolve_membership("alice") == ("", "user")
    acl.ensure_space_access(actor(), "legacy")


@pytest.mark.parametrize("endpoint", ["list_entity_types", "get_index_status"])
def test_entity_metadata_cannot_read_other_space(business_db, monkeypatch, endpoint):
    from biz.handler import entity_search

    monkeypatch.setattr(
        entity_search, "_application", lambda session: pytest.fail("must authorize before query")
    )
    with pytest.raises(HTTPException) as caught:
        getattr(entity_search, endpoint)(actor(), None, "private_b")
    assert caught.value.status_code == 403


def test_business_default_configuration_does_not_replace_platform_defaults(monkeypatch):
    from datetime import datetime

    from dao.llm_config import LlmConfigDAO
    from db_model.llm_config import LlmConfig

    monkeypatch.setenv("BUSINESS_RBAC_ENABLED", "true")
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[LlmConfig.__table__])
    factory = sessionmaker(engine)
    now = datetime.now()
    with factory() as session:
        for key, owner in [
            ("global", "admin"),
            ("a_old", "business:a"),
            ("a_new", "business:a"),
            ("b", "business:b"),
        ]:
            session.add(
                LlmConfig(
                    id=key,
                    name=key,
                    base_url="https://model.invalid",
                    api_key="test",
                    model="model",
                    owner=owner,
                    is_default=key != "a_new",
                    created_at=now,
                    updated_at=now,
                )
            )
        session.commit()
        dao = LlmConfigDAO(session)
        assert dao.get_default().id == "global"
        dao.clear_other_defaults("a_new", owner=None)
        session.expire_all()
        assert not session.get(LlmConfig, "a_old").is_default
        assert session.get(LlmConfig, "b").is_default
        assert session.get(LlmConfig, "global").is_default
    engine.dispose()
