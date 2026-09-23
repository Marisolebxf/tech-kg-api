"""Business binding CLI checks real records without live account credentials."""

import copy

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from db_model.business_access import (
    BusinessClient,
    BusinessGraphSpace,
    BusinessMember,
    BusinessSpaceRequest,
)
from db_model.platform_governance import PlatformUser, PlatformUserRole, UserGraphSpace
from script.configure_business_access import configure, inspect_bindings, main, validate_plan


@pytest.fixture
def database():
    engine = create_engine("sqlite://")
    for model in (
        PlatformUser,
        PlatformUserRole,
        UserGraphSpace,
        BusinessClient,
        BusinessMember,
        BusinessGraphSpace,
        BusinessSpaceRequest,
    ):
        model.__table__.create(engine)
    with Session(engine) as session, session.begin():
        for name in ("admin", "reader", "builder"):
            session.add(PlatformUser(user_id=f"id-{name}", username=name))
        session.flush()
        session.add(
            PlatformUserRole(
                user_id="id-builder", role_code="platform_developer", granted_by="legacy"
            )
        )
        session.add(UserGraphSpace(user_id="id-builder", space_name="private_dev"))
    yield engine
    engine.dispose()


@pytest.fixture
def plan():
    return {
        "business": {"clientId": "test-business", "name": "Test business"},
        "sharedSpace": "public_graph",
        "businessSpaces": ["private_dev", "private_test"],
        "users": [
            {"username": "admin", "userId": "id-admin", "role": "admin"},
            {"username": "reader", "userId": "id-reader", "role": "user"},
            {"username": "builder", "userId": "id-builder", "role": "developer"},
        ],
    }


def run(session, plan, **kwargs):
    return configure(
        session,
        plan,
        list_spaces=lambda: ["public_graph", "private_dev", "private_test"],
        configured_shared_space="public_graph",
        **kwargs,
    )


def test_inspect_and_dry_run_never_write(database, plan):
    with Session(database) as session, session.begin():
        inspection = inspect_bindings(session, ["builder", "missing"])
        assert inspection["unmatchedUsernames"] == ["missing"]
        assert inspection["users"][0]["legacyPersonalSpaces"] == ["private_dev"]
        result = run(session, plan)
        assert result["applied"] is False
        assert result["removeLegacyDeveloperFrom"] == ["id-builder"]
    with Session(database) as session:
        assert session.get(BusinessClient, "test-business") is None
        assert session.scalar(select(PlatformUserRole.role_code)) == "platform_developer"


def test_apply_idempotent_and_admin_is_global(database, plan):
    for _ in range(2):
        with Session(database) as session, session.begin():
            run(session, plan, apply=True)
    with Session(database) as session:
        assert len(list(session.scalars(select(BusinessClient)))) == 1
        assert len(list(session.scalars(select(BusinessGraphSpace)))) == 3
        assert session.get(BusinessMember, "id-admin") is None
        assert session.get(BusinessMember, "id-builder").role == "developer"
        assert session.get(BusinessMember, "id-reader").role == "user"
        assert session.scalar(select(PlatformUserRole.role_code)) == "platform_admin"
        assert session.scalar(select(UserGraphSpace.space_name)) == "private_dev"
        public = session.get(BusinessGraphSpace, "public_graph")
        assert public.client_id is None and public.is_shared_production


@pytest.mark.parametrize(
    "mutation",
    [
        lambda p: p["users"][-1].update(userId="wrong"),
        lambda p: p["users"][-1].update(username="missing"),
        lambda p: p["users"][-1].update(role="reviewer"),
        lambda p: p["users"][-1].update(password="not-allowed"),
        lambda p: p["businessSpaces"].append("public_graph"),
        lambda p: p["businessSpaces"].append("missing"),
        lambda p: p["users"].append(copy.deepcopy(p["users"][0])),
    ],
)
def test_invalid_plan_never_partially_writes(database, plan, mutation):
    mutation(plan)
    with Session(database) as session, session.begin():
        with pytest.raises(ValueError):
            run(session, plan, apply=True)
        # Even if caller catches validation failure and commits, there were no writes.
    with Session(database) as session:
        assert session.get(BusinessClient, "test-business") is None
        assert session.scalar(select(PlatformUserRole.role_code)) == "platform_developer"


