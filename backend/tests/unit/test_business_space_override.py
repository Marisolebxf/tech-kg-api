"""X-Business-Graph-Space 覆盖头：优先级、缓存隔离、回环重定向与依赖解析。"""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException, Request

from service.graph_space_context import (
    business_data_plane,
    business_space_override,
    get_current_space,
    selected_graph_space,
)


def _set_env(monkeypatch, *, business: bool, pinned: str | None = None) -> None:
    monkeypatch.setenv("TRS_GRAPH_SPACE", "dev")
    if business:
        monkeypatch.setenv("TRS_GRAPH_BUSINESS_BASE_URL", "http://biz:8090")
    else:
        monkeypatch.delenv("TRS_GRAPH_BUSINESS_BASE_URL", raising=False)
    if pinned:
        monkeypatch.setenv("TRS_GRAPH_BUSINESS_SPACE", pinned)
    else:
        monkeypatch.delenv("TRS_GRAPH_BUSINESS_SPACE", raising=False)


@pytest.mark.parametrize(
    "override,pinned,request_space,expected",
    [
        # 无钉死：沿用请求空间（空间下拉语义）
        (None, None, "test1012", "test1012"),
        # env 钉死压过请求空间（现状：dev2 远端映射）
        (None, "dev", "test1012", "dev"),
        # 覆盖头压过 env 钉死与请求空间（本特性的核心语义）
        ("gkx_local_1", "dev", "test1012", "gkx_local_1"),
        ("gkx_local_1", None, "test1012", "gkx_local_1"),
        # 全空回退 TRS_GRAPH_SPACE
        (None, None, None, "dev"),
    ],
)
def test_business_plane_settings_space_priority(
    monkeypatch, override, pinned, request_space, expected
):
    from infra.graph_db.config import business_plane_settings

    _set_env(monkeypatch, business=True, pinned=pinned)
    settings = business_plane_settings(request_space, override)
    assert settings is not None
    assert settings.space == expected
    assert settings.base_url == "http://biz:8090"


def test_business_plane_settings_none_without_business_base_url(monkeypatch):
    from infra.graph_db.config import business_plane_settings

    _set_env(monkeypatch, business=False)
    # 覆盖头不影响「未配置业务面 → 共用平台连接」的开关语义
    assert business_plane_settings("test1012", "gkx_local_1") is None


@pytest.mark.parametrize(
    "override,business_env,flag,expected",
    [
        # 覆盖头无条件优先——即使未配置业务面（平台面栈）也生效
        ("gkx_local_1", False, False, "gkx_local_1"),
        ("gkx_local_1", True, True, "gkx_local_1"),
        # 无覆盖时保持既有三态语义
        (None, True, True, "dev"),
        (None, True, False, "test1012"),
    ],
)
def test_effective_graph_space_override_wins(monkeypatch, override, business_env, flag, expected):
    from service.graph_space_context import effective_graph_space

    _set_env(monkeypatch, business=business_env, pinned="dev" if business_env else None)
    space_token = selected_graph_space.set("test1012")
    biz_token = business_data_plane.set(flag)
    override_token = business_space_override.set(override)
    try:
        assert effective_graph_space() == expected
    finally:
        business_space_override.reset(override_token)
        business_data_plane.reset(biz_token)
        selected_graph_space.reset(space_token)


def test_result_cache_partitioned_by_override():
    from infra.result_cache import clear, get_cached_json, set_cached_json

    clear()
    space_token = selected_graph_space.set("dev2")
    try:
        set_cached_json("same-query", "request-space-result")
        override_token = business_space_override.set("gkx_local_1")
        try:
            # 同请求空间、不同覆盖空间：不得串缓存
            assert get_cached_json("same-query") is None
            set_cached_json("same-query", "override-result")
        finally:
            business_space_override.reset(override_token)
        assert get_cached_json("same-query") == "request-space-result"
    finally:
        selected_graph_space.reset(space_token)
        clear()


def test_get_business_space_client_reads_override_context(monkeypatch):
    from infra import graph_db

    _set_env(monkeypatch, business=True, pinned="dev")
    monkeypatch.setattr(graph_db, "_space_clients", {})
    monkeypatch.setattr(
        graph_db,
        "TRSGraphClient",
        lambda settings: SimpleNamespace(_settings=settings, connect=lambda: None),
    )
    space_token = selected_graph_space.set("test1012")
    override_token = business_space_override.set("gkx_local_1")
    try:
        client = graph_db.get_business_space_client("test1012")
        assert client._settings.space == "gkx_local_1"
        # 缓存 key 按实际空间隔离，请求空间的旧条目不受影响
        assert "business::http://biz:8090::gkx_local_1" in graph_db._space_clients
    finally:
        business_space_override.reset(override_token)
        selected_graph_space.reset(space_token)


