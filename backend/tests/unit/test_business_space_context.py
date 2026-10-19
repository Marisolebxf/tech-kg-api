"""Request concurrency, cached responses and SQL annotations must not cross spaces."""

import asyncio
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from service.graph_space_context import get_current_space, selected_graph_space


async def test_context_flows_to_worker_and_child_task_without_cross_request_leak():
    async def request(space):
        token = selected_graph_space.set(space)
        try:
            await asyncio.sleep(0)
            child = asyncio.create_task(asyncio.to_thread(get_current_space))
            return await child
        finally:
            selected_graph_space.reset(token)

    assert await asyncio.gather(request("dev"), request("business-a")) == ["dev", "business-a"]
    assert selected_graph_space.get() is None


def test_default_graph_factory_routes_without_mutating_singleton(monkeypatch):
    from infra import graph_db

    default = object()
    monkeypatch.setattr(graph_db, "_client", default)
    monkeypatch.setattr(graph_db, "get_space_client", lambda space: ("client", space))
    token = selected_graph_space.set("business-a")
    try:
        assert graph_db.get_trs_graph_client() == ("client", "business-a")
        assert graph_db._client is default
    finally:
        selected_graph_space.reset(token)
    assert graph_db.get_trs_graph_client() is default


def test_serialized_result_cache_is_partitioned_and_invalidation_is_local():
    from infra.result_cache import clear, discard_prefix, get_cached_json, set_cached_json

    clear()
    token = selected_graph_space.set("dev")
    try:
        set_cached_json("/query?x=1", "public")
        selected_graph_space.set("business-a")
        assert get_cached_json("/query?x=1") is None
        set_cached_json("/query?x=1", "private")
        discard_prefix("/query")
        assert get_cached_json("/query?x=1") is None
        selected_graph_space.set("dev")
        assert get_cached_json("/query?x=1") == "public"
    finally:
        selected_graph_space.reset(token)
        clear()


async def test_graph_api_omitted_space_uses_current_space_for_get_and_post():
    from infra.graph_api_client import GraphAPIClient

    seen = []

    def respond(request):
        seen.append(request.url.params["space"])
        return httpx.Response(200, json={"success": True, "data": {"items": []}})

    token = selected_graph_space.set("business-b")
    try:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(respond), base_url="http://test"
        ) as client:
            graph = GraphAPIClient(client)
            await graph.list_nodes(label="Person")
            await graph.search_nodes(label="Person", properties={"name": "same"})
        assert seen == ["business-b", "business-b"]
    finally:
        selected_graph_space.reset(token)


def test_annotation_same_vids_are_separate_and_legacy_rows_are_not_exposed():
    from db_model.indirect_relation_annotation import (
        IndirectRelationAnnotation,
        SpaceIndirectRelationAnnotation,
    )
    from service.indirect_relation_annotation import IndirectRelationAnnotationService

    engine = create_engine("sqlite://")
    IndirectRelationAnnotation.__table__.create(engine)
    SpaceIndirectRelationAnnotation.__table__.create(engine)
    token = selected_graph_space.set("dev")
    try:
        with Session(engine) as session:
            session.add(
                IndirectRelationAnnotation(source_vid="a", target_vid="b", annotation="legacy")
            )
            session.commit()
            public = IndirectRelationAnnotationService(session)
            assert public.list_annotations([("a", "b")]) == []
            public.upsert_annotation("a", "b", "public")
            selected_graph_space.set("business-a")
            private = IndirectRelationAnnotationService(session)
            assert private.list_annotations([("a", "b")]) == []
            private.upsert_annotation("b", "a", "private")
            assert private.list_annotations([("a", "b")])[0]["annotation"] == "private"
            assert public.list_annotations([("a", "b")])[0]["annotation"] == "public"
            assert session.get(IndirectRelationAnnotation, ("a", "b")).annotation == "legacy"
    finally:
        selected_graph_space.reset(token)
        engine.dispose()


def test_sql_enterprise_enrichment_requires_selected_graph_entity(monkeypatch):
    from service import enterprise_background_analysis as module

    monkeypatch.setattr(module, "has_graph_entity", lambda *args: False)
    monkeypatch.setattr(module, "get_gkx_session", lambda: pytest.fail("SQL must not run"))
    with pytest.raises(KeyError, match="当前图空间"):
        module.EnterpriseBackgroundAnalysisService().analyze({"enterpriseId": "outside"})


