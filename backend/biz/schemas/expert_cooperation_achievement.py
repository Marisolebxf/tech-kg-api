from pydantic import BaseModel, Field, model_validator


class ExpertCooperationAchievementRequest(BaseModel):
    expert_a_id: str = Field(alias="expertAId", min_length=1, max_length=128)
    expert_b_id: str = Field(alias="expertBId", min_length=1, max_length=128)
    start_time: str | None = Field(default=None, alias="startTime", pattern=r"^\d{4}-\d{2}-\d{2}$")
    end_time: str | None = Field(default=None, alias="endTime", pattern=r"^\d{4}-\d{2}-\d{2}$")
    limit: int = Field(default=100, ge=1, le=500)

    model_config = {"populate_by_name": True}

    @model_validator(mode="after")
    def validate_pair(self):
        if self.expert_a_id == self.expert_b_id:
            raise ValueError("两个专家不能相同")
        if self.start_time and self.end_time and self.start_time > self.end_time:
            raise ValueError("startTime 不能晚于 endTime")
        return self