def test_default_graph_factory_prefers_override_on_platform_fallback(monkeypatch):
    """未配置业务面的栈：覆盖头也应把平台面连接重定向到覆盖空间。"""

    from infra import graph_db

    _set_env(monkeypatch, business=False)
    monkeypatch.setattr(graph_db, "_client", object())
    calls = []
    monkeypatch.setattr(graph_db, "get_space_client", lambda space: calls.append(space) or object())
    space_token = selected_graph_space.set("dev2")
    override_token = business_space_override.set("gkx_local_1")
    try:
        graph_db.get_trs_graph_client()
        assert calls == ["gkx_local_1"]
    finally:
        business_space_override.reset(override_token)
        selected_graph_space.reset(space_token)


@pytest.mark.parametrize("business_plane", [False, True])
def test_graph_search_get_client_redirects_space_param_to_override(monkeypatch, business_plane):
    """回环 space 参数仍是请求空间（访问校验锚点），实际连接指向覆盖空间。"""

    from biz.handler import graph_search

    _set_env(monkeypatch, business=business_plane, pinned="dev")
    business_calls = []
    monkeypatch.setattr(
        graph_search,
        "get_business_space_client",
        lambda request_space: (
            business_calls.append(request_space) or ("business-client", "gkx_local_1")
        ),
    )
    platform_calls = []
    monkeypatch.setattr(
        graph_search,
        "get_space_client",
        lambda space: platform_calls.append(space) or ("platform-client", space),
    )
    space_token = selected_graph_space.set("dev2")
    biz_token = business_data_plane.set(business_plane)
    override_token = business_space_override.set("gkx_local_1")
    try:
        client = graph_search._get_client("dev2")
        assert client[1] == "gkx_local_1"
        if business_plane:
            assert business_calls == ["gkx_local_1"]
            assert platform_calls == []
        else:
            assert platform_calls == ["gkx_local_1"]
            assert business_calls == []
    finally:
        business_space_override.reset(override_token)
        business_data_plane.reset(biz_token)
        selected_graph_space.reset(space_token)


async def test_business_dependency_parses_override_header(monkeypatch):
    from biz.router.register import require_business_data
    from service import business_access_control

    monkeypatch.setattr(business_access_control, "ensure_space_access", lambda *a: None)
    monkeypatch.setattr(business_access_control, "rbac_enabled", lambda: False)
    monkeypatch.setattr("service.llm_context.request_llm_business", lambda actor, space: "b")
    request = Request(
        {
            "type": "http",
            "query_string": b"",
            "headers": [
                (b"x-graph-space", b"dev2"),
                (b"x-business-graph-space", b"gkx_local_1"),
            ],
        }
    )
    dep = require_business_data(request, SimpleNamespace(is_admin=False))
    await anext(dep)
    try:
        # 请求空间不动（空间绑定校验锚点），覆盖头进独立 ContextVar
        assert get_current_space() == "dev2"
        assert business_space_override.get() == "gkx_local_1"
    finally:
        await dep.aclose()
    assert business_space_override.get() is None


async def test_business_dependency_blank_override_header_means_unset(monkeypatch):
    from biz.router.register import require_business_data
    from service import business_access_control

    monkeypatch.setattr(business_access_control, "ensure_space_access", lambda *a: None)
    monkeypatch.setattr(business_access_control, "rbac_enabled", lambda: False)
    monkeypatch.setattr("service.llm_context.request_llm_business", lambda actor, space: "b")
    request = Request(
        {
            "type": "http",
            "query_string": b"",
            "headers": [(b"x-graph-space", b"dev2"), (b"x-business-graph-space", b"   ")],
        }
    )
    dep = require_business_data(request, SimpleNamespace(is_admin=False))
    await anext(dep)
    try:
        assert business_space_override.get() is None
    finally:
        await dep.aclose()


@pytest.mark.parametrize(
    "headers",
    [
        # 非法字符 / 数字开头 / 超长
        [(b"x-business-graph-space", b"gkx local")],
        [(b"x-business-graph-space", b"1abc")],
        [(b"x-business-graph-space", b"a" * 65)],
        # 重复头
        [
            (b"x-business-graph-space", b"gkx_local_1"),
            (b"x-business-graph-space", b"gkx_local_1"),
        ],
    ],
)
async def test_business_dependency_rejects_invalid_override_header(monkeypatch, headers):
    from biz.router.register import require_business_data
    from service import business_access_control

    monkeypatch.setattr(business_access_control, "ensure_space_access", lambda *a: None)
    monkeypatch.setattr(business_access_control, "rbac_enabled", lambda: False)
    monkeypatch.setattr("service.llm_context.request_llm_business", lambda actor, space: "b")
    request = Request(
        {"type": "http", "query_string": b"", "headers": [(b"x-graph-space", b"dev2"), *headers]}
    )
    dep = require_business_data(request, SimpleNamespace(is_admin=False))
    with pytest.raises(HTTPException) as error:
        await anext(dep)
    assert error.value.status_code == 400
    assert business_space_override.get() is None
