"""nGQL 控制台分类器单测（不触图服务）。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from service.graph_console import GraphConsoleError, classify_statement, run_statement
from service.platform_access import PlatformActor


def _actor(is_admin: bool = False) -> PlatformActor:
    return PlatformActor(user_id="101", username="u", display_name="u", email="", is_admin=is_admin)


def test_read_statements_classified() -> None:
    assert classify_statement("MATCH (v) RETURN v LIMIT 10") == "read"
    assert classify_statement("  LOOKUP ON paper YIELD id(vertex)  ") == "read"
    assert classify_statement("SHOW SPACES;") == "read"
    assert classify_statement("DESCRIBE TAG paper") == "read"
    assert classify_statement('GET SUBGRAPH 1 STEPS FROM "p1"') == "read"
    assert classify_statement('FIND SHORTEST PATH FROM "a" TO "b" YIELD path') == "read"
    assert classify_statement("-- 注释\nMATCH (v) RETURN v") == "read"


def test_write_statements_classified() -> None:
    assert classify_statement('INSERT VERTEX paper(name) VALUES "p1":("x")') == "write"
    assert classify_statement('UPDATE VERTEX ON paper SET name = "y"') == "write"
    assert classify_statement('DELETE VERTEX "p1"') == "write"
    assert classify_statement('UPSERT VERTEX ON paper SET name = "y"') == "write"


def test_ddl_always_rejected() -> None:
    for stmt in (
        "CREATE SPACE x",
        "CREATE TAG t(name string)",
        "ALTER TAG t ADD (age int)",
        "DROP TAG paper",
        "DROP SPACE x",
        "TRUNCATE TAG paper",
        "REBUILD TAG INDEX idx",
        "SUBMIT JOB STATS",
        "ADMIN...",
        "USE techkg",
    ):
        with pytest.raises(GraphConsoleError) as exc_info:
            classify_statement(stmt)
        assert exc_info.value.status_code == 403


def test_multi_statement_rejected() -> None:
    with pytest.raises(GraphConsoleError, match="一条语句"):
        classify_statement("MATCH (v) RETURN v; DROP TAG paper")
    with pytest.raises(GraphConsoleError, match="一条语句"):
        classify_statement("SHOW SPACES; SHOW TAGS")


def test_pipe_rejected() -> None:
    with pytest.raises(GraphConsoleError, match="管道"):
        classify_statement("MATCH (v) RETURN v | YIELD count(*)")


def test_unknown_token_rejected() -> None:
    with pytest.raises(GraphConsoleError, match="不支持的语句开头"):
        classify_statement("EXEC something")


def test_empty_or_comment_only_rejected() -> None:
    with pytest.raises(GraphConsoleError):
        classify_statement("")
    with pytest.raises(GraphConsoleError):
        classify_statement("   ")
    with pytest.raises(GraphConsoleError):
        classify_statement("-- only comment")


def test_too_long_rejected() -> None:
    with pytest.raises(GraphConsoleError, match="过长"):
        classify_statement("MATCH (v) RETURN " + "x" * 5000)


def test_trailing_semicolon_ok() -> None:
    assert classify_statement("SHOW TAGS;") == "read"


@pytest.fixture
def console_backend(monkeypatch):
    monkeypatch.setenv("TRS_GRAPH_SPACE", "shared_business")
    calls = []
    bindings = {("101", "bound_private")}

    class Session:
        closed = False

        def close(self):
            self.closed = True

    class Client:
        def list_spaces(self):
            return ["shared_business", "bound_private", "other_private"]

        def execute_read(self, statement):
            calls.append(("read", statement))
            return SimpleNamespace(records=[{"result": 1}], summary={})

        def execute_write(self, statement):
            calls.append(("write", statement))
            return SimpleNamespace(records=[], summary={})

    client = Client()

    class SpaceService:
        def __init__(self, session):
            self.session = session
            self.client = client

        def is_bound(self, user_id, space):
            assert not self.session.closed
            return (user_id, space) in bindings

    monkeypatch.setattr("infra.mysql.create_session", Session)
    monkeypatch.setattr("service.graph_space.GraphSpaceService", SpaceService)
    monkeypatch.setattr("infra.graph_db.get_space_client", lambda space: client)
    return calls


@pytest.mark.parametrize("space", ["shared_business", "bound_private"])
def test_ordinary_user_can_read_shared_default_and_bound_space(console_backend, space) -> None:
    result = run_statement(_actor(), space, "RETURN 1 AS result")
    assert result["kind"] == "read"
    assert result["records"] == [{"result": 1}]
    assert console_backend == [("read", "RETURN 1 AS result")]


def test_ordinary_user_cannot_read_other_private_space(console_backend) -> None:
    with pytest.raises(GraphConsoleError) as exc_info:
        run_statement(_actor(), "other_private", "RETURN 1 AS result")
    assert exc_info.value.status_code == 403
    assert console_backend == []


@pytest.mark.parametrize("space", ["shared_business", "bound_private"])
def test_shared_or_bound_read_access_never_grants_write(console_backend, space) -> None:
    with pytest.raises(GraphConsoleError) as exc_info:
        run_statement(_actor(), space, 'DELETE VERTEX "p1"')
    assert exc_info.value.status_code == 403
    assert console_backend == []


def test_administrator_keeps_existing_write_permission(console_backend) -> None:
    result = run_statement(_actor(is_admin=True), "other_private", 'DELETE VERTEX "p1"')
    assert result["kind"] == "write"
    assert console_backend == [("write", 'DELETE VERTEX "p1"')]
