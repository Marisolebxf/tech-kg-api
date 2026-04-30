"""实体抽取 HTTP 接口"""

from fastapi import APIRouter, HTTPException

from app.schemas.entity_extraction import ExtractRequest, ExtractResponse
from app.services.entity_extractor import FOCUS_TYPES, extract

router = APIRouter(prefix="/entity", tags=["实体抽取"])


@router.post("/extraction")
def run_extraction(body: ExtractRequest) -> ExtractResponse:
    """
    从非结构化文本中抽取知识图谱实体。

    - **text**: 待抽取的文本，如工作经历、教育背景、摘要等
    - **source_type**: 文本类型，决定重点识别哪些实体
      - `work`      工作经历 → 机构、职位、时间段
      - `education` 教育背景 → 学校、学位、专业、时间段
      - `abstract`  摘要文本 → 技术领域、机构、基金
      - `general`   通用模式 → 所有实体类型
    """
    if not body.text or not body.text.strip():
        raise HTTPException(status_code=400, detail="text 不能为空")

    if body.source_type not in FOCUS_TYPES:
        raise HTTPException(
            status_code=400, detail=f"source_type 不合法，可选值：{list(FOCUS_TYPES.keys())}"
        )

    entities = extract(body.text, body.source_type)

    return ExtractResponse(
        source_type=body.source_type, entity_count=len(entities), entities=entities
    )