def test_options_never_fall_back_to_global_sql(monkeypatch):
    from service import kg_options

    monkeypatch.setattr(
        kg_options,
        "get_trs_graph_client",
        lambda: SimpleNamespace(
            find_nodes=lambda *args, **kwargs: SimpleNamespace(items=[]),
            get_edges_by_type=lambda *args, **kwargs: SimpleNamespace(items=[]),
        ),
    )
    monkeypatch.setattr(
        "sqlalchemy.orm.Session.execute", lambda *args, **kwargs: pytest.fail("不能回退到全库查询")
    )
    options = kg_options.get_options()
    assert options["scholars"] == options["enterprises"] == options["edges"] == []


@pytest.mark.parametrize("writable", [False, True])
def test_alumni_hidden_persistence_requires_request_write_capability(monkeypatch, writable):
    from application.expert_alumni_relation import ExpertAlumniRelationApplication
    from service.graph_space_context import request_can_write

    app = ExpertAlumniRelationApplication()
    monkeypatch.setattr(app._service, "query", lambda **kwargs: {"items": []})
    writes = []
    monkeypatch.setattr(
        app, "_persist_relations", lambda data: writes.append(data) or {"created": 1}
    )
    token = request_can_write.set(writable)
    try:
        result = app.query(expert_id="same-vid")
        assert len(writes) == int(writable)
        if not writable:
            assert result["persistence"]["readOnly"] is True
    finally:
        request_can_write.reset(token)


@pytest.mark.parametrize("writable", [False, True])
def test_confidence_display_does_not_implicitly_write_for_readonly_user(monkeypatch, writable):
    from service import entity_confidence
    from service.graph_space_context import request_can_write

    writes = []
    monkeypatch.setattr(
        entity_confidence, "persist_entity_confidence", lambda *args: writes.append(args)
    )
    token = request_can_write.set(writable)
    try:
        value = entity_confidence.fill_entity_confidence(
            {"name": "A"}, ["Person"], vid="same", client=object()
        )
        assert value > 0
        assert len(writes) == int(writable)
    finally:
        request_can_write.reset(token)


def test_patent_distribution_counts_only_current_space_patents(monkeypatch):
    from service import enterprise_background_analysis as module

    dao = SimpleNamespace(
        list_by_assignee=lambda name: [
            SimpleNamespace(patent_id="inside"),
            SimpleNamespace(patent_id="outside"),
        ],
        _cpc_codes=lambda row: ["G06N", "G06F"],
    )
    monkeypatch.setattr(module, "has_graph_entity", lambda vid, *args: vid == "inside")
    assert module.EnterpriseBackgroundAnalysisService()._patent_distribution(dao, "same org") == [
        {"cpcSection": "G", "count": 1}
    ]


async def test_business_dependency_scopes_readonly_access_and_restores_context(monkeypatch):
    from fastapi import HTTPException, Request

    from biz.router.register import require_business_data
    from service import business_access_control
    from service.graph_space_context import request_can_write

    checked = []

    def ensure(actor, space, action):
        checked.append((space, action))
        if action == "write":
            raise HTTPException(403, "readonly")

    monkeypatch.setattr(business_access_control, "ensure_space_access", ensure)
    monkeypatch.setattr(business_access_control, "rbac_enabled", lambda: True)
    monkeypatch.setattr("service.llm_context.request_llm_business", lambda actor, space: "b")
    request = Request(
        {"type": "http", "query_string": b"", "headers": [(b"x-graph-space", b"dev2")]}
    )
    dep = require_business_data(request, SimpleNamespace(is_admin=False))
    await anext(dep)
    try:
        assert get_current_space() == "dev2"
        assert request_can_write.get() is False
        assert await asyncio.to_thread(get_current_space) == "dev2"
    finally:
        await dep.aclose()
    assert selected_graph_space.get() is None
    assert checked == [("dev2", "read"), ("dev2", "write")]


@pytest.mark.parametrize("machine", [False, True])
async def test_project_machine_key_cannot_select_private_space(monkeypatch, machine):
    from fastapi import Request

    from biz.dependencies.project_relation_auth import project_relation_space
    from service.external_api_client import ExternalClientIdentity
    from service.platform_access import PlatformActor

    monkeypatch.setenv("TRS_GRAPH_SPACE", "dev")
    identity = (
        ExternalClientIdentity("partner") if machine else PlatformActor("u", "u", "u", "", False)
    )
    req = Request(
        {"type": "http", "query_string": b"", "headers": [(b"x-graph-space", b"business_a")]}
    )
    dependency = project_relation_space(req, identity)
    assert await anext(dependency) is identity
    try:
        assert get_current_space() == ("dev" if machine else "business_a")
    finally:
        await dependency.aclose()
    assert selected_graph_space.get() is None


