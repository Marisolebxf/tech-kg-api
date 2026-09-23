"""Check business-RBAC schema; only --apply performs additive database changes.

Run inside the backend container with its existing MYSQL_* environment:
    python -m script.migrate_business_access
    python -m script.migrate_business_access --apply
The workflow control database is deliberately not touched.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter

from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError

from db_model.business_access import (
    BusinessClient,
    BusinessGraphSpace,
    BusinessMember,
    BusinessSpaceRequest,
)
from db_model.business_algorithm_job import BusinessAlgorithmJob
from infra.mysql import get_engine

BUSINESS_TABLES = tuple(
    model.__table__
    for model in (
        BusinessClient,
        BusinessMember,
        BusinessGraphSpace,
        BusinessSpaceRequest,
        BusinessAlgorithmJob,
    )
)
REVIEW_TABLE = "manual_review_case"
SPACE_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")


def explicit_snapshot_space(input_snapshot, candidate_snapshot) -> tuple[str | None, str]:
    """Never infer a space from defaults, user ownership, schema names or frontend fields."""
    values = set()
    for raw in (input_snapshot, candidate_snapshot):
        try:
            snapshot = json.loads(raw) if isinstance(raw, str) and raw else raw or {}
        except (ValueError, TypeError):
            return None, "invalid_snapshot"
        if not isinstance(snapshot, dict):
            return None, "invalid_snapshot"
        value = snapshot.get("_graphSpace")
        if value is None or value == "":
            continue
        if not isinstance(value, str) or not SPACE_PATTERN.fullmatch(value):
            return None, "invalid_space"
        values.add(value)
    if len(values) > 1:
        return None, "conflicting_spaces"
    if not values:
        return None, "missing_space"
    return next(iter(values)), "recoverable"


def schema_report(engine) -> dict:
    inspector = inspect(engine)
    existing = set(inspector.get_table_names())
    missing_tables = [table.name for table in BUSINESS_TABLES if table.name not in existing]
    incompatible_tables = {}
    for table in BUSINESS_TABLES:
        if table.name not in existing:
            continue
        actual = {column["name"] for column in inspector.get_columns(table.name)}
        missing = sorted(set(table.c.keys()) - actual)
        if missing:
            incompatible_tables[table.name] = missing
    review_exists = REVIEW_TABLE in existing
    review_columns = (
        {column["name"] for column in inspector.get_columns(REVIEW_TABLE)}
        if review_exists
        else set()
    )
    review_index = review_exists and any(
        index["column_names"] == ["graph_space"] for index in inspector.get_indexes(REVIEW_TABLE)
    )
    # create(checkfirst=True) cannot repair an incompatible pre-release table.
    # Report its exact missing columns instead of silently claiming success.
    unique_gaps = []
    for table, columns in (
        ("kg_business_graph_space", ("shared_key",)),
        ("kg_business_space_request", ("client_id", "active_space_name")),
    ):
        if table not in existing:
            continue
        unique_columns = {
            tuple(item["column_names"]) for item in inspector.get_unique_constraints(table)
        }
        unique_columns.update(
            tuple(item["column_names"])
            for item in inspector.get_indexes(table)
            if item.get("unique")
        )
        if columns not in unique_columns:
            unique_gaps.append({"table": table, "columns": list(columns)})
    pending = (
        missing_tables
        or incompatible_tables
        or unique_gaps
        or not review_exists
        or "graph_space" not in review_columns
        or not review_index
    )
    return {
        "schema_ready": not bool(pending),
        "missing_business_tables": missing_tables,
        "incompatible_business_tables": incompatible_tables,
        "missing_unique_constraints": unique_gaps,
        "review_table_exists": review_exists,
        "review_space_column_exists": "graph_space" in review_columns,
        "review_space_index_exists": bool(review_index),
        "review_snapshot_columns_exist": {"id", "input_snapshot", "candidate_snapshot"}
        <= review_columns,
    }


def review_backfill(engine, *, apply: bool) -> dict:
    schema = schema_report(engine)
    counts = Counter()
    if not schema["review_table_exists"] or not schema["review_snapshot_columns_exist"]:
        return {"skipped": "review table or snapshot columns are absent"}
    has_space = schema["review_space_column_exists"]
    last_id = ""
    while True:
        space_filter = "AND (graph_space IS NULL OR graph_space = '')" if has_space else ""
        with engine.begin() as connection:
            rows = (
                connection.execute(
                    text(
                        "SELECT id, input_snapshot, candidate_snapshot FROM manual_review_case "
                        f"WHERE id > :last_id {space_filter} ORDER BY id LIMIT 500"
                    ),
                    {"last_id": last_id},
                )
                .mappings()
                .all()
            )
            if not rows:
                break
            for row in rows:
                space, reason = explicit_snapshot_space(
                    row["input_snapshot"], row["candidate_snapshot"]
                )
                counts[reason] += 1
                if apply and space and has_space:
                    updated = connection.execute(
                        text(
                            "UPDATE manual_review_case SET graph_space = :space "
                            "WHERE id = :case_id AND (graph_space IS NULL OR graph_space = '')"
                        ),
                        {"space": space, "case_id": row["id"]},
                    )
                    counts["updated"] += updated.rowcount
            last_id = rows[-1]["id"]
    return dict(sorted(counts.items()))


def migrate(engine, *, apply: bool = False) -> dict:
    if engine.dialect.name != "mysql":
        raise ValueError("此部署迁移仅支持 MySQL；未执行任何更改")
    before = schema_report(engine)
    applied = []
    if apply:
        if before["incompatible_business_tables"] or before["missing_unique_constraints"]:
            raise ValueError(
                "检测到不完整的预发布业务表，请先依据 --check 输出人工修复；本次未迁移"
            )
        for table in BUSINESS_TABLES:
            table.create(engine, checkfirst=True)
            if table.name in before["missing_business_tables"]:
                applied.append(f"created {table.name}")
        if before["review_table_exists"]:
            with engine.begin() as connection:
                if not before["review_space_column_exists"]:
                    connection.execute(
                        text(
                            "ALTER TABLE manual_review_case ADD COLUMN graph_space VARCHAR(64) NULL"
                        )
                    )
                    applied.append("added manual_review_case.graph_space")
                if not before["review_space_index_exists"]:
                    connection.execute(
                        text(
                            "CREATE INDEX ix_review_graph_space ON manual_review_case (graph_space)"
                        )
                    )
                    applied.append("added ix_review_graph_space")
    backfill = review_backfill(engine, apply=apply)
    after = schema_report(engine)
    return {
        "mode": "apply" if apply else "check",
        "schema": after,
        "applied": applied,
        "review_backfill": backfill,
        "note": (
            "未登记真实账号、业务、空间或配置归属。未知/冲突审核记录保持隔离。"
            "缺少旧审核表时先完成项目正常数据库初始化，再重跑此迁移。"
            "MySQL DDL自动提交；发生中断可重跑，不自动删除任何表或数据。"
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="只读检查（默认）")
    mode.add_argument("--apply", action="store_true", help="显式创建业务表并回填可靠审核归属")
    args = parser.parse_args()
    try:
        report = migrate(get_engine(), apply=args.apply)
    except ValueError as exc:
        parser.exit(1, f"{exc}\n")
    except SQLAlchemyError:
        parser.exit(1, "数据库迁移失败；请检查目标业务库、DDL权限和表结构。连接凭据不写入输出。\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not report["schema"]["schema_ready"]:
        parser.exit(2)


if __name__ == "__main__":
    main()
