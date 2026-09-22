"""Server-owned account scope for the nine business modules.

Match registered route templates and methods, never user-controlled prefixes or headers.
Business analyzers that self-call graph APIs in-process (indirect / paper-cooperation /
key-enterprise-relation / colleague) wrap the app with business_graph_app so the internal
marker lets those calls through without exposing the graph APIs to restricted clients.
"""

from __future__ import annotations

from fastapi import HTTPException, Request

_PREFIX = "/api/v1"
_INTERNAL_SCOPE_KEY = "techkg.business_graph_call"
_INTERNAL_MARKER = object()

_BUSINESS_QUERIES = {
    "/kg-construction/expert-direct-relations/query",
    "/kg-construction/expert-indirect-relations/demo/structured-result",
    "/kg-construction/expert-cooperation-achievements/query",
    "/kg-service/expert-colleague-relation",
    "/kg-construction/expert-alumni-relations/query",
    "/kg-construction/expert-paper-cooperation-relations/structured-result",
    "/kg-service/key-enterprise-relation",
    "/kg-service/industry-node-top-events",
    "/kg-construction/industry-chain-panorama/query",
}
_READ_DEPENDENCIES = {
    "/auth/me",
    "/auth/permissions",
    "/auth/security",
    "/auth/operation-logs",
    "/graph-search/spaces",
    "/kg-construction/options",
    "/kg-construction/expert-direct-relations",
    "/kg-construction/expert-indirect-relations",
    "/kg-construction/expert-cooperation-achievements",
    "/kg-construction/expert-colleague-relations",
    "/kg-construction/expert-alumni-relations",
    "/kg-construction/expert-paper-cooperation-relations",
    "/kg-construction/industry-chain-topn-event-relations",
    "/kg-construction/industry-chain-panorama",
}
_INTERNAL_GRAPH_ROUTES = {
    ("GET", "/graph-search/nodes/{node_id:path}"),
    ("GET", "/graph-search/subgraph/{node_id:path}"),
    ("POST", "/graph-search/paths/search"),
    # 重点关注科技企业关系（filtered-subgraph 取治理/合作边）与专家同事关系
    # （nodes/search 按 Person 属性定位专家）的内部自调用路径
    ("GET", "/graph-search/filtered-subgraph/{node_id}"),
    ("POST", "/graph-search/nodes/search"),
    # 产业链全景图（graph_api 回环）：无属性索引时按标签翻页扫描用 nodes 集合路由；
    # 专家直接关系（graph_api 回环）取专家的合作/任职边
    ("GET", "/graph-search/nodes"),
    ("GET", "/graph-search/node/{node_id}/edges"),
}


def enforce_business_access(request: Request) -> None:
    route = request.scope.get("route")
    path = getattr(route, "path", "")
    # FastAPI stores the actual matched template, including the API prefix.
    if not path.startswith(_PREFIX + "/"):
        raise HTTPException(403, "当前账号仅可使用九大业务模块")
    path = path[len(_PREFIX) :]
    method = request.method
    allowed = (
        (method in {"GET", "POST"} and path in _BUSINESS_QUERIES)
        or (method == "GET" and path in _READ_DEPENDENCIES)
        or (method == "POST" and path in {"/auth/refresh", "/auth/logout"})
        or (
            request.scope.get(_INTERNAL_SCOPE_KEY) is _INTERNAL_MARKER
            and (method, path) in _INTERNAL_GRAPH_ROUTES
        )
    )
    if not allowed:
        raise HTTPException(403, "当前账号仅可使用九大业务模块")


def business_graph_app(app):
    """Wrap only in-process business graph calls; credentials are still authenticated."""

    async def wrapped(scope, receive, send):
        scope = {**scope, _INTERNAL_SCOPE_KEY: _INTERNAL_MARKER}
        await app(scope, receive, send)

    return wrapped
