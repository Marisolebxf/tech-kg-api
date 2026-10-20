"""gray-gate-v2 审核服务层单测：来源账本 / park 版本化路由 / T_LINK 两段提交。

契约（docs/人工审核专项方案复核_20261021.md）：append_case_sources 唯一键幂等
与 evidence 上限；park_or_rewrite_edges 传 decisionPolicy 走 v2（rank 路由、
BLOCKED_BY_LEGACY_CASE、application 表权威三态），传 None 与旧行为逐字节一致；
submit 两段提交（Tx1 决议+意图标记 → 图写 → Tx2 APPLIED/FAILED 收敛，只从
UNKNOWN 收敛）。
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db_model.base import Base
from db_model.manual_review import ReviewCase, ReviewCaseSource, ReviewVerdictApplication
from service.gray_gate import BlockedByLegacyCaseError, UnknownPolicyVersionError, decision_policy
from service.manual_review_domain import ReviewIdentity, ReviewValidationError
from service.manual_review_production import ManualReviewService


def actor(uid="reviewer-1", roles=("reviewer",)):
    # create_direct_case 默认 domain="graph"，actor 域须覆盖（require_domain_access）
    return ReviewIdentity(uid, uid, frozenset(roles), frozenset({"graph"}), "org", "req-1")


@pytest.fixture
def service(monkeypatch: pytest.MonkeyPatch) -> ManualReviewService:
    engine = create_engine(
        "sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    svc = ManualReviewService(sessionmaker(engine, expire_on_commit=False))
    monkeypatch.setattr("service.manual_review_production.manual_review_service", svc)
    monkeypatch.setenv("GRAY_GATE_DEDUPE_IDENTITY_KEY", "unit-test-identity-key")
    return svc


def _source(record_id="r-1", *, execution="EXEC-1", binding="bind-1", evidence=None):
    return {
        "executionId": execution,
        "sourceBindingId": binding,
        "sourceRecordId": record_id,
        "sourceEventVersion": "v-1",
        "evidence": evidence if evidence is not None else {"stage": "resolve", "propKeys": ["org"]},
        "reason": "gray:resolve",
    }


def _link_case(service: ManualReviewService, *, vid="sch_new", policy="gray-gate-v2"):
    """建一个带 _incoming/_resolution 的 T_LINK 案（v2 建案快照形状）。"""
    candidate = {
        "name": "张三",
        "newIds": [vid],
        "existingCandidates": [{"vid": "sch_9", "name": "张三", "score": 0.8}],
        "_incoming": {
            "vid": vid,
            "props": {"name": "张三"},
            "sourceTable": "dwd.dwd_scholar",
            "sourceEventVersion": "v-1",
        },
        "_pendingRelations": [],
        "_graphSpace": "dev2",
        "_nodeLabel": "Scholar",
    }
    if policy is not None:
        candidate["_resolution"] = {
            "policyVersion": policy,
            "scoreDecision": "gray",
            "effectiveDisposition": "withhold_pending_review",
        }
    resp = service.create_direct_case(
        task_id="TASK-1",
        execution_id="EXEC-1",
        step_id="source:bind-1#main",
        kind="entity",
        candidate=candidate,
        object_id=vid,
        object_name="张三",
        node_label="Scholar",
        reason="消歧得分 0.80 落入灰区",
        confidence=0.8,
        template_id="T_LINK",
        graph_space="dev2",
    )
    return resp["reviewId"]


def _resolve(service, case_id, *, action="entity-confirm", result=None, fail=False):
    """直审提交；fail=True 时图写（_apply_link_verdict）抛错模拟 Tx2 失败。"""
    applied: list = []

    def fake_apply(_self, c, r):
        # 赋给类属性后按方法绑定（self 随绑定传入），首参收 self
        applied.append((c.id, dict(r)))
        if fail:
            raise RuntimeError("graph write boom")
        return {"applied": True, "vid": r.get("targetEntityId") or c.object_id}

    orig = ManualReviewService._apply_link_verdict
    ManualReviewService._apply_link_verdict = fake_apply  # type: ignore[method-assign]
    try:
        detail = service.submit(
            case_id, 1, action, result or {"entityVerdict": "create"}, "测试裁决", actor()
        )
    finally:
        ManualReviewService._apply_link_verdict = orig  # type: ignore[method-assign]
    return detail, applied


def _app_row(service, case_id):
    with service.sf() as s:
        return s.scalar(
            select(ReviewVerdictApplication).where(ReviewVerdictApplication.case_id == case_id)
        )


def _open_case_status(service, case_id):
    with service.sf() as s:
        return s.scalar(select(ReviewCase.status).where(ReviewCase.id == case_id))


# ---------------------------------------------------------------------------
# append_case_sources：唯一键幂等 + evidence 上限 + 计数
# ---------------------------------------------------------------------------


class TestAppendCaseSources:
    def test_append_and_counts(self, service):
        case_id = _link_case(service)
        out = service.append_case_sources(case_id, [_source("r-1"), _source("r-2")])
        assert out == {"appended": 2, "skipped": 0}
        with service.sf() as s:
            case = s.scalar(select(ReviewCase).where(ReviewCase.id == case_id))
            rows = s.scalars(select(ReviewCaseSource)).all()
        assert case.source_count == 2
        assert case.source_truncated_count == 0
        assert len(rows) == 2
        # evidence 只存字段名/布尔/版本（零业务值），JSON 落库
        ev = json.loads(rows[0].evidence)
        assert ev == {"stage": "resolve", "propKeys": ["org"]}

    def test_replay_same_triple_is_idempotent(self, service):
        case_id = _link_case(service)
        service.append_case_sources(case_id, [_source("r-1")])
        out = service.append_case_sources(case_id, [_source("r-1")])
        assert out == {"appended": 0, "skipped": 1}
        with service.sf() as s:
            case = s.scalar(select(ReviewCase).where(ReviewCase.id == case_id))
            assert case.source_count == 1  # 不加计
            assert len(s.scalars(select(ReviewCaseSource.id)).all()) == 1

    def test_same_record_new_execution_appends(self, service):
        # 唯一键是 (case_id, execution_id, source_record_id)：跨执行重跑同源
        # 记录是新来源行（execution 只做审计，不参与逻辑键）
        case_id = _link_case(service)
        service.append_case_sources(case_id, [_source("r-1", execution="EXEC-1")])
        out = service.append_case_sources(case_id, [_source("r-1", execution="EXEC-2")])
        assert out["appended"] == 1
        with service.sf() as s:
            case = s.scalar(select(ReviewCase).where(ReviewCase.id == case_id))
        assert case.source_count == 2

    def test_evidence_cap_after_32_sources(self, service):
        case_id = _link_case(service)
        for start in range(0, 40, 10):
            service.append_case_sources(case_id, [_source(f"r-{start + i}") for i in range(10)])
        with service.sf() as s:
            case = s.scalar(select(ReviewCase).where(ReviewCase.id == case_id))
            rows = s.scalars(select(ReviewCaseSource).order_by(ReviewCaseSource.id)).all()
        assert case.source_count == 40
        assert case.source_truncated_count == 8  # 40 - 32
        with_evidence = [r for r in rows if r.evidence]
        assert len(with_evidence) == service.CASE_SOURCE_EVIDENCE_LIMIT
        assert not rows[32].evidence  # 第 33 行起 evidence 置空（行本身仍插入）

    def test_evidence_truncated_to_2kb(self, service):
        case_id = _link_case(service)
        big = {"propKeys": ["k" * 3000]}
        service.append_case_sources(case_id, [_source("r-1", evidence=big)])
        with service.sf() as s:
            row = s.scalar(select(ReviewCaseSource))
        assert len(row.evidence) <= 2000

    def test_missing_case_is_noop(self, service):
        assert service.append_case_sources("MR-X", [_source()]) == {
            "appended": 0,
            "skipped": 0,
            "missingCase": True,
        }

    def test_empty_sources_noop(self, service):
        assert service.append_case_sources("any", []) == {"appended": 0, "skipped": 0}


# ---------------------------------------------------------------------------
# park_or_rewrite_edges：v2 版本化路由 / legacy 失败关闭 / v1 路径不变
# ---------------------------------------------------------------------------


def _edge(frm="sch_new", to="paper_1"):
    return {"fromId": frm, "toId": to, "props": {"weight": 1}}


class TestParkEdgesV2:
    def test_open_v2_case_captures_edge(self, service):
        case_id = _link_case(service, vid="sch_new")  # policyVersion=gray-gate-v2
        out = service.park_or_rewrite_edges(
            "AUTHORED_BY", [_edge()], "dev2", decision_policy=decision_policy()
        )
        assert out["parked"] == 1 and out["records"] == [] and out["dropped"] == 0
        with service.sf() as s:
            case = s.scalar(select(ReviewCase).where(ReviewCase.id == case_id))
            snapshot = json.loads(case.candidate_snapshot)
        assert snapshot["_pendingRelations"] == [
            {
                "edgeType": "AUTHORED_BY",
                "fromId": "sch_new",
                "toId": "paper_1",
                "props": {"weight": 1},
            }
        ]
        # 重放幂等：同边不重复挂
        out2 = service.park_or_rewrite_edges(
            "AUTHORED_BY", [_edge()], "dev2", decision_policy=decision_policy()
        )
        assert out2["parked"] == 1
        with service.sf() as s:
            snapshot2 = json.loads(
                s.scalar(select(ReviewCase).where(ReviewCase.id == case_id)).candidate_snapshot
            )
        assert len(snapshot2["_pendingRelations"]) == 1

    def test_legacy_only_open_case_fails_closed(self, service):
        # 只有 v1 强制案（script-pending-gray-v1）开放：不「计数后继续」
        _link_case(service, vid="sch_legacy", policy="script-pending-gray-v1")
        with pytest.raises(BlockedByLegacyCaseError) as ei:
            service.park_or_rewrite_edges(
                "AUTHORED_BY", [_edge(frm="sch_legacy")], "dev2", decision_policy=decision_policy()
            )
        assert ei.value.detail == {
            "edgeType": "AUTHORED_BY",
            "blockedEndpointCount": 1,
            "openCaseCount": 1,
        }

    def test_mixed_open_cases_route_to_v2(self, service):
        # 同 vid 同时挂 v1 案与 v2 案：rank 路由到 v2（v1 案不动）
        _link_case(service, vid="sch_mix", policy="disambiguation-gray-v1")
        v2_id = _link_case(service, vid="sch_mix", policy="gray-gate-v2")
        out = service.park_or_rewrite_edges(
            "AUTHORED_BY", [_edge(frm="sch_mix")], "dev2", decision_policy=decision_policy()
        )
        assert out["parked"] == 1
        with service.sf() as s:
            snapshot = json.loads(
                s.scalar(select(ReviewCase).where(ReviewCase.id == v2_id)).candidate_snapshot
            )
        assert len(snapshot["_pendingRelations"]) == 1

    def test_terminal_v2_merge_rewrites_endpoint(self, service):
        # R7：merge 重放的 canonical 只能来自经批准的持久 remap（方案 A 另批）——
        # 应用行/决议目标不得充当映射，未登记即 MERGE_CANONICAL_MISSING 失败关闭
        case_id = _link_case(service, vid="sch_t")
        _resolve(
            service,
            case_id,
            result={"entityVerdict": "merge", "targetEntityId": "sch_9"},
        )
        from service.gray_gate import (
            MergeCanonicalMissingError,
            register_canonical_remap_resolver,
        )

        with pytest.raises(MergeCanonicalMissingError) as ei:
            service.park_or_rewrite_edges(
                "AUTHORED_BY", [_edge(frm="sch_t")], "dev2", decision_policy=decision_policy()
            )
        assert ei.value.detail == {"reason": "remap_unavailable"}
        register_canonical_remap_resolver({"sch_t": "sch_9"}.get)
        try:
            out = service.park_or_rewrite_edges(
                "AUTHORED_BY", [_edge(frm="sch_t")], "dev2", decision_policy=decision_policy()
            )
            assert out["records"] == [{**_edge(frm="sch_t"), "fromId": "sch_9"}]
            assert out["parked"] == 0 and out["dropped"] == 0
        finally:
            register_canonical_remap_resolver(None)

    def test_terminal_v2_reject_drops_edge(self, service):
        case_id = _link_case(service, vid="sch_t")
        _resolve(service, case_id, action="reject-candidate", result={"entityVerdict": "reject"})
        out = service.park_or_rewrite_edges(
            "AUTHORED_BY", [_edge(frm="sch_t")], "dev2", decision_policy=decision_policy()
        )
        assert out == {"records": [], "parked": 0, "dropped": 1}

    def test_terminal_v2_create_keeps_reserved_vid(self, service):
        case_id = _link_case(service, vid="sch_t")
        _resolve(service, case_id, result={"entityVerdict": "create"})
        out = service.park_or_rewrite_edges(
            "AUTHORED_BY", [_edge(frm="sch_t")], "dev2", decision_policy=decision_policy()
        )
        # write_as_new：端点即预留 vid（create 图写已落），原样放行
        assert out == {"records": [_edge(frm="sch_t")], "parked": 0, "dropped": 0}

    def test_terminal_v2_without_application_row_fails_closed(self, service):
        # 决议 RESOLVED 不再隐含「图已写」：缺 application 行=UNKNOWN 失败关闭
        case_id = _link_case(service, vid="sch_t")
        detail = _resolve(service, case_id, result={"entityVerdict": "create"})[0]
        assert detail["status"] == "RESOLVED"
        with service.sf() as s:
            s.query(ReviewVerdictApplication).delete()
            s.commit()
        from service.gray_gate import VerdictNotAppliedError

        with pytest.raises(VerdictNotAppliedError):
            service.park_or_rewrite_edges(
                "AUTHORED_BY", [_edge(frm="sch_t")], "dev2", decision_policy=decision_policy()
            )

    def test_terminal_v1_snapshot_with_application_row_is_authoritative(self, service):
        # v1 快照案经 v2 两段提交：application 行同样权威——merge 重放不因快照
        # 版本回退决议目标直接放行，仍走持久 remap（R7）
        case_id = _link_case(service, vid="sch_old", policy="disambiguation-gray-v1")
        _resolve(service, case_id, result={"entityVerdict": "merge", "targetEntityId": "sch_9"})
        from service.gray_gate import MergeCanonicalMissingError

        with pytest.raises(MergeCanonicalMissingError):
            service.park_or_rewrite_edges(
                "AUTHORED_BY", [_edge(frm="sch_old")], "dev2", decision_policy=decision_policy()
            )

    def test_terminal_v1_without_application_row_reject_drops(self, service):
        # 真 v1 终态案（无任何 application 行）：回落决议读取——reject=不写图的
        # 保守处置，语义可靠
        case_id = _link_case(service, vid="sch_old", policy="script-pending-gray-v1")
        _resolve(service, case_id, action="reject-candidate", result={"entityVerdict": "reject"})
        with service.sf() as s:
            s.query(ReviewVerdictApplication).delete()
            s.commit()
        out = service.park_or_rewrite_edges(
            "AUTHORED_BY", [_edge(frm="sch_old")], "dev2", decision_policy=decision_policy()
        )
        assert out == {"records": [], "parked": 0, "dropped": 1}

    def test_terminal_v1_without_application_row_merge_fails_closed(self, service):
        # 真 v1 终态案的 merge 无应用权威：按 UNKNOWN 失败关闭（历史强制案禁
        # merge/create 仅留 reject，收口口径）
        case_id = _link_case(service, vid="sch_old", policy="script-pending-gray-v1")
        _resolve(service, case_id, result={"entityVerdict": "merge", "targetEntityId": "sch_9"})
        with service.sf() as s:
            s.query(ReviewVerdictApplication).delete()
            s.commit()
        from service.gray_gate import VerdictNotAppliedError

        with pytest.raises(VerdictNotAppliedError):
            service.park_or_rewrite_edges(
                "AUTHORED_BY", [_edge(frm="sch_old")], "dev2", decision_policy=decision_policy()
            )

    def test_unregistered_snapshot_version_fails_closed(self, service):
        _link_case(service, vid="sch_x", policy="gray-gate-v3-rc1")
        with pytest.raises(UnknownPolicyVersionError):
            service.park_or_rewrite_edges(
                "AUTHORED_BY", [_edge(frm="sch_x")], "dev2", decision_policy=decision_policy()
            )

    def test_no_policy_keeps_v1_behavior(self, service):
        # decision_policy=None（在飞旧 run 重放）：v1 案照旧收边（逐字节不变）
        case_id = _link_case(service, vid="sch_v1", policy="script-pending-gray-v1")
        out = service.park_or_rewrite_edges("AUTHORED_BY", [_edge(frm="sch_v1")], "dev2")
        assert out["parked"] == 1
        with service.sf() as s:
            snapshot = json.loads(
                s.scalar(select(ReviewCase).where(ReviewCase.id == case_id)).candidate_snapshot
            )
        assert len(snapshot["_pendingRelations"]) == 1

    def test_graph_space_filters_cases(self, service):
        # vid 跨空间同名、T_LINK 案按空间归属：其它空间的案不拦本空间的边
        _link_case(service, vid="sch_sp")  # graph_space=dev2
        out = service.park_or_rewrite_edges(
            "AUTHORED_BY", [_edge(frm="sch_sp")], "other_space", decision_policy=decision_policy()
        )
        assert out == {"records": [_edge(frm="sch_sp")], "parked": 0, "dropped": 0}


# ---------------------------------------------------------------------------
# submit 两段提交（Tx1 决议+意图标记 → 图写 → Tx2 收敛）
# ---------------------------------------------------------------------------


class TestSubmitTwoPhase:
    def test_reject_candidate_marks_not_required_without_graph(self, service):
        case_id = _link_case(service)
        detail, applied = _resolve(
            service, case_id, action="reject-candidate", result={"entityVerdict": "reject"}
        )
        assert detail["status"] == "RESOLVED"
        assert applied == []  # 无图写路径：第二段不触发
        app = _app_row(service, case_id)
        assert (app.verdict, app.apply_status) == ("reject", "NOT_REQUIRED")
        assert app.applied_at is None  # NOT_REQUIRED 建行即终态，无需收敛

    def test_create_success_converges_applied(self, service):
        case_id = _link_case(service, vid="sch_new")
        detail, applied = _resolve(service, case_id, result={"entityVerdict": "create"})
        assert detail["status"] == "RESOLVED"
        assert applied and applied[0][0] == case_id  # 图写确实被调
        app = _app_row(service, case_id)
        assert app.apply_status == "APPLIED"
        assert app.reserved_vid == "sch_new"
        assert app.applied_at is not None

    def test_merge_records_canonical_and_applies(self, service):
        case_id = _link_case(service)
        _, applied = _resolve(
            service, case_id, result={"entityVerdict": "merge", "targetEntityId": "sch_9"}
        )
        app = _app_row(service, case_id)
        assert (app.verdict, app.apply_status, app.canonical_vid) == (
            "merge",
            "APPLIED",
            "sch_9",
        )
        assert applied[0][1]["targetEntityId"] == "sch_9"

    def test_graph_write_failure_marks_failed_and_case_apply_failed(self, service):
        case_id = _link_case(service, vid="sch_bad")
        with pytest.raises(RuntimeError, match="graph write boom"):
            _resolve(service, case_id, result={"entityVerdict": "create"}, fail=True)
        app = _app_row(service, case_id)
        assert app.apply_status == "FAILED"
        assert app.error_code == "RuntimeError"
        assert app.applied_at is None
        assert _open_case_status(service, case_id) == "APPLY_FAILED"  # 进 failed 队列

    def test_merge_target_outside_candidates_rejected_before_tx1(self, service):
        # 输入问题（目标不在候选集）在 Tx1 前拒绝：案保持可提交
        case_id = _link_case(service)
        with pytest.raises(ReviewValidationError):
            _resolve(
                service, case_id, result={"entityVerdict": "merge", "targetEntityId": "sch_ghost"}
            )
        assert _open_case_status(service, case_id) == "OPEN"
        assert _app_row(service, case_id) is None  # 未落意图标记

    def test_finish_only_converges_from_unknown(self, service):
        # 幂等重放不覆盖：已 FAILED 的标记不会被后到的 APPLIED 改写
        case_id = _link_case(service, vid="sch_f")
        with pytest.raises(RuntimeError):
            _resolve(service, case_id, result={"entityVerdict": "create"}, fail=True)
        service._finish_verdict_application(case_id, actor(), "entity-confirm", "APPLIED")
        app = _app_row(service, case_id)
        assert app.apply_status == "FAILED"


# ---------------------------------------------------------------------------
# R5：APPLY_FAILED 案的 ingress 应答失败关闭（不得当开放案吞新来源）
# ---------------------------------------------------------------------------


class TestIngressResponseR5:
    def _to_apply_failed(self, service, case_id):
        with service.sf() as s:
            c = s.get(ReviewCase, case_id)
            c.status = "APPLY_FAILED"
            s.add(
                ReviewVerdictApplication(
                    case_id=case_id,
                    verdict="create",
                    apply_status="FAILED",
                    created_at=c.created_at,
                    updated_at=c.updated_at,
                )
            )
            s.commit()

    def test_apply_failed_duplicate_ingress_fails_closed(self, service):
        from service.gray_gate import VerdictNotAppliedError

        case_id = _link_case(service)
        self._to_apply_failed(service, case_id)
        with service.sf() as s:
            c = s.get(ReviewCase, case_id)
            with pytest.raises(VerdictNotAppliedError) as ei:
                service._ingress_response(c, True, session=s)
        assert ei.value.detail == {"applyStatus": "FAILED", "caseStatus": "APPLY_FAILED"}

    def test_apply_failed_without_marker_row_is_unknown(self, service):
        # 缺整行=UNKNOWN 崩溃窗口收敛态：同样失败关闭，不猜测图写结果
        from service.gray_gate import VerdictNotAppliedError

        case_id = _link_case(service)
        with service.sf() as s:
            c = s.get(ReviewCase, case_id)
            c.status = "APPLY_FAILED"
            s.commit()
            with pytest.raises(VerdictNotAppliedError) as ei:
                service._ingress_response(c, True, session=s)
        assert ei.value.detail == {"applyStatus": "UNKNOWN", "caseStatus": "APPLY_FAILED"}

    def test_find_ingress_case_round_trip(self, service):
        # R2 查询侧回环：纯源事件材料命中同一案——开放案=普通重复应答
        material = ["bind-1", "row-1", "v-1", "dev2", "Scholar", "sch_x"]
        resp = service.create_direct_case(
            task_id="TASK-1",
            execution_id="EXEC-1",
            step_id="source:bind-1#main",
            kind="entity",
            candidate={"name": "张三"},
            object_id="sch_x",
            object_name="张三",
            node_label="Scholar",
            reason="灰区",
            confidence=0.8,
            template_id="T_LINK",
            graph_space="dev2",
            dedupe_material=material,
        )
        assert resp["duplicate"] is False
        hit = service.find_ingress_case(material)
        assert hit["reviewId"] == resp["reviewId"]
        assert hit["duplicate"] is True and "priorVerdict" not in hit
        assert service.find_ingress_case(["bind-1", "row-9", "v-2", "dev2", "Scholar", "y"]) is None

    def test_find_ingress_case_apply_failed_fails_closed(self, service):
        from service.gray_gate import VerdictNotAppliedError

        material = ["bind-1", "row-1", "v-1", "dev2", "Scholar", "sch_x"]
        resp = service.create_direct_case(
            task_id="TASK-1",
            execution_id="EXEC-1",
            step_id="source:bind-1#main",
            kind="entity",
            candidate={"name": "张三"},
            object_id="sch_x",
            object_name="张三",
            node_label="Scholar",
            reason="灰区",
            confidence=0.8,
            template_id="T_LINK",
            graph_space="dev2",
            dedupe_material=material,
        )
        self._to_apply_failed(service, resp["reviewId"])
        with pytest.raises(VerdictNotAppliedError):
            service.find_ingress_case(material)


# ---------------------------------------------------------------------------
# R6：裁决后补边双端点统一路由（另一端未决转交 / 端点存在性终判）
# ---------------------------------------------------------------------------


class TestFlushPendingRelationsR6:
    def _fake_graph(self, monkeypatch):
        from types import SimpleNamespace

        edges: list = []
        fake = SimpleNamespace(create_edge=lambda f, t, e, p: edges.append((f, t)))
        monkeypatch.setattr(ManualReviewService, "_graph_client_for", lambda *a: fake)
        monkeypatch.setattr(ManualReviewService, "_insert_withheld_vertex", lambda *a: None)
        monkeypatch.setattr(ManualReviewService, "_coerce_to_schema", lambda *a, **k: {})
        monkeypatch.setattr(ManualReviewService, "_edge_fields", lambda *a: set())
        monkeypatch.setattr(ManualReviewService, "_sync_entity_search_after_write", lambda *a: None)
        return edges

    def test_other_open_endpoint_captures_flushed_edge(self, service, monkeypatch):
        # 探针⑦回归：a 案 create 裁决补边——b 端仍有开放案 → 边转交 b 案，
        # 不绕过第二端扣留直接写图
        a_id = _link_case(service, vid="a")
        b_id = _link_case(service, vid="b")
        service.park_or_rewrite_edges(
            "LINK",
            [{"fromId": "a", "toId": "b", "props": {}}],
            "dev2",
            decision_policy=decision_policy(),
        )
        edges = self._fake_graph(monkeypatch)
        service.submit(a_id, 1, "entity-confirm", {"entityVerdict": "create"}, "裁决", actor())
        assert edges == []  # 没有直接写边
        with service.sf() as s:
            snap_a = json.loads(s.get(ReviewCase, a_id).candidate_snapshot)
            snap_b = json.loads(s.get(ReviewCase, b_id).candidate_snapshot)
        assert snap_a["_pendingRelations"] == []  # 已处置边从本案摘除
        assert snap_b["_pendingRelations"] == [
            {"edgeType": "LINK", "fromId": "a", "toId": "b", "props": {}}
        ]
        # 图写明细入 VERDICT_APPLIED audit（补边去向可审计）
        from db_model.manual_review import ReviewAuditLog

        with service.sf() as s:
            row = s.scalar(
                select(ReviewAuditLog).where(
                    ReviewAuditLog.case_id == a_id, ReviewAuditLog.event_type == "VERDICT_APPLIED"
                )
            )
        assert json.loads(row.detail)["pendingRelationsParked"] == 1

    def test_missing_endpoint_fails_closed_no_hanging_edge(self, service, monkeypatch):
        # 另一端无案但图中不存在 → 存在性终判失败关闭（案 APPLY_FAILED，零写边）
        from types import SimpleNamespace

        a_id = _link_case(service, vid="a")
        with service.sf() as s:
            c = s.get(ReviewCase, a_id)
            snap = json.loads(c.candidate_snapshot)
            snap["_pendingRelations"] = [
                {"edgeType": "LINK", "fromId": "a", "toId": "ghost", "props": {}}
            ]
            c.candidate_snapshot = json.dumps(snap, ensure_ascii=False)
            s.commit()
        edges = self._fake_graph(monkeypatch)
        # 存在性探针：ghost 不存在
        monkeypatch.setattr(
            ManualReviewService,
            "_graph_client_for",
            lambda *a: SimpleNamespace(
                create_edge=lambda f, t, e, p: edges.append((f, t)),
                get_node=lambda vid: None,
            ),
        )
        from service.manual_review_domain import ReviewConflictError

        with pytest.raises((RuntimeError, ReviewConflictError)):
            service.submit(a_id, 1, "entity-confirm", {"entityVerdict": "create"}, "裁决", actor())
        assert edges == []
        assert _open_case_status(service, a_id) == "APPLY_FAILED"
        app = _app_row(service, a_id)
        assert app.apply_status == "FAILED"


# ---------------------------------------------------------------------------
# R8：详情富化不覆盖建案证据（重算进 recheck，带取数时点）
# ---------------------------------------------------------------------------


class TestDetailEnrichR8:
    def _case_with_props(self, service, *, evidence_fields: bool):
        case_id = _link_case(service)
        with service.sf() as s:
            c = s.get(ReviewCase, case_id)
            snap = json.loads(c.candidate_snapshot)
            snap["_incoming"]["props"] = {"name": "张三", "org": "A"}
            if evidence_fields:
                # v2 建案快照：候选带证据字段（建案时点 propsAgree=0.5）
                snap["existingCandidates"][0].update(
                    propsAgree=0.5, propCompared=0, propMatched=0, comparedProps=[]
                )
            s.commit()
            return c, snap

    def test_build_time_evidence_read_only_recheck_recorded(self, service, monkeypatch):
        # 探针⑧回归：当前图库属性与建案时点一致甚至变化——建案证据字段一律
        # 只读，重算结果进独立 recheck（带 asOf 时点），不与总分互相矛盾
        c, snap = self._case_with_props(service, evidence_fields=True)
        monkeypatch.setattr(ManualReviewService, "_graph_client_for", lambda *a: object())
        monkeypatch.setattr(
            ManualReviewService,
            "_es_same_name_by_vid",
            lambda *a: {"sch_9": {"props": {"name": "张三", "org": "A"}}},
        )
        out = service._enrich_link_snapshot(c, snap)
        cand = out["existingCandidates"][0]
        assert cand["propsAgree"] == 0.5  # 建案证据不被覆盖
        assert cand["score"] == 0.8  # 总分同为建案时点
        assert "recheck" in cand
        assert cand["recheck"]["nameSim"] == 1.0
        assert cand["recheck"]["propsAgree"] == 1.0  # 重算如实呈现当前图库
        assert cand["recheck"]["comparedProps"] == [{"key": "org", "match": True, "side": "both"}]
        assert out["_enriched"]["asOf"]

    def test_v1_snapshot_enriched_in_place(self, service, monkeypatch):
        # v1 存量快照（候选无证据字段）：向后兼容原位补齐，无 recheck
        c, snap = self._case_with_props(service, evidence_fields=False)
        monkeypatch.setattr(ManualReviewService, "_graph_client_for", lambda *a: object())
        monkeypatch.setattr(
            ManualReviewService,
            "_es_same_name_by_vid",
            lambda *a: {"sch_9": {"props": {"name": "张三", "org": "A"}}},
        )
        out = service._enrich_link_snapshot(c, snap)
        cand = out["existingCandidates"][0]
        assert cand["nameSim"] == 1.0 and cand["propsAgree"] == 1.0
        assert "recheck" not in cand
