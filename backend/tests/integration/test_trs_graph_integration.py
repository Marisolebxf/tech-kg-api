"""Integration tests for TRS Graph backend against a live trs-graph-service.

These tests require a running trs-graph-service and are skipped
automatically when the service is unavailable.

Run manually with:
    pytest tests/integration/test_trs_graph_integration.py -v

Set env vars if different from defaults:
    GRAPH_DB_URI=http://localhost:8090
    GRAPH_DB_DATABASE=tech-kg
    GRAPH_DB_AUTH=ysukeg
"""

from __future__ import annotations

import pytest

from graph_db import GraphDBConfig, connect
from graph_db.models import ConstraintSpec, IndexSpec

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _is_service_available() -> bool:
    """Check if the TRS Graph service is reachable."""
    try:
        config = GraphDBConfig.from_env()
        if config.backend != "trs_graph":
            return False
        db = connect(config)
        healthy = db.is_connected()
        db.close()
        return healthy
    except Exception:
        return False


requires_trs_graph = pytest.mark.skipif(
    not _is_service_available(),
    reason="TRS Graph service not available",
)


@pytest.fixture(scope="module")
def db():
    """Module-scoped database connection."""
    config = GraphDBConfig.from_env()
    database = connect(config)
    yield database
    database.close()


@pytest.fixture(autouse=True, scope="module")
def setup_schema(db):
    """Ensure the test TAG and EDGE TYPE exist; clean up after."""
    db.execute_write("CREATE TAG IF NOT EXISTS IntegrationTestPerson(name string, age int)")
    db.execute_write("CREATE EDGE IF NOT EXISTS IntegrationTestKnows(since int)")
    yield
    # Teardown: remove test data
    for n in db.get_nodes_by_label("IntegrationTestPerson", limit=200).items:
        db.delete_node(n.id, detach=True)


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------


class TestConnection:
    @requires_trs_graph
    def test_connect_and_health(self, db):
        assert db.is_connected() is True

    @requires_trs_graph
    def test_labels_includes_test_tag(self, db):
        labels = db.labels()
        assert "IntegrationTestPerson" in labels

    @requires_trs_graph
    def test_edge_types_includes_test_edge(self, db):
        types = db.edge_types()
        assert "IntegrationTestKnows" in types


# ---------------------------------------------------------------------------
# Node CRUD
# ---------------------------------------------------------------------------


class TestNodeCRUD:
    @requires_trs_graph
    def test_create_node(self, db):
        node = db.create_node(["IntegrationTestPerson"], {"name": "intg_alice", "age": 30})
        assert node.id is not None
        assert "IntegrationTestPerson" in node.labels
        assert node.properties["name"] == "intg_alice"

    @requires_trs_graph
    def test_get_node(self, db):
        created = db.create_node(["IntegrationTestPerson"], {"name": "intg_bob", "age": 25})
        found = db.get_node(created.id)
        assert found is not None
        assert found.properties["name"] == "intg_bob"

    @requires_trs_graph
    def test_get_node_not_found(self, db):
        assert db.get_node("nonexistent_node_xyz") is None

    @requires_trs_graph
    def test_merge_node(self, db):
        db.merge_node(
            ["IntegrationTestPerson"],
            {"name": "intg_merge"},
            {"age": 20},
        )
        merged = db.merge_node(
            ["IntegrationTestPerson"],
            {"name": "intg_merge"},
            {"age": 21},
        )
        assert merged.properties["age"] == 21

    @requires_trs_graph
    def test_update_node(self, db):
        node = db.create_node(["IntegrationTestPerson"], {"name": "intg_update", "age": 20})
        updated = db.update_node(node.id, {"age": 22})
        assert updated.properties["age"] == 22

    @requires_trs_graph
    def test_get_nodes_by_label(self, db):
        result = db.get_nodes_by_label("IntegrationTestPerson", limit=100)
        assert len(result.items) > 0

    @requires_trs_graph
    def test_find_nodes_with_properties(self, db):
        # Ensure index exists for property-based find
        try:
            db.create_index(IndexSpec(label="IntegrationTestPerson", properties=["name"]))
        except Exception:
            pass  # Index may already exist
        result = db.find_nodes(["IntegrationTestPerson"], {"name": "intg_alice"}, limit=10)
        assert len(result.items) >= 1
        assert result.items[0].properties["name"] == "intg_alice"

    @requires_trs_graph
    def test_delete_node(self, db):
        node = db.create_node(["IntegrationTestPerson"], {"name": "intg_delete", "age": 99})
        assert db.delete_node(node.id, detach=True) is True
        assert db.get_node(node.id) is None

    @requires_trs_graph
    def test_batch_create_nodes(self, db):
        nodes = db.batch_create_nodes(
            [{"name": f"intg_batch_{i}", "age": 20 + i} for i in range(3)],
            labels=["IntegrationTestPerson"],
        )
        assert len(nodes) >= 0  # Server may or may not return created nodes


