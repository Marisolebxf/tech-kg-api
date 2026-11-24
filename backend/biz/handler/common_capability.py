import asyncio
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from application.common_capability import CommonCapabilityApplication
from biz.dependencies.auth import CurrentActor
from infra.rate_limit import RateLimit, enforce_rate_limit

router = APIRouter(prefix="/common-capabilities", tags=["common-capabilities"])
application = CommonCapabilityApplication()

# 单请求上限 + 按用户的文本额度（批量按条数计费）：渗透 B5 实测单请求 1000 条即时执行，
# 底层逐条消耗 NLP/LLM 算力。额度可用 RATE_LIMIT_COMMON_CAPABILITIES 覆盖。
MAX_TEXT_CHARS = 5000
MAX_BATCH_TEXTS = 50
MAX_KB_ENTITIES = 200
_RATE_BUCKET = "common-capabilities"
_DEFAULT_RATE = RateLimit(limit=200, window_seconds=60)

BoundedText = Annotated[str, Field(max_length=MAX_TEXT_CHARS)]


async def _run_charged(actor, cost: int, func, *args, **kwargs):
    """先扣额度再在线程池执行：抽取/对齐为同步重计算，直接在协程里跑会卡住事件循环。"""
    await enforce_rate_limit(_RATE_BUCKET, actor.user_id, _DEFAULT_RATE, cost=cost)
    return await asyncio.to_thread(func, *args, **kwargs)


class EntityExtractionRequest(BaseModel):
    """Extract KG entities from unstructured text."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "text": "2010年至今，北京大学计算机科学与技术系，教授",
                "source_type": "work",
            }
        }
    )

    text: str = Field(
        ..., min_length=1, max_length=MAX_TEXT_CHARS, description="Text to extract entities from."
    )
    source_type: Literal["work", "education", "abstract", "general"] = Field(
        default="general",
        description="Text scenario used to focus entity types.",
    )


class EntityAlignmentRequest(BaseModel):
    """Align entities between two KG entity lists."""

    model_config = ConfigDict(json_schema_extra={"example": {"top_k": 3}})

    kg_a: list[dict[str, Any]] | None = Field(
        default=None,
        max_length=MAX_KB_ENTITIES,
        description="Left-side entity list. Empty or null uses built-in demo data.",
    )
    kg_b: list[dict[str, Any]] | None = Field(
        default=None,
        max_length=MAX_KB_ENTITIES,
        description="Right-side entity list. Empty or null uses built-in demo data.",
    )
    top_k: int = Field(default=3, ge=1, le=50, description="Number of candidates to recall.")


class EntityDisambiguationRequest(BaseModel):
    """Link an entity mention in context to a KB entity."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "text": "苹果今天在发布会上推出了新款iPhone 16。",
                "mention": "苹果",
                "top_k": 5,
            }
        }
    )

    text: str = Field(
        ..., min_length=1, max_length=MAX_TEXT_CHARS, description="Full context text."
    )
    mention: str = Field(
        ..., min_length=1, max_length=256, description="Entity mention to disambiguate."
    )
    kb: list[dict[str, Any]] | None = Field(
        default=None,
        max_length=MAX_KB_ENTITIES,
        description="Candidate KB entities. Empty or null uses built-in demo data.",
    )
    top_k: int = Field(default=5, ge=1, le=50, description="Number of candidates to recall.")


class RelationExtractionRequest(BaseModel):
    """Extract relation triples from text."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "text": "马云创立了阿里巴巴集团，阿里巴巴集团位于浙江省杭州市。",
                "method": "rule",
            }
        }
    )

    text: str = Field(
        ..., min_length=1, max_length=MAX_TEXT_CHARS, description="Text to extract relations from."
    )
    method: Literal["rule", "llm", "hybrid"] = Field(
        default="rule",
        description="Extraction method. llm/hybrid require LLM_API_KEY.",
    )


class BatchRelationExtractionRequest(BaseModel):
    """Batch extract relation triples from texts."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "texts": ["马云创立了阿里巴巴集团", "任正非创立了华为技术有限公司"],
                "method": "rule",
            }
        }
    )

    texts: list[BoundedText] = Field(
        ..., min_length=1, max_length=MAX_BATCH_TEXTS, description="Texts to process."
    )
    method: Literal["rule", "llm", "hybrid"] = Field(default="rule")


@router.get("/metadata")
async def metadata() -> dict[str, Any]:
    return {
        "capabilities": [
            "entity_extraction",
            "entity_alignment",
            "entity_disambiguation",
            "relation_extraction",
        ],
        "entity_extraction_source_types": application.focus_types(),
        "relation_extraction_methods": ["rule", "llm", "hybrid"],
    }


@router.post("/entity-extraction", responses={400: {"description": "请求参数无效"}})
async def extract_entities(body: EntityExtractionRequest, actor: CurrentActor) -> dict[str, Any]:
    if not body.text.strip():
        raise HTTPException(status_code=400, detail="text cannot be empty")
    return await _run_charged(actor, 1, application.extract_entities, body.text, body.source_type)


@router.post("/entity-alignment")
async def align_entities(body: EntityAlignmentRequest, actor: CurrentActor) -> dict[str, Any]:
    return await _run_charged(
        actor, 1, application.align_entities, body.kg_a, body.kg_b, top_k=body.top_k
    )


@router.post("/entity-disambiguation")
async def disambiguate_entity(
    body: EntityDisambiguationRequest, actor: CurrentActor
) -> dict[str, Any]:
    return await _run_charged(
        actor,
        1,
        application.disambiguate_entity,
        body.text,
        body.mention,
        body.kb,
        top_k=body.top_k,
    )


@router.post("/relation-extraction", responses={400: {"description": "请求参数无效"}})
async def extract_relation(body: RelationExtractionRequest, actor: CurrentActor) -> dict[str, Any]:
    if not body.text.strip():
        raise HTTPException(status_code=400, detail="text cannot be empty")
    return await _run_charged(
        actor, 1, application.extract_relations, body.text, method=body.method
    )


@router.post(
    "/relation-extraction/batch",
    responses={400: {"description": "请求参数无效"}, 429: {"description": "超出调用额度"}},
)
async def batch_extract_relation(
    body: BatchRelationExtractionRequest, actor: CurrentActor
) -> dict[str, Any]:
    texts = [text for text in body.texts if text.strip()]
    if not texts:
        raise HTTPException(status_code=400, detail="texts cannot be empty")
    return await _run_charged(
        actor, len(texts), application.batch_extract_relations, texts, method=body.method
    )


@router.get("/relation-extraction/examples")
async def relation_examples() -> list[dict[str, str]]:
    return application.relation_examples()
