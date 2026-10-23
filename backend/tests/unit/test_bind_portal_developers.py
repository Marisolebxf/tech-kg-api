from copy import deepcopy
from dataclasses import replace

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from config.auth import AuthSettings
from db_model.base import Base
from db_model.business_access import (
    BusinessClient,
    BusinessMember,
    BusinessMembership,
    BusinessMembershipState,
)
from db_model.platform_governance import PlatformUser, PlatformUserRole
from infra.user_center import UserCenterClient
from script.bind_portal_developers import bind

PLAN = {
    "businesses": [{"clientId": "team-a", "name": "Team A"}],
    "members": [{"userId": "213", "username": "test@example.test", "clientId": "team-a"}],
}


@pytest.fixture
def db(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            m.__table__
            for m in (
                BusinessClient,
                BusinessMember,
                BusinessMembership,
                BusinessMembershipState,
                PlatformUser,
                PlatformUserRole,
            )
        ],
    )
    monkeypatch.setattr(UserCenterClient, "role_user_ids", lambda self, code: frozenset({"213"}))
    with Session(engine) as session:
        session.add(PlatformUser(user_id="213", username="test@example.test"))
        session.commit()
        yield session
    engine.dispose()


def settings(**kwargs):
    return replace(
        AuthSettings.from_env(),
        enabled=True,
        portal_developer_role_codes=("bkg_developer",),
        initial_admin_user_ids=(),
        **kwargs,
    )


def test_dry_run_is_read_only_and_apply_is_idempotent(db):
    assert bind(db, PLAN, settings())["applied"] is False
    assert db.get(BusinessClient, "team-a") is None
    for _ in range(2):
        bind(db, PLAN, settings(), apply=True)
        db.commit()
    assert len(list(db.scalars(select(BusinessMembership)))) == 1
    assert db.get(BusinessMembership, ("213", "team-a")).role == "developer"
    assert db.get(BusinessMembershipState, "213") is not None
    assert db.get(BusinessMember, "213") is None
    assert list(db.scalars(select(PlatformUserRole))) == []


def test_username_mismatch_or_missing_portal_role_does_not_write(db, monkeypatch):
    wrong = deepcopy(PLAN)
    wrong["members"][0]["username"] = "wrong"
    with pytest.raises(ValueError):
        bind(db, wrong, settings(), apply=True)
    monkeypatch.setattr(UserCenterClient, "role_user_ids", lambda self, code: frozenset())
    with pytest.raises(ValueError):
        bind(db, PLAN, settings(), apply=True)
    assert db.get(BusinessClient, "team-a") is None


@pytest.mark.parametrize("source", [BusinessMember, BusinessMembership])
def test_existing_binding_even_disabled_business_cannot_be_transferred(db, source):
    db.add(BusinessClient(client_id="other", name="Other", enabled=False))
    db.flush()
    db.add(source(user_id="213", client_id="other", role="developer"))
    db.commit()
    with pytest.raises(ValueError, match="其他业务"):
        bind(db, PLAN, settings(), apply=True)
    assert db.get(BusinessClient, "team-a") is None


def test_admin_is_not_demoted(db):
    db.add(PlatformUserRole(user_id="213", role_code="platform_admin", granted_by="test"))
    db.commit()
    with pytest.raises(ValueError, match="管理员"):
        bind(db, PLAN, settings(), apply=True)


def test_business_only_cannot_be_promoted(db):
    with pytest.raises(ValueError, match="业务专用"):
        bind(db, PLAN, settings(business_only_user_ids=("213",)), apply=True)


def test_existing_business_name_conflict_rejected(db):
    db.add(BusinessClient(client_id="existing-id", name="Team A"))
    db.commit()
    with pytest.raises(ValueError, match="沿用现有编号"):
        bind(db, PLAN, settings(), apply=True)


def test_username_only_plan_resolves_target_database_id_without_changing_input(db):
    plan = deepcopy(PLAN)
    del plan["members"][0]["userId"]
    report = bind(db, plan, settings(), apply=True)
    db.commit()
    assert report["members"][0]["userId"] == "213"
    assert "userId" not in plan["members"][0]
    assert db.get(BusinessMembership, ("213", "team-a")).role == "developer"


@pytest.mark.parametrize("duplicate", [False, True])
def test_username_only_plan_requires_unique_registered_account(db, duplicate):
    plan = deepcopy(PLAN)
    del plan["members"][0]["userId"]
    if duplicate:
        db.add(PlatformUser(user_id="other", username=plan["members"][0]["username"]))
    else:
        db.delete(db.get(PlatformUser, "213"))
    db.commit()
    with pytest.raises(ValueError, match="唯一"):
        bind(db, plan, settings(), apply=True)
    assert db.get(BusinessClient, "team-a") is None


def test_plan_cannot_be_applied_to_another_user_center(db):
    plan = {**PLAN, "userCenterOpenApiBaseUrl": "https://target.test/uc/open-api/system"}
    with pytest.raises(ValueError, match="跨环境"):
        bind(
            db,
            plan,
            settings(user_center_open_api_base_url="https://other.test/uc/open-api/system"),
            apply=True,
        )
    assert db.get(BusinessClient, "team-a") is None
    assert not bind(
        db, plan, settings(user_center_open_api_base_url=plan["userCenterOpenApiBaseUrl"] + "/")
    )["applied"]
