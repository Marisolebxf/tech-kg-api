from pydantic import BaseModel, Field


class ExpertColleagueRelationRequest(BaseModel):
    expert_id: str = Field(alias="expertId", min_length=1, max_length=128)
    peer_id: str | None = Field(default=None, alias="peerId", max_length=128)
    institution: str | None = Field(default=None, max_length=256)
    limit: int = Field(default=20, ge=1, le=100)

    model_config = {"populate_by_name": True}
