"""gray-gate-v2 纯策略单测（docs/人工审核专项方案复核_20261021.md 契约）。

覆盖：decisionPolicy 常量与版本门禁 / T_LINK 案 rank 表确定性路由 /
priorVerdict 三态处置 / canonicalization-v1 确定性 / sourceEventVersion 与
逻辑 ingress identity 的稳定性（密钥轮换口径）/ 失败关闭错误族零标识符。
"""

from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace

import pytest
from temporalio.exceptions import ApplicationError

from service.gray_gate import (
    AUTO_MERGE_ENABLED,
    GRAY_GATE_EVIDENCE_VERSION,
    GRAY_GATE_POLICY_VERSION,
    NAME_RULE_VERSION,
    BlockedByLegacyCaseError,
    DeferredMergeBlockedError,
    EventKeyUnavailableError,
    MergeCanonicalMissingError,
    UnknownPolicyVersionError,
    VerdictNotAppliedError,
    canonical_row_bytes,
    case_policy_rank,
    case_policy_version,
    compute_event_version,
    decision_policy,
    dedupe_identity_key,
    ingress_dedupe_key,
    prior_verdict_disposition,
    require_known_policy,
    select_capture_case,
)
from service.temporal_workflows import _fail_closed_error

# ---------------------------------------------------------------------------
# decisionPolicy：纯常量 + 版本门禁
# ---------------------------------------------------------------------------


class TestDecisionPolicy:
    def test_constants_are_frozen_contract(self):
        policy = decision_policy()
        assert policy["version"] == GRAY_GATE_POLICY_VERSION == "gray-gate-v2"
        assert policy["autoMergeEnabled"] is AUTO_MERGE_ENABLED is False
        assert policy["evidenceVersion"] == GRAY_GATE_EVIDENCE_VERSION == 2
        assert policy["nameRuleVersion"] == NAME_RULE_VERSION
        assert policy["weights"] == {"name": 0.6, "props": 0.4}
        assert policy["thresholds"] == {"merge": 0.85, "grayLow": 0.65, "margin": 0.08}

    def test_policy_is_pure_no_env_leak(self):
        # 纯常量：重放确定性——两次调用逐字节相等（activity 禁读环境改策略）
        import json

        assert json.dumps(decision_policy(), sort_keys=True) == json.dumps(
            decision_policy(), sort_keys=True
        )

    def test_require_known_policy_accepts_v2(self):
        policy = decision_policy()
        assert require_known_policy(policy) is policy

    @pytest.mark.parametrize("bad", [None, {}, {"version": "gray-gate-v3"}, {"version": ""}])
    def test_require_known_policy_rejects_unknown(self, bad):
        with pytest.raises(UnknownPolicyVersionError):
            require_known_policy(bad)


# ---------------------------------------------------------------------------
# rank 表路由：确定性选择 + 未登记版本失败关闭
# ---------------------------------------------------------------------------


def _case(cid, *, policy=None, created="2026-10-01 10:00:00", status="OPEN"):
    snap = {"_resolution": {"policyVersion": policy}} if policy is not None else {}
    return {"id": cid, "created_at": created, "status": status, "snapshot": snap}


