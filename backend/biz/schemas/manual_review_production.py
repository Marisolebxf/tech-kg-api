from typing import Any

from pydantic import BaseModel, Field, field_validator

from biz.schemas.text_rules import check_text

# 各文本字段的校验口径:标识类(identifier)/自由文本类(keyword)
_ID_FIELDS = (
    "assigneeId",
    "actionId",
    "sourceTaskId",
    "batchId",
    "nodeId",
    "objectId",
    "objectType",
    "errorFingerprint",
    "templateId",
    "domain",
    "phase",
    "sourceTable",
    "sourceRecordId",
    "ruleVersion",
    "modelVersion",
    "sha256",
    "evidenceId",
    "bucket",
    "trustLevel",
)
_TEXT_FIELDS = (
    "assigneeName",
    "note",
    "reason",
    "objectName",
    "category",
    "scopeHint",
    "diagnosis",
    "fileName",
    "contentType",
    "objectKey",
    "source",
    "error",
)


def _check_identifier(value):
    if value is None or value == "":
        return value
    return check_text(str(value).strip(), label="标识")


def _check_keyword(value):
    if value is None or value == "":
        return value
    return check_text(str(value).strip(), label="输入", allow_space=True)


class _TextRuleMixin(BaseModel):
    """为 _ID_FIELDS/_TEXT_FIELDS 中声明的字段套用统一文本校验。"""

    @field_validator(*_ID_FIELDS, mode="before", check_fields=False)
    @classmethod
    def _validate_id_fields(cls, v):
        return _check_identifier(v)

    @field_validator(*_TEXT_FIELDS, mode="before", check_fields=False)
    @classmethod
    def _validate_text_fields(cls, v):
        return _check_keyword(v)


class VersionRequest(_TextRuleMixin):
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


class DirectDecideRequest(VersionRequest):
    """kg.custom.steps T_DIRECT 案例直接决策：accept 写图，reject 丢弃。

    candidate 为"修正后的完整候选"（可选，仅 accepted 时有效）：
    覆盖候选快照后写图；``_`` 前缀元字段以快照为准，传入的一律丢弃。
    """

    accepted: bool
    note: str = ""
    candidate: dict[str, Any] | None = None


class CancelRequest(VersionRequest):
    reason: str = Field(min_length=1)


class CreateCaseRequest(_TextRuleMixin):
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


class EvidenceUploadRequest(_TextRuleMixin):
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


class ExecutionCompleteRequest(_TextRuleMixin):
    success: bool
    error: str = ""


class ExtractFailuresRerunRequest(BaseModel):
    """T_EXTRACT_FAIL 抽取失败记录重跑：单条（caseIds 一个）/ 批量勾选 / 按原执行全量。"""

    caseIds: list[str] | None = Field(default=None, max_length=2000)
    executionId: str | None = None
    batchSize: int | None = Field(default=None, ge=1, le=5000)
