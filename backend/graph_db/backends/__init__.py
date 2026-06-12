"""Backend implementations for the graph database API."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from graph_db.backends.neo4j_backend import Neo4jGraphDatabase
    from graph_db.backends.trs_graph_backend import TRSGraphDatabase


def __getattr__(name: str):
    """Lazy-import backends so optional drivers are only required when used."""
    if name == "Neo4jGraphDatabase":
        from graph_db.backends.neo4j_backend import Neo4jGraphDatabase

        return Neo4jGraphDatabase
    if name == "TRSGraphDatabase":
        from graph_db.backends.trs_graph_backend import TRSGraphDatabase

        return TRSGraphDatabase
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["Neo4jGraphDatabase", "TRSGraphDatabase"]
