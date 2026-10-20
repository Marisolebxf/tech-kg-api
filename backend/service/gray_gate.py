"""gray-gate-v2 策略与失败关闭契约（人工审核灰区门控专项第一阶段）。

docs/人工审核专项方案复核_20261021.md 九轮往来收口契约的代码落点：

- ``decisionPolicy`` 在 workflow 启动时解析一次、固化进 Temporal 输入
  （``decision_policy()`` 纯常量，activity 内禁止再读环境变量改策略）；
  ``autoMergeEnabled=false``——scoreDecision=merge 不是真实灰区，remap 未就绪
  时统一 ``DEFERRED_MERGE_BLOCKED`` 失败关闭：不写实体、不放行引用旧 VID 的边、
  不建 T_LINK、不伪装任何状态，受影响来源水位不推进，执行转 FAILED；
- 失败关闭错误族（``GrayGateFailClosedError`` 子类）：全部不可重试、payload
  零标识符（原始 vid / rid 一律不进错误负载，完整清单走受控 claim-check）；
- 逻辑 ingress identity：``sha([sourceBindingId, sourceRecordId,
  sourceEventVersion, graph_space, nodeLabel, vid, reprocessBatchId?])``——
  纯源事件身份，execution_id 只进来源行审计字段；decisionPolicyVersion 与
  scoringRuleVersion 都不进键（换版重跑不换键，重放命中同一案）；
  sourceEventVersion：声明值权威，否则 canonicalization-v1 行字节全量
  HMAC-SHA256（dedupe 专用身份密钥，无盐哈希已废除）；
- T_LINK 案 policyVersion 显式 rank 表：同 VID 多案确定性路由（rank 降序 →
  created_at 升序 → case_id 字典序）；未登记版本失败关闭，不做词法比较。
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import struct
from collections.abc import Callable, Mapping
from datetime import date, datetime
from typing import Any


def _sha(value: Any) -> str:
    """与 manual_review_production.sha 同构（json 规范化 + sha256）。

    本地复制避免与 mrp 的循环 import（mrp 的 park/priorVerdict 反向依赖本模块）。
    """
    payload = json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True, default=str
    )
    return hashlib.sha256(payload.encode()).hexdigest()


# ---------------------------------------------------------------------------
# decisionPolicy（workflow 启动时解析一次，进 Temporal 输入后不再变化）
# ---------------------------------------------------------------------------

GRAY_GATE_POLICY_VERSION = "gray-gate-v2"
GRAY_GATE_EVIDENCE_VERSION = 2
# 名称规则版本：_NAME_KEYS 优先级 + normalize_alignment_text 归一
NAME_RULE_VERSION = "normalized-displayname-v1"
AUTO_MERGE_ENABLED = False

# 已实施（可被 activity 接受）的 decisionPolicy 版本。v3（auto-merge + remap）
# 另行审批，未实施——传入即 UNKNOWN_POLICY_VERSION 失败关闭。
KNOWN_POLICY_VERSIONS = frozenset({GRAY_GATE_POLICY_VERSION})


def decision_policy() -> dict[str, Any]:
    """gray-gate-v2 决策策略（纯常量，重放确定性；activity 禁读环境变量改策略）。"""
    return {
        "version": GRAY_GATE_POLICY_VERSION,
        "autoMergeEnabled": AUTO_MERGE_ENABLED,
        "evidenceVersion": GRAY_GATE_EVIDENCE_VERSION,
        "nameRuleVersion": NAME_RULE_VERSION,
        "weights": {"name": 0.6, "props": 0.4},
        "thresholds": {"merge": 0.85, "grayLow": 0.65, "margin": 0.08},
    }


def require_known_policy(policy: Mapping[str, Any] | None) -> Mapping[str, Any]:
    """校验 activity 收到的 decisionPolicy 版本；未知版本失败关闭。"""
    version = str((policy or {}).get("version") or "")
    if version not in KNOWN_POLICY_VERSIONS:
        raise UnknownPolicyVersionError(
            {"expected": sorted(KNOWN_POLICY_VERSIONS), "received": version or None}
        )
    return policy or {}


# ---------------------------------------------------------------------------
# T_LINK 案版本路由 rank 表（park 版本化路由）
# ---------------------------------------------------------------------------

# v1 强制案（script-pending-gray-v1 / disambiguation-gray-v1 / 无 _resolution 的
# 存量碰撞案）不收新边；同 VID 有 v2 开放案时按 rank 路由到 v2；全 v1 →
# BLOCKED_BY_LEGACY_CASE 失败关闭（取代「计数后继续」）。
CASE_POLICY_RANK: dict[str, int] = {
    "script-pending-gray-v1": 0,
    "disambiguation-gray-v1": 1,
    "gray-gate-v2": 2,
    "gray-gate-v3": 3,
}
# 快照缺 _resolution.policyVersion 的存量案（消歧 v1 碰撞检测建案）按最低 rank
CASE_POLICY_RANK_MISSING = 0
# 只有 rank ≥ v2 的开放案才收新边
CASE_POLICY_MIN_CAPTURE_RANK = CASE_POLICY_RANK["gray-gate-v2"]


def case_policy_rank(policy_version: Any) -> int:
    """快照 policyVersion → rank；未登记的版本串失败关闭（不做词法比较）。"""
    value = str(policy_version or "").strip()
    if not value:
        return CASE_POLICY_RANK_MISSING
    if value not in CASE_POLICY_RANK:
        raise UnknownPolicyVersionError(
            {"knownVersions": sorted(CASE_POLICY_RANK), "received": value}
        )
    return CASE_POLICY_RANK[value]


def case_policy_version(case: Any) -> Any:
    """从案（dict 或 ORM 案对象）读 ``snapshot._resolution.policyVersion``。

    ORM 对象解析 ``candidate_snapshot`` JSON（本模块不 import ORM 层，避免
    循环依赖）；快照损坏/缺 ``_resolution`` 返回 None（按 rank 0 存量案处理）。
    """
    if isinstance(case, dict):
        snapshot = case.get("snapshot")
        resolution = (snapshot or {}).get("_resolution") or {}
        return case.get("policyVersion", resolution.get("policyVersion"))
    raw = getattr(case, "candidate_snapshot", None)
    if isinstance(raw, dict):
        resolution = raw.get("_resolution") or {}
        return resolution.get("policyVersion")
    if isinstance(raw, str) and raw:
        try:
            resolution = (json.loads(raw) or {}).get("_resolution") or {}
        except (TypeError, ValueError):
            return None
        return resolution.get("policyVersion")
    return None


def select_capture_case(cases: list[Any]) -> Any | None:
    """同 VID 多开放案的确定性选择：rank 最高 → created_at 最早 → case_id 字典序。

    ``cases`` 为该 vid 的全部非终态 T_LINK 案（元素带 ``snapshot``/``policyVersion``
    键的 dict，或直接传 ORM 案对象）。只返回 rank ≥ v2 的最佳案；无 v2 案返回
    None（调用方对仍存在的 v1 案走 BLOCKED_BY_LEGACY_CASE）。含未登记版本串时
    抛 UnknownPolicyVersionError。
    """
    ranked: list[tuple[int, Any, Any, Any]] = []
    for case in cases:
        rank = case_policy_rank(case_policy_version(case))
        created_at = (
            case.get("created_at") if isinstance(case, dict) else getattr(case, "created_at", None)
        )
        case_id = case.get("id") if isinstance(case, dict) else getattr(case, "id", "")
        ranked.append((rank, created_at, case_id, case))
    eligible = [entry for entry in ranked if entry[0] >= CASE_POLICY_MIN_CAPTURE_RANK]
    if not eligible:
        return None
    eligible.sort(key=lambda entry: (-entry[0], entry[1] or "", str(entry[2])))
    return eligible[0][3]


# ---------------------------------------------------------------------------
# priorVerdict 三态处置派生（重放路径专用）
# ---------------------------------------------------------------------------


def prior_verdict_disposition(
    prior: Mapping[str, Any] | None, *, source_vid: Any = None
) -> dict[str, Any]:
    """终态 T_LINK 案重放处置派生（application 表权威，四态失败关闭）。

    输入 ``_ingress_response`` 的 ``priorVerdict`` 信封；输出处置指令：

    - reject + NOT_REQUIRED → ``{"disposition": "drop_record"}``；
    - create + APPLIED → ``{"disposition": "write_as_new", "vid": reserved_vid}``；
    - merge + APPLIED → ``{"disposition": "rewrite_to_canonical", "vid": <remap 解析>}
      （R7：canonical 只能来自经批准的持久 remap（方案 A，另批）。应用行的
      ``canonical_vid`` 仅为审计留痕，不得充当重放映射——resolver 未登记 /
      未解析一律 ``MERGE_CANONICAL_MISSING`` 失败关闭，链式目标须解析到终点）；
    - applyStatus ∈ {FAILED, UNKNOWN} / 组合不合法 / 落点缺失 → 失败关闭
      （VerdictNotAppliedError / MergeCanonicalMissingError），不猜测。
    """
    envelope = dict(prior or {})
    verdict = str(envelope.get("entityVerdict") or "")
    apply_status = str(envelope.get("applyStatus") or "UNKNOWN")
    target = str(envelope.get("targetEntityId") or "")
    if apply_status == "NOT_REQUIRED" and verdict == "reject":
        return {"disposition": "drop_record"}
    if apply_status == "APPLIED" and verdict == "create":
        if not target:
            raise VerdictNotAppliedError({"applyStatus": apply_status, "verdict": verdict})
        return {"disposition": "write_as_new", "vid": target}
    if apply_status == "APPLIED" and verdict == "merge":
        # 信封里的 targetEntityId（= application.canonical_vid）不作为重放映射：
        # 映射唯一权威是 resolve_canonical_vid（持久 remap）
        canonical = resolve_canonical_vid(source_vid)
        return {"disposition": "rewrite_to_canonical", "vid": canonical}
    raise VerdictNotAppliedError({"applyStatus": apply_status or None, "verdict": verdict or None})


# ---------------------------------------------------------------------------
# canonical remap 解析器（方案 A 前置接口，R7）
# ---------------------------------------------------------------------------

# resolver 契约：old vid → 下一跳 canonical vid（单跳）；无映射/不可用返回 None。
# 链式目标（A→B→C）由 resolve_canonical_vid 迭代解析到终点并做环检测。
CanonicalRemapResolver = Callable[[str], "str | None"]

_canonical_remap_resolver: CanonicalRemapResolver | None = None
# 单次解析的最大跳数上限（超出=映射表异常，失败关闭不猜测）
MAX_CANONICAL_REMAP_HOPS = 8


def register_canonical_remap_resolver(resolver: CanonicalRemapResolver | None) -> None:
    """登记 / 撤销持久 remap（方案 A）解析器。

    方案 A 建表落地（另批）后由部署侧登记；传 None 撤销（默认未登记——
    merge 重放一律 ``MERGE_CANONICAL_MISSING`` 失败关闭）。应用行
    ``canonical_vid`` / 决议 ``targetEntityId`` 不得充当 resolver。
    """
    global _canonical_remap_resolver
    _canonical_remap_resolver = resolver


def resolve_canonical_vid(vid: Any) -> str:
    """old vid → 链终点 canonical vid（唯一权威=已登记的持久 remap）。

    resolver 未登记 → ``remap_unavailable``；无映射 / 映射回自身 →
    ``remap_unresolved``；环 / 超过跳数上限 / resolver 异常 → 同码失败关闭。
    任何情形都不回退应用表或决议目标。
    """
    resolver = _canonical_remap_resolver
    if resolver is None:
        raise MergeCanonicalMissingError({"reason": "remap_unavailable"})
    current = str(vid or "").strip()
    if not current:
        raise MergeCanonicalMissingError({"reason": "missing_source_vid"})
    seen = {current}

    def _one_hop(value: str) -> str | None:
        try:
            nxt = resolver(value)
        except GrayGateFailClosedError:
            raise
        except Exception as exc:  # noqa: BLE001 - resolver 故障=不可用，不猜测
            raise MergeCanonicalMissingError({"reason": "resolver_error"}) from exc
        return str(nxt or "").strip() or None

    for _ in range(MAX_CANONICAL_REMAP_HOPS):
        nxt = _one_hop(current)
        if nxt is None:
            break
        if nxt in seen:
            raise MergeCanonicalMissingError({"reason": "remap_cycle"})
        current = nxt
        seen.add(nxt)
    else:
        raise MergeCanonicalMissingError({"reason": "remap_chain_too_long"})
    if current == str(vid or "").strip():
        raise MergeCanonicalMissingError({"reason": "remap_unresolved"})
    return current


# ---------------------------------------------------------------------------
# 失败关闭错误族：不可重试、payload 零标识符
# ---------------------------------------------------------------------------


class GrayGateFailClosedError(Exception):
    """gray-gate 失败关闭错误族基类。

    携带 ``code``（稳定错误码）与 ``detail``（诊断负载——只含错误码/计数/
    标签名/边类型/版本/绑定/批次号，不含任何原始 vid、rid 或业务字面量）。
    activity 边界统一转 ApplicationError(non_retryable=True)。
    """

    code = "GRAY_GATE_FAIL_CLOSED"

    def __init__(self, detail: Mapping[str, Any] | None = None):
        self.detail: dict[str, Any] = {
            key: value for key, value in (detail or {}).items() if value is not None
        }
        super().__init__(f"{self.code}: {json.dumps(self.detail, ensure_ascii=False)}")


class DeferredMergeBlockedError(GrayGateFailClosedError):
    """scoreDecision=merge 在 autoMergeEnabled=false 下的统一失败关闭（B′ 裁决）。"""

    code = "DEFERRED_MERGE_BLOCKED"


class BlockedByLegacyCaseError(GrayGateFailClosedError):
    """端点只命中 v1 强制案（无 v2 开放案）——边不「计数后继续」，同级失败关闭。"""

    code = "BLOCKED_BY_LEGACY_CASE"


class BlockedEndpointUnknownError(GrayGateFailClosedError):
    """写边前端点存在性终判未通过：未知端点清单走 claim-check，payload 只带摘要。"""

    code = "BLOCKED_ENDPOINT_UNKNOWN"


class UnknownPolicyVersionError(GrayGateFailClosedError):
    """decisionPolicy 版本或案快照 policyVersion 未登记。"""

    code = "UNKNOWN_POLICY_VERSION"


class UnstableSourceIdentityError(GrayGateFailClosedError):
    """来源行身份不稳定（sourceRecordId 不可解析）——失败关闭不建案。"""

    code = "UNSTABLE_SOURCE_IDENTITY"


class EventKeyUnavailableError(GrayGateFailClosedError):
    """dedupe 身份密钥未配置——失败关闭，不退回可枚举的无盐哈希。"""

    code = "EVENT_KEY_UNAVAILABLE"


class MergeCanonicalMissingError(GrayGateFailClosedError):
    """merge 裁决重放缺 canonical 映射（remap 方案 A 未实施）。"""

    code = "MERGE_CANONICAL_MISSING"


class VerdictNotAppliedError(GrayGateFailClosedError):
    """priorVerdict.applyStatus ∈ {FAILED, UNKNOWN} 或缺标记——失败关闭，不猜测。"""

    code = "VERDICT_NOT_APPLIED"


FAIL_CLOSED_CODES = frozenset(
    {
        cls.code
        for cls in (
            DeferredMergeBlockedError,
            BlockedByLegacyCaseError,
            BlockedEndpointUnknownError,
            UnknownPolicyVersionError,
            UnstableSourceIdentityError,
            EventKeyUnavailableError,
            MergeCanonicalMissingError,
            VerdictNotAppliedError,
        )
    }
)


# ---------------------------------------------------------------------------
# 逻辑 ingress identity：canonicalization-v1 + 完整 HMAC-SHA256
# ---------------------------------------------------------------------------

DEDUPE_IDENTITY_KEY_ENV = "GRAY_GATE_DEDUPE_IDENTITY_KEY"
CANONICALIZATION_VERSION = "canonicalization-v1"

# 运行时生成的摄取/审计元数据列：转换脚本每跑一次就重写（ingest_time 取当次
# 时间），参与行摘要会让同一源行跨重跑换摘要→重复建案（R4）。事件摘要取
# canonical 源业务行，递归剥离这些列后计算；声明 sourceEventVersion 优先不受影响。
GRAY_GATE_VOLATILE_SOURCE_KEYS = frozenset(
    {"create_time", "update_time", "ingest_time", "ingest_batch", "source_update_time"}
)


def _without_volatile_keys(value: Any, volatile: frozenset[str]) -> Any:
    """递归剥离 volatile 列（dict 键 / 嵌套 list 元素同构处理）。"""
    if isinstance(value, Mapping):
        return {
            key: _without_volatile_keys(item, volatile)
            for key, item in value.items()
            if key not in volatile
        }
    if isinstance(value, (list, tuple)):
        return [_without_volatile_keys(item, volatile) for item in value]
    return value


# 标量类型标签（canonical 字节的首字符）：不同类型同值不坍缩（"1" vs 1）
_TAG_STR = b"s"
_TAG_BYTES = b"b"
_TAG_INT = b"i"
_TAG_FLOAT = b"f"
_TAG_BOOL = b"o"
_TAG_NULL = b"n"
_TAG_DATETIME = b"d"
_TAG_DATE = b"D"
_TAG_LIST = b"l"
_TAG_MAP = b"m"


def _length_prefixed(payload: bytes) -> bytes:
    return struct.pack(">Q", len(payload)) + payload


def _canonical_value(value: Any) -> bytes:
    """值 → 确定性字节（canonicalization-v1）。

    dict 按列名字典序；每个键值长度前缀；标量类型标签；None 哨兵 ``n``；
    datetime/date 全精度 ISO-8601（源精度信息全量编入字节，不做外部位阶）；
    嵌套结构递归同构。任何无法归类的值退化为字符串标签（保持确定性）。
    """
    if value is None:
        return _TAG_NULL
    if isinstance(value, bool):
        return _TAG_BOOL + (b"1" if value else b"0")
    if isinstance(value, int):
        return _TAG_INT + str(value).encode()
    if isinstance(value, float):
        return _TAG_FLOAT + repr(value).encode()
    if isinstance(value, str):
        return _length_prefixed(_TAG_STR + value.encode("utf-8"))
    if isinstance(value, (bytes, bytearray)):
        return _length_prefixed(_TAG_BYTES + bytes(value))
    if isinstance(value, datetime):
        # isoformat 含微秒与时区（若有）——源精度全量保留
        return _length_prefixed(_TAG_DATETIME + value.isoformat().encode())
    if isinstance(value, date):
        return _length_prefixed(_TAG_DATE + value.isoformat().encode())
    if isinstance(value, Mapping):
        body = b"".join(
            _length_prefixed(str(key).encode("utf-8")) + _canonical_value(value[key])
            for key in sorted(value, key=lambda k: str(k))
        )
        return _length_prefixed(_TAG_MAP + body)
    if isinstance(value, (list, tuple)):
        body = b"".join(_canonical_value(item) for item in value)
        return _length_prefixed(_TAG_LIST + body)
    return _length_prefixed(_TAG_STR + str(value).encode("utf-8"))


def canonical_row_bytes(row: Mapping[str, Any]) -> bytes:
    """来源行/记录 → canonical 字节（列名字典序 + 长度前缀 + 类型标签）。"""
    return _canonical_value(dict(row))


def dedupe_identity_key(key: str | None = None) -> str:
    """dedupe 专用身份密钥（固定/长期/独立隔离；换钥须先显式 alias/重键迁移）。

    优先取显式传入（测试注入），否则读环境变量。未配置 →
    EventKeyUnavailableError 失败关闭——不得退回可枚举身份字段的无盐哈希。
    """
    value = (key or os.getenv(DEDUPE_IDENTITY_KEY_ENV) or "").strip()
    if not value:
        raise EventKeyUnavailableError(
            {"env": DEDUPE_IDENTITY_KEY_ENV, "hint": "配置 dedupe 身份密钥后重跑"}
        )
    return value


def compute_event_version(
    row: Mapping[str, Any] | None,
    *,
    declared_version: Any = None,
    key: str | None = None,
    volatile_keys: Any = None,
) -> tuple[str, str]:
    """sourceEventVersion：声明值权威，否则完整 HMAC-SHA256(canonical 行字节)。

    返回 ``(version, basis)``；basis ∈ {"declared", "row-hmac", "item-hmac"}
    （进案件 input_snapshot 供审计，不进 dedupe 键）。密钥缺失失败关闭。
    ``volatile_keys``（如 ``GRAY_GATE_VOLATILE_SOURCE_KEYS``）：行字节计算前
    递归剥离的运行时生成列——同一源业务行跨重跑摘要稳定（R4），真实业务
    列变化仍换摘要（= 新事件允许新案）。
    """
    basis_source: Any = dict(row or {})
    if declared_version is not None and str(declared_version).strip():
        return str(declared_version).strip(), "declared"
    if volatile_keys:
        basis_source = _without_volatile_keys(basis_source, frozenset(volatile_keys))
    digest = hmac.new(
        dedupe_identity_key(key).encode("utf-8"),
        canonical_row_bytes(basis_source),
        hashlib.sha256,
    ).hexdigest()
    basis = "row-hmac" if row else "item-hmac"
    return digest, basis


def ingress_dedupe_key(
    *,
    source_binding_id: str,
    source_record_id: str,
    source_event_version: str,
    graph_space: str | None,
    node_label: str,
    vid: str,
    reprocess_batch_id: str | None = None,
) -> str:
    """逻辑 ingress identity：sha([六元组 + reprocessBatchId?])。

    不含 execution_id（降为来源行审计字段）与任何策略/评分版本——v2→v3
    恢复重跑换版不换键，重放命中同一案；事件版本变化=新键允许新案。
    """
    return _sha(
        [
            str(source_binding_id),
            str(source_record_id),
            str(source_event_version),
            str(graph_space or ""),
            str(node_label),
            str(vid),
            *([str(reprocess_batch_id)] if reprocess_batch_id else []),
        ]
    )
