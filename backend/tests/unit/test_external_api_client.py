from contextlib import contextmanager
from datetime import timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from db_model.external_api_client import ExternalAPIClient
from service import external_api_client as service


@pytest.fixture
def client_db(monkeypatch):
    engine = create_engine("sqlite://")
    ExternalAPIClient.__table__.create(engine)

    @contextmanager
    def scope():
        with Session(engine) as session, session.begin():
            yield session

    monkeypatch.setattr(service, "session_scope", scope)
    yield scope
    engine.dispose()


def issue():
    return service.issue_key("partner-a", business_name="业务方甲", expires_days=30)


def test_issue_persists_only_digest_and_authenticates(client_db):
    key = issue()
    with client_db() as session:
        row = session.get(ExternalAPIClient, "partner-a")
        assert row.api_key_hash == service.hash_key(key)
        assert key not in [getattr(row, column.name) for column in row.__table__.columns]
        assert row.scopes == [service.PROJECT_RELATIONS_READ]
    assert service.authenticate_client("partner-a", key).client_id == "partner-a"


@pytest.mark.parametrize("failure", ["wrong", "missing", "expired", "disabled", "scope"])
def test_rejects_invalid_credentials_and_permissions(client_db, failure):
    key = issue()
    client_id = "partner-a"
    with client_db() as session:
        row = session.get(ExternalAPIClient, client_id)
        if failure == "expired":
            row.expires_at = service.utc_now() - timedelta(seconds=1)
        elif failure == "disabled":
            row.enabled = False
        elif failure == "scope":
            row.scopes = []
    if failure == "wrong":
        key = "wrong-key"
    elif failure == "missing":
        client_id = "unknown"
    with pytest.raises(service.ExternalClientError) as error:
        service.authenticate_client(client_id, key)
    assert error.value.status_code == (403 if failure == "scope" else 401)


def test_rotation_invalidates_old_key_and_keeps_disabled_state(client_db):
    old_key = issue()
    new_key = service.issue_key("partner-a", business_name=None, expires_days=30)
    assert new_key != old_key
    with pytest.raises(service.ExternalClientError):
        service.authenticate_client("partner-a", old_key)
    assert service.authenticate_client("partner-a", new_key).client_id == "partner-a"
    service.disable_client("partner-a")
    rotated = service.issue_key("partner-a", business_name=None, expires_days=30)
    with client_db() as session:
        assert session.get(ExternalAPIClient, "partner-a").enabled is False
    with pytest.raises(service.ExternalClientError):
        service.authenticate_client("partner-a", rotated)


def test_database_failure_is_safe_503(monkeypatch):
    @contextmanager
    def broken_scope():
        raise OperationalError("secret-db-statement", {}, Exception("secret-password"))
        yield

    monkeypatch.setattr(service, "session_scope", broken_scope)
    with pytest.raises(service.ExternalClientError) as error:
        service.authenticate_client("partner-a", "test-key")
    assert error.value.status_code == 503
    assert "secret" not in str(error.value)
