from __future__ import annotations

import infra.graph_db as graph_pkg
from infra.graph_db import TRSGraphClient, close_trs_graph_client, get_trs_graph_client


def test_graph_client_singleton_caches_and_resets(monkeypatch):
    monkeypatch.setenv("TRS_GRAPH_BASE_URL", "http://test")
    monkeypatch.setenv("TRS_GRAPH_SPACE", "dev")
    monkeypatch.setenv("TRS_GRAPH_API_KEY", "")
    close_trs_graph_client()
    monkeypatch.setattr(TRSGraphClient, "connect", lambda self: None)
    monkeypatch.setattr(TRSGraphClient, "is_connected", lambda self: True)
    c1 = get_trs_graph_client()
    c2 = get_trs_graph_client()
    assert c1 is c2
    assert c1._settings.space == "dev"  # noqa: SLF001
    close_trs_graph_client()
    assert graph_pkg._client is None  # noqa: SLF001
