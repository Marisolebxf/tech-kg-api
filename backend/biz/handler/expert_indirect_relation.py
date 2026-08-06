from fastapi import APIRouter, HTTPException

from application.expert_indirect_relation import ExpertIndirectRelationApplication
from biz.schema.expert_indirect_relation import (
    ExpertIndirectRelationRequest,
    ExpertIndirectRelationResponse,
)

router = APIRouter(prefix="/kg-construction/expert-indirect-relations")
application = ExpertIndirectRelationApplication()


@router.get("")
async def describe_expert_indirect_relation() -> dict[str, object]:
    return application.describe()


@router.post(
    "/demo/structured-result",
    response_model=ExpertIndirectRelationResponse,
)
async def analyze_expert_indirect_relation(
    body: ExpertIndirectRelationRequest,
) -> ExpertIndirectRelationResponse:
    try:
        result = await application.build_structured_result_only(body)
        return ExpertIndirectRelationResponse(**result)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"科技单节点间接关系分析失败: {exc}",
        ) from exc
