"""Server-owned account scope for the nine business modules.

Match registered route templates and methods, never user-controlled prefixes or headers.
The two business analyzers may use graph APIs internally without exposing those APIs
to restricted browser/API clients.
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
