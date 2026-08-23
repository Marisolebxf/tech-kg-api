from typing import Any

from pydantic import BaseModel, Field


class VersionRequest(BaseModel):
    version: int = Field(ge=1)


class TransferRequest(VersionRequest):
    assigneeId: str
    assigneeName: str = ""


class DraftRequest(VersionRequest):
    payload: dict[str, Any]


class SubmitRequest(VersionRequest):
    actionId: str
    result: dict[str, Any] = Field(default_factory=dict)
    note: str = ""


class ApprovalRequest(VersionRequest):
    note: str = ""


class CancelRequest(VersionRequest):
    reason: str = Field(min_length=1)


class CreateCaseRequest(BaseModel):
    sourceTaskId: str
    batchId: str | None = None
    nodeId: str
    objectId: str
    objectType: str
    objectName: str
    errorType: str
    errorFingerprint: str | None = None
    category: str = "其他流程异常"
    templateId: str | None = None
    domain: str
    phase: str
    scopeHint: str | None = None
    sourceTable: str | None = None
    sourceRecordId: str | None = None
    ruleVersion: str | None = None
    modelVersion: str | None = None
    diagnosis: str = ""
    input: dict[str, Any] = Field(default_factory=dict)
    candidate: dict[str, Any] = Field(default_factory=dict)


class EvidenceUploadRequest(BaseModel):
    fileName: str
    contentType: str
    sizeBytes: int = Field(gt=0)
    sha256: str


class EvidenceCompleteRequest(EvidenceUploadRequest):
    evidenceId: str
    bucket: str
    objectKey: str
    source: str = ""
    trustLevel: str = "UNVERIFIED"


class ExecutionCompleteRequest(BaseModel):
    success: bool
    error: str = ""
