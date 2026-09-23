"""Migration parsing and opt-in verification against a fresh isolated MySQL database."""

import json
import os

import pytest
from sqlalchemy import inspect, text

from script.migrate_business_access import explicit_snapshot_space, migrate


@pytest.mark.parametrize(
    ("left", "right", "space", "reason"),
    [
        ('{"_graphSpace":"business_a"}', "{}", "business_a", "recoverable"),
        ("{}", '{"_graphSpace":"production"}', "production", "recoverable"),
        ('{"_graphSpace":"a"}', '{"_graphSpace":"a"}', "a", "recoverable"),
        ('{"_graphSpace":"a"}', '{"_graphSpace":"b"}', None, "conflicting_spaces"),
        ('{"graphSpace":"production"}', "{}", None, "missing_space"),
        ("{}", "{}", None, "missing_space"),
        ("invalid-json", '{"_graphSpace":"a"}', None, "invalid_snapshot"),
        ("[]", '{"_graphSpace":"a"}', None, "invalid_snapshot"),
        ('{"_graphSpace":17}', "{}", None, "invalid_space"),
        ('{"_graphSpace":"a;USE production"}', "{}", None, "invalid_space"),
    ],
)
def test_history_backfill_only_accepts_unambiguous_explicit_space(left, right, space, reason):
    assert explicit_snapshot_space(left, right) == (space, reason)


@pytest.mark.external
def test_mysql_migration_twice_preserves_unknown_history():
    """Opt in only on a newly named disposable DB in the Docker test network.

    BUSINESS_RBAC_MIGRATION_TEST=1 MYSQL_DATABASE=rbac_migration_<unique suffix>
    The small test database remains available as evidence; no DROP is executed.
    """
    if os.getenv("BUSINESS_RBAC_MIGRATION_TEST") != "1":
        pytest.skip("requires an explicitly enabled isolated MySQL migration test")
    database = os.getenv("MYSQL_DATABASE", "")
    if not database.startswith("rbac_migration_"):
        pytest.fail("migration test requires a dedicated rbac_migration_* database")
    from infra.mysql import MySQLClient

    engine = MySQLClient(database=database, ensure_database=True).engine
    assert not inspect(engine).get_table_names(), "use a fresh test database name"
    rows = [
        ("a", {"_graphSpace": "private_a"}, {"_graphSpace": "private_a"}),
        ("b", {}, {"_graphSpace": "private_b"}),
        ("c", {"_graphSpace": "private_a"}, {"_graphSpace": "production"}),
        ("d", {}, {}),
        ("e", "invalid-json", {"_graphSpace": "private_a"}),
    ]
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE manual_review_case (id VARCHAR(64) PRIMARY KEY, "
                "input_snapshot TEXT NOT NULL, candidate_snapshot TEXT NOT NULL)"
            )
        )
        for case_id, left, right in rows:
            connection.execute(
                text("INSERT INTO manual_review_case VALUES (:id, :left, :right)"),
                {
                    "id": case_id,
                    "left": left if isinstance(left, str) else json.dumps(left),
                    "right": json.dumps(right),
                },
            )
    check = migrate(engine)
    assert check["schema"]["schema_ready"] is False
    assert not check["applied"]
    assert "graph_space" not in {
        c["name"] for c in inspect(engine).get_columns("manual_review_case")
    }
    assert inspect(engine).get_table_names() == ["manual_review_case"]

    first = migrate(engine, apply=True)
    assert first["schema"]["schema_ready"] is True
    assert first["review_backfill"]["updated"] == 2
    second = migrate(engine, apply=True)
    assert second["schema"]["schema_ready"] is True
    assert not second["applied"]
    assert second["review_backfill"].get("updated", 0) == 0
    final = migrate(engine)
    assert final["schema"]["schema_ready"] is True
    assert final["review_backfill"] == {
        "conflicting_spaces": 1,
        "invalid_snapshot": 1,
        "missing_space": 1,
    }
    with engine.connect() as connection:
        actual = dict(
            connection.execute(text("SELECT id, graph_space FROM manual_review_case")).all()
        )
        assert actual == {"a": "private_a", "b": "private_b", "c": None, "d": None, "e": None}
        assert connection.scalar(text("SELECT COUNT(*) FROM kg_business_member")) == 0
    engine.dispose()
