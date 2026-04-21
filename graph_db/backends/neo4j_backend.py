"""Neo4j backend implementing the generic GraphDatabase API.

Uses the official ``neo4j`` Python driver under the hood.
"""

from __future__ import annotations

import logging
from typing import Any, Sequence

import neo4j
from neo4j import GraphDatabase as Neo4jDriver
from neo4j.graph import Node as Neo4jNode
from neo4j.graph import Path as Neo4jPath
from neo4j.graph import Relationship as Neo4jRelationship

from graph_db.base import GraphDatabase
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

logger = logging.getLogger("graph_db.neo4j")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _neo4j_node_to_model(n: Neo4jNode) -> Node:
    return Node(id=n.element_id, labels=list(n.labels), properties=dict(n))


def _neo4j_rel_to_model(r: Neo4jRelationship) -> Edge:
    return Edge(
        id=r.element_id,
        type=r.type,
        source_id=r.start_node.element_id,
        target_id=r.end_node.element_id,
        properties=dict(r),
    )


def _neo4j_path_to_model(p: Neo4jPath) -> Path:
    return Path(
        nodes=[_neo4j_node_to_model(n) for n in p.nodes],
        edges=[_neo4j_rel_to_model(r) for r in p.relationships],
    )


def _convert_value(val: Any) -> Any:
    """Convert a Neo4j result value to our model or return as-is."""
    if isinstance(val, Neo4jNode):
        return _neo4j_node_to_model(val)
    elif isinstance(val, Neo4jRelationship):
        return _neo4j_rel_to_model(val)
    elif isinstance(val, Neo4jPath):
        return _neo4j_path_to_model(val)
    return val


def _parse_records(result) -> list[dict[str, Any]]:
    """Parse a neo4j Result into a list of plain dicts with model conversion."""
    records = []
    for rec in result:
        records.append({key: _convert_value(rec[key]) for key in rec.keys()})
    return records


def _labels_clause(labels: list[str], var: str = "n", identity_props: dict[str, Any] | None = None) -> str:
    """Build Cypher node pattern: ``(n:Label1:Label2 {k: $id_k})``.

    If *identity_props* is provided, the property match clause is placed
    inside the node parentheses (required by MERGE).
    """
    label_str = ":" + ":".join(labels) if labels else ""
    if identity_props:
        props_clause = _identity_props_clause(identity_props, var=var)
        return f"({var}{label_str} {props_clause})"
    return f"({var}{label_str})"


def _identity_props_clause(identity_props: dict[str, Any], var: str = "n") -> str:
    """Build Cypher property match clause for MERGE: ``{k1: $id_k1, k2: $id_k2}``."""
    parts = ", ".join(f"{k}: $id_{k}" for k in identity_props)
    return f"{{{parts}}}"


def _identity_params(identity_props: dict[str, Any]) -> dict[str, Any]:
    """Build parameter dict for identity props: ``{"id_k1": v1, "id_k2": v2}``."""
    return {f"id_{k}": v for k, v in identity_props.items()}


# ---------------------------------------------------------------------------
# Neo4j Transaction wrapper
# ---------------------------------------------------------------------------

