"""创建按空间隔离的新标注表，不猜测旧记录归属。

默认只读检查，--apply 才建表；保留旧 kg_indirect_relation_annotation 表。
"""
import argparse
import json

from sqlalchemy import inspect

from db_model.indirect_relation_annotation import SpaceIndirectRelationAnnotation


def schema_report(engine):
    table = SpaceIndirectRelationAnnotation.__table__
    inspector = inspect(engine)
    if not inspector.has_table(table.name):
        return {"ready": False, "missing": [table.name], "incompatible": []}
    columns = {column["name"] for column in inspector.get_columns(table.name)}
    primary = set(inspector.get_pk_constraint(table.name).get("constrained_columns") or [])
    compatible = set(table.c.keys()) <= columns and primary == {c.name for c in table.primary_key}
    return {"ready": compatible, "missing": [], "incompatible": [] if compatible else [table.name]}


def migrate(engine=None, *, apply=False):
    if engine is None:
        from infra.mysql import get_engine
        engine = get_engine()
    before = schema_report(engine)
    if before["incompatible"]:
        raise ValueError("Existing scoped annotation schema is incompatible; no changes were made")
    if apply:
        SpaceIndirectRelationAnnotation.__table__.create(engine, checkfirst=True)
    return {"schema": schema_report(engine), "created": before["missing"] if apply else [],
            "legacy_tables_unchanged": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--check", action="store_true")
    modes.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    result = migrate(apply=args.apply)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["schema"]["ready"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