class TestCasePolicyRouting:
    def test_rank_table_order(self):
        assert case_policy_rank("script-pending-gray-v1") == 0
        assert case_policy_rank("disambiguation-gray-v1") == 1
        assert case_policy_rank("gray-gate-v2") == 2
        assert case_policy_rank("gray-gate-v3") == 3

    def test_missing_version_is_lowest_rank(self):
        # 快照缺 _resolution.policyVersion 的存量碰撞案按最低 rank（v1 存量）
        assert case_policy_rank(None) == 0
        assert case_policy_rank("") == 0

    def test_unregistered_version_fails_closed(self):
        # 不做词法比较：未登记串直接失败关闭
        with pytest.raises(UnknownPolicyVersionError):
            case_policy_rank("gray-gate-v2-beta")

    def test_case_policy_version_shapes(self):
        assert case_policy_version(_case("c", policy="gray-gate-v2")) == "gray-gate-v2"
        assert case_policy_version(_case("c")) is None
        # ORM 形状：candidate_snapshot 为 JSON 字符串
        orm = SimpleNamespace(
            candidate_snapshot='{"_resolution": {"policyVersion": "gray-gate-v2"}}'
        )
        assert case_policy_version(orm) == "gray-gate-v2"
        # 损坏 JSON → None（按 rank 0 存量案处理，不崩）
        assert case_policy_version(SimpleNamespace(candidate_snapshot="{oops")) is None
        assert case_policy_version(SimpleNamespace(candidate_snapshot=None)) is None

    def test_select_prefers_highest_rank(self):
        v1 = _case("c-1", policy="disambiguation-gray-v1")
        v2 = _case("c-2", policy="gray-gate-v2")
        assert select_capture_case([v1, v2]) is v2

    def test_select_ties_break_earliest_then_lexicographic(self):
        a = _case("MR-B", policy="gray-gate-v2", created="2026-10-01 10:00:00")
        b = _case("MR-A", policy="gray-gate-v2", created="2026-10-01 10:00:00")
        c = _case("MR-Z", policy="gray-gate-v2", created="2026-10-02 09:00:00")
        assert select_capture_case([c, a, b]) is b  # 同 rank 同 created → case_id 字典序

    def test_select_all_v1_returns_none(self):
        # 无 v2 开放案 → None（调用方对残留 v1 案走 BLOCKED_BY_LEGACY_CASE）
        assert (
            select_capture_case([_case("c-1", policy="script-pending-gray-v1"), _case("c-2")])
            is None
        )

    def test_select_unregistered_version_raises(self):
        with pytest.raises(UnknownPolicyVersionError):
            select_capture_case([_case("c", policy="gray-gate-v3-rc1")])


# ---------------------------------------------------------------------------
# priorVerdict 三态处置（application 表权威）
# ---------------------------------------------------------------------------


class TestPriorVerdictDisposition:
    def test_reject_not_required_drops(self):
        assert prior_verdict_disposition(
            {"entityVerdict": "reject", "applyStatus": "NOT_REQUIRED"}
        ) == {"disposition": "drop_record"}

    def test_create_applied_writes_as_new(self):
        out = prior_verdict_disposition(
            {"entityVerdict": "create", "applyStatus": "APPLIED", "targetEntityId": "sch_1"}
        )
        assert out == {"disposition": "write_as_new", "vid": "sch_1"}

    def test_merge_applied_rewrites_to_canonical(self):
        out = prior_verdict_disposition(
            {"entityVerdict": "merge", "applyStatus": "APPLIED", "targetEntityId": "org_9"}
        )
        assert out == {"disposition": "rewrite_to_canonical", "vid": "org_9"}

    def test_merge_applied_without_canonical_fails_closed(self):
        with pytest.raises(MergeCanonicalMissingError):
            prior_verdict_disposition(
                {"entityVerdict": "merge", "applyStatus": "APPLIED", "targetEntityId": ""}
            )

    @pytest.mark.parametrize(
        "envelope",
        [
            {"entityVerdict": "create", "applyStatus": "APPLIED", "targetEntityId": ""},
            {"entityVerdict": "merge", "applyStatus": "FAILED", "targetEntityId": "x"},
            {"entityVerdict": "create", "applyStatus": "UNKNOWN"},
            {"entityVerdict": "reject", "applyStatus": "APPLIED"},
            {"entityVerdict": None, "applyStatus": None},
            {},
        ],
    )
    def test_unapplied_or_illegal_combos_fail_closed(self, envelope):
        # FAILED / UNKNOWN / 组合不合法：不猜测，VERDICT_NOT_APPLIED 失败关闭
        with pytest.raises(VerdictNotAppliedError):
            prior_verdict_disposition(envelope)


# ---------------------------------------------------------------------------
# canonicalization-v1：确定性字节（跨实现稳定、类型不坍缩、无拼接歧义）
# ---------------------------------------------------------------------------