class Neo4jTransaction:
    """Wraps a ``neo4j.Transaction`` to implement the ``Transaction`` protocol."""

    def __init__(self, tx: neo4j.Transaction):
        self._tx = tx
        self._committed = False
        self._rolled_back = False

    # -- Node CRUD --

    def create_node(
        self, labels: list[str], properties: dict[str, Any] | None = None
    ) -> Node:
        lbl = _labels_clause(labels)
        cypher = f"CREATE {lbl} SET n = $props RETURN n"
        result = self._tx.run(cypher, props=properties or {})
        rec = result.single()
        return _neo4j_node_to_model(rec["n"])

    def merge_node(
        self,
        labels: list[str],
        identity_props: dict[str, Any],
        properties: dict[str, Any] | None = None,
    ) -> Node:
        pattern = _labels_clause(labels, identity_props=identity_props)
        cypher = f"MERGE {pattern} SET n += $props RETURN n"
        params = _identity_params(identity_props)
        params["props"] = properties or {}
        result = self._tx.run(cypher, params)
        rec = result.single()
        return _neo4j_node_to_model(rec["n"])

    def get_node(self, node_id: Any) -> Node | None:
        result = self._tx.run("MATCH (n) WHERE elementId(n) = $id RETURN n", id=node_id)
        rec = result.single()
        return _neo4j_node_to_model(rec["n"]) if rec else None

    def update_node(self, node_id: Any, properties: dict[str, Any]) -> Node:
        result = self._tx.run(
            "MATCH (n) WHERE elementId(n) = $id SET n += $props RETURN n",
            id=node_id, props=properties,
        )
        rec = result.single()
        return _neo4j_node_to_model(rec["n"])

    def delete_node(self, node_id: Any, detach: bool = False) -> bool:
        keyword = "DETACH DELETE" if detach else "DELETE"
        result = self._tx.run(
            f"MATCH (n) WHERE elementId(n) = $id {keyword} n RETURN count(n) AS cnt",
            id=node_id,
        )
        rec = result.single()
        return rec["cnt"] > 0 if rec else False

    # -- Edge CRUD --

    def create_edge(
        self,
        source_id: Any,
        target_id: Any,
        edge_type: str,
        properties: dict[str, Any] | None = None,
    ) -> Edge:
        cypher = (
            "MATCH (a) WHERE elementId(a) = $source_id "
            "MATCH (b) WHERE elementId(b) = $target_id "
            f"CREATE (a)-[r:{edge_type}]->(b) SET r = $props RETURN r"
        )
        result = self._tx.run(
            cypher, source_id=source_id, target_id=target_id, props=properties or {}
        )
        rec = result.single()
        return _neo4j_rel_to_model(rec["r"])

    def merge_edge(
        self,
        source_id: Any,
        target_id: Any,
        edge_type: str,
        identity_props: dict[str, Any],
        properties: dict[str, Any] | None = None,
    ) -> Edge:
        props_clause = _identity_props_clause(identity_props, var="r")
        cypher = (
            "MATCH (a) WHERE elementId(a) = $source_id "
            "MATCH (b) WHERE elementId(b) = $target_id "
            f"MERGE (a)-[r:{edge_type} {props_clause}]->(b) "
            "SET r += $props RETURN r"
        )
        params = _identity_params(identity_props)
        params["source_id"] = source_id
        params["target_id"] = target_id
        params["props"] = properties or {}
        result = self._tx.run(cypher, params)
        rec = result.single()
        return _neo4j_rel_to_model(rec["r"])

    def get_edge(self, edge_id: Any) -> Edge | None:
        result = self._tx.run(
            "MATCH ()-[r]->() WHERE elementId(r) = $id RETURN r", id=edge_id
        )
        rec = result.single()
        return _neo4j_rel_to_model(rec["r"]) if rec else None

    def update_edge(self, edge_id: Any, properties: dict[str, Any]) -> Edge:
        result = self._tx.run(
            "MATCH ()-[r]->() WHERE elementId(r) = $id SET r += $props RETURN r",
            id=edge_id, props=properties,
        )
        rec = result.single()
        return _neo4j_rel_to_model(rec["r"])

    def delete_edge(self, edge_id: Any) -> bool:
        result = self._tx.run(
            "MATCH ()-[r]->() WHERE elementId(r) = $id DELETE r RETURN count(r) AS cnt",
            id=edge_id,
        )
        rec = result.single()
        return rec["cnt"] > 0 if rec else False

    # -- Raw query --

    def run(
        self, query: str, params: dict[str, Any] | None = None
    ) -> QueryResult:
        result = self._tx.run(query, params or {})
        return QueryResult(records=_parse_records(result))

    # -- Commit / Rollback --

    def commit(self) -> None:
        self._committed = True

    def rollback(self) -> None:
        self._rolled_back = True

    # -- Context manager --

    def __enter__(self) -> "Neo4jTransaction":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if exc_type is not None:
            self._rolled_back = True


# ---------------------------------------------------------------------------
# Neo4j GraphDatabase implementation
# ---------------------------------------------------------------------------

