"""Schema management and database info service layer."""

from __future__ import annotations

from graph_db.base import GraphDatabase
from graph_db.models import ConstraintSpec, IndexSpec


class SchemaService:
    """Encapsulates schema management and database info operations.

    Usage::

        from graph_db import connect, GraphDBConfig
        from graph_db.services import SchemaService
        from graph_db.models import IndexSpec

        db = connect(GraphDBConfig.from_env())
        svc = SchemaService(db)

        svc.create_index(IndexSpec(label="Person", properties=["name"]))
        count = svc.node_count(label="Person")
    """

    def __init__(self, db: GraphDatabase) -> None:
        self._db = db

    # ----- Index -----

    def create_index(self, spec: IndexSpec) -> None:
        self._db.create_index(spec)

    def drop_index(self, label: str, properties: list[str]) -> None:
        self._db.drop_index(label, properties)

    def list_indexes(self, label: str | None = None) -> list[IndexSpec]:
        return self._db.list_indexes(label)

    # ----- Constraint -----

    def create_constraint(self, spec: ConstraintSpec) -> None:
        self._db.create_constraint(spec)

    def drop_constraint(self, name: str) -> None:
        self._db.drop_constraint(name)

    def list_constraints(self) -> list[ConstraintSpec]:
        return self._db.list_constraints()

    # ----- Database info -----

    def node_count(self, label: str | None = None) -> int:
        return self._db.node_count(label)

    def edge_count(self, edge_type: str | None = None) -> int:
        return self._db.edge_count(edge_type)

    def labels(self) -> list[str]:
        return self._db.labels()

    def edge_types(self) -> list[str]:
        return self._db.edge_types()
