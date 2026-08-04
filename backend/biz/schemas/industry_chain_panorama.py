from pydantic import BaseModel, Field, model_validator


class IndustryChainPanoramaRequest(BaseModel):
    chain_code: str | None = Field(default=None, alias="chainCode", max_length=255)
    keyword: str | None = Field(default=None, max_length=255)
    include_events: bool = Field(default=True, alias="includeEvents")
    limit_per_type: int = Field(default=100, alias="limitPerType", ge=1, le=500)

    model_config = {"populate_by_name": True}

    @model_validator(mode="after")
    def validate_selector(self):
        if not self.chain_code and not self.keyword:
            raise ValueError("chainCode 和 keyword 至少提供一个")
        return self
