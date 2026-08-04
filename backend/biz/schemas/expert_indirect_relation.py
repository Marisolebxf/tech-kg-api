from pydantic import BaseModel, Field


class ExpertIndirectRelationRequest(BaseModel):
    expert_id: str = Field(alias="expertId", min_length=1, max_length=128)
    edge_types: list[str] = Field(default_factory=list, alias="edgeTypes", max_length=20)
    limit: int = Field(default=20, ge=1, le=100)
    space: str | None = Field(default=None, max_length=128)

    model_config = {"populate_by_name": True}
