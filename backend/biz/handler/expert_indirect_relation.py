import json
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from application.expert_indirect_relation import ExpertIndirectRelationApplication
from biz.dependencies.default_space_write import require_default_annotation_writer
from biz.dependencies.internal_api import get_internal_api_auth_headers
from biz.schema.expert_indirect_relation import (
    ExpertIndirectRelationRequest,
    ExpertIndirectRelationResponse,
)
from biz.schema.indirect_relation_annotation import (
    IndirectRelationAnnotationList,
    IndirectRelationAnnotationRequest,
    annotation_item,
)
from biz.schemas.common import ApiResponse
from infra.mysql import get_session
from infra.result_cache import get_cached_json, set_cached_json
from service.indirect_relation_annotation import IndirectRelationAnnotationService

router = APIRouter(prefix="/kg-construction/expert-indirect-relations")
application = ExpertIndirectRelationApplication()
logger = logging.getLogger(__name__)

# 批量查询边数量上限：一次查询最多返回 50 条路径 × 每条 3 跳，200 足够且防滥用。
MAX_ANNOTATION_EDGE_KEYS = 200
# GET 边参数：逗号分隔的 sourceVid:targetVid 列表；VID 字符集外加两个分隔符。
EDGE_PAIRS_QUERY_PATTERN = r"^[\w一-鿿·.\-:,]*$"


@router.get("")
async def describe_expert_indirect_relation() -> dict[str, object]:
    return application.describe()


@router.post(
    "/demo/structured-result",
    responses={404: {"description": "请求的资源不存在"}, 500: {"description": "服务内部错误"}},
)
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
        logger.exception("科技单节点间接关系分析失败")
        raise HTTPException(
            status_code=500,
            detail="科技单节点间接关系分析失败",
        ) from exc


def _parse_edge_pairs(raw: str) -> list[tuple[str, str]]:
    """解析逗号分隔的 sourceVid:targetVid 列表；格式非法时抛 422。"""
    keys: list[tuple[str, str]] = []
    for item in (part.strip() for part in raw.split(",")):
        if not item:
            continue
        source, separator, target = item.partition(":")
        if not separator or not source or not target:
            raise HTTPException(
                status_code=422,
                detail=f"边参数格式应为 sourceVid:targetVid，收到：{item}",
            )
        keys.append(IndirectRelationAnnotationService.normalize_key(source.strip(), target.strip()))
    if len(keys) > MAX_ANNOTATION_EDGE_KEYS:
        raise HTTPException(
            status_code=422,
            detail=f"单次最多查询 {MAX_ANNOTATION_EDGE_KEYS} 条边的标注",
        )
    return keys


@router.get("/annotations")
def list_indirect_relation_annotations(
    session: Annotated[Session, Depends(get_session)],
    edges: Annotated[
        str | None,
        Query(
            max_length=16384,
            pattern=EDGE_PAIRS_QUERY_PATTERN,
            description="逗号分隔的边主键列表（sourceVid:targetVid）",
        ),
    ] = None,
) -> ApiResponse:
    """按边主键批量查询关系标注；查不到数据的关系即无标注，前端展示为空。"""
    service = IndirectRelationAnnotationService(session)
    items = service.list_annotations(_parse_edge_pairs(edges or ""))
    return ApiResponse(
        data=IndirectRelationAnnotationList(items=[annotation_item(item) for item in items])
    )


@router.post("/annotations", dependencies=[Depends(require_default_annotation_writer)])
def upsert_indirect_relation_annotation(
    body: IndirectRelationAnnotationRequest,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    """保存关系标注：按边主键（两端节点 VID）upsert 到业务库，不写图数据库。"""
    service = IndirectRelationAnnotationService(session)
    item = service.upsert_annotation(body.sourceVid, body.targetVid, body.annotation)
    return ApiResponse(data=annotation_item(item), msg="关系标注已保存")
