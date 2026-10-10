"""将浏览器选择固定在单个请求中，并拒绝互相冲突的空间参数。"""

from collections.abc import AsyncIterator

from fastapi import HTTPException, Request

from biz.dependencies.auth import CurrentActor
from service.graph_space_context import selected_graph_space


def resolve_selected_space(space: str | None = None) -> str | None:
    selected = selected_graph_space.get()
    if selected and space and selected != space:
        raise HTTPException(400, "请求图空间与当前选择不一致，请刷新后重试")
    return space or selected


async def read_request_graph_space(request: Request | None) -> str | None:
    """Parse all supported selectors before auth; duplicate/conflicting values fail closed."""
    if request is None:
        return None
    from service.graph_space import SPACE_NAME_PATTERN

    headers = request.headers.getlist("X-Graph-Space")
    if len(headers) > 1:
        raise HTTPException(400, "请提供唯一的 X-Graph-Space")
    values = list(headers)
    values.extend(request.query_params.getlist("space"))
    values.extend(request.query_params.getlist("graphSpace"))
    if (
        request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        == "application/json"
    ):
        try:
            body = await request.json()
        except ValueError:
            body = None  # Original endpoint still validates malformed JSON.
        if isinstance(body, dict):
            values.extend([body.get("space"), body.get("graphSpace")])
    spaces = set()
    for value in values:
        if value is None or value == "":
            continue
        if not isinstance(value, str) or not SPACE_NAME_PATTERN.fullmatch(value):
            raise HTTPException(400, "图空间名称格式不正确")
        spaces.add(value)
    if len(spaces) > 1:
        raise HTTPException(400, "请求图空间与当前选择不一致，请刷新后重试")
    return next(iter(spaces), None)


async def bind_selected_graph_space(request: Request, actor: CurrentActor) -> AsyncIterator[None]:
    # 空间目录本身不能依赖已经选中一个空间，否则首次登录和权限收回后无法恢复。
    if request.url.path.rstrip("/").endswith("/graph-search/spaces"):
        yield
        return
    space = await read_request_graph_space(request)
    if space:
        from biz.handler.graph_search import _ensure_space_access

        _ensure_space_access(actor, space)
    token = selected_graph_space.set(space)
    try:
        yield
    finally:
        selected_graph_space.reset(token)
