from __future__ import annotations

import infra.graph_db as graph_pkg
from infra.graph_db import TRSGraphClient, close_techkg_client, get_techkg_client


def test_techkg_singleton_caches_and_resets(monkeypatch):
    monkeypatch.setenv("TRS_GRAPH_BASE_URL", "http://test")
    monkeypatch.setenv("TRS_GRAPH_SPACE", "ignored")  # techkg 固定，忽略 env space
    monkeypatch.setenv("TRS_GRAPH_API_KEY", "")
    close_techkg_client()
    monkeypatch.setattr(TRSGraphClient, "connect", lambda self: None)
    monkeypatch.setattr(TRSGraphClient, "is_connected", lambda self: True)
    c1 = get_techkg_client()
    c2 = get_techkg_client()
    assert c1 is c2
    assert c1._settings.space == "techkg"  # noqa: SLF001
    close_techkg_client()
    assert graph_pkg._techkg_client is None  # noqa: SLF001
