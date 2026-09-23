"""Authorization regressions for persisted tasks and workflow payloads."""

from contextlib import nullcontext
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from service import workflow_jobs as jobs
from service.platform_access import PlatformActor


def actor(role="developer", business="a", admin=False):
    return PlatformActor(
        "alice", "alice", "Alice", "", admin, business_id=business, business_role=role
    )


@pytest.fixture(autouse=True)
def scoped(monkeypatch):
    monkeypatch.setattr(jobs, "rbac_enabled", lambda: True)

    def check_space(actor, space, action="read"):
        if space not in {"a-space", "production"} or (action != "read" and not actor.can_develop):
            raise HTTPException(403, "denied")

    monkeypatch.setattr(jobs, "ensure_space_access", check_space)
    import infra.mysql

    monkeypatch.setattr(infra.mysql, "session_scope", lambda: nullcontext(None))


def test_same_business_colleague_can_read_job():
    jobs.authorize_workflow_resource(
        actor(), {"owner": "colleague", "clientId": "a", "graphSpace": "a-space"}
    )


def test_persisted_business_cannot_expose_production_task():
    with pytest.raises(HTTPException):
        jobs.authorize_workflow_resource(
            actor(), {"owner": "outsider", "clientId": "b", "graphSpace": "production"}
        )


def test_nested_payload_cannot_hide_second_space_alias():
    with pytest.raises(HTTPException):
        jobs.authorize_workflow_resource(
            actor(), {"payload": {"graphSpace": "a-space", "graph_space": "other-space"}}
        )


def test_ordinary_user_cannot_mutate_own_space():
    with pytest.raises(HTTPException):
        jobs.authorize_workflow_resource(actor("user"), {"graphSpace": "a-space"}, "write")


def test_legacy_unscoped_resource_is_admin_only():
    assert not jobs.workflow_resource_visible(actor(), {"id": "old-job"})
    assert jobs.workflow_resource_visible(actor(admin=True), {"id": "old-job"})


def test_all_chain_schemas_are_checked(monkeypatch):
    import infra.workflow_mysql
    from dao.schema_management import SchemaManagementDAO

    monkeypatch.setattr(infra.workflow_mysql, "workflow_session_scope", lambda: nullcontext(None))
    monkeypatch.setattr(
        SchemaManagementDAO,
        "get",
        lambda self, schema_id: SimpleNamespace(
            graph_space="a-space" if schema_id == "a" else "other-space"
        ),
    )
    with pytest.raises(HTTPException):
        jobs.authorize_workflow_resource(
            actor(), {"schemaIds": ["a", "b"], "graphSpace": "a-space"}
        )


def test_missing_background_identity_is_not_elevated():
    with pytest.raises(HTTPException):
        jobs.authorize_background_execution({"schemaId": "a"})


def test_disabled_flag_preserves_legacy_behavior(monkeypatch):
    monkeypatch.setattr(jobs, "rbac_enabled", lambda: False)
    jobs.authorize_workflow_resource(actor("user"), {}, "write")
    jobs.authorize_background_execution({})


def test_jobs_cache_does_not_survive_permission_changes(monkeypatch):
    from biz.handler import workflow_system

    monkeypatch.setattr(workflow_system, "rbac_enabled", lambda: True)
    workflow_system._jobs_cache_put("test-rbac", "sensitive-result")
    assert workflow_system._jobs_cache_get("test-rbac") is None


@pytest.mark.parametrize("membership", [("a", "user"), ("b", "developer")])
def test_background_job_rechecks_revoked_or_moved_membership(monkeypatch, membership):
    import infra.mysql
    from service import business_access_control

    fake_session = SimpleNamespace(
        get=lambda model, user_id: SimpleNamespace(username=user_id, nickname=user_id, email=""),
        scalar=lambda query: None,
    )
    monkeypatch.setattr(infra.mysql, "session_scope", lambda: nullcontext(fake_session))
    monkeypatch.setattr(business_access_control, "resolve_membership", lambda user_id: membership)
    monkeypatch.delenv("PLATFORM_INITIAL_ADMIN_USER_IDS", raising=False)
    with pytest.raises(HTTPException):
        jobs.authorize_background_execution(
            {"actorUserId": "alice", "clientId": "a", "graphSpace": "a-space"}
        )