@pytest.mark.parametrize(
    "headers,query,body",
    [
        ([(b"x-graph-space", b"dev"), (b"x-graph-space", b"dev2")], b"", None),
        ([(b"x-graph-space", b"dev"), (b"x-graph-space", b"dev")], b"", None),
        ([(b"x-graph-space", b"../dev")], b"", None),
        ([(b"x-graph-space", b"dev")], b"space=dev2", None),
        ([(b"x-graph-space", b"dev")], b"", {"graphSpace": "dev2"}),
        ([], b"", {"space": 123}),
    ],
)
async def test_selector_parser_rejects_ambiguous_or_invalid_selection(headers, query, body):
    import json

    from fastapi import HTTPException, Request

    from biz.dependencies.selected_graph_space import read_request_graph_space

    payload = json.dumps(body).encode()
    if body is not None:
        headers = [*headers, (b"content-type", b"application/json")]

    async def receive():
        return {"type": "http.request", "body": payload, "more_body": False}

    req = Request({"type": "http", "query_string": query, "headers": headers}, receive)
    with pytest.raises(HTTPException) as error:
        await read_request_graph_space(req)
    assert error.value.status_code == 400


async def test_selector_parser_supports_legacy_call_and_matching_explicit_params():
    from fastapi import Request

    from biz.dependencies.selected_graph_space import read_request_graph_space

    assert await read_request_graph_space(None) is None
    req = Request(
        {
            "type": "http",
            "query_string": b"space=dev2&graphSpace=dev2",
            "headers": [(b"x-graph-space", b"dev2")],
        }
    )
    assert await read_request_graph_space(req) == "dev2"


@pytest.mark.parametrize(
    "visibility,allowed", [("public", True), ("unassigned", False), ("business", False)]
)
def test_machine_default_public_permission_honors_new_overlay(monkeypatch, visibility, allowed):
    from contextlib import contextmanager

    from fastapi import HTTPException

    from biz.dependencies.project_relation_auth import _ensure_external_shared_space
    from db_model.business_access import BusinessClient, BusinessGraphSpace, BusinessSpacePolicy

    engine = create_engine("sqlite://")
    for model in (BusinessClient, BusinessGraphSpace, BusinessSpacePolicy):
        model.__table__.create(engine)
    with Session(engine) as session:
        session.add(BusinessClient(client_id="owner", name="owner"))
        session.add(BusinessGraphSpace(space_name="dev", is_shared_production=True))
        session.add(
            BusinessSpacePolicy(
                space_name="dev",
                visibility=visibility,
                client_id="owner" if visibility == "business" else None,
            )
        )
        session.commit()

    @contextmanager
    def session_scope():
        with Session(engine) as session:
            yield session

    monkeypatch.setattr("infra.mysql.session_scope", session_scope)
    monkeypatch.setenv("BUSINESS_RBAC_ENABLED", "true")
    monkeypatch.setenv("TRS_GRAPH_SPACE", "dev")
    try:
        if allowed:
            _ensure_external_shared_space()
        else:
            with pytest.raises(HTTPException) as error:
                _ensure_external_shared_space()
            assert error.value.status_code == 403
    finally:
        engine.dispose()


async def test_panorama_background_rebuild_keeps_original_request_space(monkeypatch):
    from service.industry_chain_panorama import IndustryChainPanoramaService, _panorama_rebuilding

    service = IndustryChainPanoramaService()
    release, done = asyncio.Event(), asyncio.Event()
    observed = []

    async def query(**kwargs):
        await release.wait()
        observed.append(get_current_space())
        done.set()

    monkeypatch.setattr(service, "query", query)
    key = ("business_a", "industry", "", 1, 1, "")
    token = selected_graph_space.set("business_a")
    try:
        service._rebuild_in_background(key, industry="industry", anchor_id=None, depth=1, top_k=1)
    finally:
        selected_graph_space.reset(token)
    second = selected_graph_space.set("dev2")
    try:
        release.set()
        await asyncio.wait_for(done.wait(), timeout=2)
        assert observed == ["business_a"]
        assert get_current_space() == "dev2"
        assert key not in _panorama_rebuilding
    finally:
        selected_graph_space.reset(second)


