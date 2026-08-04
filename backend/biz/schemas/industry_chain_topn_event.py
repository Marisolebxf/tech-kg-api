from pydantic import BaseModel, Field, model_validator


class IndustryChainTopNEventRequest(BaseModel):
    chain_code: str | None = Field(default=None, alias="chainCode", max_length=255)
    keyword: str | None = Field(default=None, max_length=255)
    node_id: str | None = Field(default=None, alias="nodeId", max_length=255)
    since: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    until: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    top_n: int = Field(default=10, alias="topN", ge=1, le=100)
    persist: bool = False
    space: str | None = Field(default=None, max_length=128)

    model_config = {"populate_by_name": True}

    @model_validator(mode="after")
    def validate_selector(self):
        if not self.chain_code and not self.keyword:
            raise ValueError("chainCode 和 keyword 至少提供一个")
        if self.since and self.until and self.since > self.until:
            raise ValueError("since 不能晚于 until")
        return self