class TestCanonicalization:
    def test_type_tags_do_not_collapse(self):
        # "1" / 1 / True 同值不同类型：字节必须不同（无盐哈希坍缩根因）
        assert canonical_row_bytes({"k": "1"}) != canonical_row_bytes({"k": 1})
        assert canonical_row_bytes({"k": 1}) != canonical_row_bytes({"k": True})
        assert canonical_row_bytes({"k": 1}) != canonical_row_bytes({"k": 1.0})

    def test_dict_key_order_irrelevant(self):
        assert canonical_row_bytes({"a": 1, "b": 2}) == canonical_row_bytes({"b": 2, "a": 1})

    def test_list_order_significant(self):
        assert canonical_row_bytes({"k": [1, 2]}) != canonical_row_bytes({"k": [2, 1]})

    def test_length_prefix_prevents_concat_ambiguity(self):
        # 拼接歧义：["ab","c"] 与 ["a","bc"] 必须字节不同
        assert canonical_row_bytes({"k": ["ab", "c"]}) != canonical_row_bytes({"k": ["a", "bc"]})

    def test_null_and_datetime_full_precision(self):
        assert canonical_row_bytes({"k": None}) != canonical_row_bytes({"k": ""})
        # 微秒精度不丢（源精度全量编入字节）
        assert canonical_row_bytes(
            {"k": datetime(2026, 10, 21, 1, 2, 3, 4)}
        ) != canonical_row_bytes({"k": datetime(2026, 10, 21, 1, 2, 3, 5)})
        assert canonical_row_bytes({"k": date(2026, 10, 21)}) != canonical_row_bytes(
            {"k": datetime(2026, 10, 21, 0, 0, 0)}
        )

    def test_nested_structures_deterministic(self):
        row = {"props": {"b": [1, {"x": None}], "a": "中文"}, "id": 7}
        assert canonical_row_bytes(row) == canonical_row_bytes(dict(reversed(list(row.items()))))


# ---------------------------------------------------------------------------
# sourceEventVersion + 逻辑 ingress identity
# ---------------------------------------------------------------------------


ROW = {"id": "r-1", "props": {"name": "张三", "org": "计算所"}}


class TestEventVersion:
    def test_declared_value_is_authoritative(self, monkeypatch):
        monkeypatch.delenv("GRAY_GATE_DEDUPE_IDENTITY_KEY", raising=False)
        # 声明值权威：不需要密钥（行字节不参与）
        version, basis = compute_event_version(ROW, declared_version="v-42")
        assert (version, basis) == ("v-42", "declared")

    def test_row_hmac_requires_key(self, monkeypatch):
        monkeypatch.setenv("GRAY_GATE_DEDUPE_IDENTITY_KEY", "k1")
        version, basis = compute_event_version(ROW)
        assert basis == "row-hmac"
        assert len(version) == 64  # HMAC-SHA256 hex
        # 同密钥同字节：稳定
        assert compute_event_version(dict(ROW))[0] == version

    def test_missing_key_fails_closed(self, monkeypatch):
        monkeypatch.delenv("GRAY_GATE_DEDUPE_IDENTITY_KEY", raising=False)
        with pytest.raises(EventKeyUnavailableError):
            compute_event_version(ROW)
        with pytest.raises(EventKeyUnavailableError):
            dedupe_identity_key()

    def test_key_rotation_changes_hmac_but_not_declared(self, monkeypatch):
        # 换钥 → row-hmac 版本换（换钥须显式 alias/重键迁移）；声明值不受影响
        monkeypatch.setenv("GRAY_GATE_DEDUPE_IDENTITY_KEY", "k1")
        v1 = compute_event_version(ROW)[0]
        monkeypatch.setenv("GRAY_GATE_DEDUPE_IDENTITY_KEY", "k2")
        v2 = compute_event_version(ROW)[0]
        assert v1 != v2
        assert compute_event_version(ROW, declared_version="v-42")[0] == "v-42"

    def test_item_hmac_for_empty_row(self, monkeypatch):
        monkeypatch.setenv("GRAY_GATE_DEDUPE_IDENTITY_KEY", "k1")
        assert compute_event_version(None)[1] == "item-hmac"