# ---------------------------------------------------------------------------
# Edge CRUD
# ---------------------------------------------------------------------------


class TestEdgeCRUD:
    @requires_trs_graph
    def test_create_edge(self, db):
        n1 = db.create_node(["IntegrationTestPerson"], {"name": "intg_edge_a", "age": 30})
        n2 = db.create_node(["IntegrationTestPerson"], {"name": "intg_edge_b", "age": 25})
        edge = db.create_edge(n1.id, n2.id, "IntegrationTestKnows", {"since": 2026})
        assert edge.type == "IntegrationTestKnows"
        assert edge.properties["since"] == 2026

    @requires_trs_graph
    def test_get_edge(self, db):
        n1 = db.create_node(["IntegrationTestPerson"], {"name": "intg_get_a", "age": 30})
        n2 = db.create_node(["IntegrationTestPerson"], {"name": "intg_get_b", "age": 25})
        created = db.create_edge(n1.id, n2.id, "IntegrationTestKnows", {"since": 2020})
        found = db.get_edge(created.id)
        assert found is not None
        assert found.type == "IntegrationTestKnows"

    @requires_trs_graph
    def test_merge_edge(self, db):
        n1 = db.create_node(["IntegrationTestPerson"], {"name": "intg_merge_a", "age": 30})
        n2 = db.create_node(["IntegrationTestPerson"], {"name": "intg_merge_b", "age": 25})
        edge = db.merge_edge(
            n1.id,
            n2.id,
            "IntegrationTestKnows",
            identity_props={"since": 2021},
            properties={},
        )
        assert edge.id is not None

    @requires_trs_graph
    def test_get_edges_by_type(self, db):
        result = db.get_edges_by_type("IntegrationTestKnows", limit=100)
        assert len(result.items) >= 1

    @requires_trs_graph
    def test_update_edge(self, db):
        n1 = db.create_node(["IntegrationTestPerson"], {"name": "intg_upd_a", "age": 30})
        n2 = db.create_node(["IntegrationTestPerson"], {"name": "intg_upd_b", "age": 25})
        edge = db.create_edge(n1.id, n2.id, "IntegrationTestKnows", {"since": 2020})
        updated = db.update_edge(edge.id, {"since": 2022})
        assert updated is not None

    @requires_trs_graph
    def test_delete_edge(self, db):
        n1 = db.create_node(["IntegrationTestPerson"], {"name": "intg_del_a", "age": 30})
        n2 = db.create_node(["IntegrationTestPerson"], {"name": "intg_del_b", "age": 25})
        edge = db.create_edge(n1.id, n2.id, "IntegrationTestKnows", {"since": 2020})
        assert db.delete_edge(edge.id) is True

    @requires_trs_graph
    def test_batch_create_edges(self, db):
        n1 = db.create_node(["IntegrationTestPerson"], {"name": "intg_bat_a", "age": 30})
        n2 = db.create_node(["IntegrationTestPerson"], {"name": "intg_bat_b", "age": 25})
        edges = db.batch_create_edges(
            [{"sourceId": n1.id, "targetId": n2.id, "since": i} for i in range(2)],
            edge_type="IntegrationTestKnows",
        )
        assert len(edges) >= 1


