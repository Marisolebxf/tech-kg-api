"""Read-only inventory by default; --apply --plan writes reviewed ownership only."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sqlalchemy import inspect, select, text
from sqlalchemy.exc import SQLAlchemyError

from db_model.business_access import BusinessClient
from db_model.config_ownership import ConfigOwnership
from db_model.llm_config import LlmConfig
from db_model.mysql_datasource import MysqlDatasource

TARGET_BUSINESS = "billion-scale-kg-engine"
PRIVATE_NAME = "开发者测试"
MODELS = {"mysql": MysqlDatasource, "llm": LlmConfig}


def inventory(connection):
    # Intentionally never select passwords, API keys or connection details.
    return {
        kind: {
            row.id: dict(row._mapping)
            for row in connection.execute(select(model.id, model.name, model.is_default))
        }
        for kind, model in MODELS.items()
    }


def make_plan(connection):
    business = connection.execute(
        select(BusinessClient.client_id, BusinessClient.name, BusinessClient.enabled).where(
            BusinessClient.client_id == TARGET_BUSINESS
        )
    ).first()
    if business is None or not business.enabled:
        raise ValueError("目标业务不存在或未启用，不能生成归属计划")
    current = inventory(connection)
    for kind, rows in current.items():
        matches = [row for row in rows.values() if row["name"] == PRIVATE_NAME]
        if len(matches) != 1:
            raise ValueError(
                f"{kind} 名称精确匹配开发者测试的记录数为 {len(matches)}，要求恰好一条"
            )
    return {
        "version": 1,
        "business_id": business.client_id,
        "business_name": business.name,
        "records": [
            {
                "config_kind": kind,
                "config_id": row["id"],
                "name": row["name"],
                "business_id": TARGET_BUSINESS if row["name"] == PRIVATE_NAME else None,
            }
            for kind, rows in current.items()
            for row in sorted(rows.values(), key=lambda r: r["id"])
        ],
    }


def validate_plan(connection, plan):
    errors = []
    if (
        not isinstance(plan, dict)
        or plan.get("version") != 1
        or plan.get("business_id") != TARGET_BUSINESS
    ):
        return ["计划版本或目标业务不正确"]
    business = connection.execute(
        select(BusinessClient.name, BusinessClient.enabled).where(
            BusinessClient.client_id == TARGET_BUSINESS
        )
    ).first()
    if business is None or not business.enabled or business.name != plan.get("business_name"):
        errors.append("目标业务不存在、未启用或业务名称变化")
    records = plan.get("records")
    if not isinstance(records, list) or not records:
        return errors + ["计划 records 必须是非空列表"]
    current = inventory(connection)
    existing = {}
    if inspect(connection).has_table(ConfigOwnership.__tablename__):
        existing = {
            (r.config_kind, r.config_id): r.business_id
            for r in connection.execute(
                select(
                    ConfigOwnership.config_kind,
                    ConfigOwnership.config_id,
                    ConfigOwnership.business_id,
                )
            )
        }
    seen = set()
    private_counts = {kind: 0 for kind in MODELS}
    for record in records:
        if not isinstance(record, dict) or not all(
            k in record for k in ("config_kind", "config_id", "name", "business_id")
        ):
            errors.append("计划条目字段不完整")
            continue
        kind, config_id = record["config_kind"], record["config_id"]
        if not isinstance(kind, str) or not isinstance(config_id, str):
            errors.append("配置类型和 ID 必须是字符串")
            continue
        key = (kind, config_id)
        if key in seen:
            errors.append(f"重复配置 {kind}/{config_id}")
        seen.add(key)
        row = current.get(kind, {}).get(config_id)
        if row is None or row["name"] != record["name"]:
            errors.append(f"配置不存在或名称变化 {kind}/{config_id}")
            continue
        target = TARGET_BUSINESS if row["name"] == PRIVATE_NAME else None
        if record["business_id"] != target:
            errors.append(f"不符合历史归属规则 {kind}/{config_id}")
        if target:
            private_counts[kind] += 1
            if row["is_default"]:
                errors.append(f"默认配置归属冲突 {kind}/{config_id}：不修改默认机制，暂停迁移")
        if key in existing and existing[key] != record["business_id"]:
            errors.append(f"已有不同归属，禁止覆盖 {kind}/{config_id}")
    if any(count != 1 for count in private_counts.values()):
        errors.append("计划必须包含 MySQL、LLM 各一条开发者测试")
    return errors


def reference_report(connection, plan):
    """All affected Schema references, including spaces requiring manual review."""
    inspector = inspect(connection)
    if not inspector.has_table("kg_schema_definition"):
        return {"status": "unavailable", "references": []}
    ids = [
        r["config_id"] for r in plan["records"] if r["config_kind"] == "mysql" and r["business_id"]
    ]
    refs = []
    for config_id in ids if inspector.has_table("kg_schema_source") else []:
        refs.extend(
            dict(r._mapping)
            for r in connection.execute(
                text(
                    "SELECT 'mysql' AS config_kind, s.id AS source_id, s.schema_id, d.graph_space, s.datasource_id "
                    "FROM kg_schema_source s JOIN kg_schema_definition d ON d.id=s.schema_id "
                    "WHERE s.datasource_id=:id"
                ),
                {"id": config_id},
            )
        )
    has_llm_column = "llm_config_id" in {
        c["name"] for c in inspector.get_columns("kg_schema_definition")
    }
    if has_llm_column:
        for record in plan["records"]:
            if record["config_kind"] == "llm" and record["business_id"]:
                refs.extend(
                    dict(r._mapping)
                    for r in connection.execute(
                        text(
                            "SELECT 'llm' AS config_kind, id AS schema_id, graph_space, llm_config_id "
                            "FROM kg_schema_definition WHERE llm_config_id=:id"
                        ),
                        {"id": record["config_id"]},
                    )
                )
    missing = []
    if not inspector.has_table("kg_schema_source"):
        missing.append("kg_schema_source")
    if not has_llm_column:
        missing.append("kg_schema_definition.llm_config_id")
    return {
        "status": "review_required" if refs else ("incomplete" if missing else "clear"),
        "references": refs,
        "missing": missing,
    }


def migrate(engine, plan=None, *, apply=False):
    if apply and plan is None:
        raise ValueError("应用必须提供已核对的 --plan 文件，禁止即时生成并应用")
    with engine.connect() as connection:
        plan = make_plan(connection) if plan is None else plan
        errors = validate_plan(connection, plan)
        references = reference_report(connection, plan) if not errors else {"status": "not_checked"}
    report = {
        "mode": "apply" if apply else "check",
        "plan": plan,
        "errors": errors,
        "schema_references": references,
        "workflow_references": "not_checked_separate_database",
        "inserted": 0,
    }
    if errors or not apply:
        return report
    # MySQL DDL auto-commits. All validations precede the additive table creation.
    ConfigOwnership.__table__.create(engine, checkfirst=True)
    with engine.begin() as connection:
        errors = validate_plan(connection, plan)
        if errors:
            raise ValueError("；".join(errors))
        for record in plan["records"]:
            predicate = (
                ConfigOwnership.config_kind == record["config_kind"],
                ConfigOwnership.config_id == record["config_id"],
            )
            if connection.execute(select(ConfigOwnership.config_id).where(*predicate)).first():
                continue
            connection.execute(
                ConfigOwnership.__table__.insert().values(
                    **{key: record[key] for key in ("config_kind", "config_id", "business_id")}
                )
            )
            report["inserted"] += 1
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--check", action="store_true")
    modes.add_argument("--apply", action="store_true")
    parser.add_argument("--plan", type=Path, help="读取精确 ID 归属计划")
    parser.add_argument("--write-plan", type=Path, help="将只读核查生成的计划保存到本地")
    args = parser.parse_args()
    if args.apply and (not args.plan or args.write_plan):
        parser.error("--apply 必须提供 --plan，不能同时使用 --write-plan")
    try:
        from infra.mysql import get_engine

        plan = json.loads(args.plan.read_text(encoding="utf-8")) if args.plan else None
        report = migrate(get_engine(), plan, apply=args.apply)
        if args.write_plan:
            # Exclusive creation prevents accidentally replacing a reviewed plan.
            with args.write_plan.open("x", encoding="utf-8") as output:
                json.dump(report["plan"], output, ensure_ascii=False, indent=2)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"计划读取或验证失败：{exc}\n")
    except SQLAlchemyError:
        parser.exit(1, "数据库核查或迁移失败；检查连接与表结构，凭据不写入输出。\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["errors"]:
        parser.exit(2)


if __name__ == "__main__":
    main()
