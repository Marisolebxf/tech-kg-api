import pytest
from sqlalchemy import create_engine, insert, select

from db_model.platform_governance import PlatformUser, PlatformUserRole
from script.bootstrap_business_admin import bootstrap


@pytest.fixture
def engine():
    engine = create_engine("sqlite://")
    PlatformUser.__table__.create(engine)
    PlatformUserRole.__table__.create(engine)
    with engine.begin() as conn:
        conn.execute(insert(PlatformUser.__table__).values(user_id="auth-id", username="operator"))
    yield engine
    engine.dispose()


def test_preview_apply_and_repeat(engine):
    assert bootstrap(engine, "operator")["isLocalAdmin"] is False
    assert bootstrap(engine, "operator", "auth-id", True)["changed"] is True
    assert bootstrap(engine, "operator", "auth-id", True)["changed"] is False
    with engine.connect() as conn:
        assert len(conn.execute(select(PlatformUserRole.__table__)).all()) == 1


@pytest.mark.parametrize(
    "username,expected", [("missing", "auth-id"), ("operator", "wrong"), ("operator", None)]
)
def test_invalid_identity_never_writes(engine, username, expected):
    with pytest.raises(ValueError):
        bootstrap(engine, username, expected, True)
    with engine.connect() as conn:
        assert conn.execute(select(PlatformUserRole.__table__)).first() is None


def test_ambiguous_username_never_writes(engine):
    with engine.begin() as conn:
        conn.execute(
            insert(PlatformUser.__table__).values(user_id="another-id", username="operator")
        )
    with pytest.raises(ValueError):
        bootstrap(engine, "operator", "auth-id", True)