@pytest.mark.parametrize("role", ["platform_admin", "portal_admin_snapshot"])
def test_refuses_demotion_of_existing_admin(database, plan, role):
    with Session(database) as session, session.begin():
        session.add(PlatformUserRole(user_id="id-builder", role_code=role, granted_by="original"))
    with Session(database) as session, session.begin():
        with pytest.raises(ValueError, match="administrator authority"):
            run(session, plan, apply=True)


def test_configured_admin_and_business_only_conflicts(database, plan):
    with Session(database) as session:
        with pytest.raises(ValueError, match="administrator authority"):
            run(session, plan, initial_admin_ids=("id-reader",))
        with pytest.raises(ValueError, match="businessOnly"):
            run(session, plan, business_only_ids=("id-builder",))
        result = run(session, plan, business_only_ids=("id-reader",))
        assert "businessOnly" in result["warnings"][0]


@pytest.mark.parametrize("conflict", ["member", "space", "shared", "name", "disabled"])
def test_conflicting_existing_state_never_overwritten(database, plan, conflict):
    with Session(database) as session, session.begin():
        session.add(BusinessClient(client_id="other", name="Other", enabled=True))
        session.flush()
        if conflict == "member":
            session.add(BusinessMember(user_id="id-builder", client_id="other", role="user"))
        elif conflict == "space":
            session.add(BusinessGraphSpace(space_name="private_test", client_id="other"))
        elif conflict == "shared":
            session.add(
                BusinessGraphSpace(
                    space_name="other_public", is_shared_production=True, shared_key="production"
                )
            )
        else:
            session.add(
                BusinessClient(
                    client_id="test-business",
                    name="Wrong" if conflict == "name" else "Test business",
                    enabled=conflict != "disabled",
                )
            )
    with Session(database) as session, session.begin(), pytest.raises(ValueError):
        run(session, plan, apply=True)


def test_shared_configuration_and_graph_service_must_match(database, plan):
    with Session(database) as session:
        with pytest.raises(ValueError, match="TRS_GRAPH_SPACE"):
            configure(session, plan, list_spaces=lambda: [], configured_shared_space="wrong")
        with pytest.raises(ValueError, match="invalid space list"):
            configure(
                session, plan, list_spaces=lambda: None, configured_shared_space="public_graph"
            )


def test_duplicate_username_is_not_resolved_by_guessing(database, plan):
    with Session(database) as session, session.begin():
        session.add(PlatformUser(user_id="another-id", username="reader"))
    with Session(database) as session, pytest.raises(ValueError, match="exactly one"):
        run(session, plan)


def test_transaction_rollback_restores_all_changes(database, plan):
    with pytest.raises(RuntimeError), Session(database) as session, session.begin():
        run(session, plan, apply=True)
        raise RuntimeError("later failure")
    with Session(database) as session:
        assert session.get(BusinessClient, "test-business") is None
        assert session.scalar(select(PlatformUserRole.role_code)) == "platform_developer"


def test_cli_inspect_cannot_apply():
    with pytest.raises(SystemExit):
        main(["--inspect", "--username", "reader", "--apply"])


def test_no_secrets_accepted_in_plan(plan):
    plan["password"] = "not-allowed"
    with pytest.raises(ValueError):
        validate_plan(plan)


@pytest.mark.parametrize("status", ["creating", "failed", "pending", "missing"])
def test_unfinished_legacy_provisioning_blocks_binding(database, plan, status):
    with Session(database) as session, session.begin():
        session.add(BusinessClient(client_id="test-business", name="Test business", enabled=True))
        session.flush()
        if status != "missing":
            session.add(
                BusinessSpaceRequest(
                    id="request",
                    client_id="test-business",
                    space_name="private_dev",
                    requested_by="id-builder",
                    status=status,
                )
            )
        session.add(
            BusinessGraphSpace(
                space_name="private_dev", client_id="test-business", provision_request_id="request"
            )
        )
    with Session(database) as session, pytest.raises(ValueError, match="provisioning"):
        run(session, plan, apply=True)


def test_graph_errors_do_not_expose_driver_credentials(database, plan):
    def unavailable():
        raise ValueError("connection secret should not be printed")

    with Session(database) as session, pytest.raises(ValueError, match="Could not verify") as exc:
        configure(session, plan, list_spaces=unavailable, configured_shared_space="public_graph")
    assert "secret" not in str(exc.value)


def test_client_id_matches_existing_underscore_contract(plan):
    plan["business"]["clientId"] = "existing_business"
    assert validate_plan(plan) is plan
