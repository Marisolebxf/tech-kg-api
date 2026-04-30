"""graph_db — Generic Graph Database Operation API.

A database-agnostic API for graph database operations with pluggable
backends (Neo4j, Memgraph, …).

Quick start::

    from graph_db import connect, GraphDBConfig

    db = connect(GraphDBConfig(
        uri="bolt://localhost:7687",
        username="neo4j",
        password="secret",
    ))

    # Node CRUD
    alice = db.create_node(["Person"], {"name": "Alice", "age": 30})
    bob = db.merge_node(["Person"], {"name": "Bob"}, {"age": 25})

    # Edge CRUD
    edge = db.create_edge(alice.id, bob.id, "KNOWS", {"since": 2020})

    # Traversal
    neighbours = db.get_neighbours(alice.id, direction="out", edge_type="KNOWS")

    # Raw Cypher
    result = db.execute_query(
        "MATCH (n:Person) WHERE n.age > $min_age RETURN n.name",
        params={"min_age": 20},
    )

    db.close()
"""

# Lazy-import backends so they self-register
from graph_db.backends import Neo4jGraphDatabase
from graph_db.base import GraphDatabase, Transaction
from graph_db.config import GraphDBConfig, connect, get_backend_names, register_backend
from graph_db.models import (
    ConstraintSpec,
    Edge,
    IndexSpec,
    Node,
    PagedResult,
    PageInfo,
    Path,
    QueryResult,
)
from graph_db.query import QueryBuilder

# Service layer
from graph_db.services import (
    EdgeService,
    NodeService,
    QueryService,
    SchemaService,
    TraversalService,
)

__all__ = [
    # Core API
    "GraphDatabase",
    "Transaction",
    # Models
    "Node",
    "Edge",
    "Path",
    "QueryResult",
    "PagedResult",
    "PageInfo",
    "IndexSpec",
    "ConstraintSpec",
    # Config & factory
    "GraphDBConfig",
    "connect",
    "register_backend",
    "get_backend_names",
    # Query builder
    "QueryBuilder",
    # Backends
    "Neo4jGraphDatabase",
    # Service layer
    "NodeService",
    "EdgeService",
    "TraversalService",
    "QueryService",
    "SchemaService",
]
