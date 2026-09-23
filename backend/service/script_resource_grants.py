"""Persist only record IDs returned by trusted semantic calls, never script claims."""

import re
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError

from db_model.script_resource_grant import ScriptResourceGrant
from infra.mysql import session_scope


def _now():
    return datetime.now(UTC).replace(tzinfo=None)


def _valid(run_key, record_id, actor, space):
    return (
        isinstance(run_key, str)
        and re.fullmatch(r"[0-9a-f]{64}", run_key)
        and isinstance(record_id, str)
        and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", record_id)
        and bool(actor.user_id)
        and isinstance(space, str)
        and 0 < len(space) <= 64
    )


def _owned(row, actor, space):
    return (
        row.graph_space == space
        and row.client_id == (actor.business_id or "")
        and row.actor_user_id == actor.user_id
    )


def remember(run_key, record_id, actor, space):
    if not _valid(run_key, record_id, actor, space):
        raise ValueError("Invalid semantic record grant scope")
    now = _now()
    try:
        with session_scope() as session:
            session.execute(
                delete(ScriptResourceGrant).where(ScriptResourceGrant.expires_at <= now)
            )
            row = session.get(ScriptResourceGrant, (run_key, record_id))
            if row is not None:
                if not _owned(row, actor, space):
                    raise ValueError("Semantic record grant belongs to another scope")
                return
            session.add(
                ScriptResourceGrant(
                    run_key=run_key,
                    record_id=record_id,
                    graph_space=space,
                    client_id=actor.business_id or "",
                    actor_user_id=actor.user_id,
                    expires_at=now + timedelta(days=30),
                )
            )
    except IntegrityError:
        # Parallel steps may observe the same trusted service record.
        if not allows(run_key, record_id, actor, space):
            raise


def allows(run_key, record_id, actor, space):
    if not _valid(run_key, record_id, actor, space):
        return False
    with session_scope() as session:
        row = session.get(ScriptResourceGrant, (run_key, record_id))
        return bool(row is not None and row.expires_at > _now() and _owned(row, actor, space))
