"""项目关系对外查询接口模型。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ProjectRelationType = Literal[
    "FUNDED_BY",
    "LEADS",
    "HAS_PARTICIPANT",
    "HAS_KEYWORD",
    "HAS_OUTPUT",
]


class ProjectRelationQueryRequest(BaseModel):
    keyword: str | None = Field(default=None, max_length=256)
    projectNumber: str | None = Field(default=None, max_length=128)
    relationTypes: list[ProjectRelationType] = Field(default_factory=list, max_length=5)
    pageSize: int = Field(default=100, ge=1, le=200)
    cursor: str | None = Field(default=None, max_length=2048)

    @field_validator("keyword", "projectNumber", "cursor", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: Any) -> Any:
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value

    @field_validator("relationTypes")
    @classmethod
    def unique_relation_types(
        cls, value: list[ProjectRelationType]
    ) -> list[ProjectRelationType]:
        return list(dict.fromkeys(value))

    @model_validator(mode="after")
    def validate_filters(self) -> ProjectRelationQueryRequest:
        if self.keyword and self.projectNumber:
            raise ValueError("keyword 和 projectNumber 不能同时传入")
        return self


class ProjectData(BaseModel):
    id: str
    projectNumber: str = ""
    title: str = ""
    projectSource: str = ""
    projectLevel: str = ""
    approvalYear: str = ""
    researchPeriod: str = ""


class RelationData(BaseModel):
    type: ProjectRelationType
    name: str
    direction: Literal["out"] = "out"
    properties: dict[str, Any] = Field(default_factory=dict)


class RelatedEntityData(BaseModel):
    id: str
    type: str
    name: str = ""
    properties: dict[str, Any] = Field(default_factory=dict)


class ProjectRelationItem(BaseModel):
    project: ProjectData
    relation: RelationData
    relatedEntity: RelatedEntityData


class ProjectRelationPage(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    items: list[ProjectRelationItem] = Field(default_factory=list)
    pageSize: int
    nextCursor: str = ""
    hasMore: bool = False
