"""Connection factory and configuration management.

Provides a unified entry point for creating GraphDatabase instances
from configuration, with support for environment variables and
connection pooling.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from graph_db.base import GraphDatabase


# ---------------------------------------------------------------------------
# Configuration dataclass
# ---------------------------------------------------------------------------

@dataclass
class GraphDBConfig:
    """Configuration for a graph database connection.

    Attributes:
        backend: Backend type — currently ``"neo4j"``.
        uri: Connection URI (e.g. ``bolt://localhost:7687``).
        username: Authentication username.
        password: Authentication password.
        database: Target database name.
        max_connection_pool_size: Driver connection-pool size.
        connection_timeout: Connection timeout in seconds.
        extra: Backend-specific extra parameters.
    """

    backend: str = "neo4j"
    uri: str = "bolt://localhost:7687"
    username: str = "neo4j"
    password: str = ""
    database: str = "neo4j"
    max_connection_pool_size: int = 50
    connection_timeout: int = 30
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_env(cls, prefix: str = "GRAPH_DB") -> "GraphDBConfig":
        """Load configuration from environment variables.

        Environment variable names are derived from the prefix and
        the field name, e.g. ``GRAPH_DB_URI``, ``GRAPH_DB_USERNAME``.
        """
        def _env(name: str) -> str | None:
            return os.environ.get(f"{prefix}_{name}")

        return cls(
            backend=_env("BACKEND") or "neo4j",
            uri=_env("URI") or "bolt://localhost:7687",
            username=_env("USERNAME") or "neo4j",
            password=_env("PASSWORD") or "",
            database=_env("DATABASE") or "neo4j",
            max_connection_pool_size=int(_env("MAX_CONNECTION_POOL_SIZE") or 50),
            connection_timeout=int(_env("CONNECTION_TIMEOUT") or 30),
        )

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "GraphDBConfig":
        """Create a config from a plain dict (keys match field names)."""
        known = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in d.items() if k in known}
        extra = {k: v for k, v in d.items() if k not in known}
        return cls(**filtered, extra=extra)


# ---------------------------------------------------------------------------
# Connection factory
# ---------------------------------------------------------------------------

_BACKEND_REGISTRY: dict[str, type[GraphDatabase]] = {}


def register_backend(name: str, cls: type[GraphDatabase]) -> None:
    """Register a backend class under a short name.

    This allows ``connect(config)`` to resolve the right class.
    """
    _BACKEND_REGISTRY[name.lower()] = cls


def _ensure_backends() -> None:
    """Lazily register built-in backends."""
    if _BACKEND_REGISTRY:
        return
    # Import and register Neo4j backend
    from graph_db.backends.neo4j_backend import Neo4jGraphDatabase
    register_backend("neo4j", Neo4jGraphDatabase)


def connect(config: GraphDBConfig | None = None, **kwargs: Any) -> GraphDatabase:
    """Create a GraphDatabase instance from config and connect.

    Args:
        config: A GraphDBConfig. If ``None``, loaded from environment.
        **kwargs: Override individual config fields.

    Returns:
        A connected GraphDatabase instance.

    Example::

        db = connect(GraphDBConfig(uri="bolt://localhost:7687",
                                    username="neo4j", password="secret"))
        # ... use db ...
        db.close()
    """
    _ensure_backends()

    if config is None:
        config = GraphDBConfig.from_env()

    # Allow kwargs overrides
    if kwargs:
        config = GraphDBConfig.from_dict({**config.__dict__, **kwargs})

    backend_name = config.backend.lower()
    cls = _BACKEND_REGISTRY.get(backend_name)
    if cls is None:
        raise ValueError(
            f"Unknown backend '{backend_name}'. "
            f"Available: {list(_BACKEND_REGISTRY.keys())}"
        )

    # Instantiate with backend-specific args
    if backend_name == "neo4j":
        db = cls(
            uri=config.uri,
            auth=(config.username, config.password),
            database=config.database,
        )
    else:
        db = cls()

    db.connect()
    return db


def get_backend_names() -> list[str]:
    """List registered backend names."""
    _ensure_backends()
    return list(_BACKEND_REGISTRY.keys())
