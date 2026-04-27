"""Schemas for the in-memory knowledge graph visual demo."""

from typing import Any

from pydantic import BaseModel, Field


class KGVisualNode(BaseModel):
    id: str
    name: str = ""
    category: str = "默认"
    properties: dict[str, Any] = Field(default_factory=dict)


class KGVisualNodeUpdate(BaseModel):
    name: str | None = None
    category: str | None = None
    properties: dict[str, Any] | None = None


class KGVisualLink(BaseModel):
    source: str
    target: str
    relation: str = "相关"
    properties: dict[str, Any] = Field(default_factory=dict)


class KGVisualLinkUpdate(BaseModel):
    relation: str | None = None
    properties: dict[str, Any] | None = None


class KGVisualGraph(BaseModel):
    nodes: list[KGVisualNode]
    links: list[KGVisualLink]


class KGVisualGraphResponse(BaseModel):
    message: str
    data: KGVisualGraph


class KGVisualNodeDetail(BaseModel):
    node: KGVisualNode
    related_links: list[KGVisualLink]


class KGVisualNodeDetailResponse(BaseModel):
    message: str
    data: KGVisualNodeDetail