async def test_internal_prewarm_cannot_trigger_admin_write_side_effects(monkeypatch):
    from fastapi import Request

    from biz.prewarm_business import _readonly_prewarm_app
    from biz.router.register import require_business_data
    from service import business_access_control
    from service.graph_space_context import request_can_write

    monkeypatch.setattr(business_access_control, "rbac_enabled", lambda: False)
    monkeypatch.setattr(business_access_control, "ensure_space_access", lambda *args: None)
    observed = []

    async def app(scope, receive, send):
        req = Request(scope)
        dep = require_business_data(req, SimpleNamespace(is_admin=True, business_only=False))
        await anext(dep)
        try:
            observed.append(request_can_write.get())
        finally:
            await dep.aclose()

    await _readonly_prewarm_app(app)(
        {"type": "http", "query_string": b"", "headers": []}, None, None
    )
    assert observed == [False]


def test_readonly_and_writable_http_cached_results_are_separate():
    from infra.result_cache import clear, get_cached_json, set_cached_json
    from service.graph_space_context import request_can_write

    clear()
    token = selected_graph_space.set("dev")
    write_token = request_can_write.set(False)
    try:
        set_cached_json("same-query", "read-result")
        request_can_write.set(True)
        assert get_cached_json("same-query") is None
        set_cached_json("same-query", "write-result")
        request_can_write.set(False)
        assert get_cached_json("same-query") == "read-result"
    finally:
        request_can_write.reset(write_token)
        selected_graph_space.reset(token)
        clear()


@pytest.mark.parametrize(
    "flag,business_env,selected,expected",
    [
        # 业务面置位 + 配置了 TRS_GRAPH_BUSINESS_*：实际取数空间是业务面空间，
        # 不随请求空间（前端下拉）变化
        (True, True, "test1012", "dev"),
        # 未置位（平台管理面）：跟随请求空间
        (False, True, "test1012", "test1012"),
        # 置位但未配置业务面变量（其他栈默认）：沿用请求空间，行为不变
        (True, False, "test1012", "test1012"),
        # 未选中空间时回退 .env 默认空间
        (False, False, None, "dev"),
    ],
)
def test_effective_graph_space_follows_business_plane(
    monkeypatch, flag, business_env, selected, expected
):
    from service.graph_space_context import effective_graph_space

    monkeypatch.setenv("TRS_GRAPH_SPACE", "dev")
    monkeypatch.delenv("TRS_GRAPH_BUSINESS_BASE_URL", raising=False)
    monkeypatch.delenv("TRS_GRAPH_BUSINESS_SPACE", raising=False)
    if business_env:
        monkeypatch.setenv("TRS_GRAPH_BUSINESS_BASE_URL", "http://biz:8090")
        monkeypatch.setenv("TRS_GRAPH_BUSINESS_SPACE", "dev")
    from service.graph_space_context import business_data_plane

    space_token = selected_graph_space.set(selected) if selected is not None else None
    biz_token = business_data_plane.set(True) if flag else None
    try:
        assert effective_graph_space() == expected
    finally:
        if biz_token is not None:
            business_data_plane.reset(biz_token)
        if space_token is not None:
            selected_graph_space.reset(space_token)


@pytest.mark.parametrize("flag", [False, True])
def test_graph_search_get_client_prefers_business_plane_on_loopback(monkeypatch, flag):
    """九大业务进程内回环带显式 space 参数时，取数连接仍须走业务面。

    回环（graph_api / GraphSearchApiClient）总是携带 space=<请求空间> 查询参数，
    修复前 _get_client(space) 直接 get_space_client(space)，绕过 business_data_plane
    判断，导致产业链全景等回环型模块跟着前端空间下拉取数。
    """
    from biz.handler import graph_search
    from service.graph_space_context import business_data_plane

    monkeypatch.setenv("TRS_GRAPH_BUSINESS_BASE_URL", "http://biz:8090")
    monkeypatch.setenv("TRS_GRAPH_BUSINESS_SPACE", "dev")
    calls = []
    monkeypatch.setattr(
        graph_search,
        "get_business_space_client",
        lambda request_space: (
            calls.append(("business", request_space)) or ("business-client", "dev")
        ),
    )
    platform_calls = []
    monkeypatch.setattr(
        graph_search,
        "get_space_client",
        lambda space: platform_calls.append(space) or ("platform-client", space),
    )
    token = selected_graph_space.set("test1012")
    biz_token = business_data_plane.set(flag)
    try:
        client = graph_search._get_client("test1012")
        if flag:
            assert client == ("business-client", "dev")
            assert calls == [("business", "test1012")]
            assert platform_calls == []
        else:
            assert client == ("platform-client", "test1012")
            assert calls == []
            assert platform_calls == ["test1012"]
    finally:
        business_data_plane.reset(biz_token)
        selected_graph_space.reset(token)
