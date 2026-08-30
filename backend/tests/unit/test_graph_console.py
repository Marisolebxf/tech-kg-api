"""nGQL 控制台分类器单测（不触图服务）。"""

from __future__ import annotations

import pytest

from service.graph_console import GraphConsoleError, classify_statement
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
