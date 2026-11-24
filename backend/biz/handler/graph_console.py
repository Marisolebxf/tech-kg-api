"""nGQL 控制台 API：登录用户可执行只读语句（普通用户限行数），平台管理员另可执行写语句，DDL 一律禁止。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from biz.dependencies.auth import CurrentActor
from biz.dependencies.selected_graph_space import bind_selected_graph_space
from infra.rate_limit import RateLimit, enforce_rate_limit
from service.graph_console import GraphConsoleError, run_statement_cached_payload


async def _console_rate_limit(actor: CurrentActor) -> None:
    # 按用户限频，重查询循环触发会把共享图库打到内存高水位（渗透 B4）。
    await enforce_rate_limit("graph-console", actor.user_id, RateLimit(60, 60))


router = APIRouter(
    prefix="/graph-console",
    tags=["graph-console"],
    dependencies=[Depends(bind_selected_graph_space), Depends(_console_rate_limit)],
)


class GraphConsoleRequest(BaseModel):
    space: str = Field(min_length=1, max_length=64)
    statement: str = Field(min_length=1, max_length=4000)


@router.post("/query")
def run_ngql(payload: GraphConsoleRequest, actor: CurrentActor) -> Response:
    try:
        body = run_statement_cached_payload(actor, payload.space, payload.statement)
    except GraphConsoleError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return Response(body, media_type="application/json")
