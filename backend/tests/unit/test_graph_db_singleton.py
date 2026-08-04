from __future__ import annotations

import infra.graph_db as graph_pkg
from infra.graph_db import (
    TRSGraphClient,
    close_graph_clients,
    close_techkg_client,
    get_graph_client,
    get_techkg_client,
)


def test_techkg_singleton_caches_and_resets(monkeypatch):
    monkeypatch.setenv("TRS_GRAPH_BASE_URL", "http://test")
    monkeypatch.setenv("TRS_GRAPH_SPACE", "dev")
    monkeypatch.setenv("TRS_GRAPH_API_KEY", "")
    close_techkg_client()
    monkeypatch.setattr(TRSGraphClient, "connect", lambda self: None)
    monkeypatch.setattr(TRSGraphClient, "is_connected", lambda self: True)
    c1 = get_techkg_client()
    c2 = get_techkg_client()
    assert c1 is c2
    assert c1._settings.space == "dev"  # noqa: SLF001
    close_techkg_client()
    assert graph_pkg._techkg_client is None  # noqa: SLF001


def test_explicit_space_clients_are_cached_and_closed(monkeypatch):
    close_graph_clients()
    closed: list[str] = []
    monkeypatch.setattr(TRSGraphClient, "connect", lambda self: None)
    monkeypatch.setattr(
        TRSGraphClient,
        "close",
        lambda self: closed.append(self._settings.space),  # noqa: SLF001
    )

    first = get_graph_client("space-a")
    second = get_graph_client("space-a")
    other = get_graph_client("space-b")

    assert first is second
    assert first is not other
    close_graph_clients()
    assert sorted(closed) == ["space-a", "space-b"]
