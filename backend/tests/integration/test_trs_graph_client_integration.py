"""Integration tests for TRSGraphClient against a live trs-graph-service.

Skipped automatically when the service is unavailable. Run manually::

    pytest tests/integration/test_trs_graph_client_integration.py -v

Configure via TRS_GRAPH_* env vars (see TRSGraphSettings.from_env);
defaults are TRS_GRAPH_BASE_URL=http://localhost:8090,
TRS_GRAPH_SPACE=entity_binding_demo, TRS_GRAPH_API_KEY unset.
"""

from __future__ import annotations

import pytest

from infra.graph_db import TRSGraphClient
from infra.graph_db.config import TRSGraphSettings


def _is_service_available() -> bool:
    """Best-effort liveness + writability check. Returns False on any failure."""
    try:
        repo = TRSGraphClient(TRSGraphSettings.from_env())
        repo.connect()
        if not repo.is_connected():
            return False
        # Probe writability: a service may be UP but reject writes (auth/space).
        repo.execute_write("CREATE TAG IF NOT EXISTS IntegrationTestPerson(name string, age int)")
        return True
    except Exception:
        return False
    finally:
        try:
            repo.close()
        except Exception:
            pass


@pytest.fixture(scope="module")
def repo():
    """Connected TRSGraphClient. Skips the whole module if the service is unavailable."""
    if not _is_service_available():
        pytest.skip("TRS Graph service not available")
    r = TRSGraphClient(TRSGraphSettings.from_env())
    r.connect()
    yield r
    r.close()


@pytest.fixture(autouse=True, scope="module")
def setup_schema(repo):
    """Ensure the test TAG and EDGE TYPE exist; clean up test data after."""
    repo.execute_write("CREATE TAG IF NOT EXISTS IntegrationTestPerson(name string, age int)")
    repo.execute_write("CREATE EDGE IF NOT EXISTS IntegrationTestKnows(since int)")
    yield
    for n in repo.get_nodes_by_label("IntegrationTestPerson", limit=200).items:
        repo.delete_node(n.id, detach=True)


@pytest.mark.external
class TestIntegration:
    def test_node_crud(self, repo):
        n = repo.create_node(["IntegrationTestPerson"], {"name": "Alice", "age": 30})
        fetched = repo.get_node(n.id)
        assert fetched is not None
        assert fetched.properties["name"] == "Alice"
        assert repo.delete_node(n.id) is True

    def test_edge_crud(self, repo):
        a = repo.create_node(["IntegrationTestPerson"], {"name": "A"})
        b = repo.create_node(["IntegrationTestPerson"], {"name": "B"})
        e = repo.create_edge(a.id, b.id, "IntegrationTestKnows", {"since": 2024})
        assert e.source_id == str(a.id)
        found = repo.get_edge(e.id, edge_type="IntegrationTestKnows")
        assert found is not None
        assert repo.delete_edge(e.id, edge_type="IntegrationTestKnows") is True

    def test_info(self, repo):
        assert isinstance(repo.node_count(), int)
        assert isinstance(repo.edge_count(), int)
        assert "IntegrationTestPerson" in repo.labels()
        assert "IntegrationTestKnows" in repo.edge_types()
