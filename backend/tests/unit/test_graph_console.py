"""nGQL 控制台分类器单测（不触图服务）。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from service import graph_console
from service.graph_console import (
    GraphConsoleError,
    bound_read_statement,
    classify_statement,
    run_statement,
)
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


class _Calls(list):
    rows: list


@pytest.fixture
def console_backend(monkeypatch):
    monkeypatch.setenv("TRS_GRAPH_SPACE", "shared_business")
    calls = _Calls()
    rows = [{"result": 1}]
    bindings = {("101", "bound_private")}

    class Session:
        closed = False

        def close(self):
            self.closed = True

    class Client:
        def list_spaces(self):
            return ["shared_business", "bound_private", "other_private"]

        def execute_read(self, statement, **kwargs):
            calls.append(("read", statement))
            return SimpleNamespace(records=rows[:], summary={})

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

        def _all_spaces(self):
            # 控制台空间存在性校验走 SHOW SPACES 的 30s 缓存入口（同配置页）
            return client.list_spaces()

    monkeypatch.setattr("infra.mysql.create_session", Session)
    monkeypatch.setattr("service.graph_space.GraphSpaceService", SpaceService)
    monkeypatch.setattr("infra.graph_db.get_space_client", lambda space: client)
    calls.rows = rows
    return calls


@pytest.mark.parametrize("space", ["shared_business", "bound_private"])
def test_ordinary_user_can_read_shared_default_and_bound_space(console_backend, space) -> None:
    result = run_statement(_actor(), space, "RETURN 1 AS result")
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
    run_statement(_actor(is_admin=True), "other_private", 'DELETE VERTEX "p1"')
    assert console_backend == [("write", 'DELETE VERTEX "p1"')]


# ---------- 渗透 B1：普通用户只读语句的服务端行数上限 ----------


@pytest.mark.parametrize(
    "statement,expected",
    [
        (
            "LOOKUP ON Paper YIELD properties(vertex)",
            "LOOKUP ON Paper YIELD properties(vertex) | LIMIT 1000",
        ),
        (
            'GO FROM "p1" OVER CITES YIELD dst(edge);',
            'GO FROM "p1" OVER CITES YIELD dst(edge) | LIMIT 1000',
        ),
        (
            'FETCH PROP ON Paper "p1" YIELD vertex AS v',
            'FETCH PROP ON Paper "p1" YIELD vertex AS v | LIMIT 1000',
        ),
        ("MATCH (v:Paper) RETURN v", "MATCH (v:Paper) RETURN v LIMIT 1000"),
        ("MATCH (v:Paper)--(p) RETURN p LIMIT 20", "MATCH (v:Paper)--(p) RETURN p LIMIT 20"),
        (
            "MATCH (a)-->(b)<--(c) RETURN a SKIP 5 LIMIT 1000;",
            "MATCH (a)-->(b)<--(c) RETURN a SKIP 5 LIMIT 1000",
        ),
        (
            'MATCH (v) WHERE v.Paper.url == "http://x -- LIMIT 5" RETURN v',
            'MATCH (v) WHERE v.Paper.url == "http://x -- LIMIT 5" RETURN v LIMIT 1000',
        ),
        (
            "UNWIND range(1, 100000000) AS x RETURN x",
            "UNWIND range(1, 100000000) AS x RETURN x LIMIT 1000",
        ),
        ("SHOW TAGS", "SHOW TAGS"),
        ("RETURN 1 AS result", "RETURN 1 AS result"),
    ],
)
def test_user_read_statements_get_row_bound(statement, expected) -> None:
    assert bound_read_statement(statement) == expected


@pytest.mark.parametrize(
    "statement,reason",
    [
        ("MATCH (v) RETURN v LIMIT 469009", "LIMIT"),
        ("MATCH (v) RETURN v -- LIMIT 5", "注释"),
        ("MATCH (v) RETURN v # LIMIT 5", "注释"),
        ("MATCH (v) RETURN v // LIMIT 5", "注释"),
        ("MATCH (v) RETURN v /* LIMIT 5 */", "注释"),
        ("MATCH (v) RETURN v UNION MATCH (u) RETURN u LIMIT 1", "集合运算"),
        ('GO FROM "a" OVER e YIELD dst(edge) UNION GO FROM "b" OVER e YIELD dst(edge)', "集合运算"),
        ('MATCH (v) WHERE v.P.name == "x RETURN v', "引号"),
    ],
)
def test_unboundable_user_statements_rejected(statement, reason) -> None:
    with pytest.raises(GraphConsoleError, match=reason):
        bound_read_statement(statement)


def test_ordinary_user_query_is_executed_bounded_and_truncated(console_backend) -> None:
    console_backend.rows[:] = [{"v": i} for i in range(1500)]
    result = run_statement(_actor(), "shared_business", "LOOKUP ON Paper YIELD properties(vertex)")
    assert console_backend == [("read", "LOOKUP ON Paper YIELD properties(vertex) | LIMIT 1000")]
    assert len(result["records"]) == 1000
    assert result["summary"]["truncated"] is True


def test_administrator_reads_are_not_rewritten(console_backend) -> None:
    run_statement(_actor(is_admin=True), "shared_business", "LOOKUP ON Paper YIELD id(vertex)")
    assert console_backend == [("read", "LOOKUP ON Paper YIELD id(vertex)")]


def test_bounded_and_unbounded_results_never_share_cache(console_backend, monkeypatch) -> None:
    monkeypatch.setattr(graph_console, "_ngql_payload_cache", {})
    statement = "LOOKUP ON Paper YIELD id(vertex)"
    graph_console.run_statement_cached_payload(_actor(is_admin=True), "shared_business", statement)
    graph_console.run_statement_cached_payload(_actor(), "shared_business", statement)
    assert [call[1] for call in console_backend] == [statement, statement + " | LIMIT 1000"]
