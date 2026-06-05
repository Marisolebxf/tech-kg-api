"""Entity binding request/response data models."""

from typing import Optional
from pydantic import BaseModel


class BindingExecuteRequest(BaseModel):
    binding_type: str = "all"  # "talent_paper" | "talent_patent" | "org_org" | "all"


class BindingPairDetail(BaseModel):
    source_name: str
    source_id: str
    source_label: str
    target_name: str
    target_id: str
    target_label: str
    confidence: float
    method: str
    rule_score: float
    llm_score: float
    status: str
    reason: str = ""


class BindingResult(BaseModel):
    binding_type: str
    total_candidates: int = 0
    confirmed: int = 0
    candidate: int = 0
    rejected: int = 0
    details: list[BindingPairDetail] = []


class BindingStatsResponse(BaseModel):
    talent_paper: Optional[BindingResult] = None
    talent_patent: Optional[BindingResult] = None
    org_org: Optional[BindingResult] = None
    total_confirmed: int = 0
    total_candidates: int = 0


class BindingGraphResponse(BaseModel):
    nodes: list[dict] = []
    edges: list[dict] = []


class InitDataResponse(BaseModel):
    edge_types_created: list[str] = []
    indexes_created: list[str] = []
    nodes_inserted: dict[str, int] = {}
    message: str = ""


class ClearResponse(BaseModel):
    message: str = ""
    edges_deleted: int = 0
