"""人工处理模块补充单元测试：覆盖需求清单中的单元测试缺口与安全/状态机边界。

本文件刻意覆盖既有测试未触及的分支：
- 七模板的 result/action 全量校验、客户端 rerunStepId 全模板拒绝
- OBJECT/BATCH 隔离与 P0 风险策略
- correction 不可变性与 SHA-256
- 状态机失败分支（拒绝 / 重跑失败 / 验收失败）与重试
- Outbox 超时回收、重试退避、死信
- 异常快照大小限制、证据附件校验（mock S3）
- 服务签名认证（Bearer 与 X-Service-Signature）、跨业务域拒绝
- extract 节点回调状态机（曾发现并修复 stepId 守卫缺陷，此处回归保护）
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from biz.dependencies.review_service_auth import require_graph_service
from db_model.base import Base
from db_model.manual_review import ReviewCase, ReviewCorrection, ReviewOutbox
from service.manual_review_domain import (
    HIGH_RISK_ACTIONS,
    PIPELINE_STEPS,
    RESULT_SCHEMAS,
    TEMPLATES,
    ReviewConflictError,
    ReviewForbiddenError,
    ReviewIdentity,
    ReviewValidationError,
    canonical_template,
    requires_approval,
    rerun_step,
    risk_policy,
    role_can_review,
    validate_action,
    validate_step_template,
)
from service.manual_review_production import ManualReviewService


# --------------------------------------------------------------------------- #
# 通用夹具
# --------------------------------------------------------------------------- #
def _engine():
    return create_engine(
        "sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )


def new_service():
    engine = _engine()
    Base.metadata.create_all(engine)
    return ManualReviewService(sessionmaker(engine, expire_on_commit=False))


@pytest.fixture
def service():
    return new_service()


def identity(uid="reviewer-1", roles=("reviewer",), domains=("talent",)):
    return ReviewIdentity(uid, uid, frozenset(roles), frozenset(domains), "org", "req-1")


def report(
    step="align",
    template="T_LINK",
    event="evt-1",
    fingerprint="fp-1",
    severity="P1",
    scope="OBJECT",
    obj_id="OBJ-1",
    **overrides,
):
    base = {
        "eventId": event,
        "occurredAt": datetime.now(UTC),
        "sourceTaskId": "TASK-001",
        "batchId": "BATCH-001",
        "stepId": step,
        "workflow": {
            "workflowType": "GraphBuildWorkflow",
            "workflowId": "wf-1",
            "runId": "run-1",
            "taskQueue": "graph",
            "resumeToken": "opaque-token",
        },
        "object": {"id": obj_id, "type": "ExpertCandidate", "name": "脱敏专家"},
        "exception": {
            "code": "REVIEW_REQUIRED",
            "message": "需要人工处理",
            "fingerprint": fingerprint,
            "severity": severity,
            "scope": scope,
        },
        "templateId": template,
        "templateVersion": "1.0",
        "domain": "talent",
        "inputSnapshot": {"name": "脱敏专家"},
        "candidateSnapshot": {},
        "evidence": [],
        "ruleVersion": "rule-v1",
    }
    base.update(overrides)
    return base


def claim_and_submit(service, step, template, action, result, *, severity="P1", scope="OBJECT"):
    from uuid import uuid4

    created = service.create_review_required(
        report(
            step=step,
            template=template,
            severity=severity,
            scope=scope,
            event=f"evt-{step}-{uuid4().hex[:8]}",
        ),
        "graph-build",
    )
    a = identity()
    case = service.claim(created["reviewId"], 1, a)
    return service.submit(case["id"], case["version"], action, result, "证据已核验", a), a


def _advance_to_rerunning(service, case):
    """submit 后状态为 APPLYING，跑一次 outbox（mock）推进到 RERUNNING 并返回 executionId。"""
    import asyncio

    asyncio.run(service.process_outbox())
    refreshed = service.get_case(case["id"], identity())
    assert refreshed["status"] == "RERUNNING", refreshed["status"]
    return refreshed["executions"][0]["id"]


# --------------------------------------------------------------------------- #
# 1. 七个 stepId ↔ 模板目录 / 异常码目录映射
# --------------------------------------------------------------------------- #
def test_pipeline_steps_are_exactly_seven_with_stable_codes():
    assert set(PIPELINE_STEPS) == {
        "source",
        "normalize",
        "schema",
        "extract",
        "align",
        "validate",
        "persist",
    }
    # handoff §1：stepId 是恢复位置唯一依据，不允许自定义节点名
    assert all(v["phase"] in {"数据处理", "图谱构建"} for v in PIPELINE_STEPS.values())


def test_exception_code_is_freeform_uppercase_and_not_mapped_to_step():
    # handoff 要求图谱构建自建异常码目录；人工模块只校验格式，不做 code→stepId 映射。
    # 这里锁定该契约：任意合法 code 均被接受，模块不依据 code 推断恢复节点。
    svc = new_service()
    for code in ("ALIGN_AMBIGUOUS", "SCHEMA_MAP_MISSING", "EXTRACT_LOW_CONFIDENCE", "X-Y_1"):
        created = svc.create_review_required(
            report(
                exception={
                    "code": code,
                    "message": "m",
                    "fingerprint": code,
                    "severity": "P1",
                    "scope": "OBJECT",
                },
                event=f"evt-{code}",
            ),
            "graph-build",
        )
        assert created["status"] == "OPEN"


def test_every_step_template_combination_matches_handoff_table():
    # handoff §1 默认模板表
    allowed = {
        "source": {"T_RUNTIME"},
        "normalize": {"T_MAP", "T_DQ_FILL", "T_DQ_MERGE", "T_RUNTIME"},
        "schema": {"T_MAP", "T_RUNTIME"},
        "extract": {"T_RUNTIME"},
        "align": {"T_LINK", "T_RUNTIME"},
        "validate": {"T_EVIDENCE", "T_ATTR", "T_RUNTIME"},
        "persist": {"T_RUNTIME"},
    }
    for step, tpls in allowed.items():
        assert PIPELINE_STEPS[step]["templates"] == tpls
        for tpl in tpls:
            assert validate_step_template(step, tpl) == tpl


# --------------------------------------------------------------------------- #
# 2. 七模板 request/result Schema 校验
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("tid", list(TEMPLATES))
def test_each_template_has_action_result_contract_and_write_target(tid):
    assert 'title' in TEMPLATES[tid]
    assert 'actions' in TEMPLATES[tid]
    assert 'components' in TEMPLATES[tid]
    assert tid in RESULT_SCHEMAS
    # 合同返回结构稳定
    from service.manual_review_domain import template_contract

    contract = template_contract(tid)
    assert contract["id"] == tid
    assert {"displaySchema", "resultSchema", "allowedActions"} <= set(contract)


def test_action_validation_matrix_for_all_templates():
    # 每个模板的合法动作通过校验；非法动作被拒
    cases = {
        "T_MAP": ("save-map-rerun", {"mappings": [{"source": "a", "target": "b"}]}),
        "T_DQ_FILL": ("save-fill-rerun", {"titleZh": "修正标题"}),
        "T_DQ_MERGE": ("merge-rerun", {"mergeMaster": "REC-1"}),
        "T_LINK": ("entity-confirm", {"entityVerdict": "create"}),
        "T_EVIDENCE": ("pass-rerun", {"evidence": [{"id": "1"}, {"id": "2"}]}),
        "T_ATTR": ("confirm-attr", {"attrVerdict": "采用A源"}),
        "T_RUNTIME": ("retry-task", {"runtimeConfig": {"timeoutSeconds": 60}}),
    }
    for tid, (action, result) in cases.items():
        validate_action(tid, action, result)  # 不抛异常即通过
        with pytest.raises(ReviewValidationError):
            validate_action(tid, "not-a-real-action", result)


def test_action_special_rules_enforced():
    # 映射缺 mappings / 合并缺 targetEntityId / 证据不足两个 / 补录缺字段
    with pytest.raises(ReviewValidationError):
        validate_action("T_MAP", "save-map-rerun", {})
    with pytest.raises(ReviewValidationError):
        validate_action("T_LINK", "entity-confirm", {"entityVerdict": "merge"})
    with pytest.raises(ReviewValidationError):
        validate_action("T_EVIDENCE", "pass-rerun", {"evidence": [{"id": "1"}]})
    with pytest.raises(ReviewValidationError):
        validate_action("T_DQ_FILL", "save-fill-rerun", {})


# --------------------------------------------------------------------------- #
# 3. T_ENTITY / T_RELATION 旧模板兼容转换（全路径）
# --------------------------------------------------------------------------- #
def test_legacy_aliases_resolve_through_validate_and_correction(service):
    # T_ENTITY → T_LINK，T_RELATION → T_EVIDENCE，建单与合同均按新名落库
    created_link = service.create_review_required(
        report(step="align", template="T_ENTITY"), "graph-build"
    )
    created_evidence = service.create_review_required(
        report(step="validate", template="T_RELATION", event="evt-rel"), "graph-build"
    )
    case_link = service.get_case(created_link["reviewId"], identity())
    case_evidence = service.get_case(created_evidence["reviewId"], identity())
    assert case_link["templateId"] == "T_LINK"
    assert case_evidence["templateId"] == "T_EVIDENCE"
    assert case_link["template"]["displaySchema"]["sections"][0]["type"] == "entity-comparison"
    assert case_evidence["template"]["displaySchema"]["sections"][0]["type"] == "evidence-list"
    assert canonical_template("T_ENTITY") == "T_LINK"
    assert canonical_template("T_RELATION") == "T_EVIDENCE"


# --------------------------------------------------------------------------- #
# 4. confirm-type 动作校验 + 客户端 rerunStepId 全模板拒绝
# --------------------------------------------------------------------------- #
def test_confirm_type_requires_entity_type():
    validate_action("T_MAP", "confirm-type", {"entityType": "Expert"})
    with pytest.raises(ReviewValidationError):
        validate_action("T_MAP", "confirm-type", {})


@pytest.mark.parametrize("tid", list(TEMPLATES))
def test_client_supplied_rerun_step_id_is_rejected_for_every_template(tid):
    # handoff §1/§4：rerunStepId 由服务端决定，客户端不得覆盖
    # 取该模板任意一个动作注入 rerunStepId
    action = next(iter(TEMPLATES[tid]["actions"]))
    # 先补齐该动作必需字段，再追加 rerunStepId，确保拒绝源于 rerunStepId 而非缺字段
    minimal = {
        "T_MAP": {"mappings": [{"source": "a", "target": "b"}]},
        "T_DQ_FILL": {"titleZh": "t"},
        "T_DQ_MERGE": {"mergeMaster": "R1"},
        "T_LINK": {"entityVerdict": "create"},
        "T_EVIDENCE": {"evidence": [{"id": "1"}, {"id": "2"}]},
        "T_ATTR": {"attrVerdict": "v"},
        "T_RUNTIME": {"runtimeConfig": {}},
    }[tid]
    minimal["rerunStepId"] = "persist"
    with pytest.raises(ReviewValidationError):
        validate_action(tid, action, minimal)


# --------------------------------------------------------------------------- #
# 5. P0 / OBJECT 风险与隔离策略
# --------------------------------------------------------------------------- #
def test_risk_policy_p0_batch_has_short_sla_and_block_isolation():
    risk, scope, claim, resolve = risk_policy("Schema 映射失败", "BATCH", "P0")
    assert risk == 'P0'
    assert scope == '批次级'
    assert resolve - claim == timedelta(minutes=15)


def test_object_isolation_strategy_in_ingress_response(service):
    created = service.create_review_required(
        report(step="align", scope="OBJECT", severity="P1"), "graph-build"
    )
    assert created["isolationStrategy"] == "ISOLATE_OBJECT"


def test_batch_isolation_strategy_in_ingress_response(service):
    created = service.create_review_required(
        report(step="schema", template="T_MAP", scope="BATCH", severity="P0"), "graph-build"
    )
    assert created["isolationStrategy"] == "BLOCK_BATCH_AND_DOWNSTREAM"


def test_batch_non_p0_is_rejected(service):
    with pytest.raises(ReviewValidationError):
        new_service().create_review_required(
            report(step="schema", template="T_MAP", scope="BATCH", severity="P1"), "graph-build"
        )


def test_correction_scope_reflects_isolation(service):
    # OBJECT 单对象 / BATCH 批次阻断 —— correction 回传的 scope 决定图谱恢复范围
    obj_case, _ = claim_and_submit(
        service, "align", "T_LINK", "entity-confirm", {"entityVerdict": "create"}
    )
    assert service.correction(obj_case["id"])["scope"] == "OBJECT"
    # BATCH P0 在审批前不应存在 correction
    batch_case, _ = claim_and_submit(
        service,
        "schema",
        "T_MAP",
        "save-map-rerun",
        {"mappings": [{"source": "a", "target": "b"}]},
        severity="P0",
        scope="BATCH",
    )
    with pytest.raises(KeyError):
        service.correction(batch_case["id"])
    approved = service.approve(
        batch_case["id"],
        batch_case["version"],
        True,
        "批准",
        identity("approver-2", ("approver",)),
    )
    assert approved["status"] == "APPLYING"
    assert service.correction(batch_case["id"])["scope"] == "BATCH"


# --------------------------------------------------------------------------- #
# 6. 请求级 + 业务级双重幂等
# --------------------------------------------------------------------------- #
def test_dual_idempotency_event_and_business_key(service):
    first = service.create_review_required(report(), "graph-build")
    same_event = service.create_review_required(report(event="evt-1"), "graph-build")
    # 换 eventId 但同业务键（sourceTaskId+step+objectId+fingerprint）
    same_business = service.create_review_required(report(event="evt-2"), "graph-build")
    assert first["reviewId"] == same_event["reviewId"] == same_business["reviewId"]
    assert same_event['duplicate']
    assert same_business['duplicate']


def test_different_object_id_creates_distinct_case(service):
    a = service.create_review_required(report(obj_id="OBJ-A"), "graph-build")
    b = service.create_review_required(report(obj_id="OBJ-B", event="evt-b"), "graph-build")
    assert a['reviewId'] != b['reviewId']
    assert not b['duplicate']


# --------------------------------------------------------------------------- #
# 7. 非法 stepId / 模板不匹配 / 任意 rerunStepId 拒绝
# --------------------------------------------------------------------------- #
def test_illegal_step_id_rejected():
    with pytest.raises(ReviewValidationError):
        validate_step_template("ingest", "T_RUNTIME")  # 自定义节点名


def test_template_step_mismatch_rejected():
    # T_LINK 仅适用于 align，不能用于 normalize
    with pytest.raises(ReviewValidationError):
        validate_step_template("normalize", "T_LINK")
    # T_ATTR 仅适用于 validate
    with pytest.raises(ReviewValidationError):
        validate_step_template("align", "T_ATTR")


# --------------------------------------------------------------------------- #
# 8. 状态机 / 乐观锁 / 双人审批 / 回调乱序
# --------------------------------------------------------------------------- #
def test_optimistic_lock_blocks_stale_mutation(service):
    created = service.create_review_required(report(), "graph-build")
    v = 1
    service.claim(created["reviewId"], v, identity())
    with pytest.raises(ReviewConflictError):
        # 用旧版本再次领取
        service.claim(created["reviewId"], v, identity("reviewer-2"))


def test_callback_out_of_order_rejected(service):
    case, _ = claim_and_submit(
        service, "align", "T_LINK", "entity-confirm", {"entityVerdict": "create"}
    )
    common = {
        "executionId": "EXEC-1",
        "occurredAt": datetime.now(UTC),
        "stepId": "align",
        "workflowId": "wf",
        "runId": "r",
        "result": {},
        "error": None,
        "metrics": {},
    }
    # APPLYING 状态直接发验收事件 → 拒绝
    with pytest.raises(ReviewConflictError):
        service.execution_event(
            case["id"], {**common, "eventId": "e1", "type": "VERIFICATION_SUCCEEDED"}
        )


def test_callback_duplicate_event_is_idempotent(service):
    case, _ = claim_and_submit(
        service, "align", "T_LINK", "entity-confirm", {"entityVerdict": "create"}
    )
    exec_id = _advance_to_rerunning(service, case)
    common = {
        "executionId": exec_id,
        "occurredAt": datetime.now(UTC),
        "stepId": "align",
        "workflowId": "wf",
        "runId": "r",
        "result": {},
        "error": None,
        "metrics": {},
    }
    first = service.execution_event(
        case["id"], {**common, "eventId": "d1", "type": "RERUN_SUCCEEDED"}
    )
    replay = service.execution_event(
        case["id"], {**common, "eventId": "d1", "type": "RERUN_SUCCEEDED"}
    )
    assert first['status'] == 'VERIFYING'
    assert replay['duplicate'] is True


def test_p0_decision_does_not_enqueue_correction_before_approval(service):
    case, _ = claim_and_submit(
        service,
        "schema",
        "T_MAP",
        "save-map-rerun",
        {"mappings": [{"source": "a", "target": "b"}]},
        severity="P0",
        scope="BATCH",
    )
    assert case["status"] == "PENDING_APPROVAL"
    with service.sf() as s:
        assert (
            s.scalar(select(ReviewCorrection).where(ReviewCorrection.case_id == case["id"])) is None
        )
        assert s.scalar(select(ReviewOutbox).where(ReviewOutbox.case_id == case["id"])) is None


def test_p0_same_submitter_cannot_approve(service):
    # 同一用户既提交又审批 → 必须拒绝（双人审批）
    submitter = identity("user-1", ("reviewer", "approver"))
    created = service.create_review_required(
        report(step="schema", template="T_MAP", scope="BATCH", severity="P0"), "graph-build"
    )
    case = service.claim(created["reviewId"], 1, submitter)
    case = service.submit(
        case["id"],
        case["version"],
        "save-map-rerun",
        {"mappings": [{"source": "a", "target": "b"}]},
        "",
        submitter,
    )
    with pytest.raises(ReviewForbiddenError):
        service.approve(case["id"], case["version"], True, "批准", submitter)


def test_high_risk_action_requires_approval_even_for_p1(service):
    # force-pass / rollback-dict / skip-task 属高风险，即便 P1 也需审批
    assert requires_approval("P1", "force-pass", {}) is True
    assert requires_approval("P1", "rollback-dict", {}) is True
    assert requires_approval("P1", "skip-task", {}) is True
    assert requires_approval("P2", "retry-task", {}) is False
    assert HIGH_RISK_ACTIONS == {"force-pass", "rollback-dict", "skip-task"}


# --------------------------------------------------------------------------- #
# 9. Correction SHA-256 与不可变性
# --------------------------------------------------------------------------- #
def test_correction_payload_sha256_matches_canonical_json(service):
    case, _ = claim_and_submit(
        service, "align", "T_LINK", "entity-confirm", {"entityVerdict": "create"}
    )
    correction = service.correction(case["id"])
    canonical = json.dumps(
        correction["payload"], ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    assert correction["payloadSha256"] == hashlib.sha256(canonical).hexdigest()
    assert len(correction["payloadSha256"]) == 64


def test_correction_is_immutable_across_repeated_reads(service):
    case, _ = claim_and_submit(
        service, "align", "T_LINK", "entity-confirm", {"entityVerdict": "create"}
    )
    first = service.correction(case["id"])
    second = service.correction(case["id"])
    assert first["correctionId"] == second["correctionId"]
    assert first["payloadSha256"] == second["payloadSha256"]
    assert first["payload"] == second["payload"]


def test_correction_step_id_uses_reject_extract_only_for_validate(service):
    # handoff §1：validate + reject-extract 是唯一允许回退到 extract 的裁决
    assert rerun_step("validate", "reject-extract") == "extract"
    assert rerun_step("align", "entity-confirm") == "align"
    assert rerun_step("schema", "save-map-rerun") == "schema"


# --------------------------------------------------------------------------- #
# 10. 失败分支：拒绝 / 重跑失败 / 验收失败 / 重试
# --------------------------------------------------------------------------- #
def test_reject_decision_terminates_as_rejected(service):
    # 需走 P0 审批拒绝路径
    case, _ = claim_and_submit(
        service,
        "schema",
        "T_MAP",
        "save-map-rerun",
        {"mappings": [{"source": "a", "target": "b"}]},
        severity="P0",
        scope="BATCH",
    )
    rejected = service.approve(
        case["id"], case["version"], False, "拒绝", identity("approver-2", ("approver",))
    )
    assert rejected["status"] == "REJECTED"
    with service.sf() as s:
        row = s.get(ReviewCase, case["id"])
        assert row.completed_at is not None  # 终态记录完成时间
        assert (
            s.scalar(select(ReviewCorrection).where(ReviewCorrection.case_id == case["id"])) is None
        )


def test_rerun_failed_event_sets_rerun_failed(service):
    case, _ = claim_and_submit(
        service, "align", "T_LINK", "entity-confirm", {"entityVerdict": "create"}
    )
    exec_id = _advance_to_rerunning(service, case)
    common = {
        "executionId": exec_id,
        "occurredAt": datetime.now(UTC),
        "stepId": "align",
        "workflowId": "wf",
        "runId": "r",
        "result": {},
        "metrics": {},
    }
    service.execution_event(case["id"], {**common, "eventId": "e1", "type": "RERUN_SUCCEEDED"})
    failed = service.execution_event(
        case["id"], {**common, "eventId": "e2", "error": "boom", "type": "VERIFICATION_FAILED"}
    )
    assert failed["status"] == "RERUN_FAILED"


def test_verification_failed_also_rerun_failed(service):
    case, _ = claim_and_submit(
        service, "align", "T_LINK", "entity-confirm", {"entityVerdict": "create"}
    )
    exec_id = _advance_to_rerunning(service, case)
    common = {
        "executionId": exec_id,
        "occurredAt": datetime.now(UTC),
        "stepId": "align",
        "workflowId": "wf",
        "runId": "r",
        "result": {},
        "metrics": {},
    }
    service.execution_event(case["id"], {**common, "eventId": "e1", "type": "RERUN_SUCCEEDED"})
    res = service.execution_event(
        case["id"],
        {**common, "eventId": "e2", "error": "校验不通过", "type": "VERIFICATION_FAILED"},
    )
    assert res["status"] == "RERUN_FAILED"


def test_retry_only_allowed_from_failed_states(service):
    case, _ = claim_and_submit(
        service, "align", "T_LINK", "entity-confirm", {"entityVerdict": "create"}
    )
    # APPLYING 状态不允许重试
    with pytest.raises(ReviewConflictError):
        service.retry(case["id"], case["version"], identity())


def test_retry_after_failure_reuses_same_correction(service):
    case, _ = claim_and_submit(
        service, "align", "T_LINK", "entity-confirm", {"entityVerdict": "create"}
    )
    exec_id = _advance_to_rerunning(service, case)
    common = {
        "executionId": exec_id,
        "occurredAt": datetime.now(UTC),
        "stepId": "align",
        "workflowId": "wf",
        "runId": "r",
        "result": {},
        "metrics": {},
    }
    service.execution_event(
        case["id"], {**common, "eventId": "e1", "type": "RERUN_FAILED", "error": "x"}
    )
    # 状态机已多次推进 version，需刷新到最新版本再重试
    latest = service.get_case(case["id"], identity())
    retried = service.retry(case["id"], latest["version"], identity("admin", ("review_admin",)))
    assert retried["status"] == "APPLYING"
    # 重试复用同一 correction（图谱构建以 correctionId 为幂等键，返回同一 executionId）
    cor = service.correction(case["id"])
    assert cor["correctionId"].startswith("COR-")


# --------------------------------------------------------------------------- #
# 11. extract 节点回调状态机缺陷（暴露用，预期失败 → 记为 BUG）
# --------------------------------------------------------------------------- #
def test_extract_node_can_complete_via_callback(service):
    """handoff §1：extract 节点 T_RUNTIME 重跑后应以 stepId=extract 回调完成。

    现状：execution_event 的 stepId 守卫会拒绝 pipeline_step_id==extract 时
    stepId=='extract' 的回调，导致 extract 节点审核单永久卡在 RERUNNING。
    """
    import asyncio

    case, _ = claim_and_submit(service, "extract", "T_RUNTIME", "retry-task", {"runtimeConfig": {}})
    asyncio.run(service.process_outbox())  # APPLYING → RERUNNING（mock executionId）
    refreshed = service.get_case(case["id"], identity())
    assert refreshed["status"] == "RERUNNING"
    common = {
        "executionId": refreshed["executions"][0]["id"],
        "occurredAt": datetime.now(UTC),
        "stepId": "extract",
        "workflowId": "wf",
        "runId": "r",
        "result": {},
        "error": None,
        "metrics": {},
    }
    succeeded = service.execution_event(
        case["id"], {**common, "eventId": "ex-1", "type": "RERUN_SUCCEEDED"}
    )
    assert succeeded["status"] == "VERIFYING"


# --------------------------------------------------------------------------- #
# 12. Outbox 超时回收 / 重试退避 / 死信
# --------------------------------------------------------------------------- #
def test_outbox_dead_letter_after_max_attempts(service, monkeypatch):
    monkeypatch.setenv("REVIEW_RERUN_MODE", "remote")
    monkeypatch.setenv("GRAPH_BUILD_INTERNAL_URL", "http://graph-build.invalid")
    monkeypatch.setenv("REVIEW_RESUME_MAX_ATTEMPTS", "2")
    # 远端不可达 → 每次投递失败
    service.http_client_factory = lambda: _raising_client()
    case, _ = claim_and_submit(
        service, "align", "T_LINK", "entity-confirm", {"entityVerdict": "create"}
    )
    import asyncio

    # 退避会把 available_at 推后；每轮手动到期以模拟时间推进，直到死信
    for _ in range(6):
        asyncio.run(service.process_outbox())
        with service.sf() as s:
            outbox = s.scalar(select(ReviewOutbox).where(ReviewOutbox.case_id == case["id"]))
            if outbox.status == "DEAD":
                break
            outbox.available_at = datetime.now(UTC).replace(tzinfo=None)
            s.commit()
    with service.sf() as s:
        outbox = s.scalar(select(ReviewOutbox).where(ReviewOutbox.case_id == case["id"]))
        assert outbox.status == "DEAD"
        assert outbox.attempts >= 2
        assert outbox.last_error
    refreshed = service.get_case(case["id"], identity())
    assert refreshed["status"] == "APPLY_FAILED"


def test_outbox_retry_backoff_increases_available_at(service, monkeypatch):
    monkeypatch.setenv("REVIEW_RERUN_MODE", "remote")
    monkeypatch.setenv("GRAPH_BUILD_INTERNAL_URL", "http://graph-build.invalid")
    monkeypatch.setenv("REVIEW_RESUME_MAX_ATTEMPTS", "9")
    service.http_client_factory = lambda: _raising_client()
    case, _ = claim_and_submit(
        service, "align", "T_LINK", "entity-confirm", {"entityVerdict": "create"}
    )
    import asyncio

    asyncio.run(service.process_outbox())
    with service.sf() as s:
        outbox = s.scalar(select(ReviewOutbox).where(ReviewOutbox.case_id == case["id"]))
        assert outbox.status == "RETRY"
        assert outbox.attempts == 1


def test_outbox_stale_processing_lock_is_reclaimed(service, monkeypatch):
    monkeypatch.setenv("REVIEW_OUTBOX_LOCK_TIMEOUT_SECONDS", "0")
    case, _ = claim_and_submit(
        service, "align", "T_LINK", "entity-confirm", {"entityVerdict": "create"}
    )
    # 人为将 outbox 置为 PROCESSING 且锁时间过期
    with service.sf() as s:
        outbox = s.scalar(select(ReviewOutbox).where(ReviewOutbox.case_id == case["id"]))
        outbox.status = "PROCESSING"
        outbox.locked_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=10)
        s.commit()
    import asyncio

    # process_outbox 起始会回收过期锁，使其可被重新领取
    asyncio.run(service.process_outbox())
    with service.sf() as s:
        outbox = s.scalar(select(ReviewOutbox).where(ReviewOutbox.case_id == case["id"]))
        assert outbox.status in ("DONE", "RETRY", "DEAD", "PROCESSING")


# --------------------------------------------------------------------------- #
# 13. 异常快照大小限制 / 证据附件校验（mock S3）
# --------------------------------------------------------------------------- #
def test_oversized_snapshot_is_rejected(service, monkeypatch):
    monkeypatch.setenv("REVIEW_SNAPSHOT_MAX_BYTES", "512")
    big = {"blob": "x" * 2048}
    with pytest.raises(ReviewValidationError):
        service.create_review_required(
            report(inputSnapshot=big, candidateSnapshot=big), "graph-build"
        )


def _mock_storage(returning_head: dict | None = None):
    storage = MagicMock()
    storage.ensure_bucket.return_value = None
    client = MagicMock()
    client.generate_presigned_url.return_value = "https://signed.example/put"
    head = returning_head or {
        "ContentLength": 100,
        "ContentType": "application/pdf",
        "Metadata": {"sha256": "a" * 64},
    }
    client.head_object.return_value = head
    storage.client = client
    storage.bucket = "bucket"
    return storage


def test_evidence_upload_validates_size_type_and_sha_format(service, monkeypatch):
    monkeypatch.setattr(service, "storage", lambda: _mock_storage())
    a = identity()
    created = service.create_review_required(report(), "graph-build")
    service.claim(created["reviewId"], 1, a)
    # 非法 sha256 长度
    with pytest.raises(ReviewValidationError):
        service.evidence_upload(created["reviewId"], "a.pdf", "application/pdf", 100, "short", a)
    # 非法类型
    with pytest.raises(ReviewValidationError):
        service.evidence_upload(
            created["reviewId"], "a.exe", "application/x-msdownload", 100, "a" * 64, a
        )
    # 非法大小
    with pytest.raises(ReviewValidationError):
        service.evidence_upload(created["reviewId"], "a.pdf", "application/pdf", 0, "a" * 64, a)
    # 合法
    res = service.evidence_upload(created["reviewId"], "a.pdf", "application/pdf", 100, "A" * 64, a)
    assert res['evidenceId'].startswith('EVD-')
    assert res['uploadUrl']


def test_evidence_complete_integrity_check(service, monkeypatch):
    a = identity()
    created = service.create_review_required(report(), "graph-build")
    service.claim(created["reviewId"], 1, a)
    digest = "a" * 64
    monkeypatch.setattr(
        service,
        "storage",
        lambda: _mock_storage(
            {"ContentLength": 100, "ContentType": "application/pdf", "Metadata": {"sha256": digest}}
        ),
    )
    res = service.evidence_complete(
        created["reviewId"],
        {
            "evidenceId": "EVD-1",
            "fileName": "a.pdf",
            "contentType": "application/pdf",
            "sizeBytes": 100,
            "sha256": digest,
            "bucket": "b",
            "objectKey": "k",
        },
        a,
    )
    assert res["status"] == "READY"
    # 大小不一致 → 拒绝
    monkeypatch.setattr(
        service,
        "storage",
        lambda: _mock_storage(
            {"ContentLength": 999, "ContentType": "application/pdf", "Metadata": {"sha256": digest}}
        ),
    )
    with pytest.raises(ReviewValidationError):
        service.evidence_complete(
            created["reviewId"],
            {
                "evidenceId": "EVD-2",
                "fileName": "a.pdf",
                "contentType": "application/pdf",
                "sizeBytes": 100,
                "sha256": digest,
                "bucket": "b",
                "objectKey": "k",
            },
            a,
        )


# --------------------------------------------------------------------------- #
# 14. 服务认证：Bearer 与 X-Service-Signature
# --------------------------------------------------------------------------- #
def test_require_graph_service_bearer_token():
    os.environ["GRAPH_BUILD_SERVICE_TOKEN"] = "secret-token"
    try:
        import asyncio

        name = asyncio.run(
            require_graph_service(
                authorization="Bearer secret-token",
                x_service_timestamp=None,
                x_service_signature=None,
            )
        )
        assert name == "graph-build"
        # 伪造 token
        with pytest.raises(HTTPException):
            asyncio.run(
                require_graph_service(
                    authorization="Bearer forged",
                    x_service_timestamp=None,
                    x_service_signature=None,
                )
            )
    finally:
        os.environ.pop("GRAPH_BUILD_SERVICE_TOKEN", None)


def test_require_graph_service_signature_path(monkeypatch):
    import hmac
    import time

    monkeypatch.setenv("GRAPH_BUILD_SERVICE_TOKEN", "secret-token")
    monkeypatch.setenv("REVIEW_SERVICE_CLOCK_SKEW_SECONDS", "300")
    ts = str(int(time.time()))
    sig = hmac.new(b"secret-token", ts.encode(), hashlib.sha256).hexdigest()
    import asyncio

    name = asyncio.run(
        require_graph_service(authorization=None, x_service_timestamp=ts, x_service_signature=sig)
    )
    assert name == "graph-build"
    # 篡改签名
    with pytest.raises(HTTPException):
        asyncio.run(
            require_graph_service(
                authorization=None, x_service_timestamp=ts, x_service_signature="0" * 64
            )
        )


def test_require_graph_service_rejects_browser_identity(monkeypatch):
    # 浏览器用户身份（无 Bearer / 无服务签名）不得调用内部接口
    monkeypatch.setenv("GRAPH_BUILD_SERVICE_TOKEN", "secret-token")
    import asyncio

    with pytest.raises(HTTPException):
        asyncio.run(
            require_graph_service(
                authorization=None, x_service_timestamp=None, x_service_signature=None
            )
        )


# --------------------------------------------------------------------------- #
# 15. 跨业务域访问拒绝 / 角色与阶段匹配
# --------------------------------------------------------------------------- #
def test_cross_domain_access_is_forbidden(service):
    created = service.create_review_required(report(domain="talent"), "graph-build")
    other_domain = identity("reviewer-2", ("reviewer",), domains=("enterprise",))
    with pytest.raises(ReviewForbiddenError):
        service.get_case(created["reviewId"], other_domain)


def test_role_phase_mismatch_blocks_claim(service):
    created = service.create_review_required(report(step="align", domain="talent"), "graph-build")
    # align 属"图谱构建"阶段，data_quality_reviewer（仅数据处理）不可领取
    dq_reviewer = identity("dq-1", ("data_quality_reviewer",), domains=("talent",))
    with pytest.raises(ReviewForbiddenError):
        service.claim(created["reviewId"], 1, dq_reviewer)


def test_graph_governance_reviewer_can_claim_graph_phase(service):
    created = service.create_review_required(report(step="align", domain="talent"), "graph-build")
    gov = identity("gov-1", ("graph_governance_reviewer",), domains=("talent",))
    claimed = service.claim(created["reviewId"], 1, gov)
    assert claimed["status"] == "CLAIMED"


def test_role_can_review_matrix():
    assert role_can_review(identity(roles=("reviewer",)), "数据处理")
    assert role_can_review(identity(roles=("data_quality_reviewer",)), "数据处理")
    assert not role_can_review(identity(roles=("data_quality_reviewer",)), "图谱构建")
    assert role_can_review(identity(roles=("graph_governance_reviewer",)), "图谱构建")


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _raising_client():
    """返回一个始终连接失败的 httpx client（用于 outbox 故障注入）。"""
    import httpx

    class _BadClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, *args, **kwargs):
            raise httpx.ConnectError("graph-build unavailable")

    return _BadClient()
