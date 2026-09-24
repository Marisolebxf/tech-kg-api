"""Inspect or configure business RBAC in MYSQL_*; dry-run unless --apply.

Plan JSON contains business {clientId, name}, sharedSpace, businessSpaces,
and users [{username, userId, role: admin|user|developer}]. No passwords.
Run --inspect --username NAME to discover IDs before preparing a plan.
This tool neither creates graph spaces nor deletes legacy personal bindings.
"""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Callable
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from db_model.business_access import (
    BusinessClient,
    BusinessGraphSpace,
    BusinessMember,
    BusinessSpaceRequest,
)
from db_model.platform_governance import PlatformUser, PlatformUserRole, UserGraphSpace

ADMIN = "platform_admin"
LEGACY_DEVELOPER = "platform_developer"
PORTAL_ADMIN = "portal_admin_snapshot"
SPACE_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}\Z")
CLIENT_PATTERN = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}\Z")


def _string(value: object, name: str, maximum: int) -> str:
    if not isinstance(value, str) or not value or value != value.strip() or len(value) > maximum:
        raise ValueError(f"{name} must be a nonempty trimmed string, at most {maximum} characters")
    return value


def validate_plan(plan: object) -> dict:
    if not isinstance(plan, dict) or set(plan) != {
        "business",
        "sharedSpace",
        "businessSpaces",
        "users",
    }:
        raise ValueError("Plan must contain only business, sharedSpace, businessSpaces, users")
    business = plan["business"]
    if not isinstance(business, dict) or set(business) != {"clientId", "name"}:
        raise ValueError("business must contain only clientId and name")
    client_id = _string(business["clientId"], "clientId", 64)
    if not CLIENT_PATTERN.fullmatch(client_id):
        raise ValueError("clientId must use lowercase letters, digits, underscores and hyphens")
    _string(business["name"], "business.name", 200)
    spaces = plan["businessSpaces"]
    if not isinstance(spaces, list):
        raise ValueError("businessSpaces must be an array")
    all_spaces = [plan["sharedSpace"], *spaces]
    for space in all_spaces:
        if not SPACE_PATTERN.fullmatch(_string(space, "space", 64)):
            raise ValueError("Invalid graph space name")
    if len(all_spaces) != len(set(all_spaces)):
        raise ValueError("Duplicate or overlapping shared/business spaces")
    users = plan["users"]
    if not isinstance(users, list) or not users:
        raise ValueError("users must be a nonempty array")
    for user in users:
        if not isinstance(user, dict) or set(user) != {"username", "userId", "role"}:
            raise ValueError("Each user must contain only username, userId and role")
        _string(user["username"], "username", 128)
        _string(user["userId"], "userId", 128)
        if user["role"] not in ("admin", "user", "developer"):
            raise ValueError("role must be admin, user or developer")
    if len({u["userId"] for u in users}) != len(users) or len(
        {u["username"] for u in users}
    ) != len(users):
        raise ValueError("Duplicate users")
    return plan


def inspect_bindings(session: Session, usernames: list[str]) -> dict:
    users = session.scalars(select(PlatformUser).where(PlatformUser.username.in_(usernames))).all()
    records = []
    for user in users:
        member = session.get(BusinessMember, user.user_id)
        records.append(
            {
                "username": user.username,
                "userId": user.user_id,
                "roles": sorted(
                    session.scalars(
                        select(PlatformUserRole.role_code).where(
                            PlatformUserRole.user_id == user.user_id
                        )
                    )
                ),
                "legacyPersonalSpaces": sorted(
                    session.scalars(
                        select(UserGraphSpace.space_name).where(
                            UserGraphSpace.user_id == user.user_id
                        )
                    )
                ),
                "membership": {"clientId": member.client_id, "role": member.role}
                if member
                else None,
            }
        )
    return {
        "users": records,
        "unmatchedUsernames": sorted(set(usernames) - {u.username for u in users}),
        "spaces": [
            {"spaceName": s.space_name, "clientId": s.client_id, "shared": s.is_shared_production}
            for s in session.scalars(select(BusinessGraphSpace))
        ],
    }


