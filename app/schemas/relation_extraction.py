"""关系抽取 API 的请求/响应模型。"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RelationExtractionRequest(BaseModel):
    """从文本中抽取实体与关系三元组。"""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "text": "马云创立了阿里巴巴集团，阿里巴巴集团位于浙江省杭州市。",
                "method": "rule",
            }
        }
    )

    text: str = Field(..., min_length=1, description="待抽取关系的文本")
    method: str = Field(
        default="rule",
        pattern="^(rule|llm|hybrid)$",
        description="抽取方法: rule（规则匹配）/ llm（大模型） / hybrid（混合）",
    )


class BatchRelationExtractionRequest(BaseModel):
    """批量从多个文本中抽取实体与关系三元组。"""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "texts": [
                    "马云创立了阿里巴巴集团",
                    "任正非创立了华为技术有限公司",
                ],
                "method": "rule",
            }
        }
    )

    texts: list[str] = Field(..., min_length=1, description="待抽取的文本列表")
    method: str = Field(
        default="rule",
        pattern="^(rule|llm|hybrid)$",
        description="抽取方法: rule / llm / hybrid",
    )


class RelationEntityItem(BaseModel):
    """关系抽取中的实体项。"""

    id: str
    text: str
    type: str


class RelationTripleItem(BaseModel):
    """关系抽取中的三元组项。"""

    head: dict[str, Any]
    relation: str
    tail: dict[str, Any]
    confidence: float = 1.0
    source: str = "unknown"


class RelationExtractionResponse(BaseModel):
    """关系抽取结果响应。"""

    text: str
    method: str
    entities: list[dict[str, Any]]
    relations: list[dict[str, Any]]
    task_id: str | None = None
    task_status: str = "completed"
    persist_to_graph: bool = False


class RelationExtractionTaskStatusResponse(BaseModel):
    """关系抽取后台任务状态。"""

    task_id: str
    task_kind: str = ""
    status: str
    method: str
    entity_count: int = 0
    relation_count: int = 0
    written_entities: int = 0
    written_relations: int = 0
    job_node_id: str = ""
    source_hash: str = ""
    storage_backend: str = ""
    execution_backend: str = ""
    error: str = ""
    queued_at: str = ""
    started_at: str = ""
    finished_at: str = ""
    updated_at: str = ""
