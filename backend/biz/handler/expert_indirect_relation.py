import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from application.expert_indirect_relation import ExpertIndirectRelationApplication
from biz.dependencies.internal_api import get_internal_api_auth_headers
from biz.schema.expert_indirect_relation import (
    ExpertIndirectRelationRequest,
    ExpertIndirectRelationResponse,
)
from infra.result_cache import get_cached_json, set_cached_json

router = APIRouter(prefix="/kg-construction/expert-indirect-relations")
application = ExpertIndirectRelationApplication()


@router.get("")
async def describe_expert_indirect_relation() -> dict[str, object]:
    return application.describe()


@router.post("/demo/structured-result", responses={404: {"description": "请求的资源不存在"}, 500: {"description": "服务内部错误"}})
async def analyze_expert_indirect_relation(
    body: ExpertIndirectRelationRequest,
    request: Request,
) -> Response:
    """单节点间接关系：命中预序列化 JSON 跳过 ASGITransport 自调用 + Milvus 路径分析，
    避免 500 并发下的超时（路径分析+Milvus 是重负载，缓存命中后零开销）。"""
    key = json.dumps(body.model_dump(), ensure_ascii=False, sort_keys=True)
    cached = get_cached_json(key)
    if cached is not None:
        return Response(content=cached, media_type="application/json")
    try:
        result = await application.build_structured_result_only(
            body,
            auth_headers=get_internal_api_auth_headers(request),
            app=request.app,
        )
        body_json = json.dumps(
            ExpertIndirectRelationResponse(**result).model_dump(), ensure_ascii=False
        )
        set_cached_json(key, body_json)
        return Response(content=body_json, media_type="application/json")
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail=f"科技单节点间接关系分析失败: {exc}",
        ) from exc