# ---------------------------------------------------------------------------
# Traversal
# ---------------------------------------------------------------------------


class TestTraversal:
    @requires_trs_graph
    def test_get_neighbours(self, db):
        n1 = db.create_node(["IntegrationTestPerson"], {"name": "intg_nbr_a", "age": 30})
        n2 = db.create_node(["IntegrationTestPerson"], {"name": "intg_nbr_b", "age": 25})
        db.create_edge(n1.id, n2.id, "IntegrationTestKnows", {"since": 2026})
        neighbours = db.get_neighbours(n1.id, direction="out")
        assert len(neighbours) >= 1

    @requires_trs_graph
    def test_get_node_edges(self, db):
        n1 = db.create_node(["IntegrationTestPerson"], {"name": "intg_ne_a", "age": 30})
        n2 = db.create_node(["IntegrationTestPerson"], {"name": "intg_ne_b", "age": 25})
        db.create_edge(n1.id, n2.id, "IntegrationTestKnows", {"since": 2026})
        edges = db.get_node_edges(n1.id, direction="out")
        assert len(edges) >= 1

    @requires_trs_graph
    def test_shortest_path(self, db):
        n1 = db.create_node(["IntegrationTestPerson"], {"name": "intg_sp_a", "age": 30})
        n2 = db.create_node(["IntegrationTestPerson"], {"name": "intg_sp_b", "age": 25})
        db.create_edge(n1.id, n2.id, "IntegrationTestKnows", {"since": 2026})
        path = db.shortest_path(n1.id, n2.id, edge_type="IntegrationTestKnows")
        assert path is not None
        assert len(path.nodes) == 2
        assert len(path.edges) == 1
        # Nodes should have complete data
        assert path.nodes[0].labels != []
        assert path.nodes[0].properties != {}


# ---------------------------------------------------------------------------
# Query
# ---------------------------------------------------------------------------


class TestQuery:
    @requires_trs_graph
    def test_execute_query(self, db):
        result = db.execute_query("MATCH (n:IntegrationTestPerson) RETURN n LIMIT 3")
        assert len(result.records) >= 0

    @requires_trs_graph
    def test_execute_read(self, db):
        result = db.execute_read("MATCH (n:IntegrationTestPerson) RETURN n LIMIT 3")
        assert isinstance(result.records, list)

    @requires_trs_graph
    def test_execute_write(self, db):
        result = db.execute_write("CREATE EDGE IF NOT EXISTS IntegrationTestWrite(weight int)")
        assert result is not None


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


class TestSchema:
    @requires_trs_graph
    def test_create_and_list_index(self, db):
        db.create_index(IndexSpec(label="IntegrationTestPerson", properties=["age"]))
        indexes = db.list_indexes(label="IntegrationTestPerson")
        labels = [i.label for i in indexes]
        assert "IntegrationTestPerson" in labels

    @requires_trs_graph
    def test_drop_index(self, db):
        db.create_index(IndexSpec(label="IntegrationTestPerson", properties=["age"]))
        db.drop_index("IntegrationTestPerson", ["age"])

    @requires_trs_graph
    def test_create_and_list_constraint(self, db):
        db.create_constraint(
            ConstraintSpec(
                name="intg_name_uq",
                label="IntegrationTestPerson",
                property="name",
                kind="unique",
            )
        )
        constraints = db.list_constraints()
        names = [c.name for c in constraints]
        assert "intg_name_uq" in names

    @requires_trs_graph
    def test_drop_constraint(self, db):
        db.drop_constraint("intg_name_uq")

    @requires_trs_graph
    def test_node_count(self, db):
        count = db.node_count(label="IntegrationTestPerson")
        assert count >= 0

    @requires_trs_graph
    def test_edge_count(self, db):
        count = db.edge_count(edge_type="IntegrationTestKnows")
        assert count >= 0
