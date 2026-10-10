"""Permission migration and multi-business/public boundaries against real SQL rows."""

from contextlib import contextmanager
from dataclasses import replace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from db_model.base import Base
from db_model.business_access import (
    BusinessClient,
    BusinessGraphSpace,
    BusinessMember,
    BusinessMembershipState,
    BusinessSpacePolicy,
)
from db_model.platform_governance import PlatformUser
from script import migrate_space_permissions as migration
from service import business_access_control as acl
from service.platform_access import PlatformActor


@pytest.fixture
def database(monkeypatch):
    monkeypatch.setenv("BUSINESS_RBAC_ENABLED", "true")
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine, tables=[m.__table__ for m in (BusinessClient, BusinessMember, BusinessGraphSpace, PlatformUser)])
    migration.migrate(engine, apply=True)

    @contextmanager
    def scope():
        with Session(engine) as session, session.begin():
            yield session

    monkeypatch.setattr(acl, "session_scope", scope)
    monkeypatch.setattr("infra.mysql.session_scope", scope)
    with scope() as session:
        session.add_all([BusinessClient(client_id="a", name="A"), BusinessClient(client_id="b", name="B")])
        session.add(PlatformUser(user_id="dev", username="dev"))
        session.flush()
        session.add(BusinessMember(user_id="dev", client_id="a", role="developer"))
        session.add_all([
            BusinessGraphSpace(space_name="dev", is_shared_production=True, shared_key="production"),
            BusinessGraphSpace(space_name="dev2", client_id="a"),
            BusinessGraphSpace(space_name="a_space", client_id="a"),
            BusinessGraphSpace(space_name="b_space", client_id="b"),
        ])
    yield engine, scope
    engine.dispose()


def developer():
    return acl.with_memberships(PlatformActor("dev", "dev", "Dev", "", False))


def two_business_plan():
    return {"memberships": [{"userId": "dev", "businesses": [
        {"clientId": "a", "role": "developer"}, {"clientId": "b", "role": "developer"}]}],
        "spaces": [{"name": "dev2", "visibility": "public", "clientId": None}]}


def test_additive_migration_preserves_legacy_authority_and_requires_explicit_assignment(database):
    engine, scope = database
    assert inspect(engine).get_pk_constraint("kg_business_member")["constrained_columns"] == ["user_id"]
    assert developer().developer_business_ids == ("a",)
    migration.migrate(engine, apply=True, plan=two_business_plan())
    assert developer().developer_business_ids == ("a", "b")
    with scope() as session:
        assert session.get(BusinessMember, "dev").client_id == "a"
        assert session.get(BusinessGraphSpace, "dev2").client_id == "a"
        assert session.get(BusinessGraphSpace, "dev").shared_key == "production"
    for space in ("a_space", "b_space"):
        acl.ensure_space_access(developer(), space, "write")
    for space in ("dev", "dev2"):
        acl.ensure_space_access(developer(), space, "read")
        acl.ensure_space_access(developer(), space, "review_view")
        for action in ("write", "review"):
            with pytest.raises(HTTPException):
                acl.ensure_space_access(developer(), space, action)


def test_explicit_empty_memberships_do_not_resurrect_legacy_grant(database):
    engine, _ = database
    migration.migrate(engine, apply=True, plan={"memberships": [{"userId": "dev", "businesses": []}]})
    actor = developer()
    assert not actor.can_develop
    assert acl.allowed_space_names(actor) == ["dev"]
    assert acl.resolve_membership("dev") == ("", "user")


def test_plan_check_is_readonly_and_invalid_plan_does_not_partially_grant(database):
    engine, scope = database
    migration.migrate(engine, plan=two_business_plan())
    assert developer().developer_business_ids == ("a",)
    bad = two_business_plan()
    bad["spaces"].append({"name": "bad", "visibility": "business", "clientId": "missing"})
    with pytest.raises(ValueError):
        migration.migrate(engine, apply=True, plan=bad)
    with scope() as session:
        assert session.get(BusinessMembershipState, "dev") is None
        assert not session.scalars(select(BusinessSpacePolicy)).all()


def test_multibusiness_configuration_context_is_explicit_and_cannot_cross_task_business(database):
    from biz.dependencies.resources import (
        assigned_resource_owner,
        ensure_owner_access,
        resource_owner_filter,
    )
    engine, _ = database
    migration.migrate(engine, apply=True, plan=two_business_plan())
    actor = developer()
    with pytest.raises(HTTPException):
        assigned_resource_owner(replace(actor, context_graph_space="dev"))
    selected = replace(actor, context_graph_space="b_space")
    assert resource_owner_filter(selected) == "business:b"
    assert assigned_resource_owner(selected, "business:a") == "business:b"
    with pytest.raises(HTTPException):
        ensure_owner_access(selected, "business:a")
    with pytest.raises(HTTPException):
        resource_owner_filter(replace(selected, context_business_id="a"))


