"""Cypher query execution service layer."""

from __future__ import annotations

from typing import Any

from graph_db.base import GraphDatabase
from graph_db.models import QueryResult


class QueryService:
    """Encapsulates Cypher query execution.

    Usage::

        from graph_db import connect, GraphDBConfig
        from graph_db.services import QueryService

        db = connect(GraphDBConfig.from_env())
        svc = QueryService(db)

        result = svc.execute("MATCH (n:Person) RETURN n.name LIMIT 10")
    """

    def __init__(self, db: GraphDatabase) -> None:
        self._db = db

    def execute(self, query: str, params: dict[str, Any] | None = None) -> QueryResult:
        return self._db.execute_query(query, params)

    def read(self, query: str, params: dict[str, Any] | None = None) -> QueryResult:
        return self._db.execute_read(query, params)

    def write(self, query: str, params: dict[str, Any] | None = None) -> QueryResult:
        return self._db.execute_write(query, params)
