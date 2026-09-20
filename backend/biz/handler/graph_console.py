"""nGQL 控制台 API：登录用户可执行只读语句，平台管理员另可执行写语句，DDL 一律禁止。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field

from biz.dependencies.auth import CurrentActor
from service.graph_console import GraphConsoleError, run_statement_cached_payload

router = APIRouter(prefix="/graph-console", tags=["graph-console"])


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
