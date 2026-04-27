"""GraphRAG demo request/response schemas."""

from pydantic import BaseModel, ConfigDict, Field


class GraphRAGDemoInitRequest(BaseModel):
    """Initialize the demo graph in Neo4j."""

    reset: bool = Field(default=False, description="Whether to clear old demo nodes first.")


class GraphRAGDemoInitResponse(BaseModel):
    document_count: int
    chunk_count: int
    entity_count: int
    relationship_count: int
    sample_questions: list[str]


class GraphRAGDemoQueryRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "query": "GraphRAG 和普通向量检索有什么区别？",
                "top_k": 3,
                "max_related": 6,
            }
        }
    )

    query: str = Field(..., min_length=1, description="User question for the GraphRAG demo.")
    top_k: int = Field(default=3, ge=1, le=10, description="Number of chunk candidates to keep.")
    max_related: int = Field(
        default=6,
        ge=1,
        le=20,
        description="Maximum related entities to expose in the response.",
    )


class GraphRAGDemoChunk(BaseModel):
    chunk_id: str
    document_id: str
    document_title: str
    text: str
    score: float
    entities: list[dict]
    related_entities: list[dict]


class GraphRAGDemoQueryResponse(BaseModel):
    query: str
    answer: str
    method: str
    chunks: list[GraphRAGDemoChunk]
    retrieved_entities: list[dict]
    context_preview: str


class GraphRAGDemoOverviewResponse(BaseModel):
    name: str
    description: str
    graph_schema: dict
    sample_questions: list[str]
