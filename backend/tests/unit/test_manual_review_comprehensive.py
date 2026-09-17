"""人工处理模块补充单元测试：模板契约 / 状态机 / RBAC / 附件边界。

graph-build 移交通道（内部入口 / correction / outbox / 服务认证）删除后，
本文件聚焦三个产活模板（T_DIRECT / T_LINK / T_EXTRACT_FAIL）的：
- 模板 result/action 契约、旧别名兼容、客户端 rerunStepId 全模板拒绝
- 建案幂等、乐观锁、P0 四方签核与双人审批、拒绝终态
- 附件上传校验（mock S3）、直判候选大小限制
- 跨业务域拒绝、角色与阶段匹配、过期领取回收
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db_model.base import Base
from db_model.manual_review import ReviewCase
from service.manual_review_domain import (
    PIPELINE_STEPS,
    RESULT_SCHEMAS,
    TEMPLATES,
    ReviewConflictError,
    ReviewForbiddenError,
    ReviewIdentity,
    ReviewValidationError,
    canonical_template,
    role_can_review,
    template_contract,
    validate_action,
    write_target,
)
from service.manual_review_production import ManualReviewService


# --------------------------------------------------------------------------- #
# 通用夹具
# --------------------------------------------------------------------------- #
@pytest.fixture
def service():
    engine = create_engine(
        "sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return ManualReviewService(sessionmaker(engine, expire_on_commit=False))


def identity(uid="reviewer-1", roles=("reviewer",), domains=("talent",)):
    return ReviewIdentity(uid, uid, frozenset(roles), frozenset(domains), "org", "req-1")


def direct_kwargs(**overrides):
    """同名冲突 T_LINK 建案参数（confidence 决定 P0/P1）。"""
    value = dict(
        task_id="TASK-1",
        execution_id="EXEC-1",
        step_id="align",
        kind="entity",
        candidate={
            "scholar_id": "S-1",
            "name_zh": "脱敏专家",
            "existingCandidates": [{"id": "E-1"}],
        },
        object_id="S-1",
        reason="同名冲突待人工裁决",
        confidence=0.9,
        domain="talent",
        template_id="T_LINK",
    )
    value.update(overrides)
    return value


def open_and_submit(service, action, result, **overrides):
    """直审模式：建案即 OPEN，get_case 取 version 后直接提交（无需领取）。"""
    created = service.create_direct_case(**direct_kwargs(**overrides))
    a = identity()
    case = service.get_case(created["reviewId"], a)  # 新建 case version=1（建案响应不含 version）
    return service.submit(case["id"], case["version"], action, result, "证据已核验", a), a


# --------------------------------------------------------------------------- #
# 1. 流水线节点契约 / 模板目录
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
    assert all(v["phase"] in {"数据处理", "图谱构建"} for v in PIPELINE_STEPS.values())


def test_templates_only_live_on_extract_and_align_nodes():
    # 移交通道删除后，仅 extract / align 节点挂产活模板；其余节点保留名称映射供存量展示
    assert PIPELINE_STEPS["extract"]["templates"] == {"T_EXTRACT_FAIL"}
    assert PIPELINE_STEPS["align"]["templates"] == {"T_LINK"}
    for step in ("source", "normalize", "schema", "validate", "persist"):
        assert PIPELINE_STEPS[step]["templates"] == set()


@pytest.mark.parametrize("tid", list(TEMPLATES))
def test_each_template_has_action_result_contract_and_write_target(tid):
    assert "title" in TEMPLATES[tid]
    assert "actions" in TEMPLATES[tid]
    assert "components" in TEMPLATES[tid]
    assert tid in RESULT_SCHEMAS
    assert write_target(tid)
    contract = template_contract(tid)
    assert contract["id"] == tid
    assert {"displaySchema", "resultSchema", "allowedActions"} <= set(contract)


def test_dormant_templates_are_gone_from_catalog():
    for tid in ("T_MAP", "T_DQ_FILL", "T_DQ_MERGE", "T_EVIDENCE", "T_ATTR", "T_RUNTIME"):
        assert tid not in TEMPLATES
        assert tid not in RESULT_SCHEMAS


# --------------------------------------------------------------------------- #
# 2. 产活模板 result/action 校验
# --------------------------------------------------------------------------- #
def test_action_validation_matrix_for_live_templates():
    cases = {
        "T_LINK": ("entity-confirm", {"entityVerdict": "create"}),
        "T_DIRECT": ("accept", {"accepted": True}),
        "T_EXTRACT_FAIL": ("rerun-record", {"rerun": True}),
    }
    for tid, (action, result) in cases.items():
        validate_action(tid, action, result)  # 不抛异常即通过
        with pytest.raises(ReviewValidationError):
            validate_action(tid, "not-a-real-action", result)


def test_entity_confirm_special_rules_enforced():
    # 缺裁决值 / merge 缺 targetEntityId
    with pytest.raises(ReviewValidationError):
        validate_action("T_LINK", "entity-confirm", {})
    with pytest.raises(ReviewValidationError):
        validate_action("T_LINK", "entity-confirm", {"entityVerdict": "merge"})
    with pytest.raises(ReviewValidationError):
        validate_action("T_LINK", "entity-confirm", {"entityVerdict": "unknown"})


@pytest.mark.parametrize("tid", list(TEMPLATES))
def test_client_supplied_rerun_step_id_is_rejected_for_every_template(tid):
    # rerunStepId 由服务端决定，客户端不得覆盖
    minimal = {
        "T_LINK": {"entityVerdict": "create"},
        "T_DIRECT": {"accepted": True},
        "T_EXTRACT_FAIL": {"rerun": True},
    }[tid]
    action = next(iter(TEMPLATES[tid]["actions"]))
    minimal["rerunStepId"] = "persist"
    with pytest.raises(ReviewValidationError):
        validate_action(tid, action, minimal)


def test_legacy_alias_t_entity_resolves_to_t_link():
    assert canonical_template("T_ENTITY") == "T_LINK"
    assert template_contract("T_ENTITY")["id"] == "T_LINK"


# --------------------------------------------------------------------------- #
# 3. 直审模式：提交即执行（无审批环节，P0 亦然）
# --------------------------------------------------------------------------- #
def test_submit_executes_immediately_for_all_risk_levels(service):
    # 直审模式：P0/P1 提交均直接落 RESOLVED，不产生 PENDING_APPROVAL
    for confidence in (0.4, 0.9):
        case, _ = open_and_submit(
            service,
            "entity-confirm",
            {"entityVerdict": "merge", "targetEntityId": "E-1"},
            confidence=confidence,
        )
        assert case["status"] == "RESOLVED"


def test_ingress_response_reports_object_isolation(service):
    created = service.create_direct_case(**direct_kwargs())
    assert created["isolationStrategy"] == "ISOLATE_OBJECT"
    assert created["status"] == "OPEN"


# --------------------------------------------------------------------------- #
# 4. 建案幂等（业务键：task+step+object+快照哈希）
# --------------------------------------------------------------------------- #
def test_create_is_idempotent_by_business_key(service):
    first = service.create_direct_case(**direct_kwargs())
    second = service.create_direct_case(**direct_kwargs())
    assert first["reviewId"] == second["reviewId"]
    assert second["duplicate"] is True


def test_different_object_id_creates_distinct_case(service):
    a = service.create_direct_case(**direct_kwargs())
    b = service.create_direct_case(**direct_kwargs(object_id="S-2", task_id="TASK-2"))
    assert a["reviewId"] != b["reviewId"]
    assert not b["duplicate"]


# --------------------------------------------------------------------------- #
# 5. 状态机 / 乐观锁 / 双人审批
# --------------------------------------------------------------------------- #
def test_optimistic_lock_blocks_stale_mutation(service):
    created = service.create_direct_case(**direct_kwargs())
    service.claim(created["reviewId"], 1, identity())
    with pytest.raises(ReviewConflictError):
        service.claim(created["reviewId"], 1, identity("reviewer-2"))


def test_claimed_by_other_blocks_submit(service):
    # 领取为可选保留：已被他人领取的 case 仍限领取人 / review_admin 提交
    created = service.create_direct_case(**direct_kwargs())
    service.claim(created["reviewId"], 1, identity("user-1"))
    detail = service.get_case(created["reviewId"], identity("user-2"))
    with pytest.raises(ReviewForbiddenError):
        service.submit(
            detail["id"],
            detail["version"],
            "entity-confirm",
            {"entityVerdict": "create"},
            "",
            identity("user-2"),
        )


def test_reject_candidate_terminates_with_completion_time(service):
    case, _ = open_and_submit(service, "reject-candidate", {"entityVerdict": "reject"})
    assert case["status"] == "RESOLVED"
    with service.sf() as s:
        row = s.get(ReviewCase, case["id"])
        assert row.completed_at is not None  # 终态记录完成时间


def test_reclaim_expired_returns_stale_claim_to_open(service):
    created = service.create_direct_case(**direct_kwargs())
    case = service.claim(created["reviewId"], 1, identity())
    with service.sf() as s:
        row = s.get(ReviewCase, case["id"])
        row.heartbeat_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=10)
        s.commit()
    assert service.reclaim_expired(minutes=5) == 1
    refreshed = service.get_case(case["id"], identity())
    assert refreshed["status"] == "OPEN"
    assert refreshed["assigneeId"] is None


# --------------------------------------------------------------------------- #
# 6. 直判候选大小限制
# --------------------------------------------------------------------------- #
def test_direct_decide_oversized_candidate_rejected(service, monkeypatch):
    monkeypatch.setenv("REVIEW_SNAPSHOT_MAX_BYTES", "512")
    created = service.create_direct_case(
        **direct_kwargs(step_id="extract", template_id="T_DIRECT", node_label="Scholar")
    )
    with pytest.raises(ReviewValidationError):
        service.direct_decide(
            created["reviewId"], 1, True, "", identity(), candidate={"blob": "x" * 2048}
        )


# --------------------------------------------------------------------------- #
# 7. 附件上传校验（mock S3）
# --------------------------------------------------------------------------- #
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
    created = service.create_direct_case(**direct_kwargs())
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
    assert res["evidenceId"].startswith("EVD-")
    assert res["uploadUrl"]


def test_evidence_complete_integrity_check(service, monkeypatch):
    a = identity()
    created = service.create_direct_case(**direct_kwargs())
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
# 8. 跨业务域访问拒绝 / 角色与阶段匹配
# --------------------------------------------------------------------------- #
def test_cross_domain_access_is_forbidden(service):
    created = service.create_direct_case(**direct_kwargs(domain="talent"))
    other_domain = identity("reviewer-2", ("reviewer",), domains=("enterprise",))
    with pytest.raises(ReviewForbiddenError):
        service.get_case(created["reviewId"], other_domain)


def test_role_phase_mismatch_blocks_claim(service):
    created = service.create_direct_case(**direct_kwargs())
    # 图谱构建阶段，data_quality_reviewer（仅数据处理）不可领取
    dq_reviewer = identity("dq-1", ("data_quality_reviewer",))
    with pytest.raises(ReviewForbiddenError):
        service.claim(created["reviewId"], 1, dq_reviewer)


def test_graph_governance_reviewer_can_claim_graph_phase(service):
    created = service.create_direct_case(**direct_kwargs())
    gov = identity("gov-1", ("graph_governance_reviewer",))
    claimed = service.claim(created["reviewId"], 1, gov)
    assert claimed["status"] == "CLAIMED"


def test_role_can_review_matrix():
    assert role_can_review(identity(roles=("reviewer",)), "数据处理")
    assert role_can_review(identity(roles=("data_quality_reviewer",)), "数据处理")
    assert not role_can_review(identity(roles=("data_quality_reviewer",)), "图谱构建")
    assert role_can_review(identity(roles=("graph_governance_reviewer",)), "图谱构建")


# --------------------------------------------------------------------------- #
# 9. 队列筛选（service 层 kind / category / 状态分组）
# --------------------------------------------------------------------------- #
def test_list_cases_kind_and_category_filters(service):
    link = service.create_direct_case(**direct_kwargs())
    extract = service.create_direct_case(
        **direct_kwargs(step_id="extract", template_id="T_EXTRACT_FAIL", task_id="TASK-X")
    )
    direct = service.create_direct_case(
        **direct_kwargs(
            step_id="seed",
            template_id="T_DIRECT",
            kind="relation",
            task_id="TASK-R",
            object_id="S-R",
        )
    )
    a = identity("admin-1", ("review_admin",))

    def ids(**f):
        return {x["id"] for x in service.list_cases(f, a)["items"]}

    assert link["reviewId"] in ids(kind="entity")  # T_LINK 兜底实体
    assert extract["reviewId"] in ids(kind="entity")
    assert direct["reviewId"] not in ids(kind="entity")
    assert direct["reviewId"] in ids(kind="relation")
    assert link["reviewId"] in ids(category="A")
    assert direct["reviewId"] in ids(category="A")
    assert extract["reviewId"] in ids(category="C")
    assert extract["reviewId"] not in ids(category="A")
    # 状态分组：pending=非终态
    pending = {x["id"] for x in service.list_cases({"status_group": "pending"}, a)["items"]}
    assert {link["reviewId"], extract["reviewId"], direct["reviewId"]} <= pending
