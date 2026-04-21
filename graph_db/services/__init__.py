"""Service layer for graph database operations.

Each service class wraps a ``GraphDatabase`` instance and provides
domain-oriented methods for a specific concern.

Usage::

    from graph_db import connect, GraphDBConfig
    from graph_db.services import NodeService, EdgeService

    db = connect(GraphDBConfig.from_env())
    nodes = NodeService(db)
    edges = EdgeService(db)
"""

from graph_db.services.edge_service import EdgeService
from graph_db.services.node_service import NodeService
from graph_db.services.query_service import QueryService
from graph_db.services.schema_service import SchemaService
from graph_db.services.traversal_service import TraversalService

__all__ = [
    "NodeService",
    "EdgeService",
    "TraversalService",
    "QueryService",
    "SchemaService",
]
