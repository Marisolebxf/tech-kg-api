"""关系抽取 HTTP 接口。"""

import os
from typing import Annotated

from fastapi import APIRouter, Body

from app.schemas.relation_extraction import (
    BatchRelationExtractionRequest,
    RelationExtractionRequest,
)
from app.services.relation_extraction import (
    batch_extract_relations,
    extract_relations,
)

router = APIRouter(prefix="/relation", tags=["关系抽取"])

_LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
_LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://open.bigmodel.cn/api/paas/v4")
_LLM_MODEL = os.environ.get("LLM_MODEL", "glm-4-flash")

_EXTRACTION_OPENAPI_EXAMPLES = {
    "rule_create": {
        "summary": "规则抽取 - 创立关系",
        "description": "使用规则模式抽取「创立」关系。",
        "value": {
            "text": "马云创立了阿里巴巴集团，阿里巴巴集团位于浙江省杭州市。",
            "method": "rule",
        },
    },
    "rule_multi": {
        "summary": "规则抽取 - 多关系",
        "description": "一段包含多种关系的文本，规则模式可同时抽取。",
        "value": {
            "text": (
                "任正非创立了华为技术有限公司，华为技术有限公司位于广东省深圳市。"
                "孟晚舟担任华为技术有限公司的CFO。"
                "华为技术有限公司推出了鸿蒙操作系统产品。"
            ),
            "method": "rule",
        },
    },
    "hybrid": {
        "summary": "混合抽取（需要 LLM_API_KEY）",
        "description": "规则 + LLM 交叉验证，需要设置 LLM_API_KEY 环境变量。",
        "value": {
            "text": "马斯克创立了特斯拉公司，特斯拉公司位于美国得克萨斯州。",
            "method": "hybrid",
        },
    },
}

_BATCH_EXTRACTION_OPENAPI_EXAMPLES = {
    "two_texts": {
        "summary": "批量抽取两条文本",
        "value": {
            "texts": [
                "马云创立了阿里巴巴集团",
                "任正非创立了华为技术有限公司",
            ],
            "method": "rule",
        },
    },
}


@router.post("/extraction")
def run_extraction(
    body: Annotated[
        RelationExtractionRequest,
        Body(openapi_examples=_EXTRACTION_OPENAPI_EXAMPLES),
    ],
) -> dict:
    """
    从文本中抽取实体与关系三元组。
    支持三种抽取方法：rule（规则匹配）、llm（大模型）、hybrid（混合）。
    """
    return extract_relations(
        text=body.text,
        method=body.method,
        llm_api_key=_LLM_API_KEY or None,
        llm_base_url=_LLM_BASE_URL,
        llm_model=_LLM_MODEL,
    )


@router.post("/extraction/batch")
def run_batch_extraction(
    body: Annotated[
        BatchRelationExtractionRequest,
        Body(openapi_examples=_BATCH_EXTRACTION_OPENAPI_EXAMPLES),
    ],
) -> dict:
    """
    批量从多个文本中抽取实体与关系三元组，合并去重后返回。
    """
    return batch_extract_relations(
        texts=body.texts,
        method=body.method,
        llm_api_key=_LLM_API_KEY or None,
        llm_base_url=_LLM_BASE_URL,
        llm_model=_LLM_MODEL,
    )


@router.get("/examples")
def get_examples() -> list[dict]:
    """获取示例文本列表。"""
    from app.services.relation_extraction import EXAMPLE_TEXTS

    return EXAMPLE_TEXTS
