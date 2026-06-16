"""实体对齐与实体消歧 HTTP 接口。"""

from typing import Annotated

from fastapi import APIRouter, Body

from app.schemas.entity_linking import EntityAlignmentRequest, EntityDisambiguationRequest
from app.services.entity_alignment import align_knowledge_graphs
from app.services.entity_disambiguation import disambiguate_entity

router = APIRouter(prefix="/entity", tags=["实体对齐与消歧"])

_ALIGNMENT_OPENAPI_EXAMPLES = {
    "builtin_top_k": {
        "summary": "使用内置图谱（推荐）",
        "description": "不传 kg_a/kg_b，仅指定 top_k；服务端使用内置中英文示例数据。",
        "value": {"top_k": 3},
    },
    "empty_body": {
        "summary": "空 JSON {}，全部默认",
        "description": "top_k 默认为 3，kg_a/kg_b 使用内置数据。",
        "value": {},
    },
    "empty_lists": {
        "summary": "空列表表示使用内置",
        "description": "kg_a/kg_b 为 [] 时与内置示例图谱等价。",
        "value": {"kg_a": [], "kg_b": [], "top_k": 3},
    },
}

_DISAMBIGUATION_OPENAPI_EXAMPLES = {
    "apple_company": {
        "summary": "苹果 → 科技公司（内置 KB）",
        "description": "不传 kb，使用内置知识库。",
        "value": {
            "text": "苹果今天在发布会上推出了新款iPhone 16。",
            "mention": "苹果",
            "top_k": 5,
        },
    },
    "apple_fruit": {
        "summary": "苹果 → 水果",
        "value": {
            "text": "营养专家建议每天吃一个苹果，其中的膳食纤维有助于消化。",
            "mention": "苹果",
            "top_k": 5,
        },
    },
    "builtin_kb_explicit_null": {
        "summary": "显式 null kb（等同内置）",
        "value": {
            "text": "苹果今天在发布会上推出了新款iPhone 16。",
            "mention": "苹果",
            "kb": None,
            "top_k": 5,
        },
    },
    "empty_kb_array": {
        "summary": "kb 为空数组（等同内置）",
        "value": {
            "text": "苹果今天在发布会上推出了新款iPhone 16。",
            "mention": "苹果",
            "kb": [],
            "top_k": 5,
        },
    },
}


@router.post("/alignment")
def run_alignment(
    body: Annotated[
        EntityAlignmentRequest,
        Body(openapi_examples=_ALIGNMENT_OPENAPI_EXAMPLES),
    ],
) -> dict:
    """
    双知识图谱实体对齐：召回 → 精排 → 规则裁决。
    省略 `kg_a` / `kg_b`、或传入空列表 `[]` 时，使用项目内置中英文示例数据。
    """
    return align_knowledge_graphs(body.kg_a, body.kg_b, top_k=body.top_k)


@router.post("/disambiguation")
def run_disambiguation(
    body: Annotated[
        EntityDisambiguationRequest,
        Body(openapi_examples=_DISAMBIGUATION_OPENAPI_EXAMPLES),
    ],
) -> dict:
    """
    实体消歧 / 实体链接：给定句子与 mention，链接到知识库实体或 Nil。
    省略 `kb`、或传入空列表 `[]` 时，使用项目内置歧义知识库。
    """
    return disambiguate_entity(body.text, body.mention, body.kb, top_k=body.top_k)
