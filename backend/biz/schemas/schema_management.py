"""Schema 管理接口请求模型。"""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from biz.schemas.text_rules import check_text
from service.schema_ddl import is_valid_data_type

ENTITY_NAME_PATTERN = re.compile(r"^[A-Z][A-Za-z0-9]*$")
RELATION_NAME_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")
KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_-]*$")
PROPERTY_NAME_PATTERN = re.compile(r"^[A-Za-z_]\w*$")


def _to_camel(value: str) -> str:
    parts = value.split("_")
    return parts[0] + "".join(part.capitalize() for part in parts[1:])


class CamelModel(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True, alias_generator=_to_camel, str_strip_whitespace=True
    )


class SchemaPropertyInput(CamelModel):
    name: str = Field(min_length=1, max_length=64)
    data_type: str = Field(min_length=1, max_length=64)
    required: bool = False
    rule: str = Field(default="", max_length=64)
    category: str = Field(default="core", pattern="^(core|dynamic)$")

    @field_validator("rule", mode="before")
    @classmethod
    def validate_rule(cls, value: str) -> str:
        if not value:
            return value
        return check_text(value.strip(), label="属性规则", allow_space=True)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if not PROPERTY_NAME_PATTERN.fullmatch(value):
            raise ValueError("属性名只能包含字母、数字和下划线，且不能以数字开头")
        return value

    @field_validator("data_type")
    @classmethod
    def validate_data_type(cls, value: str) -> str:
        if not is_valid_data_type(value):
            raise ValueError(
                "data_type 必须是 string/int64/double/bool/date/datetime/geo 或 fixed_string(N)"
            )
        return value


class SchemaCreateBase(CamelModel):
    schema_key: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=64)
    description: str = Field(default="", max_length=64)
    identity_key: str = Field(default="", max_length=64)
    properties: list[SchemaPropertyInput] = Field(min_length=1, max_length=200)
    mappings: list[str] = Field(default_factory=list, max_length=100)
    is_core: bool = False
    version: str = Field(default="v1.0", min_length=1, max_length=32)
    llm_config_id: str | None = Field(default=None, max_length=64)

    @field_validator("schema_key")
    @classmethod
    def validate_key(cls, value: str) -> str:
        if not KEY_PATTERN.fullmatch(value):
            raise ValueError("schemaKey 必须以小写字母开头，只能包含小写字母、数字、-、_")
        return value

    @field_validator("label", "description", "identity_key", mode="before")
    @classmethod
    def validate_texts(cls, value: str) -> str:
        if not value:
            return value
        return check_text(value.strip(), label="Schema 文本", allow_space=True)

    @field_validator("mappings")
    @classmethod
    def validate_mappings(cls, value: list[str]) -> list[str]:
        normalized = [item.strip() for item in value if item.strip()]
        if len(set(normalized)) != len(normalized):
            raise ValueError("来源映射不能重复")
        for item in normalized:
            check_text(item, label="来源映射名称")
        return normalized

    @model_validator(mode="after")
    def validate_property_names(self) -> SchemaCreateBase:
        names = [item.name for item in self.properties]
        if len(set(names)) != len(names):
            raise ValueError("属性名不能重复")
        return self


class EntitySchemaCreate(SchemaCreateBase):
    @field_validator("name")
    @classmethod
    def validate_entity_name(cls, value: str) -> str:
        if not ENTITY_NAME_PATTERN.fullmatch(value):
            raise ValueError("实体 Schema 名称必须使用 PascalCase")
        return value


class RelationSchemaCreate(SchemaCreateBase):
    source_schema_id: str | None = Field(default=None, min_length=1, max_length=36)
    target_schema_id: str | None = Field(default=None, min_length=1, max_length=36)
    source_expression: str | None = Field(default=None, min_length=1, max_length=64)
    target_expression: str | None = Field(default=None, min_length=1, max_length=64)
    relation_category: str = Field(default="fact", pattern="^(fact|inferred)$")

    @field_validator("source_expression", "target_expression", mode="before")
    @classmethod
    def validate_expressions(cls, value: str | None) -> str | None:
        if not value:
            return value
        return check_text(value.strip(), label="关系表达式", allow_space=True)

    @field_validator("name")
    @classmethod
    def validate_relation_name(cls, value: str) -> str:
        if not RELATION_NAME_PATTERN.fullmatch(value):
            raise ValueError("关系 Schema 名称必须使用 UPPER_SNAKE_CASE")
        return value

    @model_validator(mode="after")
    def validate_endpoints(self) -> RelationSchemaCreate:
        if not self.source_schema_id and not self.source_expression:
            raise ValueError("必须提供关系起点 Schema 或起点表达式")
        if not self.target_schema_id and not self.target_expression:
            raise ValueError("必须提供关系终点 Schema 或终点表达式")
        return self
