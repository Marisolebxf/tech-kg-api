"""Serialize index rebuilds and supported graph writes with a MySQL lock."""

from __future__ import annotations

import logging
import os
import re
import uuid
from contextlib import contextmanager
from functools import wraps

from sqlalchemy import inspect, text, update
from sqlalchemy.orm import Session

from db_model.entity_literal_index import states
from infra.workflow_mysql import get_workflow_engine
from service.entity_literal_index import EntityLiteralIndex, digest

logger = logging.getLogger(__name__)


@contextmanager
def locked_index_session(space: str):
    # Keep one physical connection: advisory locks are connection-scoped, and
    # a normal Session may return its connection to the pool after each commit.
    with get_workflow_engine().connect() as connection:
        name = "entity_literal:" + digest(space).hex()[:40]
        mysql = connection.dialect.name == "mysql"
        if mysql and connection.scalar(text("SELECT GET_LOCK(:name, 60)"), {"name": name}) != 1:
            raise RuntimeError("文字索引正在重建，请稍后重试写图")
        connection.commit()
        try:
            with Session(bind=connection) as session:
                yield session
        finally:
            if mysql:
                connection.execute(text("SELECT RELEASE_LOCK(:name)"), {"name": name})
                connection.commit()


def sync_literal_write(method):
    """Wrap graph node CRUD. Graph/index failure never silently serves stale data.

    Index maintenance is enabled by default. Graph-only installations with no
    literal state table keep their existing behavior.
    """

    @wraps(method)
    def wrapped(graph, *args, **kwargs):
        raw_query = method.__name__ in {"execute_query", "execute_write"}
        if raw_query:
            query = args[0] if args else kwargs.get("query", "")
            # Read/statistics/edge statements do not change entity properties.
            if not re.search(
                r"\b(?:INSERT|UPSERT|UPDATE|DELETE)\s+VERTEX\b|"
                r"\b(?:ALTER|DROP)\s+TAG\b|\b(?:DROP|CLEAR)\s+SPACE\b",
                query,
                re.IGNORECASE,
            ):
                return method(graph, *args, **kwargs)
        if os.getenv("ENTITY_LITERAL_INDEX_SYNC_ENABLED", "true").lower() in {"false", "0", "off"}:
            return method(graph, *args, **kwargs)
        # Index not provisioned yet: preserve existing graph-only installations.
        try:
            exists = inspect(get_workflow_engine()).has_table(states.name)
        except Exception:
            # Do not permit a write whose index cannot be maintained: otherwise
            # a recovered control DB could keep serving an old ready generation.
            raise RuntimeError("无法确认文字索引状态，写图暂不可用，请检查控制库") from None
        if not exists:
            return method(graph, *args, **kwargs)
        with locked_index_session(graph.space) as session:
            state = session.execute(states.select().where(states.c.space == graph.space)).first()
            if state is None:
                return method(graph, *args, **kwargs)
            # Commit invalidation BEFORE graph mutation. If the process dies
            # between stores, readers see an explicit rebuild requirement.
            was_ready = state.ready
            session.execute(update(states).where(states.c.space == graph.space).values(ready=0))
            session.commit()
            result = method(graph, *args, **kwargs)
            index = EntityLiteralIndex(session)
            try:
                if method.__name__ == "delete_node":
                    index.sync_node(graph.space, vid=args[0] if args else kwargs["node_id"])
                elif method.__name__ == "execute_entity_write":
                    node_ids = kwargs.get("node_ids", [])
                    if not node_ids:
                        raise RuntimeError("节点写入未提供受影响 VID")
                    for vid in dict.fromkeys(node_ids):
                        node = graph.get_node(vid)
                        query = args[0] if args else kwargs.get("query", "")
                        if node is None and not re.search(
                            r"\bDELETE\s+VERTEX\b", query, re.IGNORECASE
                        ):
                            raise RuntimeError("图写后无法读回完整节点，索引保持失效")
                        index.sync_node(graph.space, node, vid=vid)
                elif raw_query:
                    # Arbitrary nGQL cannot be decoded safely into affected IDs.
                    was_ready = 0
                else:
                    if method.__name__ == "batch_create_nodes" and not result:
                        was_ready = 0
                    for node in result if isinstance(result, list) else [result]:
                        index.sync_node(graph.space, node)
                session.execute(
                    update(states)
                    .where(states.c.space == graph.space)
                    .values(ready=was_ready, revision=uuid.uuid4().hex)
                )
                session.commit()
            except Exception:
                session.rollback()
                session.execute(update(states).where(states.c.space == graph.space).values(ready=0))
                session.commit()
                logger.exception(
                    "图写成功，但文字索引同步失败；该空间索引已失效 space=%s", graph.space
                )
            return result

    return wrapped
