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
    total_candidate: int = 0


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


class ExpertRelationGraphNode(BaseModel):
    id: str
    kind: str
    x: int
    y: int
    icon: str = ""
    title: str
    subtitle: str = ""
    desc: str = ""
    chips: list[str] = []
    achievements: list[dict] = []


class ExpertRelationGraphEdge(BaseModel):
    type: str = "curve"
    from_: list[int]
    c1: Optional[list[int]] = None
    c2: Optional[list[int]] = None
    to: list[int]
    stroke: str
    marker: str
    width: int = 4
    dash: str = ""
    label: str = ""
    label_x: int
    label_y: int
    label_color: str = "#8f52db"


class ExpertRelationGraph(BaseModel):
    width: int = 860
    height: int = 640
    nodes: list[ExpertRelationGraphNode] = []
    edges: list[ExpertRelationGraphEdge] = []


class ExpertRelationScenario(BaseModel):
    key: str
    label: str
    last_test_time: str
    graph: ExpertRelationGraph
    detail_rows: list[list]
    api_example: dict


class ExpertRelationDemoResponse(BaseModel):
    scenarios: list[ExpertRelationScenario] = []
