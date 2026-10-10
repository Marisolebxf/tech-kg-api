"""新增权限表，保留其他实例仍使用的旧表。

默认只检查元数据；--apply 才建表，--plan 只应用明确列出的成员/空间，不猜测归属。
"""

from __future__ import annotations

import argparse
import json
import re

from sqlalchemy import delete, inspect
from sqlalchemy.orm import Session

from db_model.business_access import (
    BusinessClient,
    BusinessMembership,
    BusinessMembershipState,
    BusinessSpacePolicy,
)
from db_model.platform_governance import PlatformUser

TABLES = (BusinessMembershipState.__table__, BusinessMembership.__table__, BusinessSpacePolicy.__table__)


def schema_report(engine) -> dict:
    inspector = inspect(engine)
    names = set(inspector.get_table_names())
    missing = [table.name for table in TABLES if table.name not in names]
    incompatible = []
    for table in TABLES:
        if table.name not in names:
            continue
        columns = {column["name"] for column in inspector.get_columns(table.name)}
        primary = set(inspector.get_pk_constraint(table.name).get("constrained_columns") or [])
        if not set(table.c.keys()) <= columns or primary != {c.name for c in table.primary_key}:
            incompatible.append(table.name)
    return {"ready": not missing and not incompatible, "missing": missing, "incompatible": incompatible}


def apply_plan(session: Session, plan: dict, *, apply: bool = False) -> dict:
    if not isinstance(plan, dict) or set(plan) - {"memberships", "spaces"}:
        raise ValueError("Plan accepts only memberships and spaces")
    memberships, spaces = plan.get("memberships", []), plan.get("spaces", [])
    if not isinstance(memberships, list) or not isinstance(spaces, list):
        raise ValueError("memberships and spaces must be lists")
    users_seen, spaces_seen = set(), set()
    for member in memberships:
        if not isinstance(member, dict) or set(member) != {"userId", "businesses"}:
            raise ValueError("Membership requires userId and businesses")
        uid = member["userId"]
        if uid in users_seen or session.get(PlatformUser, uid) is None:
            raise ValueError("Unknown or duplicate userId")
        users_seen.add(uid)
        if not isinstance(member["businesses"], list):
            raise ValueError("businesses must be a list")
        ids = set()
        for grant in member["businesses"]:
            if not isinstance(grant, dict) or set(grant) != {"clientId", "role"}:
                raise ValueError("Grant requires clientId and role")
            business = session.get(BusinessClient, grant["clientId"])
            if not business or not business.enabled or business.client_id in ids:
                raise ValueError("Unknown, disabled or duplicate business")
            ids.add(business.client_id)
            if grant["role"] not in {"user", "developer"}:
                raise ValueError("Membership role must be user or developer")
    for space in spaces:
        if not isinstance(space, dict) or set(space) != {"name", "visibility", "clientId"}:
            raise ValueError("Space requires name, visibility and clientId")
        name = space["name"]
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", name) or name in spaces_seen:
            raise ValueError("Invalid or duplicate space name")
        spaces_seen.add(name)
        if space["visibility"] not in {"public", "business", "unassigned"}:
            raise ValueError("Invalid visibility")
        if space["visibility"] == "business":
            business = session.get(BusinessClient, space["clientId"])
            if not business or not business.enabled:
                raise ValueError("Unknown or disabled space business")
        elif space["clientId"] is not None:
            raise ValueError("Public/unassigned spaces cannot belong to a business")
    # 全部计划校验通过后才允许修改任何权限记录。
    if apply:
        for member in memberships:
            uid = member["userId"]
            if session.get(BusinessMembershipState, uid) is None:
                session.add(BusinessMembershipState(user_id=uid))
            session.execute(delete(BusinessMembership).where(BusinessMembership.user_id == uid))
            session.add_all(BusinessMembership(user_id=uid, client_id=g["clientId"], role=g["role"]) for g in member["businesses"])
        for space in spaces:
            row = session.get(BusinessSpacePolicy, space["name"])
            if row is None:
                row = BusinessSpacePolicy(space_name=space["name"])
                session.add(row)
            row.visibility, row.client_id = space["visibility"], space["clientId"]
        session.flush()
    return {"applied": apply, "membership_users": len(memberships), "space_policies": len(spaces),
            "legacy_tables_unchanged": True}


def migrate(engine, *, apply: bool = False, plan: dict | None = None) -> dict:
    before = schema_report(engine)
    if before["incompatible"]:
        raise ValueError("Existing v2 schema is incompatible; no changes were made")
    if apply:
        for table in TABLES:
            table.create(engine, checkfirst=True)
    result = {"schema": schema_report(engine), "created": before["missing"] if apply else [],
              "legacy_tables_unchanged": True, "assignments": None}
    if plan is not None:
        with Session(engine) as session, session.begin():
            result["assignments"] = apply_plan(session, plan, apply=apply)
    return result


def main() -> None:
    from infra.mysql import get_engine

    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--check", action="store_true")
    modes.add_argument("--apply", action="store_true")
    parser.add_argument("--plan", help="Explicitly reviewed JSON assignments; no secrets")
    args = parser.parse_args()
    plan = None
    if args.plan:
        with open(args.plan, encoding="utf-8-sig") as stream:
            plan = json.load(stream)
    result = migrate(get_engine(), apply=args.apply, plan=plan)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["schema"]["ready"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
