from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class WorkflowContext(BaseModel):
    workflowType: str = Field(min_length=1, max_length=128)
    workflowId: str = Field(min_length=1, max_length=256)
    runId: str | None = None
    taskQueue: str = Field(min_length=1, max_length=128)
    resumeToken: str = Field(min_length=1, max_length=1000)


class ReviewObject(BaseModel):
    id: str = Field(min_length=1, max_length=256)
    type: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=500)


class ReviewException(BaseModel):
    code: str = Field(pattern=r"^[A-Z0-9_\-]{2,128}$")
    message: str = Field(min_length=1)
    fingerprint: str = Field(min_length=1, max_length=128)
    severity: Literal["P0", "P1", "P2"]
    scope: Literal["OBJECT", "BATCH"]


class EvidenceItem(BaseModel):
    id: str | None = None
    source: str = ""
    trustLevel: str = "UNVERIFIED"
    summary: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)


class ReviewRequiredRequest(BaseModel):
    eventId: str = Field(min_length=1, max_length=128)
    occurredAt: datetime
    sourceTaskId: str
    batchId: str | None = None
    stepId: Literal["source", "normalize", "schema", "extract", "align", "validate", "persist"]
    workflow: WorkflowContext
    object: ReviewObject
    exception: ReviewException
    templateId: str
    templateVersion: str = "1.0"
    domain: str = "graph"
    inputSnapshot: dict[str, Any] = Field(default_factory=dict)
    candidateSnapshot: dict[str, Any] = Field(default_factory=dict)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    ruleVersion: str | None = None
    modelVersion: str | None = None
    sourceTable: str | None = None
    sourceRecordId: str | None = None


class ExecutionEventRequest(BaseModel):
    eventId: str = Field(min_length=1, max_length=128)
    executionId: str = Field(min_length=1, max_length=128)
    type: Literal[
        "CORRECTION_ACCEPTED",
        "RERUN_STARTED",
        "RERUN_PROGRESS",
        "RERUN_SUCCEEDED",
        "RERUN_FAILED",
        "VERIFICATION_SUCCEEDED",
        "VERIFICATION_FAILED",
    ]
    occurredAt: datetime
    stepId: Literal["source", "normalize", "schema", "extract", "align", "validate", "persist"]
    workflowId: str | None = None
    runId: str | None = None
    result: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