class Neo4jGraphDatabase(GraphDatabase):
    """Neo4j implementation of the generic GraphDatabase API.

    Args:
        uri: Neo4j bolt URI (e.g. ``bolt://localhost:7687``).
        auth: Tuple of (username, password).
        database: Target database name (default ``"neo4j"``).

    Example::

        db = Neo4jGraphDatabase("bolt://localhost:7687", ("neo4j", "password"))
        db.connect()
        node = db.create_node(["Person"], {"name": "Alice"})
        db.close()
    """

    def __init__(
        self,
        uri: str,
        auth: tuple[str, str],
        database: str = "neo4j",
    ):
        self._uri = uri
        self._auth = auth
        self._database = database
        self._driver: neo4j.Driver | None = None

    # ----- connection lifecycle -----

    def connect(self) -> None:
        if self._driver is not None:
            return
        self._driver = Neo4jDriver.driver(self._uri, auth=self._auth)
        self._driver.verify_connectivity()
        logger.info("Connected to Neo4j at %s", self._uri)

    def close(self) -> None:
        if self._driver is not None:
            self._driver.close()
            self._driver = None
            logger.info("Disconnected from Neo4j")

    def is_connected(self) -> bool:
        if self._driver is None:
            return False
        try:
            self._driver.verify_connectivity()
            return True
        except Exception:
            return False

    # ----- internal helpers -----

    def _session(self, **kwargs) -> neo4j.Session:
        assert self._driver is not None, "Not connected — call connect() first"
        return self._driver.session(database=self._database, **kwargs)

    # ==================================================================
    # Node CRUD
    # ==================================================================

    def create_node(
        self, labels: list[str], properties: dict[str, Any] | None = None
    ) -> Node:
        with self._session() as session:
            def _create(tx):
                lbl = _labels_clause(labels)
                result = tx.run(f"CREATE {lbl} SET n = $props RETURN n", props=properties or {})
                return _neo4j_node_to_model(result.single()["n"])
            return session.execute_write(_create)

    def merge_node(
        self,
        labels: list[str],
        identity_props: dict[str, Any],
        properties: dict[str, Any] | None = None,
    ) -> Node:
        with self._session() as session:
            def _merge(tx):
                pattern = _labels_clause(labels, identity_props=identity_props)
                cypher = f"MERGE {pattern} SET n += $props RETURN n"
                params = _identity_params(identity_props)
                params["props"] = properties or {}
                return _neo4j_node_to_model(tx.run(cypher, params).single()["n"])
            return session.execute_write(_merge)

    def get_node(self, node_id: Any) -> Node | None:
        with self._session() as session:
            def _get(tx):
                result = tx.run(
                    "MATCH (n) WHERE elementId(n) = $id RETURN n", id=node_id
                )
                rec = result.single()
                return _neo4j_node_to_model(rec["n"]) if rec else None
            return session.execute_read(_get)

    def get_nodes_by_label(
        self, label: str, *, limit: int = 100, offset: int = 0
    ) -> PagedResult:
        with self._session() as session:
            def _query(tx):
                total = tx.run(
                    f"MATCH (n:{label}) RETURN count(n) AS cnt"
                ).single()["cnt"]
                result = tx.run(
                    f"MATCH (n:{label}) RETURN n ORDER BY elementId(n) "
                    f"SKIP $offset LIMIT $limit",
                    offset=offset, limit=limit,
                )
                nodes = [_neo4j_node_to_model(rec["n"]) for rec in result]
                return PagedResult(
                    items=nodes,
                    page=PageInfo(offset=offset, limit=limit, total=total),
                )
            return session.execute_read(_query)

    def find_nodes(
        self,
        labels: list[str],
        properties: dict[str, Any],
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> PagedResult:
        lbl = _labels_clause(labels)
        if properties:
            prop_match = ", ".join(f"n.{k} = $p_{k}" for k in properties)
            params = {f"p_{k}": v for k, v in properties.items()}
            where_clause = f" WHERE {prop_match}"
        else:
            params = {}
            where_clause = ""
        params["offset"] = offset
        params["limit"] = limit

        with self._session() as session:
            def _query(tx):
                cnt = tx.run(
                    f"MATCH {lbl}{where_clause} RETURN count(n) AS cnt", params
                ).single()["cnt"]
                result = tx.run(
                    f"MATCH {lbl}{where_clause} RETURN n "
                    f"ORDER BY elementId(n) SKIP $offset LIMIT $limit",
                    params,
                )
                nodes = [_neo4j_node_to_model(rec["n"]) for rec in result]
                return PagedResult(
                    items=nodes,
                    page=PageInfo(offset=offset, limit=limit, total=cnt),
                )
            return session.execute_read(_query)

    def update_node(self, node_id: Any, properties: dict[str, Any]) -> Node:
        with self._session() as session:
            def _update(tx):
                result = tx.run(
                    "MATCH (n) WHERE elementId(n) = $id SET n += $props RETURN n",
                    id=node_id, props=properties,
                )
                return _neo4j_node_to_model(result.single()["n"])
            return session.execute_write(_update)

    def delete_node(self, node_id: Any, *, detach: bool = False) -> bool:
        keyword = "DETACH DELETE" if detach else "DELETE"
        with self._session() as session:
            def _delete(tx):
                result = tx.run(
                    f"MATCH (n) WHERE elementId(n) = $id {keyword} n "
                    f"RETURN count(n) AS cnt",
                    id=node_id,
                )
                rec = result.single()
                return rec["cnt"] > 0 if rec else False
            try:
                return session.execute_write(_delete)
            except neo4j.exceptions.ConstraintError:
                # Node has relationships and detach=False
                raise ValueError(
                    f"Cannot delete node {node_id}: it still has relationships. "
                    "Use detach=True to delete with relationships."
                )

    # ==================================================================
    # Edge CRUD
    # ==================================================================

    def create_edge(
        self,
        source_id: Any,
        target_id: Any,
        edge_type: str,
        properties: dict[str, Any] | None = None,
    ) -> Edge:
        with self._session() as session:
            def _create(tx):
                cypher = (
                    "MATCH (a) WHERE elementId(a) = $source_id "
                    "MATCH (b) WHERE elementId(b) = $target_id "
                    f"CREATE (a)-[r:{edge_type}]->(b) SET r = $props RETURN r"
                )
                result = tx.run(
                    cypher,
                    source_id=source_id, target_id=target_id,
                    props=properties or {},
                )
                return _neo4j_rel_to_model(result.single()["r"])
            return session.execute_write(_create)

    def merge_edge(
        self,
        source_id: Any,
        target_id: Any,
        edge_type: str,
        identity_props: dict[str, Any],
        properties: dict[str, Any] | None = None,
    ) -> Edge:
        props_clause = _identity_props_clause(identity_props, var="r")
        with self._session() as session:
            def _merge(tx):
                cypher = (
                    "MATCH (a) WHERE elementId(a) = $source_id "
                    "MATCH (b) WHERE elementId(b) = $target_id "
                    f"MERGE (a)-[r:{edge_type} {props_clause}]->(b) "
                    "SET r += $props RETURN r"
                )
                params = _identity_params(identity_props)
                params["source_id"] = source_id
                params["target_id"] = target_id
                params["props"] = properties or {}
                result = tx.run(cypher, params)
                return _neo4j_rel_to_model(result.single()["r"])
            return session.execute_write(_merge)

    def get_edge(self, edge_id: Any) -> Edge | None:
        with self._session() as session:
            def _get(tx):
                result = tx.run(
                    "MATCH ()-[r]->() WHERE elementId(r) = $id RETURN r",
                    id=edge_id,
                )
                rec = result.single()
                return _neo4j_rel_to_model(rec["r"]) if rec else None
            return session.execute_read(_get)

    def get_edges_by_type(
        self, edge_type: str, *, limit: int = 100, offset: int = 0
    ) -> PagedResult:
        with self._session() as session:
            def _query(tx):
                cnt = tx.run(
                    f"MATCH ()-[r:{edge_type}]->() RETURN count(r) AS cnt"
                ).single()["cnt"]
                result = tx.run(
                    f"MATCH ()-[r:{edge_type}]->() RETURN r "
                    f"ORDER BY elementId(r) SKIP $offset LIMIT $limit",
                    offset=offset, limit=limit,
                )
                edges = [_neo4j_rel_to_model(rec["r"]) for rec in result]
                return PagedResult(
                    items=edges,
                    page=PageInfo(offset=offset, limit=limit, total=cnt),
                )
            return session.execute_read(_query)

    def find_edges(
        self,
        edge_type: str,
        properties: dict[str, Any],
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> PagedResult:
        if properties:
            prop_match = ", ".join(f"r.{k} = $p_{k}" for k in properties)
            params = {f"p_{k}": v for k, v in properties.items()}
            where_clause = f" WHERE {prop_match}"
        else:
            params = {}
            where_clause = ""
        params["offset"] = offset
        params["limit"] = limit

        with self._session() as session:
            def _query(tx):
                cnt = tx.run(
                    f"MATCH ()-[r:{edge_type}]->(){where_clause} "
                    f"RETURN count(r) AS cnt", params
                ).single()["cnt"]
                result = tx.run(
                    f"MATCH ()-[r:{edge_type}]->(){where_clause} "
                    f"RETURN r ORDER BY elementId(r) SKIP $offset LIMIT $limit",
                    params,
                )
                edges = [_neo4j_rel_to_model(rec["r"]) for rec in result]
                return PagedResult(
                    items=edges,
                    page=PageInfo(offset=offset, limit=limit, total=cnt),
                )
            return session.execute_read(_query)

    def update_edge(self, edge_id: Any, properties: dict[str, Any]) -> Edge:
        with self._session() as session:
            def _update(tx):
                result = tx.run(
                    "MATCH ()-[r]->() WHERE elementId(r) = $id "
                    "SET r += $props RETURN r",
                    id=edge_id, props=properties,
                )
                return _neo4j_rel_to_model(result.single()["r"])
            return session.execute_write(_update)

    def delete_edge(self, edge_id: Any) -> bool:
        with self._session() as session:
            def _delete(tx):
                result = tx.run(
                    "MATCH ()-[r]->() WHERE elementId(r) = $id "
                    "DELETE r RETURN count(r) AS cnt",
                    id=edge_id,
                )
                rec = result.single()
                return rec["cnt"] > 0 if rec else False
            return session.execute_write(_delete)

    # ==================================================================
    # Neighbourhood / traversal
    # ==================================================================

    def get_node_edges(
        self,
        node_id: Any,
        *,
        direction: str = "both",
        edge_type: str | None = None,
        limit: int = 100,
    ) -> list[Edge]:
        type_clause = f":{edge_type}" if edge_type else ""
        if direction == "out":
            pattern = f"(n)-[r{type_clause}]->()"
        elif direction == "in":
            pattern = f"()-[r{type_clause}]->(n)"
        else:
            pattern = f"(n)-[r{type_clause}]-()"

        with self._session() as session:
            def _query(tx):
                result = tx.run(
                    f"MATCH {pattern} WHERE elementId(n) = $id "
                    f"RETURN r LIMIT $limit",
                    id=node_id, limit=limit,
                )
                return [_neo4j_rel_to_model(rec["r"]) for rec in result]
            return session.execute_read(_query)

    def get_neighbours(
        self,
        node_id: Any,
        *,
        direction: str = "both",
        edge_type: str | None = None,
        limit: int = 100,
    ) -> list[Node]:
        type_clause = f":{edge_type}" if edge_type else ""
        if direction == "out":
            pattern = f"(n)-[r{type_clause}]->(m)"
        elif direction == "in":
            pattern = f"(m)-[r{type_clause}]->(n)"
        else:
            pattern = f"(n)-[r{type_clause}]-(m)"

        with self._session() as session:
            def _query(tx):
                result = tx.run(
                    f"MATCH {pattern} WHERE elementId(n) = $id "
                    f"RETURN DISTINCT m LIMIT $limit",
                    id=node_id, limit=limit,
                )
                return [_neo4j_node_to_model(rec["m"]) for rec in result]
            return session.execute_read(_query)

    def shortest_path(
        self,
        source_id: Any,
        target_id: Any,
        *,
        edge_type: str | None = None,
        max_depth: int = 10,
    ) -> Path | None:
        # Neo4j shortestPath does not support same start and end node
        if source_id == target_id:
            node = self.get_node(source_id)
            if node is None:
                return None
            return Path(nodes=[node], edges=[])
        rel_pattern = f":{edge_type}" if edge_type else ""
        with self._session() as session:
            def _query(tx):
                cypher = (
                    "MATCH (a) WHERE elementId(a) = $source_id "
                    "MATCH (b) WHERE elementId(b) = $target_id "
                    f"MATCH p = shortestPath((a)-[{rel_pattern}*..{max_depth}]-(b)) "
                    "RETURN p"
                )
                result = tx.run(cypher, source_id=source_id, target_id=target_id)
                rec = result.single()
                return _neo4j_path_to_model(rec["p"]) if rec else None
            return session.execute_read(_query)

    # ==================================================================
    # Query execution
    # ==================================================================

    def execute_query(
        self, query: str, params: dict[str, Any] | None = None
    ) -> QueryResult:
        with self._session() as session:
            result = session.run(query, params or {})
            return QueryResult(records=_parse_records(result))

    def execute_read(
        self, query: str, params: dict[str, Any] | None = None
    ) -> QueryResult:
        with self._session() as session:
            def _read(tx):
                result = tx.run(query, params or {})
                return QueryResult(records=_parse_records(result))
            return session.execute_read(_read)

    def execute_write(
        self, query: str, params: dict[str, Any] | None = None
    ) -> QueryResult:
        with self._session() as session:
            def _write(tx):
                result = tx.run(query, params or {})
                return QueryResult(records=_parse_records(result))
            return session.execute_write(_write)

    # ==================================================================
    # Transactions
    # ==================================================================

    def transaction(self) -> Neo4jTransaction:
        session = self._session()
        tx = session.begin_transaction()
        return Neo4jTransaction(tx)

    # ==================================================================
    # Batch operations
    # ==================================================================

    def batch_create_nodes(
        self,
        items: Sequence[dict[str, Any]],
        labels: list[str],
    ) -> list[Node]:
        lbl = _labels_clause(labels, var="n")
        cypher = (
            f"UNWIND $items AS item "
            f"CREATE {lbl} SET n = item RETURN n"
        )
        with self._session() as session:
            def _batch(tx):
                result = tx.run(cypher, items=list(items))
                return [_neo4j_node_to_model(rec["n"]) for rec in result]
            return session.execute_write(_batch)

    def batch_create_edges(
        self,
        items: Sequence[dict[str, Any]],
        edge_type: str,
    ) -> list[Edge]:
        cypher = (
            "UNWIND $items AS item "
            "MATCH (a) WHERE elementId(a) = item.source_id "
            "MATCH (b) WHERE elementId(b) = item.target_id "
            f"CREATE (a)-[r:{edge_type}]->(b) SET r = item.props RETURN r"
        )
        params = [
            {"source_id": it["source_id"], "target_id": it["target_id"],
             "props": {k: v for k, v in it.items() if k not in ("source_id", "target_id")}}
            for it in items
        ]
        with self._session() as session:
            def _batch(tx):
                result = tx.run(cypher, items=params)
                return [_neo4j_rel_to_model(rec["r"]) for rec in result]
            return session.execute_write(_batch)

    # ==================================================================
    # Schema management
    # ==================================================================

    def create_index(self, spec: IndexSpec) -> None:
        if spec.unique:
            cypher = (
                f"CREATE CONSTRAINT FOR (n:{spec.label}) "
                f"REQUIRE n.{spec.properties[0]} IS UNIQUE"
            )
        else:
            if len(spec.properties) == 1:
                cypher = f"CREATE INDEX FOR (n:{spec.label}) ON (n.{spec.properties[0]})"
            else:
                props = ", ".join(f"n.{p}" for p in spec.properties)
                cypher = f"CREATE INDEX FOR (n:{spec.label}) ON ({props})"
        with self._session() as session:
            try:
                session.run(cypher)
            except neo4j.exceptions.ClientError as e:
                if "AlreadyExists" in e.code or "already exists" in str(e):
                    raise ValueError(f"Index already exists: {e.message}")
                raise

    def drop_index(self, label: str, properties: list[str]) -> None:
        with self._session() as session:
            result = session.run("SHOW INDEXES")
            for rec in result:
                if (rec.get("labelsOrTypes") == [label]
                        and rec.get("properties") == properties):
                    session.run(f"DROP INDEX {rec['name']}")
                    return
            raise ValueError(f"No index found for {label}.{properties}")

    def list_indexes(self, label: str | None = None) -> list[IndexSpec]:
        with self._session() as session:
            try:
                result = session.run("SHOW INDEXES")
            except neo4j.exceptions.ClientError:
                return []
            indexes = []
            for rec in result:
                lbls = rec.get("labelsOrTypes") or []
                props = rec.get("properties") or []
                # Skip internal indexes (those with no label or empty properties)
                if not lbls or not props:
                    continue
                if label and label not in lbls:
                    continue
                try:
                    indexes.append(IndexSpec(
                        label=lbls[0],
                        properties=props,
                        unique=(
                            rec.get("uniqueness") == "UNIQUE"
                            or rec.get("owningConstraint") is not None
                        ),
                    ))
                except Exception:
                    continue
            return indexes

    def create_constraint(self, spec: ConstraintSpec) -> None:
        if spec.kind == "unique":
            cypher = (
                f"CREATE CONSTRAINT {spec.name} FOR (n:{spec.label}) "
                f"REQUIRE n.{spec.property} IS UNIQUE"
            )
        elif spec.kind == "node_key":
            cypher = (
                f"CREATE CONSTRAINT {spec.name} FOR (n:{spec.label}) "
                f"REQUIRE (n.{spec.property}) IS NODE KEY"
            )
        elif spec.kind == "exists":
            cypher = (
                f"CREATE CONSTRAINT {spec.name} FOR (n:{spec.label}) "
                f"REQUIRE n.{spec.property} IS NOT NULL"
            )
        else:
            raise ValueError(f"Unknown constraint kind: {spec.kind}")
        with self._session() as session:
            try:
                session.run(cypher)
            except neo4j.exceptions.ClientError as e:
                if "AlreadyExists" in e.code or "already exists" in str(e):
                    raise ValueError(f"Constraint already exists: {e.message}")
                raise

    def drop_constraint(self, name: str) -> None:
        with self._session() as session:
            try:
                session.run(f"DROP CONSTRAINT {name}")
            except neo4j.exceptions.DatabaseError as e:
                if "ConstraintDropFailed" in e.code or "No such constraint" in str(e):
                    raise ValueError(f"Constraint '{name}' does not exist")
                raise

    def list_constraints(self) -> list[ConstraintSpec]:
        with self._session() as session:
            try:
                result = session.run("SHOW CONSTRAINTS")
            except neo4j.exceptions.ClientError:
                return []
            constraints = []
            for rec in result:
                try:
                    constraints.append(ConstraintSpec(
                        name=rec.get("name", ""),
                        label=(rec.get("labelsOrTypes") or [""])[0],
                        property=(rec.get("properties") or [""])[0],
                        kind="unique",
                    ))
                except Exception:
                    continue
            return constraints

    # ==================================================================
    # Database info
    # ==================================================================

    def node_count(self, label: str | None = None) -> int:
        match = f"(n:{label})" if label else "(n)"
        with self._session() as session:
            result = session.run(f"MATCH {match} RETURN count(n) AS cnt")
            return result.single()["cnt"]

    def edge_count(self, edge_type: str | None = None) -> int:
        match = f"()-[r:{edge_type}]->()" if edge_type else "()-[r]->()"
        with self._session() as session:
            result = session.run(f"MATCH {match} RETURN count(r) AS cnt")
            return result.single()["cnt"]

    def labels(self) -> list[str]:
        with self._session() as session:
            result = session.run("CALL db.labels()")
            return [rec["label"] for rec in result]

    def edge_types(self) -> list[str]:
        with self._session() as session:
            result = session.run("CALL db.relationshipTypes()")
            return [rec["relationshipType"] for rec in result]