def test_public_task_read_does_not_require_creator_business_but_write_is_denied(database):
    from service.workflow_jobs import authorize_workflow_resource
    engine, _ = database
    migration.migrate(engine, apply=True, plan=two_business_plan())
    actor = developer()
    task = {"owner": "admin", "clientId": "old-business", "graphSpace": "dev2"}
    authorize_workflow_resource(actor, task, "read")
    with pytest.raises(HTTPException):
        authorize_workflow_resource(actor, task, "write")
    for client in ("a", "b"):
        authorize_workflow_resource(actor, {"owner": "admin", "clientId": client, "graphSpace": f"{client}_space"}, "read")
    with pytest.raises(HTTPException):
        authorize_workflow_resource(actor, {"owner": "admin", "clientId": "a", "graphSpace": "b_space"}, "read")


def test_admin_business_directory_and_unassigned_space_are_explicit(database, monkeypatch):
    from service.graph_space import GraphSpaceService
    admin = PlatformActor("admin", "admin", "Admin", "", True)
    monkeypatch.setattr(GraphSpaceService, "_all_spaces", lambda self: ["dev", "a_space", "unknown"])
    assert [item["clientId"] for item in acl.business_summaries(admin)] == ["a", "b"]
    unknown = next(item for item in acl.space_items(admin) if item["name"] == "unknown")
    assert unknown["groupKind"] == "unassigned" and unknown["writeAllowed"]
    assert "unknown" not in acl.allowed_space_names(developer())


def test_configuration_reassignment_requires_valid_business_but_preserves_unchanged_legacy_owner(database):
    from biz.dependencies.resources import validate_owner_update
    admin = PlatformActor("admin", "admin", "Admin", "", True)
    validate_owner_update(admin, {"owner": "old-person"}, current_owner="old-person")
    validate_owner_update(admin, {"owner": "business:b"}, current_owner="old-person")
    with pytest.raises(HTTPException):
        validate_owner_update(admin, {"owner": "business:missing"}, current_owner="old-person")
    payload = {"owner": "business:b"}
    validate_owner_update(developer(), payload)
    assert "owner" not in payload


def test_schema_capabilities_are_readonly_in_public_even_for_original_creator(database):
    import json

    from biz.handler.schema_management import _scope_schema_capabilities
    original = {"items": [
        {"graphSpace": "dev", "canDelete": True, "canManageProperties": True},
        {"graphSpace": "a_space", "canDelete": True, "canManageProperties": True},
    ]}
    result = json.loads(_scope_schema_capabilities(json.dumps(original), developer()))
    assert not result["items"][0]["canDelete"]
    assert not result["items"][0]["canManageProperties"]
    assert result["items"][1]["canDelete"]


def test_task_capability_uses_persisted_space_and_rejects_current_space_mismatch(database):
    from service.workflow_jobs import authorize_workflow_resource, workflow_resource_capabilities
    actor = developer()
    assert workflow_resource_capabilities(actor, {"id": "unknown"})["graphSpace"] is None
    assert not workflow_resource_capabilities(actor, {"id": "unknown"})["canOperate"]
    public = workflow_resource_capabilities(actor, {"owner": "admin", "graphSpace": "dev"})
    assert public["graphSpace"] == "dev" and not public["writeAllowed"]
    with pytest.raises(HTTPException):
        authorize_workflow_resource(replace(actor, context_graph_space="dev"),
            {"owner": "admin", "clientId": "a", "graphSpace": "a_space"}, "read")


def test_source_binding_without_request_header_still_uses_schema_business(database, monkeypatch):
    from types import SimpleNamespace

    from biz.dependencies.resources import ensure_owner_access
    from biz.handler import schema_management, workflow_system
    from biz.schemas.schema_management import SchemaSourcesReplace
    engine, _ = database
    migration.migrate(engine, apply=True, plan=two_business_plan())
    monkeypatch.setattr(schema_management.SchemaManagementDAO, "get",
                        lambda self, key: SimpleNamespace(graph_space="a_space"))
    monkeypatch.setattr(workflow_system, "_validate_resource_selectors",
                        lambda actor, selectors: ensure_owner_access(actor, "business:b"))
    payload = SchemaSourcesReplace(sources=[{
        "datasourceId": "config-b", "databaseName": "source_db", "tableName": "items",
    }])
    with pytest.raises(HTTPException) as error:
        schema_management.replace_schema_sources("schema-a", developer(), None, payload)
    assert error.value.status_code == 403