def configure(
    session: Session,
    plan: dict,
    *,
    list_spaces: Callable[[], list[str]],
    configured_shared_space: str,
    initial_admin_ids: tuple[str, ...] = (),
    business_only_ids: tuple[str, ...] = (),
    apply: bool = False,
) -> dict:
    """Validate all state before mutations. Caller owns transaction commit/rollback."""
    plan = validate_plan(plan)
    shared = plan["sharedSpace"]
    if configured_shared_space != shared:
        raise ValueError(
            "sharedSpace conflicts with TRS_GRAPH_SPACE; reconcile configuration first"
        )
    try:
        available = list_spaces()  # Actual graph service, never cached/fallback metadata.
    except Exception:
        raise ValueError("Could not verify graph spaces; no bindings were modified") from None
    if not isinstance(available, list) or any(not isinstance(s, str) for s in available):
        raise ValueError("Graph service returned an invalid space list")
    missing = set([shared, *plan["businessSpaces"]]) - set(available)
    if missing:
        raise ValueError(f"Graph spaces do not exist: {', '.join(sorted(missing))}")

    # Lock existing records during application; uniqueness constraints reject concurrent inserts.
    def rows(model):
        query = select(model)
        return list(session.scalars(query.with_for_update() if apply else query))

    clients = {r.client_id: r for r in rows(BusinessClient)}
    members = {r.user_id: r for r in rows(BusinessMember)}
    spaces = {r.space_name: r for r in rows(BusinessGraphSpace)}
    for name in [shared, *plan["businessSpaces"]]:
        registry = spaces.get(name)
        if registry and registry.provision_request_id:
            request = session.get(
                BusinessSpaceRequest, registry.provision_request_id, with_for_update=apply
            )
            if request is None or request.status != "ready" or request.space_name != name:
                raise ValueError(f"Space provisioning is unresolved: {name}")
    known_users = rows(PlatformUser)
    all_roles = rows(PlatformUserRole)
    client_id = plan["business"]["clientId"]
    client = clients.get(client_id)
    if client and (not client.enabled or client.name != plan["business"]["name"]):
        raise ValueError("Existing business is disabled or its name conflicts with the plan")
    for row in spaces.values():
        if (row.is_shared_production or row.shared_key is not None) and row.space_name != shared:
            raise ValueError("A different shared space is already registered")
    existing_shared = spaces.get(shared)
    if existing_shared and (
        not existing_shared.is_shared_production
        or existing_shared.client_id is not None
        or existing_shared.shared_key != "production"
    ):
        raise ValueError("Existing shared space ownership conflicts with the plan")
    for name in plan["businessSpaces"]:
        row = spaces.get(name)
        if row and (
            row.client_id != client_id or row.is_shared_production or row.shared_key is not None
        ):
            raise ValueError(f"Space ownership conflict: {name}")
    warnings, removals = [], []
    for entry in plan["users"]:
        uid = entry["userId"]
        matches = [u for u in known_users if u.username == entry["username"]]
        if len(matches) != 1 or matches[0].user_id != uid:
            raise ValueError(
                "username must match exactly one registered user and the supplied userId"
            )
        roles = {r.role_code for r in all_roles if r.user_id == uid}
        if entry["role"] != "admin" and (roles & {ADMIN, PORTAL_ADMIN} or uid in initial_admin_ids):
            raise ValueError(
                f"User {uid} already has administrator authority; refusing implicit demotion"
            )
        if uid in business_only_ids:
            if entry["role"] != "user":
                raise ValueError(
                    f"User {uid} is businessOnly; requested elevated role cannot take effect"
                )
            warnings.append(f"User {uid} retains the businessOnly restriction")
        member = members.get(uid)
        if entry["role"] != "admin" and member and member.client_id != client_id:
            raise ValueError(f"User {uid} belongs to another business; no implicit transfer")
        if LEGACY_DEVELOPER in roles:
            removals.append(uid)
    report = {
        "applied": apply,
        "plan": plan,
        "removeLegacyDeveloperFrom": removals,
        "preserveLegacyPersonalBindings": True,
        "warnings": warnings,
    }
    if not apply:
        return report
    if not client:
        session.add(
            BusinessClient(client_id=client_id, name=plan["business"]["name"], enabled=True)
        )
        session.flush()  # Parent must exist before FK children; all validations already passed.
    if not existing_shared:
        session.add(
            BusinessGraphSpace(
                space_name=shared, is_shared_production=True, shared_key="production"
            )
        )
    for name in plan["businessSpaces"]:
        if name not in spaces:
            session.add(
                BusinessGraphSpace(space_name=name, client_id=client_id, is_shared_production=False)
            )
    for entry in plan["users"]:
        uid = entry["userId"]
        if entry["role"] == "admin":
            if not any(r.user_id == uid and r.role_code == ADMIN for r in all_roles):
                session.add(
                    PlatformUserRole(user_id=uid, role_code=ADMIN, granted_by="business-access-cli")
                )
        elif uid in members:
            members[uid].role = entry["role"]
        else:
            session.add(BusinessMember(user_id=uid, client_id=client_id, role=entry["role"]))
    if removals:
        session.execute(
            delete(PlatformUserRole).where(
                PlatformUserRole.user_id.in_(removals),
                PlatformUserRole.role_code == LEGACY_DEVELOPER,
            )
        )
    session.flush()
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", type=Path)
    mode.add_argument("--inspect", action="store_true")
    parser.add_argument("--username", action="append", default=[])
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    if args.inspect and (args.apply or not args.username):
        parser.error("--inspect requires --username and cannot use --apply")
    if args.plan and args.username:
        parser.error("--username is only available with --inspect")
    from config.auth import AuthSettings
    from infra.mysql import get_engine

    settings = AuthSettings.from_env()
    try:
        with Session(get_engine()) as session, session.begin():
            if args.inspect:
                result = inspect_bindings(session, args.username)
                for user in result["users"]:
                    user["initialAdmin"] = user["userId"] in settings.initial_admin_user_ids
                    user["businessOnly"] = user["userId"] in settings.business_only_user_ids
            else:
                from infra.graph_db import TRSGraphSettings, get_trs_graph_client

                plan = validate_plan(json.loads(args.plan.read_text(encoding="utf-8-sig")))
                if not settings.enabled:
                    raise ValueError("AUTH_ENABLED must be true for real role configuration")
                if settings.bootstrap_first_admin or settings.dev_first_user_admin:
                    raise ValueError(
                        "Automatic first-user admin configuration conflicts with explicit role setup"
                    )
                result = configure(
                    session,
                    plan,
                    list_spaces=get_trs_graph_client().list_spaces,
                    configured_shared_space=TRSGraphSettings.from_env().space,
                    initial_admin_ids=settings.initial_admin_user_ids,
                    business_only_ids=settings.business_only_user_ids,
                    apply=args.apply,
                )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
    except Exception:
        # Drivers can embed passwords/connection URLs; never print their messages.
        print(
            json.dumps(
                {
                    "error": "Database or graph operation failed; transaction rolled back. Check service availability and schema migration."
                }
            )
        )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
