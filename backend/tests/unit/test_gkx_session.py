from __future__ import annotations

import infra.gkx as gkx


def test_gkx_url_uses_env(monkeypatch):
    monkeypatch.setenv("PAPER_COOP_MYSQL_HOST", "db.example")
    monkeypatch.setenv("PAPER_COOP_MYSQL_PORT", "3307")
    monkeypatch.setenv("PAPER_COOP_MYSQL_USERNAME", "u")
    monkeypatch.setenv("PAPER_COOP_MYSQL_PASSWORD", "p")
    monkeypatch.setenv("PAPER_COOP_MYSQL_DATABASE", "gkx_local")
    gkx.reset_gkx_client()
    url = gkx._gkx_url()
    assert url.startswith("mysql+pymysql://u:p@db.example:3307/gkx_local")


def test_get_gkx_client_is_singleton(monkeypatch):
    monkeypatch.setenv("PAPER_COOP_MYSQL_DATABASE", "gkx_local")
    gkx.reset_gkx_client()
    c1 = gkx.get_gkx_client()
    c2 = gkx.get_gkx_client()
    assert c1 is c2
    gkx.reset_gkx_client()
