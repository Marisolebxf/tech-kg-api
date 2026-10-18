from __future__ import annotations

import infra.graph_db as graph_pkg
from infra.graph_db import (
    TRSGraphClient,
    close_space_clients,
    close_trs_graph_client,
    get_trs_graph_client,
)
from infra.graph_db.config import business_plane_settings
from service.graph_space_context import business_data_plane, selected_graph_space


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


def test_business_plane_settings_disabled_by_default(monkeypatch):
    monkeypatch.delenv("TRS_GRAPH_BUSINESS_BASE_URL", raising=False)
    assert business_plane_settings("dev2") is None
    # compose 传空串默认值时同样视为未配置
    monkeypatch.setenv("TRS_GRAPH_BUSINESS_BASE_URL", "   ")
    assert business_plane_settings("dev2") is None


def test_business_plane_settings_falls_back_to_platform_env(monkeypatch):
    monkeypatch.setenv("TRS_GRAPH_BASE_URL", "http://platform")
    monkeypatch.setenv("TRS_GRAPH_SPACE", "dev")
    monkeypatch.setenv("TRS_GRAPH_API_KEY", "platform-key")
    monkeypatch.setenv("TRS_GRAPH_TIMEOUT", "77")
    monkeypatch.setenv("TRS_GRAPH_BUSINESS_BASE_URL", "http://business:8095")
    settings = business_plane_settings("dev2")
    assert settings is not None
    assert settings.base_url == "http://business:8095"
    assert settings.space == "dev2"  # 未设 BUSINESS_SPACE → 沿用请求空间
    assert settings.api_key == "platform-key"
    assert settings.timeout == 77
    monkeypatch.setenv("TRS_GRAPH_BUSINESS_SPACE", "dev")
    monkeypatch.setenv("TRS_GRAPH_BUSINESS_API_KEY", "business-key")
    monkeypatch.setenv("TRS_GRAPH_BUSINESS_TIMEOUT", "120")
    mapped = business_plane_settings("dev2")
    assert mapped is not None
    assert (mapped.space, mapped.api_key, mapped.timeout) == ("dev", "business-key", 120)
    # 请求空间缺省时落到平台空间
    assert business_plane_settings().space == "dev"


def test_get_trs_graph_client_routes_business_plane(monkeypatch):
    monkeypatch.setattr(TRSGraphClient, "connect", lambda self: None)
    monkeypatch.setattr(TRSGraphClient, "is_connected", lambda self: True)
    monkeypatch.setenv("TRS_GRAPH_BASE_URL", "http://platform")
    monkeypatch.setenv("TRS_GRAPH_SPACE", "dev")
    monkeypatch.setenv("TRS_GRAPH_API_KEY", "")
    monkeypatch.setenv("TRS_GRAPH_BUSINESS_BASE_URL", "http://business:8095")
    monkeypatch.setenv("TRS_GRAPH_BUSINESS_SPACE", "dev")
    close_space_clients()
    business_token = business_data_plane.set(True)
    space_token = selected_graph_space.set("dev2")
    try:
        client = get_trs_graph_client()
        assert client._settings.base_url == "http://business:8095"  # noqa: SLF001
        assert client._settings.space == "dev"  # noqa: SLF001
        assert get_trs_graph_client() is client  # 同连接同空间复用缓存
    finally:
        selected_graph_space.reset(space_token)
        business_data_plane.reset(business_token)
    close_space_clients()
    # 平台请求（未置位）仍走平台面连接
    platform_token = selected_graph_space.set("dev2")
    try:
        platform = get_trs_graph_client()
        assert platform._settings.base_url == "http://platform"  # noqa: SLF001
        assert platform._settings.space == "dev2"  # noqa: SLF001
    finally:
        selected_graph_space.reset(platform_token)
    close_space_clients()


def test_business_plane_unset_keeps_platform_client(monkeypatch):
    monkeypatch.setattr(TRSGraphClient, "connect", lambda self: None)
    monkeypatch.setattr(TRSGraphClient, "is_connected", lambda self: True)
    monkeypatch.setenv("TRS_GRAPH_BASE_URL", "http://platform")
    monkeypatch.setenv("TRS_GRAPH_SPACE", "dev")
    monkeypatch.delenv("TRS_GRAPH_BUSINESS_BASE_URL", raising=False)
    close_space_clients()
    business_token = business_data_plane.set(True)
    space_token = selected_graph_space.set("dev2")
    try:
        # 业务面未配置 → 返回的即是平台面 get_space_client(dev2) 同一实例
        assert get_trs_graph_client() is graph_pkg.get_space_client("dev2")
    finally:
        selected_graph_space.reset(space_token)
        business_data_plane.reset(business_token)
    close_space_clients()
