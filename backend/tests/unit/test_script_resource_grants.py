from contextlib import contextmanager
from datetime import timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from db_model.script_resource_grant import ScriptResourceGrant
from service import script_resource_grants as grants


@pytest.fixture
def database(monkeypatch):
    engine = create_engine("sqlite://", poolclass=StaticPool)
    ScriptResourceGrant.__table__.create(engine)

    @contextmanager
    def scope():
        with Session(engine) as session:
            with session.begin():
                yield session

    monkeypatch.setattr(grants, "session_scope", scope)
    yield engine
    engine.dispose()


def actor(user="alice", business="client-a"):
    return SimpleNamespace(user_id=user, business_id=business)


def test_grant_survives_steps_but_not_scope_changes(database):
    grants.remember("a" * 64, "record-1", actor(), "private")
    grants.remember("a" * 64, "record-1", actor(), "private")
    assert grants.allows("a" * 64, "record-1", actor(), "private")
    assert not grants.allows("b" * 64, "record-1", actor(), "private")
    assert not grants.allows("a" * 64, "record-1", actor(business="client-b"), "private")
    assert not grants.allows("a" * 64, "record-1", actor(user="bob"), "private")
    assert not grants.allows("a" * 64, "record-1", actor(), "production")
    assert not grants.allows("a" * 64, "forged", actor(), "private")
    with pytest.raises(ValueError):
        grants.remember("a" * 64, "record-1", actor(user="bob"), "private")


def test_expired_grants_are_denied_and_cleaned_on_registration(database, monkeypatch):
    now = grants._now()
    monkeypatch.setattr(grants, "_now", lambda: now)
    grants.remember("a" * 64, "record-1", actor(), "private")
    monkeypatch.setattr(grants, "_now", lambda: now + timedelta(days=30))
    assert not grants.allows("a" * 64, "record-1", actor(), "private")
    grants.remember("b" * 64, "record-2", actor(), "private")
    with Session(database) as session:
        assert len(session.scalars(select(ScriptResourceGrant)).all()) == 1


@pytest.mark.parametrize("record", ["../other", "x?y", "x%2fy", "x#y", "", "x" * 129])
def test_path_control_record_ids_cannot_be_granted(database, record):
    assert not grants.allows("a" * 64, record, actor(), "private")
    with pytest.raises(ValueError):
        grants.remember("a" * 64, record, actor(), "private")