class TestIngressDedupeKey:
    def test_stable_across_calls(self):
        kwargs = dict(
            source_binding_id="bind-1",
            source_record_id="r-1",
            source_event_version="v-1",
            graph_space="dev2",
            node_label="Scholar",
            vid="sch_1",
        )
        assert ingress_dedupe_key(**kwargs) == ingress_dedupe_key(**kwargs)

    @pytest.mark.parametrize(
        "override",
        [
            {"source_binding_id": "bind-2"},
            {"source_record_id": "r-2"},
            {"source_event_version": "v-2"},  # 事件版本变化=新键允许新案
            {"graph_space": "other"},
            {"node_label": "Person"},
            {"vid": "sch_2"},
        ],
    )
    def test_every_material_component_matters(self, override):
        base = dict(
            source_binding_id="bind-1",
            source_record_id="r-1",
            source_event_version="v-1",
            graph_space="dev2",
            node_label="Scholar",
            vid="sch_1",
        )
        assert ingress_dedupe_key(**base) != ingress_dedupe_key(**{**base, **override})

    def test_reprocess_batch_extends_key(self):
        base = dict(
            source_binding_id="bind-1",
            source_record_id="r-1",
            source_event_version="v-1",
            graph_space="dev2",
            node_label="Scholar",
            vid="sch_1",
        )
        # 重处理批次是可选第七元：显式传入才进键（普通重跑命中同案）
        assert ingress_dedupe_key(**base) != ingress_dedupe_key(**base, reprocess_batch_id="rp-1")


# ---------------------------------------------------------------------------
# 失败关闭错误族：稳定错误码 + detail 零标识符 + 边界转换
# ---------------------------------------------------------------------------


class TestFailClosedErrors:
    def test_codes_are_stable(self):
        assert DeferredMergeBlockedError.code == "DEFERRED_MERGE_BLOCKED"
        assert BlockedByLegacyCaseError.code == "BLOCKED_BY_LEGACY_CASE"
        assert UnknownPolicyVersionError.code == "UNKNOWN_POLICY_VERSION"
        assert EventKeyUnavailableError.code == "EVENT_KEY_UNAVAILABLE"
        assert VerdictNotAppliedError.code == "VERDICT_NOT_APPLIED"
        assert MergeCanonicalMissingError.code == "MERGE_CANONICAL_MISSING"

    def test_detail_drops_none_values(self):
        err = VerdictNotAppliedError({"applyStatus": "UNKNOWN", "verdict": None})
        assert err.detail == {"applyStatus": "UNKNOWN"}

    def test_deferred_merge_detail_has_no_identifiers(self):
        # detail 只允许错误码/计数/标签名/边类型/版本/绑定/批次号——零 vid/rid
        err = DeferredMergeBlockedError(
            {"stage": "resolve", "score": 0.97, "autoMergeEnabled": False, "policyVersion": "x"}
        )
        assert set(err.detail) == {"stage", "score", "autoMergeEnabled", "policyVersion"}

    def test_boundary_conversion_non_retryable_application_error(self):
        err = BlockedByLegacyCaseError({"edgeType": "AUTHORED_BY", "openCaseCount": 1})
        app_err = _fail_closed_error(err)
        assert isinstance(app_err, ApplicationError)
        assert app_err.non_retryable is True
        assert app_err.type == "BLOCKED_BY_LEGACY_CASE"
        # temporalio ApplicationError.details 是位置可变参数收集的 Sequence
        assert list(app_err.details) == [{"edgeType": "AUTHORED_BY", "openCaseCount": 1}]

    def test_boundary_conversion_defaults(self):
        # 非错误族异常兜底 GRAY_GATE_FAIL_CLOSED；无 detail 不强塞负载
        app_err = _fail_closed_error(RuntimeError("boom"))
        assert app_err.type == "GRAY_GATE_FAIL_CLOSED"
        assert app_err.details == ()