def test_schema_definition_and_backfill_keys_do_not_collide_across_spaces(monkeypatch):
    from service import schema_extraction

    monkeypatch.setattr(schema_extraction, "rbac_enabled", lambda: True)
    first = schema_extraction.build_extract_definition(
        {"id": "schema-a", "schema_key": "same-name", "graph_space": "a-space"}
    )
    second = schema_extraction.build_extract_definition(
        {"id": "schema-b", "schema_key": "same-name", "graph_space": "b-space"}
    )
    assert first["id"] != second["id"]
    assert schema_extraction.extract_watermark_definition_ids("same-name", "schema-a") == [
        first["id"]
    ]


def test_schema_detail_checks_persisted_space_before_cached_payload(monkeypatch):
    from biz.handler import schema_management

    monkeypatch.setattr(schema_management, "rbac_enabled", lambda: True)
    monkeypatch.setattr(
        schema_management.SchemaManagementDAO,
        "get",
        lambda self, schema_id: SimpleNamespace(graph_space="other-space"),
    )
    monkeypatch.setattr(
        schema_management,
        "ensure_space_access",
        lambda *args: (_ for _ in ()).throw(HTTPException(403, "denied")),
    )
    with pytest.raises(HTTPException):
        schema_management.get_schema_detail("schema-other", actor(), None)


async def test_overview_never_queries_unauthorized_space(monkeypatch):
    from biz.handler import platform_overview

    monkeypatch.setattr(platform_overview, "rbac_enabled", lambda: True)
    monkeypatch.setattr(
        platform_overview,
        "ensure_space_access",
        lambda *args: (_ for _ in ()).throw(HTTPException(403, "denied")),
    )
    with pytest.raises(HTTPException):
        await platform_overview._get_overview("other-space", actor())


@pytest.mark.parametrize("admin", [False, True])
def test_schema_target_override_is_rejected_even_for_admin(monkeypatch, admin):
    import infra.workflow_mysql
    from dao.schema_management import SchemaManagementDAO

    monkeypatch.setattr(infra.workflow_mysql, "workflow_session_scope", lambda: nullcontext(None))
    monkeypatch.setattr(
        SchemaManagementDAO, "get", lambda self, schema_id: SimpleNamespace(graph_space="a-space")
    )
    with pytest.raises(HTTPException):
        jobs.authorize_workflow_resource(
            actor(admin=admin), {"schemaId": "schema-a", "graphSpace": "production"}, "write"
        )


def test_creator_moving_business_does_not_reassign_job():
    jobs.authorize_workflow_resource(
        actor(), {"owner": "departed-user", "clientId": "a", "graphSpace": "a-space"}, "write"
    )


def test_legacy_job_without_business_is_hidden():
    assert not jobs.workflow_resource_visible(actor(), {"owner": "alice", "graphSpace": "a-space"})


def test_default_space_writes_deny_ordinary_and_test_users(monkeypatch):
    from dataclasses import replace

    from biz.dependencies import default_space_write

    monkeypatch.setattr(default_space_write, "rbac_enabled", lambda: True)
    with pytest.raises(HTTPException):
        default_space_write.require_default_annotation_writer(actor("user"))
    with pytest.raises(HTTPException):
        default_space_write.require_default_space_writer(
            replace(actor(admin=True), business_only=True)
        )


async def test_admin_edit_keeps_existing_job_business(monkeypatch):
    job = {
        "id": "job-a",
        "owner": "departed",
        "clientId": "a",
        "graphSpace": "a-space",
        "taskType": "legacy",
        "schedule": {"kind": "once"},
    }
    repo = SimpleNamespace(get_job=lambda job_id: job, save_job=lambda value: None)
    service = jobs.WorkflowJobService(repo)
    result = await service.update_job(actor(admin=True, business=""), "job-a", {"name": "Renamed"})
    assert result["clientId"] == "a"


def test_admin_new_job_uses_private_space_business(monkeypatch):
    import infra.mysql

    row = SimpleNamespace(is_shared_production=False, client_id="a")
    monkeypatch.setattr(
        infra.mysql,
        "session_scope",
        lambda: nullcontext(SimpleNamespace(get=lambda model, name: row)),
    )
    assert jobs._job_business(actor(admin=True, business=""), {"graphSpace": "a-space"}) == "a"
