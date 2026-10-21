"""生产人工审核服务（队列 / 直审裁决 / 直判写图 / 抽取失败重跑）。

2026-09-15 起移除「外部 graph-build 服务」移交通道（内部入口 / correction /
outbox / resume 派发 / 执行回调）：审核模块只管裁决与记录决议。
2026-09-17 起 T_LINK 裁决接入真实执行（写前扣留 case 写图 + 待定关系补写，
见 ``_apply_link_verdict``）；存量写后 case（无 ``_incoming`` 快照）仍只记录决议。
2026-09-17 起改为直审模式：OPEN 打开即可 submit（领取为可选保留），一切提交
即执行——审批环节（PENDING_APPROVAL 四方签核）已移除。
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import case, delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError

from db_model.manual_review import (
    ReviewAuditLog,
    ReviewCase,
    ReviewCaseSource,
    ReviewDecision,
    ReviewDraft,
    ReviewEvidence,
    ReviewVerdictApplication,
)
from infra.mysql import get_session_factory
from infra.s3 import S3Storage
from service.gray_gate import (
    BlockedByLegacyCaseError,
    GrayGateFailClosedError,
    VerdictNotAppliedError,
    case_policy_rank,
    case_policy_version,
    prior_verdict_disposition,
    select_capture_case,
)
from service.manual_review_domain import (
    EDITABLE_STATUSES,
    PIPELINE_STEPS,
    SUBMITTABLE_STATUSES,
    TEMPLATES,
    TERMINAL_STATUSES,
    ReviewConflictError,
    ReviewForbiddenError,
    ReviewIdentity,
    ReviewValidationError,
    canonical_template,
    require_domain_access,
    require_role,
    role_can_review,
    template_contract,
    validate_action,
    write_target,
)
from utils.time_display import utc_to_cst_str

STATE_OR_VERSION_CONFLICT = "状态或版本冲突"


def now():
    return datetime.now(UTC).replace(tzinfo=None)


def _now_str() -> str:
    """图库审计列用的本地时间串（与 write_records 溯源列补值同格式）。"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def dump(v):
    return json.dumps(v, ensure_ascii=False, separators=(",", ":"), sort_keys=True, default=str)


def load(v):
    return json.loads(v) if v else None


def sha(v):
    return hashlib.sha256(dump(v).encode()).hexdigest()


def _load_ingress_state(s, c) -> dict:
    """终态/失败案的耐久应用状态读取（priorVerdict 信封材料）。

    manual_review_verdict_application 为权威（APPLIED 带落点）；旧案缺整行时
    决议里的 entityVerdict 可读（reject 语义可靠），应用状态一律 UNKNOWN——
    不从 RESOLVED/APPROVED 猜测图写结果。
    """
    app = s.scalar(select(ReviewVerdictApplication).where(ReviewVerdictApplication.case_id == c.id))
    if app:
        return {
            "entityVerdict": app.verdict,
            "applyStatus": app.apply_status,
            "targetEntityId": (app.canonical_vid if app.verdict == "merge" else app.reserved_vid),
        }
    d = s.scalar(
        select(ReviewDecision)
        .where(ReviewDecision.case_id == c.id)
        .order_by(ReviewDecision.id.desc())
    )
    res = (load(d.result) or {}) if d else {}
    return {
        "entityVerdict": res.get("entityVerdict"),
        "applyStatus": "UNKNOWN",
        "targetEntityId": None,
    }


def _case_has_application(s, case_id) -> bool:
    """案是否有 verdict application 行（终态处置的权威优先判定）。"""
    return (
        s.scalar(
            select(ReviewVerdictApplication.id).where(ReviewVerdictApplication.case_id == case_id)
        )
        is not None
    )


def resolve_job_ids(execution_ids: list[str | None]) -> dict[str, str]:
    """EXEC 执行 ID → 所属图谱构建任务 ID（job-xxx）批量解析。

    人工审核「来源记录」跳任务详情用；控制面库（techkg_control）不可达时
    返回空映射，不影响审核队列本身——建案时快照里有 jobId 的 case 不依赖此查询。
    """
    ids = [i for i in execution_ids if i]
    if not ids:
        return {}
    try:
        from service.workflow_repository import repository

        return repository.job_ids_by_execution_ids(execution_ids)
    except Exception:  # noqa: BLE001
        logger.warning("resolve jobId for review cases failed", exc_info=True)
        return {}


def resolve_execution_ids_by_job_keyword(keyword: str) -> list[str]:
    """jobId 关键词 → 执行 ID 集合（队列按「来源记录」jobId 搜索的存量案兜底）。

    快照没写 jobId 的 case，来源记录列展示值来自控制面 EXEC→job 解析；
    搜该 jobId 须反向解出执行 ID 回快照匹配。控制面库不可达时返回空列表，
    其余搜索条件不受影响——与 resolve_job_ids 同一套容错。
    """
    try:
        from service.workflow_repository import repository

        return repository.execution_ids_by_job_keyword(keyword)
    except Exception:  # noqa: BLE001
        logger.warning("resolve executionIds by job keyword failed", exc_info=True)
        return []


# T_EXTRACT_FAIL 只读口径（2026-10-10）：「已完成」以执行概要成功为准——
# 重跑执行终态里只有 COMPLETED 算成功；FAILED/ABNORMAL（异常=抽取完成但含
# 行级失败记录）/CANCELED/TERMINATED/TIMED_OUT 都不算，执行记录缺失
# （控制库被清理）同样不算。概要非成功的案按「重跑失败」展示并可一直重跑。
_EXEC_NON_SUCCESS_TERMINAL = {"FAILED", "ABNORMAL", "CANCELED", "TERMINATED", "TIMED_OUT"}


def resolve_execution_statuses(execution_ids: list[str | None]) -> dict[str, str] | None:
    """按执行 ID 批量取控制面执行状态（T_EXTRACT_FAIL 只读口径推导用）。

    返回 None 表示控制面不可达——此时**跳过推导**、保留库内状态，避免把
    正常队列整体误判成「重跑失败」；返回 dict 时，缺失的 key = 执行记录
    已不存在，调用方按「无成功凭证」处理。
    """
    ids = [i for i in execution_ids if i]
    if not ids:
        return {}
    try:
        from service.workflow_repository import repository

        return repository.execution_statuses_by_ids(execution_ids)
    except Exception:  # noqa: BLE001
        logger.warning("resolve execution status for review cases failed", exc_info=True)
        return None


def effective_extract_fail_status(
    stored: str, rerun_execution_id: str | None, exec_statuses: dict[str, str] | None
) -> str:
    """T_EXTRACT_FAIL 案的有效状态（只读推导，不回写库）。

    - RESOLVED：绑定重跑执行 COMPLETED → 维持「已完成」（只读）；执行 RUNNING
      → RERUNNING（完成回写在途/待同步——执行行尚未收尾时如实展示「重跑中」，
      不冒认完成也不误报失败；写侧门控同口径 RUNNING 禁止重复派发）；执行
      非成功终态或记录缺失 → RERUN_FAILED（重跑失败，可再次重跑，不冒认完成）。
    - RERUNNING：执行仍在跑 → 维持「重跑中」；执行已终态但案未回写（回滚
      失败滞留）或记录缺失 → RERUN_FAILED，避免永久卡成不可操作行。
    - 其余状态原样返回；exec_statuses 为 None（控制面不可达）时不推导。
    """
    if exec_statuses is None:
        return stored
    if stored == "RESOLVED":
        if not rerun_execution_id:
            return stored
        status = exec_statuses.get(rerun_execution_id)
        if status == "COMPLETED":
            return "RESOLVED"
        if status == "RUNNING":
            return "RERUNNING"
        return "RERUN_FAILED"
    if stored == "RERUNNING":
        status = exec_statuses.get(rerun_execution_id or "")
        return "RERUNNING" if status == "RUNNING" else "RERUN_FAILED"
    return stored


def extract_fail_rerunnable(snapshot: dict[str, Any], exec_statuses: dict[str, str] | None) -> bool:
    """写侧门控（重跑/删除）与只读口径对齐。

    RESOLVED/RERUNNING 的 T_EXTRACT_FAIL 案，绑定重跑执行为非成功终态或
    记录缺失时仍放行——「重跑异常/失败的记录可以一直重跑」；执行仍在跑
    （RUNNING）或已成功（COMPLETED）则维持原禁用。控制面不可达时保守不放行。
    """
    if exec_statuses is None:
        return False
    rerun_id = str(snapshot.get("rerunExecutionId") or "")
    if not rerun_id:
        return False
    status = exec_statuses.get(rerun_id)
    return status is None or status in _EXEC_NON_SUCCESS_TERMINAL


logger = logging.getLogger("service.manual_review")


def ensure_review_queue_indexes() -> None:
    """幂等补人工审核队列索引（无迁移框架，仅 MySQL 方言；启动 best-effort 调用）。

    跨空间队列查询按 category（template_id 集合）过滤后计数+分页：存量表只有
    status/graph_space 索引，50 万行时 template_id 过滤走全表扫描×2，实测单请求
    约 3s。补 (template_id, status, created_at) 后走索引区间扫描（实测 0.4s 内）。
    新建表由 create_all 按 __table_args__ 自带该索引；本函数只兜存量环境。
    """
    from sqlalchemy import inspect, text

    from infra.mysql import get_engine

    engine = get_engine()
    if engine.dialect.name != "mysql":
        return
    inspector = inspect(engine)
    if "manual_review_case" not in inspector.get_table_names():
        return
    names = {index["name"] for index in inspector.get_indexes("manual_review_case")}
    if "ix_review_template" in names:
        return
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE INDEX ix_review_template "
                "ON manual_review_case (template_id, status, created_at)"
            )
        )
    logger.info("已补人工审核队列索引 ix_review_template (template_id, status, created_at)")


# 存量 T_DIRECT 案例的 risk_level 是中文"中/高"（旧口径），序列化时归一到 P1/P0，
# 保证展示与过滤口径统一；排序用同款 CASE 归一，避免"高"按码点沉底。
_RISK_NORMALIZE = {"中": "P1", "高": "P0"}


def _risk_label(v: str | None) -> str:
    return _RISK_NORMALIZE.get(v or "", v or "")


class ManualReviewService:
    def __init__(self, session_factory=None):
        self.sf = session_factory or get_session_factory()

    def require_case_access(self, identity, review_case):
        identity.ensure_space(review_case.graph_space)
        require_domain_access(identity, review_case.domain)

    def require_case_view(self, identity, review_case):
        """查看档：detail/logs 等读路径用；操作路径仍走 require_case_access。"""
        identity.ensure_space_view(review_case.graph_space)
        require_domain_access(identity, review_case.domain)

    def authorize_case(self, case_id, identity):
        with self.sf() as s:
            self.require_case_access(identity, self.need(s, case_id))

    def authorize_case_view(self, case_id, identity):
        with self.sf() as s:
            self.require_case_view(identity, self.need(s, case_id))

    def _can_operate(self, identity, review_case) -> bool:
        spaces = identity.review_spaces()
        return spaces is None or review_case.graph_space in spaces

    def authorize_rerun(self, identity, *, case_ids=None, execution_id=None):
        """Authorize the complete selected set, then freeze IDs for the rerun service."""
        identity.review_spaces()
        with self.sf() as s:
            if case_ids:
                rows = [self.need(s, case_id) for case_id in dict.fromkeys(case_ids)]
            elif execution_id:
                rows = s.scalars(
                    select(ReviewCase).where(
                        ReviewCase.template_id == "T_EXTRACT_FAIL",
                        ReviewCase.status.in_(("OPEN", "RERUN_FAILED", "RESOLVED", "RERUNNING")),
                    )
                ).all()
                rows = [
                    row
                    for row in rows
                    if (load(row.input_snapshot) or {}).get("executionId") == execution_id
                ]
                # 只读口径对齐：概要非成功（异常/失败/记录缺失）的已完成·滞留案
                # 同样可重跑；真正的门控在 list_extract_fail_cases，这里放行进集合
                exec_statuses = resolve_execution_statuses(
                    [(load(row.input_snapshot) or {}).get("rerunExecutionId") for row in rows]
                )
                rows = [
                    row
                    for row in rows
                    if row.status in ("OPEN", "RERUN_FAILED")
                    or extract_fail_rerunnable(load(row.input_snapshot) or {}, exec_statuses)
                ]
            else:
                raise ReviewValidationError("请选择审核记录或指定执行记录")
            for row in rows:
                self.require_case_access(identity, row)
            if not rows:
                raise ReviewValidationError("没有可重跑的审核记录")
            return [row.id for row in rows]

    def _ingress_response(self, c, duplicate, *, session=None):
        """建案 ingress 应答（gray-gate-v2 扩展 priorVerdict）。

        命中存量案（duplicate=True）且为 T_LINK 终态时附 ``priorVerdict``：
        ``{caseId, status, entityVerdict, targetEntityId, applyStatus}``——
        applyStatus 权威落点 manual_review_verdict_application（APPLIED 带写点），
        旧案缺整行按 UNKNOWN（不得从 RESOLVED/APPROVED 猜测）。三态处置
        （drop_record / write_as_new / rewrite_to_canonical）由调用方经
        ``service.gray_gate.prior_verdict_disposition`` 派生，此处只上桌事实。

        R5：非终态按可提交状态区分——OPEN/CLAIMED/IN_REVIEW 是真正待裁决的
        开放案（普通重复应答，继续扣留等裁决）；其余（APPLY_FAILED/中断等）
        先读耐久应用标记，FAILED/UNKNOWN 一律 ``VERDICT_NOT_APPLIED`` 失败
        关闭（不得把应用失败的案当开放案吞入新来源、也不猜测图写结果）。
        """
        response = {
            "reviewId": c.id,
            "status": c.status,
            "riskLevel": _risk_label(c.risk_level),
            "isolationStrategy": "BLOCK_BATCH_AND_DOWNSTREAM"
            if c.isolation_scope == "BATCH"
            else "ISOLATE_OBJECT",
            "duplicate": duplicate,
        }
        if not duplicate or canonical_template(c.template_id) != "T_LINK":
            return response
        if c.status in SUBMITTABLE_STATUSES:
            return response
        if c.status not in TERMINAL_STATUSES:
            # APPLY_FAILED / 中断等：应用标记权威，FAILED/UNKNOWN 失败关闭
            try:
                if session is not None:
                    state = _load_ingress_state(session, c)
                else:
                    with self.sf() as s:
                        state = _load_ingress_state(s, c)
            except GrayGateFailClosedError:
                raise
            except Exception:  # noqa: BLE001 - 标记读取失败同按 UNKNOWN 失败关闭
                logger.warning("priorVerdict 读取失败 case=%s，按 UNKNOWN 对待", c.id)
                state = {"entityVerdict": None, "applyStatus": "UNKNOWN", "targetEntityId": None}
            raise VerdictNotAppliedError(
                {"applyStatus": state.get("applyStatus") or "UNKNOWN", "caseStatus": c.status}
            )

        try:
            if session is not None:
                state = _load_ingress_state(session, c)
            else:
                with self.sf() as s:
                    state = _load_ingress_state(s, c)
        except Exception:  # noqa: BLE001 - priorVerdict 读失败按 UNKNOWN 失败关闭
            logger.warning("priorVerdict 读取失败 case=%s，按 UNKNOWN 对待", c.id, exc_info=True)
            state = {"entityVerdict": None, "applyStatus": "UNKNOWN", "targetEntityId": None}
        response["priorVerdict"] = {
            "caseId": c.id,
            "status": c.status,
            **state,
        }
        return response

    def find_ingress_case(self, dedupe_material: list[str] | None):
        """稳定事件身份查既有案（R2 前置裁决的查询侧）。

        ``dedupe_material`` 与建案时同构（``_gray_ingress_material`` 材料，键=对
        材料整体 sha）；无既有案返回 None，命中返回 ``_ingress_response(case,
        True)``——终态附 priorVerdict、待裁决返回普通重复应答、应用失败/
        UNKNOWN 在应答内失败关闭（调用方不得把技术失败当业务态）。
        """
        if not dedupe_material:
            return None
        key = sha(list(dedupe_material))
        with self.sf() as s:
            existing = s.scalar(select(ReviewCase).where(ReviewCase.dedupe_key == key))
            if existing is None:
                return None
            return self._ingress_response(existing, True, session=s)

    def _flipped_rerun_failed_ids(self, conditions: list) -> set[str]:
        """圈定「库内 RESOLVED/RERUNNING 但有效状态=重跑失败」的 T_EXTRACT_FAIL 案 ID。

        状态筛选与表格徽标 1:1 的支撑（conditions 为调用方已累积的基础过滤，
        含精确 status 时即只核该状态候选）：RERUN_FAILED 不落库，过滤「重跑失败」
        按执行概要圈定这批案；过滤「已完成/重跑中」用同一批反向剔除。控制面
        不可达时返回空集（跳过推导，保留库内口径，与列表展示的保守行为一致）。
        """
        with self.sf() as s:
            candidates = s.scalars(
                select(ReviewCase).where(
                    *conditions,
                    ReviewCase.template_id == "T_EXTRACT_FAIL",
                    ReviewCase.status.in_(("RESOLVED", "RERUNNING")),
                )
            ).all()
            if not candidates:
                return set()
            snapshots = [(c, load(c.input_snapshot) or {}) for c in candidates]
            exec_statuses = resolve_execution_statuses(
                [snapshot.get("rerunExecutionId") for _, snapshot in snapshots]
            )
            if exec_statuses is None:
                return set()
            return {
                c.id
                for c, snapshot in snapshots
                if effective_extract_fail_status(
                    c.status, snapshot.get("rerunExecutionId"), exec_statuses
                )
                == "RERUN_FAILED"
            }

    def list_cases(self, f, a):
        require_role(
            a,
            "reviewer",
            "data_quality_reviewer",
            "graph_governance_reviewer",
            "approver",
            "auditor",
        )
        page = max(int(f.get("page") or 1), 1)
        size = min(max(int(f.get("page_size") or 50), 1), 200)
        q = []
        # 可见范围=查看档（开发维护额外可见共享生产空间，只读）；
        # 操作范围=操作档，逐行以 canOperate 下发供前端禁用按钮（后端写口仍强校验）
        view_spaces = a.review_view_spaces()
        operate_spaces = a.review_spaces()
        if view_spaces is not None:
            q.append(ReviewCase.graph_space.in_(view_spaces))
        # 图空间过滤（队列页跟随全局空间选择）：显式传入时只看该空间，不传=跨空间全量；
        # 与上面 RBAC 授权空间集合是 AND 相交——请求未授权空间自然得到空列表
        if f.get("graph_space"):
            q.append(ReviewCase.graph_space == f["graph_space"])
        for k, col in (
            ("risk", ReviewCase.risk_level),
            ("domain", ReviewCase.domain),
            ("template_id", ReviewCase.template_id),
            ("assignee_id", ReviewCase.assignee_id),
        ):
            if f.get(k):
                q.append(col == f[k])
        # 状态分组：pending=待处理（非终态）；processed=已处理（终态）
        status_groups = {
            "pending": ReviewCase.status.notin_(TERMINAL_STATUSES),
            "processed": ReviewCase.status.in_(TERMINAL_STATUSES),
        }
        if f.get("status_group") in status_groups:
            q.append(status_groups[f["status_group"]])
        # 对象种类：T_DIRECT 案例 object_type 即 kind（entity/relation）；
        # T_LINK 是实体对齐，按实体兜底
        if f.get("kind") == "entity":
            q.append(or_(ReviewCase.object_type == "entity", ReviewCase.template_id == "T_LINK"))
        elif f.get("kind") == "relation":
            q.append(ReviewCase.object_type == "relation")
        queues = {
            "mine": ReviewCase.assignee_id == a.user_id,
            "unclaimed": ReviewCase.status == "OPEN",
            "approval": ReviewCase.status == "PENDING_APPROVAL",
            "failed": ReviewCase.status.in_(("APPLY_FAILED", "RERUN_FAILED")),
            "history": ReviewCase.status.in_(TERMINAL_STATUSES),
        }
        if f.get("queue") in queues:
            q.append(queues[f["queue"]])
        # category 过滤：A=入库决策（T_DIRECT/T_LINK）；C=抽取失败重跑（T_EXTRACT_FAIL）；
        # 不传=所有 template
        categories = {
            "A": ("T_DIRECT", "T_LINK"),
            "C": ("T_EXTRACT_FAIL",),
        }
        if f.get("category") in categories:
            q.append(ReviewCase.template_id.in_(categories[f["category"]]))
        if a.domains and "*" not in a.domains and not a.has_any("review_admin", "auditor"):
            q.append(ReviewCase.domain.in_(a.domains))
        if f.get("keyword"):
            kw = str(f["keyword"])
            x = f"%{kw}%"
            # 「来源记录」信息一并可搜（失败重跑队列此前只搜案号/对象/记录 id，
            # 搜来源记录列展示的 jobId 或抽取执行 EXEC 一律空）：来源表 +
            # 快照里的 jobId/executionId——快照是紧凑 JSON（separators=(",",":")），
            # 锚定 "key":"value" 形态匹配。值必须紧跟键引号（键后不留 %）：
            # 值模糊会从 executionId 键出发跨过中间 JSON 落到 rerunOfExecutionId
            # 的值上——重跑两代案互相命中，搜一个执行翻倍出两代的案
            keyword_match = [
                ReviewCase.id.like(x),
                ReviewCase.object_name.like(x),
                ReviewCase.source_record_id.like(x),
                ReviewCase.source_table.like(x),
                ReviewCase.input_snapshot.like(f'%"jobId":"{kw}"%'),
                ReviewCase.input_snapshot.like(f'%"executionId":"{kw}"%'),
            ]
            # 存量案快照没写 jobId（来源记录列靠控制面 EXEC→job 解析展示）：
            # 反向按 job 关键词解出执行 ID，回快照精确匹配，搜展示值才能命中
            keyword_match.extend(
                ReviewCase.input_snapshot.like(f'%"executionId":"{execution_id}"%')
                for execution_id in resolve_execution_ids_by_job_keyword(kw)
            )
            q.append(or_(*keyword_match))
        # 更新时间窗口过滤（队列页「时间」下拉）：1h/24h/7d/30d
        updated_within_hours = {"1h": 1, "24h": 24, "7d": 24 * 7, "30d": 24 * 30}
        if f.get("updated_within") in updated_within_hours:
            q.append(
                ReviewCase.updated_at
                >= datetime.now() - timedelta(hours=updated_within_hours[f["updated_within"]])
            )
        # 状态精确过滤（队列页「状态」下拉与表格徽标 1:1）：RERUN_FAILED 是只读
        # 推导态（库内不落值，见 effective_extract_fail_status），按执行概要把
        # 「RESOLVED/RERUNNING 但重跑执行非成功」的案圈进来；反之过滤
        # RESOLVED/RERUNNING 时把同一批剔出去——选什么状态表格就只出什么徽标。
        requested_status = str(f.get("status") or "")
        if requested_status == "RERUN_FAILED":
            q.append(ReviewCase.id.in_(self._flipped_rerun_failed_ids(q)))
        elif requested_status:
            q.append(ReviewCase.status == requested_status)
            if requested_status in ("RESOLVED", "RERUNNING"):
                flipped = self._flipped_rerun_failed_ids(q)
                if flipped:
                    q.append(ReviewCase.id.notin_(flipped))
        # 排序：updated_desc/updated_asc 按更新时间；默认 风险等级 + 创建时间。
        # 三种排序统一补 id 唯一尾键：T_EXTRACT_FAIL 案例同一秒批量落库，风险/时间大量并列，
        # 无唯一尾键时 LIMIT/OFFSET 翻页内容不稳定，同一行会在相邻页重复出现（前端表现为
        # 批量勾选后翻到下一页仍有选中行）
        if f.get("sort") == "updated_desc":
            order = [ReviewCase.updated_at.desc(), ReviewCase.id]
        elif f.get("sort") == "updated_asc":
            order = [ReviewCase.updated_at.asc(), ReviewCase.id]
        else:
            order = [
                case(
                    {"高": "P0", "中": "P1"},
                    value=ReviewCase.risk_level,
                    else_=ReviewCase.risk_level,
                ),
                ReviewCase.created_at,
                ReviewCase.id,
            ]
        with self.sf() as s:
            total = s.scalar(select(func.count()).select_from(ReviewCase).where(*q)) or 0
            # 两步取页（延迟关联）：排序键含 CASE 表达式走不了索引序，直接对整行
            # 排序会把匹配集（跨空间 4 万+ 行、含大 TEXT 快照）整体物化进
            # filesort，实测单页 5s+；先窄列排序取当页主键再按主键回表取整行，
            # 结果顺序不变，实测 1.5s 内
            page_ids = s.scalars(
                select(ReviewCase.id)
                .where(*q)
                .order_by(*order)
                .offset((page - 1) * size)
                .limit(size)
            ).all()
            if page_ids:
                found = {
                    row.id: row
                    for row in s.scalars(
                        select(ReviewCase).where(ReviewCase.id.in_(page_ids))
                    ).all()
                }
                rows = [found[case_id] for case_id in page_ids if case_id in found]
            else:
                rows = []
            # 来源记录跳任务详情：一次 IN 查询批量解析本页 EXEC→jobId（快照已有 jobId 的行跳过）
            job_map = resolve_job_ids(
                [(load(x.input_snapshot) or {}).get("executionId") for x in rows]
            )
            # T_EXTRACT_FAIL 只读口径：同样一次 IN 批量取本页重跑执行状态，供
            # case_dict 推导有效状态（只有 RESOLVED/RERUNNING 案需要核验执行概要）
            exec_statuses = resolve_execution_statuses(
                [
                    (load(x.input_snapshot) or {}).get("rerunExecutionId")
                    for x in rows
                    if x.template_id == "T_EXTRACT_FAIL" and x.status in ("RESOLVED", "RERUNNING")
                ]
            )
            return {
                "items": [
                    self.case_dict(
                        x, job_map, operate_spaces=operate_spaces, exec_statuses=exec_statuses
                    )
                    for x in rows
                ],
                "total": total,
                "page": page,
                "pageSize": size,
            }

    def get_case(self, i, a):
        with self.sf() as s:
            c = self.need(s, i)
            self.require_case_view(a, c)
            d = self.detail(s, c)
            # T_LINK 判定证据实时富化（fail-open，不回写快照）：候选属性/评分明细/
            # 同名总数/挂起边端点名——建案快照只存 vid/name/score，打开详情时现查补齐
            d["candidate"] = self._enrich_link_snapshot(c, d.get("candidate") or {})
            if isinstance(d.get("data"), dict):
                d["data"]["candidate"] = d["candidate"]
            # 只读查看档（如开发维护看共享空间）：detail 默认可操作，按操作档覆写
            d["canOperate"] = self._can_operate(a, c)
            return d

    def claim(self, i, v, a):
        t = now()
        with self.sf() as s:
            c = self.need(s, i)
            self.require_case_access(a, c)
            if not role_can_review(a, c.phase):
                raise ReviewForbiddenError("角色与任务阶段不匹配")
            r = s.execute(
                update(ReviewCase)
                .where(ReviewCase.id == i, ReviewCase.version == v, ReviewCase.status == "OPEN")
                .values(
                    status="CLAIMED",
                    assignee_id=a.user_id,
                    assignee_name=a.user_name,
                    claimed_at=t,
                    heartbeat_at=t,
                    updated_at=t,
                    version=ReviewCase.version + 1,
                )
            )
            if r.rowcount != 1:
                raise ReviewConflictError("任务已被领取或版本冲突")
            self.audit(s, c, a, "CASE_CLAIMED", "OPEN", "CLAIMED", {})
            s.commit()
        return self.get_case(i, a)

    def mutate(self, i, v, a, values, event, admin=False):
        with self.sf() as s:
            c = self.need(s, i)
            self.require_case_access(a, c)
            if not admin and c.assignee_id != a.user_id:
                raise ReviewForbiddenError("任务不属于当前用户")
            if c.version != v:
                raise ReviewConflictError("版本冲突")
            old = c.status
            for k, x in values.items():
                setattr(c, k, x)
            c.version += 1
            c.updated_at = now()
            self.audit(s, c, a, event, old, c.status, {})
            s.commit()
            return self.detail(s, c)

    def heartbeat(self, i, v, a):
        return self.mutate(i, v, a, {"heartbeat_at": now()}, "HEARTBEAT")

    def release(self, i, v, a):
        return self.mutate(
            i,
            v,
            a,
            {
                "status": "OPEN",
                "assignee_id": None,
                "assignee_name": None,
                "claimed_at": None,
                "heartbeat_at": None,
            },
            "CASE_RELEASED",
        )

    def transfer(self, i, v, uid, name, a):
        require_role(a, "reviewer" if a.platform_actor else "review_admin")
        if a.platform_actor:
            from service.business_access_control import ensure_space_access

            with self.sf() as session:
                review_case = self.need(session, i)
                self.require_case_access(a, review_case)
                space = review_case.graph_space
            from service.workflow_jobs import _job_business, authorize_background_execution

            client_id = _job_business(a.platform_actor, {"graphSpace": space})
            target = authorize_background_execution(
                {"actorUserId": uid, "clientId": client_id, "graphSpace": space}
            )
            ensure_space_access(target, space, action="review")
        return self.mutate(
            i,
            v,
            a,
            {"assignee_id": uid, "assignee_name": name, "heartbeat_at": now()},
            "CASE_TRANSFERRED",
            True,
        )

    def draft(self, i, v, p, a):
        with self.sf() as s:
            c = self.owned(s, i, a)
            if c.version != v or c.status not in EDITABLE_STATUSES:
                raise ReviewConflictError(STATE_OR_VERSION_CONFLICT)
            s.merge(ReviewDraft(case_id=i, payload=dump(p), updated_by=a.user_id, updated_at=now()))
            old = c.status
            c.status = "IN_REVIEW"
            c.version += 1
            c.updated_at = now()
            self.audit(s, c, a, "DRAFT_SAVED", old, c.status, {})
            s.commit()
            return self.detail(s, c)

    def submit(self, i, v, action, result, note, a):
        """直审模式：OPEN 可直接提交（领取为可选），一切提交即执行、不设审批。

        已被他人领取的 case 仍限领取人 / review_admin 操作；并发仍是 version
        乐观锁——两人同开一个 case，先提交者生效，后提交者报版本冲突。

        gray-gate-v2 起 T_LINK 裁决走两段提交（docs/人工审核专项方案复核
        _20261021.md）：Tx1 = 决议 + 意图标记（``manual_review_verdict_application``：
        无图写的裁决直接 NOT_REQUIRED；写前扣留案（快照带 ``_incoming``）的
        merge/create 记 UNKNOWN 意图与落点 vid）+ 案 RESOLVED，先落库；
        随后图写在事务外执行；Tx2 按结果把标记收敛为 APPLIED（applied_at）/
        FAILED（error_code + 案 APPLY_FAILED 进 failed 队列），异常照常上抛。
        重放与跨执行改写（priorVerdict / park）一律以 application 表为权威，
        缺行或 UNKNOWN 即失败关闭——决议 RESOLVED 不再隐含「图已写」。输入
        问题（retype / 目标不在候选集）在 Tx1 前拒绝，案保持可提交（与旧
        事务内回滚语义等价）。
        """
        needs_apply = False
        with self.sf() as s:
            c = self.need(s, i)
            self.require_case_access(a, c)
            if not role_can_review(a, c.phase):
                raise ReviewForbiddenError("角色与任务阶段不匹配")
            if c.status in ("CLAIMED", "IN_REVIEW") and c.assignee_id != a.user_id:
                if not a.has_any("review_admin"):
                    raise ReviewForbiddenError("任务未由当前用户领取")
            if c.status not in SUBMITTABLE_STATUSES:
                raise ReviewConflictError(STATE_OR_VERSION_CONFLICT)
            # 原子占位（version CAS）：T_LINK 裁决写图耗时秒级，旧「读时校验」
            # 窗口内双击/并发提交会双双通过（图写两遍、决议双落库）。先原子占住
            # version 再执行写图；后续异常回滚事务即自动释放占位。
            t = now()
            reserved = s.execute(
                update(ReviewCase)
                .where(
                    ReviewCase.id == i,
                    ReviewCase.version == v,
                    ReviewCase.status.in_(SUBMITTABLE_STATUSES),
                )
                .values(version=ReviewCase.version + 1, updated_at=t)
            )
            if reserved.rowcount != 1:
                raise ReviewConflictError(STATE_OR_VERSION_CONFLICT)
            s.expire(c, ["version", "updated_at"])
            validate_action(c.template_id, action, result)
            verdict = str(result.get("entityVerdict") or "")
            snapshot = load(c.candidate_snapshot) or {}
            incoming = snapshot.get("_incoming")
            application: ReviewVerdictApplication | None = None
            if canonical_template(c.template_id) == "T_LINK" and action in (
                "entity-confirm",
                "reject-candidate",
            ):
                if action == "entity-confirm" and incoming:
                    if verdict == "retype":
                        raise ReviewValidationError("retype 暂不支持：请驳回后修正脚本重跑")
                    if verdict == "merge":
                        allowed = {
                            str(x.get("vid"))
                            for x in snapshot.get("existingCandidates") or []
                            if x.get("vid")
                        }
                        if str(result.get("targetEntityId") or "") not in allowed:
                            raise ReviewValidationError("目标实体不在候选集内")
                # 写前扣留案（带 _incoming）的 merge/create 才有图写第二段；
                # reject / 存量写后案（实体已在图）不需要图写 → 直接 NOT_REQUIRED
                needs_apply = (
                    bool(incoming) and action == "entity-confirm" and verdict in ("merge", "create")
                )
                application = ReviewVerdictApplication(
                    case_id=i,
                    verdict=verdict,
                    apply_status="UNKNOWN" if needs_apply else "NOT_REQUIRED",
                    canonical_vid=(
                        str(result.get("targetEntityId") or "")[:256] or None
                        if verdict == "merge"
                        else None
                    ),
                    reserved_vid=(
                        str(incoming.get("vid") or c.object_id)[:256] or None
                        if verdict == "create" and incoming
                        else None
                    ),
                    created_at=t,
                    updated_at=t,
                )
            d = ReviewDecision(
                case_id=i,
                action_id=action,
                result=dump(result),
                note=note,
                submitted_by=a.user_id,
                status="APPROVED",
                created_at=t,
                decided_at=t,
            )
            s.add(d)
            s.flush()
            if application is not None:
                application.decision_id = d.id
                s.add(application)
            old = c.status
            c.submitted_by = a.user_id
            # OPEN 直审时记录处理人，历史里可追溯（队列不再显示"待领取"）
            if not c.assignee_id:
                c.assignee_id = a.user_id
                c.assignee_name = a.user_name
            c.status = "RESOLVED"
            c.completed_at = t
            c.updated_at = t
            self.audit(
                s,
                c,
                a,
                "DECISION_SUBMITTED",
                old,
                c.status,
                {
                    "actionId": action,
                    "applyIntent": application.apply_status if application else None,
                },
            )
            s.commit()
        # 两段提交第二段（gray-gate-v2）：图写在 Tx1 落库后、事务外执行。
        # 失败不回滚决议——application 标记 FAILED、案置 APPLY_FAILED 进
        # failed 队列（人工重应用另行审批）；异常照常上抛给审核端。
        if needs_apply:
            with self.sf() as s2:
                c2 = self.need(s2, i)
                try:
                    apply_detail = self._apply_link_verdict(c2, result)
                except Exception as exc:
                    self._finish_verdict_application(
                        i, a, action, "FAILED", error_code=type(exc).__name__
                    )
                    raise
                self._finish_verdict_application(i, a, action, "APPLIED", apply_detail=apply_detail)
                # 事务落库后再联动实体检索（索引增量 + 缓存失效），best-effort 不影响
                # 裁决结果。挪后台线程执行：embedding + 索引写入秒级耗时不拖裁决响应
                # （图已写、标记已落库，联动失败本就由下次全量重建兜底）。
                threading.Thread(
                    target=self._sync_entity_search_after_write,
                    args=(apply_detail,),
                    daemon=True,
                    name=f"review-index-sync-{c2.id}",
                ).start()
                return self.detail(s2, c2)
        with self.sf() as s3:
            return self.detail(s3, self.need(s3, i))

    def _finish_verdict_application(
        self,
        case_id: str,
        a: Any,
        action_id: str,
        outcome: str,
        *,
        error_code: str | None = None,
        apply_detail: dict[str, Any] | None = None,
    ) -> None:
        """两段提交 Tx2：application 意图标记收敛（UNKNOWN → APPLIED / FAILED）。

        - APPLIED：``applied_at`` 落库 + ``VERDICT_APPLIED`` audit（带图写明细）；
        - FAILED：``error_code`` + 案置 ``APPLY_FAILED``（failed 队列）+ audit。
        只从 UNKNOWN 收敛（已 APPLIED/FAILED 的幂等重放不覆盖）。标记自身失败
        仅记日志：图写已发生/未发生的事实不因标记失败改变，缺 APPLIED 的
        UNKNOWN 即崩溃窗口收敛口径，重放侧失败关闭兜底。
        """
        t = now()
        try:
            with self.sf() as s:
                app = s.scalar(
                    select(ReviewVerdictApplication).where(
                        ReviewVerdictApplication.case_id == case_id
                    )
                )
                if app is None or app.apply_status != "UNKNOWN":
                    return
                case = s.scalar(select(ReviewCase).where(ReviewCase.id == case_id))
                if outcome == "APPLIED":
                    app.apply_status = "APPLIED"
                    app.applied_at = t
                    if case is not None:
                        self.audit(
                            s,
                            case,
                            a,
                            "VERDICT_APPLIED",
                            case.status,
                            case.status,
                            {"actionId": action_id, **(apply_detail or {})},
                        )
                else:
                    app.apply_status = "FAILED"
                    app.error_code = (str(error_code or "") or "UNKNOWN_ERROR")[:64]
                    if case is not None:
                        old_status = case.status
                        case.status = "APPLY_FAILED"
                        case.updated_at = t
                        self.audit(
                            s,
                            case,
                            a,
                            "APPLY_FAILED",
                            old_status,
                            case.status,
                            {"actionId": action_id, "errorCode": app.error_code},
                        )
                app.updated_at = t
                s.commit()
        except Exception:  # noqa: BLE001 - Tx2 标记失败不吞图写结果
            logger.exception("verdict application 标记失败 case=%s outcome=%s", case_id, outcome)

    def create_direct_case(
        self,
        *,
        task_id: str,
        execution_id: str | None,
        step_id: str,
        kind: str,
        candidate: dict[str, Any],
        object_id: str | None = None,
        object_name: str | None = None,
        node_label: str | None = None,
        edge_type: str | None = None,
        from_id: str | None = None,
        to_id: str | None = None,
        reason: str = "",
        confidence: float | None = None,
        evidence: list[Any] | None = None,
        workflow_id: str | None = None,
        workflow_run_id: str | None = None,
        domain: str = "graph",
        service_actor: str = "kg.custom.steps",
        source_record: dict[str, Any] | None = None,
        source_table: str | None = None,
        source_record_id: str | None = None,
        llm_input: dict[str, Any] | None = None,
        llm_output: str | None = None,
        template_id: str = "T_DIRECT",
        workflow_type: str | None = None,
        exception_code: str | None = None,
        resume_token: str | None = None,
        extra_snapshot: dict[str, Any] | None = None,
        graph_space: str | None = None,
        dedupe_material: list[str] | None = None,
    ) -> dict[str, Any]:
        """直接 OPEN 状态入队（打开即可裁决，无需领取）。

        默认 T_DIRECT（kg.custom.steps pendingReview）：candidate_snapshot 附加
        kind/nodeLabel/edgeType/fromId/toId 元字段，direct_decide 读这些字段写图。
        ``template_id`` 可选 T_EXTRACT_FAIL（抽取失败重跑）/ T_LINK（同名冲突对齐），
        ``extra_snapshot`` 合入 input_snapshot 供对应处理端读取。

        ``dedupe_material``（gray-gate-v2 逻辑 ingress identity）：给定即取代
        ``sha([task_id, step_id, obj_id, sha(snapshot)])`` 作为 dedupe 键材料——
        纯源事件身份 ``[sourceBindingId, sourceRecordId, sourceEventVersion,
        graph_space, nodeLabel, vid, reprocessBatchId?]``（不含 execution_id 与
        任何策略/评分版本）：跨手工恢复/失败重跑重放命中同一案（OPEN=no-op、
        TERMINAL=按 priorVerdict 重放），源事件版本变化=新键允许新案。快照哈希
        随召回可用性/证据版本漂移的问题随之消除。
        """
        t = now()
        recorded_spaces = {
            str(value).strip()
            for value in (
                candidate.get("_graphSpace"),
                (extra_snapshot or {}).get("_graphSpace"),
            )
            if value
        }
        if not graph_space and len(recorded_spaces) > 1:
            raise ReviewValidationError("审核记录的图空间信息冲突")
        graph_space = (graph_space or next(iter(recorded_spaces), "")).strip() or None
        if graph_space:
            candidate = {**candidate, "_graphSpace": graph_space}
            extra_snapshot = {**(extra_snapshot or {}), "_graphSpace": graph_space}
        obj_id = (
            object_id
            or candidate.get("id")
            or candidate.get("scholar_id")
            or f"{step_id}-{uuid4().hex[:8]}"
        )
        obj_name = object_name or candidate.get("name_zh") or candidate.get("name") or obj_id
        snapshot = {
            **candidate,
            "_kind": kind,
            "_nodeLabel": node_label,
            "_edgeType": edge_type,
            "_fromId": from_id,
            "_toId": to_id,
            "_confidence": confidence,
        }
        dedupe_key = (
            sha(list(dedupe_material))
            if dedupe_material
            else sha([task_id, step_id, obj_id, sha(snapshot)])
        )
        risk = "P1" if (confidence is None or confidence >= 0.7) else "P0"
        effective_workflow_type = workflow_type or "kg.custom.steps"
        c = ReviewCase(
            id=f"MR-{t:%Y%m%d}-{uuid4().hex[:12].upper()}",
            graph_space=graph_space,
            dedupe_key=dedupe_key,
            event_id=f"kg-step-{uuid4().hex}",
            source_task_id=task_id,
            batch_id=None,
            node_id=step_id,
            pipeline_step_id=step_id,
            object_id=obj_id,
            object_type=kind,
            object_name=obj_name,
            error_type=reason or "需要人工审核",
            error_fingerprint=sha([reason, snapshot]),
            category=TEMPLATES[template_id]["title"],
            template_id=template_id,
            template_version="1.0",
            domain=domain,
            phase="图谱构建",
            risk_level=risk,
            scope="OBJECT",
            status="OPEN",
            version=1,
            sla_claim_at=t + timedelta(hours=1),
            sla_resolve_at=t + timedelta(hours=24),
            workflow_type=effective_workflow_type,
            workflow_id=workflow_id,
            workflow_run_id=workflow_run_id,
            task_queue="tech-kg-workflows",
            resume_token=resume_token or f"kg-step:{task_id}:{step_id}",
            exception_code=exception_code or "KG_STEP_PENDING_REVIEW",
            isolation_scope="OBJECT",
            template_payload_version="1.0",
            input_snapshot=dump(
                {
                    "evidence": evidence or [],
                    "executionId": execution_id,
                    "confidence": confidence,
                    "source_record": source_record,
                    "llm_input": llm_input,
                    "llm_output": llm_output,
                    **(extra_snapshot or {}),
                }
            ),
            source_table=source_table,
            source_record_id=source_record_id,
            candidate_snapshot=dump(snapshot),
            diagnosis=reason or "需要人工审核",
            created_at=t,
            updated_at=t,
        )
        actor = ReviewIdentity(
            service_actor,
            service_actor,
            frozenset({"review_admin"}),
            frozenset({"*"}),
            "service",
            c.event_id,
        )
        with self.sf() as s:
            existing = s.scalar(select(ReviewCase).where(ReviewCase.dedupe_key == dedupe_key))
            if existing:
                return self._ingress_response(existing, True)
            try:
                s.add(c)
                self.audit(
                    s,
                    c,
                    actor,
                    "CASE_CREATED",
                    None,
                    "OPEN",
                    {"stepId": step_id, "kind": kind, "reason": reason},
                )
                s.commit()
            except IntegrityError:
                s.rollback()
                existing = s.scalar(select(ReviewCase).where(ReviewCase.dedupe_key == dedupe_key))
                if not existing:
                    raise
                return self._ingress_response(existing, True)
        return self._ingress_response(c, False)

    # ------------------------------------------------------------------
    # gray-gate-v2：来源账本 + 裁决应用标记
    # ------------------------------------------------------------------

    # 案件来源行 evidence 上限（前 N 个来源带全量 evidence，之后行如实插入但
    # evidence 置空，靠 source_truncated_count 表达截断——明细行无界、evidence 有界）
    CASE_SOURCE_EVIDENCE_LIMIT = 32
    # advisory 告警线：单案来源行数超过即记 warning（转人工口径），不阻塞追加
    CASE_SOURCE_ROWS_ADVISORY = 1024

    def append_case_sources(
        self,
        case_id: str,
        sources: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """T_LINK 案来源行幂等追加（gray-gate-v2）。

        同一 MySQL 事务内：``SELECT ... FOR UPDATE`` 锁案行 → 逐条 INSERT
        （唯一键 ``(case_id, execution_id, source_record_id)``；已存在=同执行
        同源记录重放，跳过不加计）→ UPDATE 逻辑计数（source_count /
        source_truncated_count）。evidence 只存字段名与布尔（≤2KB，零业务值），
        案件生命周期内前 ``CASE_SOURCE_EVIDENCE_LIMIT`` 个非截断来源携带，其余
        行 evidence 空。冲突/异常整体回滚不加计（IntegrityError 上抛交活动重试，
        重放收敛靠唯一键）。>1024 行记 warning（advisory，转人工告警口径）。
        """
        if not sources:
            return {"appended": 0, "skipped": 0}
        t = now()
        appended = 0
        skipped = 0
        with self.sf() as s:
            case = s.scalar(select(ReviewCase).where(ReviewCase.id == case_id).with_for_update())
            if case is None:
                # 案件不存在（并发删除等）：不加计不报错——来源账本从属于案件
                return {"appended": 0, "skipped": 0, "missingCase": True}
            carried = int(case.source_count or 0) - int(case.source_truncated_count or 0)
            for source in sources:
                execution_id = str(source.get("executionId") or "")[:64]
                record_id = str(source.get("sourceRecordId") or "")[:128]
                if not record_id:
                    continue
                exists = s.scalar(
                    select(ReviewCaseSource.id).where(
                        ReviewCaseSource.case_id == case_id,
                        ReviewCaseSource.execution_id == execution_id,
                        ReviewCaseSource.source_record_id == record_id,
                    )
                )
                if exists:
                    skipped += 1
                    continue
                evidence = dump(source.get("evidence") or "")
                if len(evidence) > 2000:
                    evidence = evidence[:2000]
                keep_evidence = carried < self.CASE_SOURCE_EVIDENCE_LIMIT
                if not keep_evidence:
                    evidence = ""
                s.add(
                    ReviewCaseSource(
                        case_id=case_id,
                        execution_id=execution_id,
                        source_binding_id=str(source.get("sourceBindingId") or "")[:64],
                        source_record_id=record_id,
                        source_event_version=str(source.get("sourceEventVersion") or "")[:128],
                        evidence=evidence if keep_evidence else "",
                        reason=str(source.get("reason") or "")[:256],
                        created_at=t,
                    )
                )
                carried += 1
                case.source_count = int(case.source_count or 0) + 1
                if not keep_evidence:
                    case.source_truncated_count = int(case.source_truncated_count or 0) + 1
                case.updated_at = t
                appended += 1
            if int(case.source_count or 0) > self.CASE_SOURCE_ROWS_ADVISORY:
                logger.warning(
                    "T_LINK 案来源行数超过 advisory 线（case=%s rows=%s>%s），建议转人工核查",
                    case_id,
                    case.source_count,
                    self.CASE_SOURCE_ROWS_ADVISORY,
                )
            s.commit()
        return {"appended": appended, "skipped": skipped}

    # ------------------------------------------------------------------
    # T_EXTRACT_FAIL：抽取失败记录重跑生命周期
    # ------------------------------------------------------------------

    def _extract_service_actor(self, tag: str) -> ReviewIdentity:
        return ReviewIdentity(
            "kg.schema.extract",
            "kg.schema.extract",
            frozenset({"review_admin"}),
            frozenset({"*"}),
            "service",
            f"{tag}-{uuid4().hex[:8]}",
        )

    def list_extract_fail_cases(
        self,
        *,
        case_ids: list[str] | None = None,
        execution_id: str | None = None,
        statuses: tuple[str, ...] = ("OPEN", "RERUN_FAILED"),
    ) -> list[dict[str, Any]]:
        """查可重跑的 T_EXTRACT_FAIL case（供重跑服务分组、下发）。

        与只读口径对齐：除给定状态外，RESOLVED/RERUNNING 案在其绑定重跑执行
        非成功终态（异常/失败/终止）或执行记录已缺失时同样可重跑——「已完成」
        必须以执行概要成功为准，概要非成功的失败记录可以一直重跑。
        """
        fetch_statuses = tuple(dict.fromkeys((*statuses, "RESOLVED", "RERUNNING")))
        with self.sf() as s:
            q = select(ReviewCase).where(ReviewCase.template_id == "T_EXTRACT_FAIL")
            if case_ids:
                q = q.where(ReviewCase.id.in_(case_ids))
            if fetch_statuses:
                q = q.where(ReviewCase.status.in_(fetch_statuses))
            rows = s.scalars(q).all()
            exec_statuses = resolve_execution_statuses(
                [(load(x.input_snapshot) or {}).get("rerunExecutionId") for x in rows]
            )
        result: list[dict[str, Any]] = []
        for c in rows:
            snapshot = load(c.input_snapshot) or {}
            if c.status not in statuses and not extract_fail_rerunnable(snapshot, exec_statuses):
                continue
            if execution_id and snapshot.get("executionId") != execution_id:
                continue
            record_id = str(c.source_record_id or "")
            if not record_id:
                continue
            result.append(
                {
                    "caseId": c.id,
                    "graphSpace": c.graph_space,
                    "recordId": record_id,
                    "sourceBindingId": str(snapshot.get("sourceBindingId") or ""),
                    "schemaId": snapshot.get("schemaId"),
                    "schemaKey": snapshot.get("schemaKey"),
                    "executionId": snapshot.get("executionId"),
                    "jobId": snapshot.get("jobId"),
                    "attempt": int(snapshot.get("attempt") or 1),
                    "sourceTable": c.source_table,
                    "status": c.status,
                }
            )
        return result

    def mark_extract_rerun(
        self, case_ids: list[str], *, rerun_execution_id: str | None = None
    ) -> int:
        """重跑下发前把 T_EXTRACT_FAIL case 标 RERUNNING（必须在触发执行**之前**调用）。

        先标记再触发，避免竞态（执行先完成而 case 尚未标记导致回写落空）。
        执行 id 由 ``attach_rerun_execution`` 在触发成功后补写进 snapshot。
        触发失败由调用方 ``revert_extract_rerun`` 回滚为 OPEN。

        终态/RERUNNING 的案默认跳过；例外是只读口径放行的「概要非成功」案
        （重跑异常/失败后误归已完成、或滞留重跑中）——重新标 RERUNING 拉起
        正常闭环，结束时 resolve 照常回写成功/仍失败。
        """
        actor = self._extract_service_actor("rerun")
        t = now()
        marked = 0
        with self.sf() as s:
            cases = [
                c
                for c in (
                    s.scalar(select(ReviewCase).where(ReviewCase.id == case_id))
                    for case_id in case_ids
                )
                if c is not None
            ]
            # 只有终态/RERUNNING 案才需要核验执行概要（OPEN/RERUN_FAILED 恒可标）
            gate_candidates = [
                c for c in cases if c.status in TERMINAL_STATUSES or c.status == "RERUNNING"
            ]
            exec_statuses = (
                resolve_execution_statuses(
                    [
                        (load(c.input_snapshot) or {}).get("rerunExecutionId")
                        for c in gate_candidates
                    ]
                )
                if gate_candidates
                else {}
            )
            for c in cases:
                if c.template_id != "T_EXTRACT_FAIL":
                    continue
                if (c.status in TERMINAL_STATUSES or c.status == "RERUNNING") and not (
                    extract_fail_rerunnable(load(c.input_snapshot) or {}, exec_statuses)
                ):
                    continue
                snapshot = load(c.input_snapshot) or {}
                if rerun_execution_id:
                    snapshot["rerunExecutionId"] = rerun_execution_id
                c.input_snapshot = dump(snapshot)
                old = c.status
                c.status = "RERUNNING"
                c.version += 1
                c.updated_at = t
                self.audit(
                    s,
                    c,
                    actor,
                    "RERUN_STARTED",
                    old,
                    c.status,
                    {"rerunExecutionId": rerun_execution_id},
                )
                marked += 1
            s.commit()
        return marked

    def attach_rerun_execution(self, case_ids: list[str], rerun_execution_id: str) -> int:
        """触发成功后把重跑执行 id 补写进 case snapshot（前端展示/追踪）。

        只补写本次已标 RERUNING 的案：mark 阶段被跳过的案（如真正已完成）
        不改绑执行，保持「已完成·概要成功」的核验链稳定。
        """
        t = now()
        attached = 0
        try:
            with self.sf() as s:
                for case_id in case_ids:
                    c = s.scalar(select(ReviewCase).where(ReviewCase.id == case_id))
                    if c is None or c.status != "RERUNNING":
                        continue
                    snapshot = load(c.input_snapshot) or {}
                    snapshot["rerunExecutionId"] = rerun_execution_id
                    c.input_snapshot = dump(snapshot)
                    c.updated_at = t
                    attached += 1
                s.commit()
        except Exception:  # noqa: BLE001
            logger.warning("补写 rerunExecutionId 失败 cases=%s", case_ids, exc_info=True)
        return attached

    def revert_extract_rerun(self, case_ids: list[str], *, reason: str) -> int:
        """重跑触发失败时把 RERUNNING 回滚为 OPEN（best-effort，不抛错）。"""
        actor = self._extract_service_actor("rerun-revert")
        t = now()
        reverted = 0
        try:
            with self.sf() as s:
                for case_id in case_ids:
                    c = s.scalar(select(ReviewCase).where(ReviewCase.id == case_id))
                    if c is None or c.status != "RERUNNING":
                        continue
                    old = c.status
                    c.status = "OPEN"
                    c.version += 1
                    c.updated_at = t
                    self.audit(s, c, actor, "RERUN_PROGRESS", old, c.status, {"reason": reason})
                    reverted += 1
                s.commit()
        except Exception:  # noqa: BLE001
            return reverted
        return reverted

    def resolve_extract_rerun(
        self,
        *,
        rerun_case_ids: list[str],
        failed_records: list[dict[str, Any]],
        rerun_execution_id: str | None,
        task_id: str,
        kind: str = "entity",
        name: str | None = None,
    ) -> dict[str, Any]:
        """重跑执行结束后回写 T_EXTRACT_FAIL case。

        记录不在本次 failures → RESOLVED（RERUN_SUCCEEDED）；仍失败 → 原 case
        RESOLVED（被取代）+ 新 case（attempt+1，绑本次重跑执行），供再次点击重跑。
        """
        failed_by_key: dict[tuple[str, str], dict[str, Any]] = {
            (str(f.get("sourceBindingId") or ""), str(f.get("recordId") or "")): f
            for f in failed_records
            if isinstance(f, dict)
        }
        actor = self._extract_service_actor("rerun-resolve")
        t = now()
        resolved = 0
        refailed: list[dict[str, Any]] = []
        with self.sf() as s:
            cases = s.scalars(
                select(ReviewCase).where(ReviewCase.id.in_(rerun_case_ids or []))
            ).all()
            for c in cases:
                if c.template_id != "T_EXTRACT_FAIL" or c.status != "RERUNNING":
                    continue
                snapshot = load(c.input_snapshot) or {}
                key = (str(snapshot.get("sourceBindingId") or ""), str(c.source_record_id))
                old = c.status
                c.status = "RESOLVED"
                c.updated_at = t
                if key in failed_by_key:
                    self.audit(
                        s,
                        c,
                        actor,
                        "RERUN_FAILED",
                        old,
                        "RESOLVED",
                        {"rerunExecutionId": rerun_execution_id, "superseded": True},
                    )
                    refailed.append(
                        {"case": c, "snapshot": snapshot, "failure": failed_by_key[key]}
                    )
                else:
                    self.audit(
                        s,
                        c,
                        actor,
                        "RERUN_SUCCEEDED",
                        old,
                        "RESOLVED",
                        {"rerunExecutionId": rerun_execution_id},
                    )
                resolved += 1
            s.commit()
        recreated = 0
        for item in refailed:
            case = item["case"]
            snapshot = item["snapshot"]
            failure = item["failure"]
            next_attempt = int(snapshot.get("attempt") or 1) + 1
            try:
                self.create_direct_case(
                    graph_space=case.graph_space,
                    task_id=case.source_task_id or task_id,
                    execution_id=rerun_execution_id,
                    step_id=case.pipeline_step_id or "extract",
                    kind=case.object_type or kind,
                    candidate={
                        "recordId": str(case.source_record_id),
                        "error": str(failure.get("error") or ""),
                        "schemaKey": snapshot.get("schemaKey"),
                        # attempt 必须进去重键：原 case 的 candidate 与本调用完全
                        # 相同（同 task/step/record/error），不带 attempt 会命中
                        # 原案去重，attempt+1 新 case 永远建不出来
                        "attempt": next_attempt,
                    },
                    object_id=str(case.source_record_id),
                    object_name=case.object_name,
                    node_label=(name if (case.object_type or kind) == "entity" else None),
                    edge_type=(name if (case.object_type or kind) != "entity" else None),
                    reason=f"重跑仍失败: {str(failure.get('error') or '')[:500]}",
                    workflow_id=case.workflow_id,
                    source_table=case.source_table,
                    source_record_id=str(case.source_record_id),
                    domain=case.domain or "graph",
                    service_actor="kg.schema.extract",
                    template_id="T_EXTRACT_FAIL",
                    workflow_type="kg.schema.extract",
                    exception_code="KG_EXTRACT_RECORD_FAILED",
                    resume_token=f"extract-fail:{rerun_execution_id}:{case.source_record_id}",
                    extra_snapshot={
                        **{k: v for k, v in snapshot.items() if k != "rerunExecutionId"},
                        "attempt": next_attempt,
                        "rerunOfExecutionId": snapshot.get("executionId"),
                        "executionId": rerun_execution_id,
                    },
                )
                recreated += 1
            except Exception:  # noqa: BLE001
                logger.warning("重跑仍失败的新 case 创建失败: %s", case.id, exc_info=True)
        return {"resolved": resolved, "refailed": len(refailed), "recreated": recreated}

    # ------------------------------------------------------------------
    # T_LINK：实体对齐裁决执行（写前扣留 case 真实写图）
    # ------------------------------------------------------------------

    def park_or_rewrite_edges(
        self,
        edge_type: str,
        records: list[dict[str, Any]],
        graph_space: str | None = None,
        decision_policy: dict[str, Any] | None = None,
        live_resolved_vids: set[str] | None = None,
    ) -> dict[str, Any]:
        """关系写图前端点消歧处理（``write_records`` 关系分支调用，跨执行兜底）。

        - 端点命中未决 T_LINK 灰区 case → 该边挂到 case 快照 ``_pendingRelations``
          （裁决 merge/create 时统一补写，不产生 Nebula 悬挂点；按边类型+端点去重幂等）；
        - 端点 case 已裁决 merge → 端点改写为目标实体后正常返回写；
        - 端点实体已被驳回（verdict=reject）→ 该边一并丢弃；
        - 其余（含已裁决 create，预留 vid 已入库）→ 原样返回写。

        ``graph_space``：抽取目标图空间。vid 跨空间同名（person_xxx 在所有空间
        指同一学者），T_LINK case 却按空间归属——不按空间过滤时，其它空间
        （gkx_verify_1 等验证场）的未决 case 会拦下本空间的边并暂存进外空间
        快照，裁决补写也落到外空间图。传空时不过滤（旧调用兼容）。

        ``decision_policy``（gray-gate-v2）：传 gray-gate-v2 策略时走版本化路由
        （``_park_edges_v2``）——开放案按 rank 表确定性选 capture 案（仅 rank ≥ 2
        收新边），端点只余 v1 强制案时 ``BLOCKED_BY_LEGACY_CASE`` 失败关闭（不再
        「计数后继续」）；非终态且不可提交（APPLY_FAILED/中断）失败关闭（R5）；
        终态案处置以 ``manual_review_verdict_application`` 为权威
        （``prior_verdict_disposition`` 三态；merge 重放 canonical 只能来自持久
        remap，R7）。传 None（旧调用/在飞 run 重放）时本方法行为与
        gray-gate-v2 之前逐字节一致。

        ``live_resolved_vids``：当次裁决已活的端点（R6 裁决补边专用，见
        ``_park_edges_v2``）；仅 v2 路由生效。
        """
        if not records:
            return {"records": [], "parked": 0, "dropped": 0}
        endpoints = {str(r.get("fromId")) for r in records} | {str(r.get("toId")) for r in records}
        with self.sf() as s:
            filters = [
                ReviewCase.template_id == "T_LINK",
                ReviewCase.object_id.in_(endpoints),
            ]
            if graph_space:
                filters.append(ReviewCase.graph_space == graph_space)
            cases = s.scalars(select(ReviewCase).where(*filters)).all()
            if decision_policy is not None:
                return self._park_edges_v2(
                    s, edge_type, records, cases, live_resolved_vids=live_resolved_vids
                )
            return self._park_edges_v1(s, edge_type, records, cases)

    def _park_edges_v1(
        self,
        s: Any,
        edge_type: str,
        records: list[dict[str, Any]],
        cases: list[ReviewCase],
    ) -> dict[str, Any]:
        """park 旧路径（gray-gate-v2 之前的行为，在飞 run 重放安全）。"""
        verdicts: dict[str, tuple[str | None, str | None]] = {}
        open_cases = {c.object_id: c for c in cases if c.status not in TERMINAL_STATUSES}
        for c in cases:
            if c.object_id in open_cases:
                continue
            d = s.scalar(
                select(ReviewDecision)
                .where(ReviewDecision.case_id == c.id)
                .order_by(ReviewDecision.id.desc())
            )
            res = (load(d.result) or {}) if d else {}
            verdicts[c.object_id] = (res.get("entityVerdict"), res.get("targetEntityId"))
        parked_records = [
            r
            for r in records
            if str(r.get("fromId")) in open_cases or str(r.get("toId")) in open_cases
        ]
        for record in parked_records:
            vid = next(
                v for v in (str(record.get("fromId")), str(record.get("toId"))) if v in open_cases
            )
            case = open_cases[vid]
            snapshot = load(case.candidate_snapshot) or {}
            pending = snapshot.setdefault("_pendingRelations", [])
            rel = {
                "edgeType": edge_type,
                "fromId": str(record.get("fromId")),
                "toId": str(record.get("toId")),
                "props": record.get("props") or {},
            }
            if not any(
                p.get("edgeType") == rel["edgeType"]
                and p.get("fromId") == rel["fromId"]
                and p.get("toId") == rel["toId"]
                for p in pending
            ):
                pending.append(rel)
                case.candidate_snapshot = dump(snapshot)
                case.updated_at = now()
        s.commit()
        kept: list[dict[str, Any]] = []
        dropped = 0
        for record in records:
            frm, to = str(record.get("fromId")), str(record.get("toId"))
            if frm in open_cases or to in open_cases:
                continue
            if "reject" in (verdicts.get(frm, (None, None))[0], verdicts.get(to, (None, None))[0]):
                dropped += 1
                continue
            out = dict(record)
            for key, vid in (("fromId", frm), ("toId", to)):
                verdict, target = verdicts.get(vid, (None, None))
                if verdict == "merge" and target:
                    out[key] = str(target)
            kept.append(out)
        return {"records": kept, "parked": len(parked_records), "dropped": dropped}

    def _cas_mutate_case_snapshot(
        self,
        case_id: str,
        mutate,
        *,
        require_submittable: bool = False,
        max_attempts: int = 8,
    ):
        """案件快照乐观 CAS 短事务读改写（R6-b）。

        park attach / 转交 / 裁决摘除共用同一并发约束：每次尝试在独立短事务
        内重读最新 ``(version, status, candidate_snapshot)``，条件 UPDATE 以
        **双谓词**守卫（等价同事务锁定重读）：

        - ``version = 读值``：submit 的 version CAS 预留会递增 version——裁决
          与 park 互斥，案件转终态后 attach 必然失配重试（重读状态后失败
          关闭），不产孤儿暂存边；
        - ``candidate_snapshot = 读到的原字节``：park 与 park 互斥（park 不递增
          version，不占用 submit 的乐观锁梯子——评审端提交版本号不因暂存边
          到达而失效）。

        ``mutate`` 就地修改快照，返回值在提交成功后透传。``rowcount = 0``
        （并发提交抢先）整体重试，重试基于他人刚提交的新快照再次套用——成功
        park 的边不丢。重试耗尽抛 RuntimeError（失败关闭：activity 失败、
        来源水位不推进）。

        ``require_submittable``（park attach 用）：同事务重读发现案件已转
        终态（裁决先落库）时不追加，抛 RuntimeError 让调用方重试重路由——
        杜绝「裁决已定、边后到被挂进永不再看的快照」的孤儿边。
        """
        for _ in range(max_attempts):
            with self.sf() as s:
                row = s.execute(
                    select(
                        ReviewCase.version,
                        ReviewCase.status,
                        ReviewCase.candidate_snapshot,
                    ).where(ReviewCase.id == case_id)
                ).first()
                if row is None:
                    return None  # 案件行已不存在：调用方按自身语义处置
                if require_submittable and row.status not in SUBMITTABLE_STATUSES:
                    raise RuntimeError("capture 案在暂存落库前已转终态，失败关闭重试重路由")
                snapshot = load(row.candidate_snapshot) or {}
                out = mutate(snapshot)
                stale_bytes = row.candidate_snapshot
                snapshot_pred = (
                    ReviewCase.candidate_snapshot == stale_bytes
                    if stale_bytes is not None
                    else ReviewCase.candidate_snapshot.is_(None)
                )
                reserved = s.execute(
                    update(ReviewCase)
                    .where(ReviewCase.id == case_id, ReviewCase.version == row.version)
                    .where(snapshot_pred)
                    .values(candidate_snapshot=dump(snapshot), updated_at=now())
                )
                if reserved.rowcount == 1:
                    s.commit()
                    return out
                s.rollback()
        raise RuntimeError("案件快照并发冲突重试耗尽（park/裁决补边失败关闭）")

    def _park_edges_v2(
        self,
        s: Any,
        edge_type: str,
        records: list[dict[str, Any]],
        cases: list[ReviewCase],
        live_resolved_vids: set[str] | None = None,
    ) -> dict[str, Any]:
        """park 版本化路由（gray-gate-v2）。

        每个端点 vid 独立路由：开放案走 ``select_capture_case``（rank 降序 →
        created_at 升序 → case_id 字典序，仅 rank ≥ 2 收新边），无 v2 开放案
        而仍有 v1 强制案 → ``BLOCKED_BY_LEGACY_CASE`` 失败关闭；非终态且不可
        提交（APPLY_FAILED/中断）→ ``VERDICT_NOT_APPLIED`` 失败关闭（R5：应用
        失败的案不得吞入新边，恢复走人工重应用通道）；终态案以 application
        表权威派生处置（drop / 原样写 / 改写 canonical——merge 重放的 canonical
        只能来自经批准的持久 remap（R7），应用行/决议目标不得充当映射）。快照
        含未登记 policyVersion 串 → ``UNKNOWN_POLICY_VERSION``。错误 detail
        零标识符（完整端点清单由调用方走受控 claim-check）。

        ``live_resolved_vids``（R6，裁决补边路径专用）：本次裁决已活的端点
        （创建落点 / merge 目标）——凭评审员当次决议直接放行，跳过案件路由
        （含该端点上无关的开放案，避免评审员已定的边被别的案再扣）。

        R6-b：attach 不再「读快照→内存追加→整体覆盖提交」（两个 worker 并发
        park 同案会互相覆盖、都报成功、被覆盖边永不可见），改走
        ``_cas_mutate_case_snapshot`` 版本 CAS 短事务——park、转交、摘除与
        submit 的 version CAS 共用一致并发约束；案件落库前转终态（并发裁决
        先提交）失败关闭，重试后按终态处置重路由，不产孤儿暂存边。
        """
        live = {str(v) for v in (live_resolved_vids or ())}
        open_by_vid: dict[str, list[ReviewCase]] = {}
        terminal_by_vid: dict[str, list[ReviewCase]] = {}
        ranks: dict[str, int] = {}
        for c in cases:
            if str(c.object_id) in live:
                continue  # 当次裁决已活端点：不再进路由（R6）
            # 未登记版本串在此失败关闭（含开放与终态案，不做词法比较）
            ranks[c.id] = case_policy_rank(case_policy_version(c))
            if c.status in TERMINAL_STATUSES:
                bucket = terminal_by_vid
            elif c.status in SUBMITTABLE_STATUSES:
                bucket = open_by_vid
            else:
                # APPLY_FAILED / 中断等：耐久应用标记权威，FAILED/UNKNOWN 失败
                # 关闭（R5）——不吞边、不猜测
                app = s.scalar(
                    select(ReviewVerdictApplication).where(ReviewVerdictApplication.case_id == c.id)
                )
                raise VerdictNotAppliedError(
                    {
                        "applyStatus": (app.apply_status if app else "UNKNOWN"),
                        "caseRank": ranks[c.id],
                    }
                )
            bucket.setdefault(c.object_id, []).append(c)

        # 终态处置：application 行存在即权威（prior_verdict_disposition 三态；
        # merge 走持久 remap 解析，R7）。无任何 application 行的真 v1 终态案
        # 回落决议读取——仅 reject 语义可靠，merge/create 无应用权威按 UNKNOWN
        # 失败关闭（历史强制案禁 merge/create，收口口径）
        verdicts: dict[str, tuple[str | None, str | None]] = {}
        for vid, tcases in terminal_by_vid.items():
            capture = select_capture_case(tcases)
            authority = capture
            if authority is None:
                with_app = [c for c in tcases if _case_has_application(s, c.id)]
                if with_app:
                    # v1 快照案但经 v2 两段提交落裁决：application 行同样权威
                    authority = max(
                        with_app, key=lambda c: (ranks[c.id], c.created_at or "", str(c.id))
                    )
            if authority is not None:
                app = s.scalar(
                    select(ReviewVerdictApplication).where(
                        ReviewVerdictApplication.case_id == authority.id
                    )
                )
                if app is None:
                    # 案缺 application 行=UNKNOWN，失败关闭不猜测
                    raise VerdictNotAppliedError(
                        {"applyStatus": "UNKNOWN", "caseRank": ranks[authority.id]}
                    )
                target = None
                if app.verdict == "create":
                    target = app.reserved_vid
                disposition = prior_verdict_disposition(
                    {
                        "entityVerdict": app.verdict,
                        "applyStatus": app.apply_status,
                        "targetEntityId": target,
                    },
                    source_vid=vid,
                )
            else:
                for c in tcases:
                    d = s.scalar(
                        select(ReviewDecision)
                        .where(ReviewDecision.case_id == c.id)
                        .order_by(ReviewDecision.id.desc())
                    )
                    res = (load(d.result) or {}) if d else {}
                    if res.get("entityVerdict") == "reject":
                        verdicts[vid] = ("reject", None)
                    else:
                        raise VerdictNotAppliedError(
                            {"applyStatus": "UNKNOWN", "caseRank": ranks[c.id]}
                        )
                continue
            if disposition["disposition"] == "drop_record":
                verdicts[vid] = ("reject", None)
            elif disposition["disposition"] == "rewrite_to_canonical":
                verdicts[vid] = ("merge", disposition["vid"])
            else:  # write_as_new：端点即预留 vid（resolve 路径已落图），原样写
                verdicts[vid] = ("create", disposition["vid"])

        # 开放案路由：capture 选择（仅 rank≥2）；无 v2 开放案 → BLOCKED_BY_LEGACY_CASE
        capture_by_vid: dict[str, ReviewCase] = {}
        legacy_blocked: list[str] = []
        for vid, ocases in open_by_vid.items():
            capture = select_capture_case(ocases)
            if capture is None:
                legacy_blocked.append(vid)
            else:
                capture_by_vid[vid] = capture
        if legacy_blocked:
            # 失败关闭：不把 v2 的边挂进 v1 案快照（v1 案裁决语义不含 application）
            raise BlockedByLegacyCaseError(
                {
                    "edgeType": edge_type,
                    "blockedEndpointCount": len(legacy_blocked),
                    "openCaseCount": sum(len(v) for v in open_by_vid.values()),
                }
            )

        parked_records = [
            r
            for r in records
            if str(r.get("fromId")) in capture_by_vid or str(r.get("toId")) in capture_by_vid
        ]
        for record in parked_records:
            vid = next(
                v
                for v in (str(record.get("fromId")), str(record.get("toId")))
                if v in capture_by_vid
            )
            rel = {
                "edgeType": edge_type,
                "fromId": str(record.get("fromId")),
                "toId": str(record.get("toId")),
                "props": record.get("props") or {},
            }

            # R6-b：attach 走版本 CAS 短事务（不再内存改快照后整体覆盖提交）。
            # 并发 park 同案在 version 守卫下串行化：后到者读到先到者刚提交的
            # 快照再追加，双方成功确认的边都保留；案件在落库前转终态则失败
            # 关闭重试重路由（require_submittable）。
            def _attach(snapshot: dict[str, Any], _rel: dict[str, Any] = rel) -> None:
                pending = snapshot.setdefault("_pendingRelations", [])
                if not any(
                    p.get("edgeType") == _rel["edgeType"]
                    and p.get("fromId") == _rel["fromId"]
                    and p.get("toId") == _rel["toId"]
                    for p in pending
                ):
                    pending.append(_rel)

            self._cas_mutate_case_snapshot(
                str(capture_by_vid[vid].id), _attach, require_submittable=True
            )
        # 外层读事务收尾提交：快照写入已全部走 CAS 短事务，此处无脏对象；
        # 保留 commit 维持事务边界语义（长事务不再覆写 candidate_snapshot）
        s.commit()
        kept: list[dict[str, Any]] = []
        dropped = 0
        for record in records:
            frm, to = str(record.get("fromId")), str(record.get("toId"))
            if frm in capture_by_vid or to in capture_by_vid:
                continue
            if "reject" in (verdicts.get(frm, (None, None))[0], verdicts.get(to, (None, None))[0]):
                dropped += 1
                continue
            out = dict(record)
            for key, vid in (("fromId", frm), ("toId", to)):
                verdict, target = verdicts.get(vid, (None, None))
                if verdict == "merge" and target:
                    out[key] = str(target)
            kept.append(out)
        return {"records": kept, "parked": len(parked_records), "dropped": dropped}

    def _enrich_link_snapshot(self, c: ReviewCase, snapshot: dict[str, Any]) -> dict[str, Any]:
        """T_LINK 详情实时富化（只读，不回写快照）：给裁决补判定证据。

        建案快照只存 ``{vid, name, score}``（temporal_workflows 建案处丢弃了
        评分明细与候选属性），存量 OPEN 案打开详情时现查图库补齐：

        - 每个候选补全量 ``props`` 并重算评分明细（nameSim/propsAgree/comparedProps）；
          建案快照已带证据字段（v2）时建案时点只读——重算结果进独立 ``recheck``
          （``_enriched.asOf`` 取数时点），总分与明细不互相矛盾（R8）；
        - 图库同名实体总数（TOP_K 截断外的候选评审员看不见）；
        - ``_pendingRelations`` 挂起边补两端显示名（reject 会把这些边一并丢弃）。

        任一步失败按原快照返回，不阻塞详情。
        """
        if canonical_template(c.template_id) != "T_LINK" or not snapshot:
            return snapshot
        incoming = snapshot.get("_incoming")
        incoming_props = (incoming.get("props") or {}) if isinstance(incoming, dict) else {}
        display = str(snapshot.get("name") or c.object_name or "")
        incoming_vid = str((incoming or {}).get("vid") or c.object_id or "")
        try:
            from service.entity_disambiguation import (
                display_name,
                recall_same_name,
                score_candidate,
            )

            client = self._graph_client_for(snapshot)
            try:
                # 同名召回一次拿全：总数 + 各候选属性（tag 无显示名列时为空，逐点降级）；
                # tag 取快照 _nodeLabel（与 _apply_link_verdict 同源，ReviewCase 无此列）
                node_label = str(snapshot.get("_nodeLabel") or "")
                by_vid: dict[str, dict[str, Any]] = {}
                if display and node_label:
                    space = str(snapshot.get("_graphSpace") or "")
                    es_by_vid = self._es_same_name_by_vid(space, node_label, display)
                    if es_by_vid is not None:
                        by_vid = es_by_vid
                    else:
                        # ES 不可用/名字列未回填 → 图召回（四列 OR 全扫，实测秒级）；
                        # v2 起返回 (candidates, routeStatus) 信封，此处只用候选
                        recalled, _route_status = recall_same_name(client, node_label, [display])
                        recalled = recalled or {}
                        # 矛盾防御：快照有候选而召回为空（trs-graph 会话池紧张时 DESCRIBE
                        # 偶发 500 → 降级裸 name 列 → 空结果），重试一次再采信
                        if not any(recalled.values()) and snapshot.get("existingCandidates"):
                            recalled, _route_status = recall_same_name(
                                client, node_label, [display]
                            )
                            recalled = recalled or {}
                        by_vid = {
                            str(cand.get("vid")): cand
                            for cands in recalled.values()
                            for cand in cands
                            if cand.get("vid")
                        }
                by_vid.pop(incoming_vid, None)

                def _props_of(vid: str) -> dict[str, Any]:
                    raw: dict[str, Any] = {}
                    if by_vid.get(vid, {}).get("props"):
                        raw = by_vid[vid]["props"] or {}
                    else:
                        for _ in range(2):  # 单次抖动重试一次，仍失败按空属性
                            try:
                                node = client.get_node(vid)
                                raw = dict(getattr(node, "properties", {}) or {})
                                break
                            except Exception:  # noqa: BLE001
                                continue
                    # 图库历史乱码读出即修（对照表/评分/挂起边点名共用此出口）
                    return {k: self._fix_mojibake(v) for k, v in raw.items()}

                for cand in snapshot.get("existingCandidates") or []:
                    if not isinstance(cand, dict) or not cand.get("vid"):
                        continue
                    props = _props_of(str(cand["vid"]))
                    if props:
                        cand["props"] = props
                        # 建案时快照的候选名同样可能来自乱码属性，一并修复后再评分
                        cand["name"] = self._fix_mojibake(cand.get("name")) or cand.get("name")
                        _, detail = score_candidate(
                            display,
                            incoming_props,
                            str(cand.get("name") or display_name(props)),
                            props,
                        )
                        if any(
                            key in cand
                            for key in ("nameSim", "propsAgree", "comparedProps", "propCompared")
                        ):
                            # R8：建案时点证据只读——当前图库属性与建案时不一致
                            # 本身就是需要如实呈现的事实（总分/明细若被覆盖，
                            # cand.score 与重算明细会互相矛盾）。重算结果进独立
                            # ``recheck``（带 asOf 时点），不覆盖建案证据字段；
                            # cand.score / _resolution.matchScore 同为建案时点不动
                            cand["recheck"] = {
                                "nameSim": detail.get("nameSim"),
                                "propsAgree": detail.get("propsAgree"),
                                "propCompared": detail.get("propCompared"),
                                "propMatched": detail.get("propMatched"),
                                "comparedProps": detail.get("comparedProps"),
                            }
                        else:
                            # 存量案建案无证据字段（v1 快照）：原位补齐（向后兼容）
                            cand.update(detail)  # nameSim / propsAgree / comparedProps

                # 挂起边两端显示名（reject 裁决会把这些边一并丢弃，评审员需可见代价）
                names: dict[str, str] = {}
                for rel in snapshot.get("_pendingRelations") or []:
                    if not isinstance(rel, dict):
                        continue
                    for side in ("fromId", "toId"):
                        vid = str(rel.get(side) or "")
                        if vid and vid not in names:
                            names[vid] = display_name(_props_of(vid)) or vid
                    rel["fromName"] = names.get(str(rel.get("fromId") or ""), "")
                    rel["toName"] = names.get(str(rel.get("toId") or ""), "")

                snapshot["_enriched"] = {
                    "policyVersion": "detail-enrich-v1",
                    "sameNameTotal": len(by_vid),
                    # R8：recheck（建案后候选属性变化的重算）取数时点
                    "asOf": _now_str(),
                }
            finally:
                pass  # 客户端已换 infra 按空间共享缓存，不可 close
        except Exception as exc:  # noqa: BLE001
            logger.warning("T_LINK 详情证据富化失败 case=%s，按原快照展示: %s", c.id, exc)
        return snapshot

    def _es_same_name_by_vid(
        self, space: str, node_label: str, display: str
    ) -> dict[str, dict[str, Any]] | None:
        """ES 精确同名召回（T_LINK 详情富化快路）：四个显示名列 keyword 等值。

        ES 未配置 / 空间未同步 / 名字列未回填 / 查询异常一律返回 None，
        调用方回退图同名召回（图召回是四列 OR 全扫，实测秒级——ES 命中后
        详情富化从 ~1.8s 降到 ~0.4s）。只用于评审证据展示，不进消歧判定。"""
        from infra.elasticsearch import get_entity_keyword_es

        if not space or not display:
            return None
        store = get_entity_keyword_es()
        if store is None:
            return None
        try:
            if not store.ready(space) or not store.names_indexed(space):
                return None
            docs = store.search_by_names(space, [display], entity_type=node_label, size=200)
        except Exception:  # noqa: BLE001 - 展示富化 fail-open
            logger.warning(
                "T_LINK 详情 ES 同名召回失败，回退图查询 name=%s: ", display, exc_info=True
            )
            return None
        by_vid: dict[str, dict[str, Any]] = {}
        for doc in docs:
            vid = str(doc.get("vid") or "")
            if not vid:
                continue
            item = doc.get("item") if isinstance(doc.get("item"), dict) else {}
            name = ""
            for col in ("name", "name_zh", "name_cn", "name_en"):
                if doc.get(col):
                    name = str(doc[col])
                    break
            by_vid[vid] = {
                "vid": vid,
                "name": name or str(item.get("name") or ""),
                "props": dict(item.get("properties") or {}),
            }
        return by_vid

    @staticmethod
    def _fix_mojibake(value: Any) -> Any:
        """修复图库读出的 UTF-8→单字节编码乱码串（如 ``æ¸…å¤§å­¦`` → ``清华大学``）。

        历史写入通道把中文按 latin-1/cp1252 字节落库（后续消歧更新字段正常），
        候选属性整片乱码会同时毁掉对照表与属性一致率评分。仅当全串能还原回
        单字节且 utf-8 解码后含 CJK 才替换——正常中文单字节编码必抛错、纯
        ASCII 解码后不含 CJK，均原样返回，零误伤；只修读出的值，不动图数据。
        """
        if not isinstance(value, str) or not value:
            return value
        # 逐字符还原原字节：cp1252 优先（€ ˆ ™ “ 等映射 0x80-0x9F），其未定义
        # 空洞（0x81/0x8D/0x8F/0x90/0x9D，Java 通道按 ISO 控制符解码）用 latin-1
        # 兜底；出现两种编码都编不了的字符（正常中文/emoji）即认定非双重编码串
        out = bytearray()
        for ch in value:
            try:
                out += ch.encode("cp1252")
            except UnicodeEncodeError:
                try:
                    out += ch.encode("latin-1")
                except UnicodeEncodeError:
                    return value
        try:
            fixed = bytes(out).decode("utf-8")
        except UnicodeDecodeError:
            return value
        if any("一" <= ch <= "鿿" for ch in fixed):
            return fixed
        return value

    def _graph_client_for(self, snapshot: dict[str, Any]) -> Any:
        """按快照记载的图空间取共享客户端（缺省走环境默认空间）。

        直连客户端每开一次详情/每裁一次决都要新建会话 + connect（实测
        ~390ms），换 infra 的按空间缓存客户端后连接复用；共享客户端
        调用方不得 close。"""
        from infra.graph_db import get_space_client
        from infra.graph_db.config import TRSGraphSettings

        space = str(snapshot.get("_graphSpace") or TRSGraphSettings.from_env().space)
        return get_space_client(space)

    def _apply_link_verdict(self, c: ReviewCase, result: dict[str, Any]) -> dict[str, Any]:
        """T_LINK 裁决执行：merge→扣留记录并入所选候选；create→按预留 vid 新建。

        写前扣留 case（快照含 ``_incoming``）：实体落图走
        ``_insert_withheld_vertex``（per-VID 锁 + FETCH 旧值列级合并后整列
        INSERT——Nebula 整标签覆盖语义下裸 INSERT 会清掉目标既有列，见其
        docstring），merge 与 create 是同一条语句、仅 vid 不同；
        ``_pendingRelations`` 里的待定边在实体落图后经 ``_flush_pending_relations``
        双端点统一路由补写（R6：另一端未决转交该端开放案、reject 丢弃、两端
        允许才存在性终判后 INSERT）。图写失败异常上抛 → Tx2 收敛 FAILED、案
        APPLY_FAILED 进 failed 队列（人工重应用另批）。存量写后 case（无
        ``_incoming``）只记录决议。
        """
        snapshot = load(c.candidate_snapshot) or {}
        from service.business_access_control import rbac_enabled

        if rbac_enabled():
            if not c.graph_space:
                raise ReviewForbiddenError("审核记录未明确归属图空间")
            snapshot["_graphSpace"] = c.graph_space
        incoming = snapshot.get("_incoming")
        if not incoming:
            return {"applied": False, "note": "存量写后 case：实体已在图，仅记录决议"}
        from infra.graph_db.config import TRSGraphSettings

        graph_space = str(snapshot.get("_graphSpace") or TRSGraphSettings.from_env().space)
        node_label = str(snapshot.get("_nodeLabel") or "")
        verdict = result.get("entityVerdict")
        if verdict == "merge":
            target = str(result.get("targetEntityId") or "")
            allowed = {
                str(x.get("vid")) for x in snapshot.get("existingCandidates") or [] if x.get("vid")
            }
            if target not in allowed:
                raise ReviewValidationError("目标实体不在候选集内")
            vid = target
        elif verdict == "create":
            vid = str(incoming.get("vid") or c.object_id)
        else:
            raise ReviewValidationError("retype 暂不支持：请驳回后修正脚本重跑")
        client = self._graph_client_for(snapshot)
        try:
            self._insert_withheld_vertex(client, c, snapshot, incoming, vid, graph_space)
            written_edges, parked_edges, dropped_edges = self._flush_pending_relations(
                c,
                snapshot,
                client,
                graph_space,
                old_vid=str(incoming.get("vid") or c.object_id),
                vid=vid,
            )
        finally:
            pass  # 客户端已换 infra 按空间共享缓存，不可 close
        return {
            "applied": True,
            "verdict": verdict,
            "vid": vid,
            "graphSpace": graph_space,
            "nodeLabel": node_label,
            "pendingRelationsWritten": written_edges,
            "pendingRelationsParked": parked_edges,
            "pendingRelationsDropped": dropped_edges,
        }

    def _flush_pending_relations(
        self,
        c: ReviewCase,
        snapshot: dict[str, Any],
        client: Any,
        graph_space: str,
        *,
        old_vid: str,
        vid: str,
    ) -> tuple[int, int, int]:
        """裁决后补写 ``_pendingRelations`` 挂起边（R6：双端点统一路由）。

        旧 vid 改写为当次裁决落点后，每条边经 ``park_or_rewrite_edges`` 统一
        路由（当次已活端点凭评审员决议直接放行，不再被其它开放案扣留）：

        - 另一端仍待裁决（OPEN/CLAIMED/IN_REVIEW）→ 转交该端 capture 案耐久
          暂存（attach 先落库、再从本案快照摘除，同案幂等去重；崩溃窗口内的
          双挂由另一端案去重收敛，本案已终态不会二次补写）；
        - 另一端已 reject → 丢弃；
        - 另一端应用失败/UNKNOWN、或仅剩 v1 强制案 → 失败关闭（案 APPLY_FAILED，
          走人工重应用恢复，另批）；
        - 两端允许（已活端点 / 终态 create / 无案）→ 存在性终判后 INSERT：
          非已活端点必须 ``get_node`` 真实存在，缺失或探查失败即失败关闭，
          不产悬挂边。

        返回 ``(written, parked, dropped)``。
        """
        pending_rels = [
            rel for rel in (snapshot.get("_pendingRelations") or []) if isinstance(rel, dict)
        ]
        if not pending_rels:
            return 0, 0, 0
        from service.gray_gate import decision_policy as _v2_policy

        written = parked = dropped = 0
        remaining: list[dict[str, Any]] = []
        handled_rels: list[dict[str, Any]] = []
        edge_fields: dict[str, set[str] | None] = {}
        for rel in pending_rels:
            edge_type = rel.get("edgeType")
            frm, to = str(rel.get("fromId")), str(rel.get("toId"))
            if not edge_type:
                remaining.append(rel)
                continue
            if frm == old_vid:
                frm = vid
            if to == old_vid:
                to = vid
            record = {"fromId": frm, "toId": to, "props": dict(rel.get("props") or {})}
            routed = self.park_or_rewrite_edges(
                str(edge_type),
                [record],
                graph_space,
                decision_policy=_v2_policy(),
                live_resolved_vids={vid},
            )
            parked += routed["parked"]
            dropped += routed["dropped"]
            for out in routed["records"]:
                # 存在性终判：非当次已活端点必须真实存在（探查异常原样上抛）
                for key in ("fromId", "toId"):
                    endpoint = str(out.get(key) or "")
                    if not endpoint or endpoint == vid:
                        continue
                    if client.get_node(endpoint) is None:
                        raise RuntimeError("pending 边端点在图中不存在，按失败关闭处理")
                props = self._coerce_to_schema(
                    client, edge_type, out.get("props") or {}, is_edge=True
                )
                # 平台 DDL 给边注入 NOT NULL create_time/update_time（无默认值），
                # 暂存边属性没有这些列 → INSERT 被 Nebula 拒（400 not nullable）。
                # 按边实际 schema 补审计列（与 _insert_withheld_vertex 同策略：
                # 列存在才补，schema 查不出时旧兜底照补）。
                if edge_type not in edge_fields:
                    edge_fields[edge_type] = self._edge_fields(client, edge_type)
                fields = edge_fields[edge_type]
                for key, value in (
                    ("create_time", _now_str()),
                    ("update_time", _now_str()),
                    ("source_table", props.get("source_table") or "schema_extract"),
                ):
                    if fields is None or key in fields:
                        props.setdefault(key, value)
                client.create_edge(
                    str(out.get("fromId")), str(out.get("toId")), str(edge_type), props
                )
                written += 1
            if routed["parked"] or routed["dropped"] or routed["records"]:
                handled_rels.append(rel)
        if handled_rels:
            # 已处置边（转交/丢弃/写出）从本案快照摘除（R6-b：版本 CAS 短事务
            # 按 (edgeType, fromId, toId) 精确摘除——并发 park 在窗口内追加的
            # 新边不在摘除清单内，不丢）；同步改内存对象，调用方 detail 视图
            # 不回显陈旧挂起边
            snapshot["_pendingRelations"] = remaining

            def _detach(current: dict[str, Any]) -> None:
                keys = {
                    (str(r.get("edgeType")), str(r.get("fromId")), str(r.get("toId")))
                    for r in handled_rels
                }
                current["_pendingRelations"] = [
                    r2
                    for r2 in (current.get("_pendingRelations") or [])
                    if not (
                        isinstance(r2, dict)
                        and (str(r2.get("edgeType")), str(r2.get("fromId")), str(r2.get("toId")))
                        in keys
                    )
                ]

            self._cas_mutate_case_snapshot(str(c.id), _detach)
            c.candidate_snapshot = dump(snapshot)
        return written, parked, dropped

    def _sync_entity_search_after_write(self, apply_detail: dict[str, Any]) -> None:
        """T_LINK 裁决写图成功后联动实体检索（FUNC-00813 队列与图库联动）：

        ① 单实体增量入 Milvus 索引——新实体立即可模糊检索，不必等全量重建；
        ② 失效实体搜索/浏览缓存——清掉提交前的旧空结果，避免 60s/300s 缓存空窗。
        best-effort：任何失败仅记录日志，绝不影响裁决提交（图已写，索引等下次全量重建兜底）。
        """
        if not apply_detail.get("applied"):
            return
        space = str(apply_detail.get("graphSpace") or "")
        label = str(apply_detail.get("nodeLabel") or "")
        vid = str(apply_detail.get("vid") or "")
        if not (space and label and vid):
            return
        try:
            # import 也在 try 内：模块级依赖异常同样不能让已落库的 submit 抛错
            from infra.workflow_mysql import create_workflow_session
            from service.entity_search import EntitySearchService

            session = create_workflow_session()
            try:
                result = EntitySearchService(session).upsert_entity(
                    space=space,
                    node_label=label,
                    vid=vid,
                    is_new=apply_detail.get("verdict") == "create",
                )
            finally:
                session.close()
            if result.get("upserted"):
                logger.info("裁决写图后实体已入索引 vid=%s space=%s", vid, space)
            else:
                logger.info(
                    "裁决写图后实体未入索引 vid=%s reason=%s（等待下次全量重建兜底）",
                    vid,
                    result.get("reason"),
                )
        except Exception:  # noqa: BLE001 - 索引联动失败不影响裁决
            logger.warning("裁决写图后同步实体索引失败 vid=%s（不影响裁决）", vid, exc_info=True)
        try:
            from service.entity_search import invalidate_entity_caches_sync

            invalidate_entity_caches_sync()
        except Exception:  # noqa: BLE001 - 缓存失效失败不影响裁决
            logger.warning("裁决写图后失效实体检索缓存失败（不影响裁决）", exc_info=True)

    @staticmethod
    def _tag_fields(client: Any, label: str) -> set[str] | None:
        """DESCRIBE TAG 取列集合；失败返回 None（调用方走兜底）。"""
        try:
            desc = client.execute_query(f"DESCRIBE TAG `{label}`")
            return {f for f in (r.get("Field") for r in desc.records or []) if isinstance(f, str)}
        except Exception:  # noqa: BLE001
            logger.warning("DESCRIBE TAG %s 失败，写图按旧兜底补审计列", label)
            return None

    @staticmethod
    def _edge_fields(client: Any, edge_type: str) -> set[str] | None:
        """DESCRIBE EDGE 取列集合；失败返回 None（调用方走兜底补审计列）。"""
        try:
            desc = client.execute_query(f"DESCRIBE EDGE `{edge_type}`")
            return {f for f in (r.get("Field") for r in desc.records or []) if isinstance(f, str)}
        except Exception:  # noqa: BLE001
            logger.warning("DESCRIBE EDGE %s 失败，补边按旧兜底补审计列", edge_type)
            return None

    @staticmethod
    def _fetch_existing_props(client: Any, label: str, vid: str) -> dict[str, Any]:
        """FETCH 图上该 vid 已有属性（裁决写前合并用，与写图路径 #526 同语义）。

        读失败（单次抖动重试一次后仍失败）上抛——合并失败宁可让裁决重试，
        绝不静默退回「覆盖清列」。图上旧属性无法解析（trs-graph 把 map 序列
        化成 JSON 字符串但坏了）或形状异常（非 dict）同样抛错：按「无旧值」
        继续写等于静默覆盖清列。图上 NULL（从未置过的列）不进合并。目标不
        存在 → 空 dict（调用方等同新建路径）。
        """
        import json as _json

        from infra.graph_db.exceptions import GraphRequestError

        quoted = _json.dumps(vid, ensure_ascii=False)
        result = None
        last_exc: Exception | None = None
        for _ in range(2):  # 单次抖动重试一次（与本文件 _props_of 同口径）
            try:
                result = client.execute_read(
                    f"FETCH PROP ON `{label}` {quoted} "
                    "YIELD id(vertex) AS vid, properties(vertex) AS props"
                )
                break
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
        if result is None:
            assert last_exc is not None
            raise last_exc
        for row in getattr(result, "records", None) or []:
            if not isinstance(row, dict) or str(row.get("vid") or "") != vid:
                continue
            value = row.get("props")
            if isinstance(value, str):
                try:
                    value = _json.loads(value)
                except ValueError as exc:
                    raise GraphRequestError(
                        f"图上旧属性无法解析（{label} vid={vid}，值形如 "
                        f"{str(value)[:60]!r}）——中止裁决写入防覆盖清列",
                        status_code=502,
                    ) from exc
            if value is None:
                return {}
            if not isinstance(value, dict):
                raise GraphRequestError(
                    f"图上旧属性形状异常（{label} vid={vid}，"
                    f"type={type(value).__name__}）——中止裁决写入防覆盖清列",
                    status_code=502,
                )
            # 图上 NULL（从未置过的列）不进合并，避免把 NULL 显式写回
            return {k: v for k, v in value.items() if v is not None}
        return {}

    def _insert_withheld_vertex(
        self,
        client: Any,
        c: ReviewCase,
        snapshot: dict[str, Any],
        incoming: dict[str, Any],
        vid: str,
        graph_space: str = "",
    ) -> None:
        """扣留实体按「per-VID 锁 → FETCH 旧值 → 列级合并 → 整列 INSERT」落图。

        Nebula 的 ``INSERT VERTEX`` 对已存在顶点是**整标签覆盖**：未列出的列
        会被重置成默认值（2026-10-19 服务器隔离空间实测：merge 裁决后 8 个
        合并目标学者 h_index 等既有列全被清空、source_record_id 被改写为作
        者行 vid）。旧注释「空值列不写＝不覆盖目标已有值」与真实语义相反，
        已删除。

        合并策略与平台写图路径（temporal_workflows 的 ``_merge_entity_rows``
        /``_fetch_existing_props``，#526）同款：

        - **列冲突规则**：扣留行**非空**列覆盖目标既有值；扣留行缺失/空值列
          保留目标既有值（图上 NULL 不进合并）；
        - **create_time/update_time** 不从图上保留，每次写入由平台兜底刷新
          （#526 口径，见下方 audit 注入）；
        - **身份/溯源列**（id/source_record_id/source_table/match_method/
          match_evidence/ingest_time 等）#526 未单独约定，走上述通用规则：
          目标已有值保留、扣留行非空才覆盖；两边全缺时按 audit 兜底补
          （id=vid、source_table=扣留行来源表或 schema_extract、name=快照
          展示名）；
        - **目标不存在**（create 裁决的预留 vid / merge 目标已被删）：FETCH
          空 → 合并结果即扣留行列，等同新建路径。

        并发保护：与工作流写图路径共用同一把 per-VID fail-closed Redis 锁
        （``entity_write_guard.vid_write_lock_sync``，键
        ``kg:entity:vid:{space}:{label}:{md5(vid)}``，SET NX PX + token 比删），
        锁内完成 FETCH→合并→INSERT 整个读改写窗口——工作流正写同 VID 时本
        路径等待/超时拒绝，绝不并发覆盖。锁的租约生命周期与异步版对齐：
        临界区内**心跳线程**按 TTL/3 持续续租（在途 INSERT 阻塞写线程期间
        租约持续有效，Redis 健康只是请求慢时第二写者结构性拿不到锁），叠加
        边界校验——FETCH 返回后若耗时超过 TTL/3 先续租拉长写窗口、**INSERT
        派发前必须续租并校验持有权**、**INSERT 返回后校验在途期间是否丢租**。
        临界区跨过 TTL（慢图请求、两次 FETCH、线程暂停、网络阻塞、短 TTL
        配置）且续租失败时租约已被他人接管，按旧快照继续整标签 INSERT 会静
        默清掉对方列，故丢失抛 ``VidWriteLeaseLostError`` 禁止新的/后续的
        写。拿不到锁 / FETCH 失败 / 图上旧属性无法解析 / 租约丢失 → 抛错
        （fail-closed 零新增写，submit 事务回滚、案件状态不前移，审核员重
        新提交即重试；合并后 INSERT 幂等安全）。**在途边界（诚实声明）**：
        派发后的 INSERT 无法取消、事后抛错不能回滚图库——INSERT 返回后发现
        丢租（心跳在 Redis 故障窗口内判丢）时图写可能已落地，处置是抛错让
        submit 回滚（案件不前移、后续暂存边零写），重提重新 FETCH 合并即可
        收敛（合并保留接管者落下的列）；残余窗口与 #526 异步版心跳间故障的
        在途窗口同级，此处不假装能回滚。
        """
        import json as _json
        from datetime import datetime as _dt

        from service import entity_write_guard as _guard

        node_label = snapshot.get("_nodeLabel")
        if not node_label:
            raise ReviewValidationError("实体候选缺 nodeLabel")
        props = {
            key: value
            for key, value in (incoming.get("props") or {}).items()
            if value not in (None, "")
        }
        props = self._coerce_to_schema(client, node_label, props)
        # 审计/身份列按 tag 实际 schema 补（vendor ETL 的 Organization 没有
        # id/create_time 等列，强塞会 Unknown column 400）；schema 查不出来时
        # 维持旧兜底让 trs-graph 报错暴露问题
        fields = self._tag_fields(client, node_label)
        now_str = _dt.now().strftime("%Y-%m-%d %H:%M:%S")
        # 平台 DDL 的 name 列 NOT NULL 无默认值：源脚本把名字写进 name_cn 等
        # 业务列、name 留空（空值列不写）时 INSERT 缺列被 Nebula 拒（400
        # not null field doesn't have a default value）——按快照记载的展示名补
        display_name = str(snapshot.get("name") or c.object_name or "").strip()

        def _locked_write(lease: _guard._SyncVidLease) -> None:
            old = self._fetch_existing_props(client, node_label, vid)
            # FETCH 耗时超过阈值（默认 TTL/3）→ 先续租拉长后续写窗口（慢图
            # 请求下临界区可能逼近 TTL）
            lease.refresh_if_aged()
            # 列级合并：目标既有列保留（create_time/update_time 除外，仍由
            # 平台每次刷新），扣留行非空列覆盖
            merged = {
                **{k: v for k, v in old.items() if k not in ("create_time", "update_time")},
                **props,
            }
            audit = {
                "id": vid,
                "create_time": now_str,
                "update_time": now_str,
                "source_table": incoming.get("sourceTable") or "schema_extract",
            }
            if display_name:
                audit["name"] = display_name
            for key, value in audit.items():
                if fields is None or key in fields:
                    merged.setdefault(key, value)

            def _ngql_value(value: Any) -> str:
                if isinstance(value, bool):
                    return "true" if value else "false"
                if isinstance(value, (int, float)):
                    return str(value)
                return _json.dumps(str(value), ensure_ascii=False)

            cols = ", ".join(f"`{key}`" for key in merged)
            values = ", ".join(_ngql_value(merged[key]) for key in merged)
            quoted_vid = _json.dumps(vid, ensure_ascii=False)
            # INSERT 派发前必须续租并校验持有权：临界区跨过 TTL 时租约已被
            # 他人接管，按过期快照整标签 INSERT 会清掉对方列且不抛错——续
            # 租失败即熔断（零新增写，submit 回滚、重提重试）
            lease.ensure_lease()
            client.execute_write(
                f"INSERT VERTEX `{node_label}`({cols}) VALUES {quoted_vid}:({values})"
            )
            # INSERT 返回后校验：在途期间心跳续租失败（Redis 故障窗口）则租
            # 约已丢失——图写可能已落地且不可取消，抛错熔断后续写（暂存边
            # 等），submit 回滚、案件不前移；重提重新 FETCH 合并收敛
            lease.raise_if_lost()

        with _guard.vid_write_lock_sync(graph_space, node_label, vid) as lease:
            _locked_write(lease)

    def direct_decide(
        self,
        case_id: str,
        version: int,
        accepted: bool,
        note: str,
        identity: Any,
        candidate: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """kg.custom.steps T_DIRECT 案例两步决策：accept 直接写图，reject 丢弃。

        不重启 workflow、不要求 submit 阶段。
        candidate 传"修正后的完整候选"（仅 accept 有效）：``_`` 前缀元字段
        （写图目标/审计元数据）一律以快照为准，防止改写 label/端点注入。
        """
        require_role(identity, "reviewer")
        stripped: dict[str, Any] | None = None
        if candidate is not None:
            if not accepted:
                raise ReviewValidationError("驳回不需要候选修正")
            stripped = {k: v for k, v in candidate.items() if not k.startswith("_")}
            if not stripped:
                raise ReviewValidationError("修正后的候选不能为空")
            if len(dump(stripped)) > int(os.getenv("REVIEW_SNAPSHOT_MAX_BYTES", "2097152")):
                raise ReviewValidationError("修正后的候选超出大小限制")
        with self.sf() as s:
            c = self.need(s, case_id)
            self.require_case_access(identity, c)
            if c.template_id != "T_DIRECT":
                raise ReviewValidationError("仅 T_DIRECT 案例支持 direct_decide")
            if c.status != "OPEN":
                raise ReviewConflictError("状态或版本冲突")
            # 原子占位（version CAS，与 submit 同口径）：accept 写图耗时秒级，
            # 防「读时校验」窗口内双击/并发双写图
            reserved = s.execute(
                update(ReviewCase)
                .where(
                    ReviewCase.id == case_id,
                    ReviewCase.version == version,
                    ReviewCase.status == "OPEN",
                )
                .values(version=ReviewCase.version + 1, updated_at=now())
            )
            if reserved.rowcount != 1:
                raise ReviewConflictError("状态或版本冲突")
            s.expire(c, ["version", "updated_at"])
            old = c.status
            audit_detail: dict[str, Any] = {"note": note}
            if stripped is not None:
                old_snapshot = load(c.candidate_snapshot) or {}
                old_fields = {k: v for k, v in old_snapshot.items() if not k.startswith("_")}
                meta = {k: v for k, v in old_snapshot.items() if k.startswith("_")}
                # 只记 key 不记值，避免敏感数据/大快照进审计日志
                audit_detail["candidateModified"] = True
                audit_detail["modifiedFields"] = {
                    "added": sorted(k for k in stripped if k not in old_fields),
                    "changed": sorted(
                        k for k in stripped if k in old_fields and old_fields[k] != stripped[k]
                    ),
                    "removed": sorted(k for k in old_fields if k not in stripped),
                }
                audit_detail["originalCandidateSha256"] = sha(old_fields)
                c.candidate_snapshot = dump({**stripped, **meta})
                c.updated_at = now()
            if accepted:
                self._write_candidate_to_graph(c)
                c.status = "RESOLVED"
            else:
                c.status = "REJECTED"
            c.completed_at = now()
            c.updated_at = now()
            # 与 submit 通道同口径落一条决议：详情接口靠它回显最终裁决，
            # 否则 T_DIRECT case 刷新后裁决单选回落默认值
            t = now()
            s.add(
                ReviewDecision(
                    case_id=c.id,
                    action_id="accept" if accepted else "reject",
                    result=dump({"accepted": accepted}),
                    note=note,
                    submitted_by=identity.user_id,
                    status="APPROVED",
                    created_at=t,
                    decided_at=t,
                )
            )
            self.audit(
                s,
                c,
                identity,
                "DIRECT_ACCEPTED" if accepted else "DIRECT_REJECTED",
                old,
                c.status,
                audit_detail,
            )
            s.commit()
            return self.detail(s, c)

    def refresh_candidates(self, i: str, v: int, a: Any) -> dict[str, Any]:
        """T_LINK 受控刷新未决候选（MR-CAND B）：按案件图空间重跑多路召回+打分。

        只重读图、零写图。合并策略：旧候选保留（评审员可能已开始对照）、图中
        已失效的剔除、新召回的按得分追加；快照候选形维持 ``{vid,name,score}``
        （props/nameSim 等证据字段由详情富化现查现补，不入快照）。

        - 判定「变更」含失效剔除与名称/得分刷新（不能因「没有新增候选」当
          no-op）；真 no-op（合并结果逐字段等于旧集）不动版本、不落审计。
        - 读-改-写全程在同一事务：召回期间不预读版本，最终以 version CAS 落位
          （与 submit 同通道）——刷新/刷新、刷新/提交并发时后到者 409。
        - 快照即白名单：刷新后 ``_apply_link_verdict`` 只认新候选集，指向已
          剔除候选的 merge 目标会被 400 拒绝（评审员按刷新后列表重选）。
        """
        with self.sf() as s:
            c = self.need(s, i)
            self.require_case_access(a, c)
            if not role_can_review(a, c.phase):
                raise ReviewForbiddenError("角色与任务阶段不匹配")
            if canonical_template(c.template_id) != "T_LINK":
                raise ReviewValidationError("仅 T_LINK 消歧案支持刷新候选")
            if c.status not in SUBMITTABLE_STATUSES:
                raise ReviewConflictError(STATE_OR_VERSION_CONFLICT)
            snapshot = load(c.candidate_snapshot) or {}
            incoming = snapshot.get("_incoming")
            if not isinstance(incoming, dict) or not incoming:
                raise ReviewValidationError("存量写后案无待入库记录，不支持刷新候选")
            display = str(snapshot.get("name") or c.object_name or "")
            node_label = str(snapshot.get("_nodeLabel") or "")
            if not (display and node_label):
                raise ReviewValidationError("快照缺少名称或节点标签，无法刷新候选")
            incoming_props = dict(incoming.get("props") or {})
            incoming_vid = str(incoming.get("vid") or c.object_id or "")
            space = str(snapshot.get("_graphSpace") or c.graph_space or "") or None
            from service.entity_disambiguation import TOP_K, recall_candidates, score_candidate

            client = self._graph_client_for(snapshot)
            recalled = (recall_candidates(client, node_label, [display], space=space) or {}).get(
                display, []
            )
            scored: list[dict[str, Any]] = []
            for cand in recalled:
                vid = str(cand.get("vid") or "")
                if not vid or vid == incoming_vid:
                    continue
                score, detail = score_candidate(
                    display, incoming_props, cand.get("name"), cand.get("props")
                )
                scored.append(
                    {"vid": vid, "name": cand.get("name"), "score": round(score, 3), **detail}
                )
            fresh = sorted(scored, key=lambda x: x["score"], reverse=True)[:TOP_K]
            fresh_by_vid = {
                str(x["vid"]): {
                    "vid": str(x["vid"]),
                    "name": x.get("name"),
                    "score": x.get("score"),
                }
                for x in fresh
            }
            old = [
                x
                for x in (snapshot.get("existingCandidates") or [])
                if isinstance(x, dict) and x.get("vid")
            ]
            old_vids = {str(x["vid"]) for x in old}
            kept = [
                {**x, **fresh_by_vid[str(x["vid"])]} for x in old if str(x["vid"]) in fresh_by_vid
            ]
            added_vids = [vid for vid in fresh_by_vid if vid not in old_vids]
            merged = kept + [fresh_by_vid[vid] for vid in added_vids]
            if merged == old:
                # 真 no-op：零新增、零剔除、名称/得分无变化 → 不动版本不落审计
                return self.detail(s, c)
            t = now()
            reserved = s.execute(
                update(ReviewCase)
                .where(
                    ReviewCase.id == i,
                    ReviewCase.version == v,
                    ReviewCase.status.in_(SUBMITTABLE_STATUSES),
                )
                .values(version=ReviewCase.version + 1, updated_at=t)
            )
            if reserved.rowcount != 1:
                raise ReviewConflictError(STATE_OR_VERSION_CONFLICT)
            s.expire(c, ["version", "updated_at"])
            removed_vids = sorted(old_vids - set(fresh_by_vid))
            snapshot["existingCandidates"] = merged
            snapshot["_candidateRefresh"] = {
                "policyVersion": "refresh-candidates-v1",
                "recallPolicy": "exact+milvus-dense-v1",
                "refreshedAt": t.strftime("%Y-%m-%d %H:%M:%S"),
                "addedVids": added_vids,
                "removedVids": removed_vids,
            }
            c.candidate_snapshot = dump(snapshot)
            c.updated_at = t
            self.audit(
                s,
                c,
                a,
                "CANDIDATES_REFRESHED",
                c.status,
                c.status,
                {
                    "addedVids": added_vids,
                    "removedVids": removed_vids,
                    "oldCandidates": [
                        {"vid": str(x.get("vid")), "name": x.get("name"), "score": x.get("score")}
                        for x in old
                    ],
                    "newCandidates": [
                        {"vid": str(x.get("vid")), "name": x.get("name"), "score": x.get("score")}
                        for x in merged
                    ],
                },
            )
            s.commit()
            return self.detail(s, c)

    def _write_candidate_to_graph(self, c: ReviewCase) -> None:
        """accept 时把 candidate_snapshot 灌图。entity→merge_node，relation→create_edge。

        字段先 ``_coerce_to_schema`` 对齐 tag/edge schema（多余字段塞 extra_json），
        避免 NebulaGraph ``Unknown column`` 400。
        """
        from infra.graph_db import get_space_client, get_trs_graph_client
        from service.business_access_control import rbac_enabled

        snapshot = load(c.candidate_snapshot)
        kind = snapshot.get("_kind") or c.object_type
        candidate = {k: v for k, v in snapshot.items() if not k.startswith("_")}
        if rbac_enabled():
            if not c.graph_space:
                raise ReviewForbiddenError("审核记录未明确归属图空间")
            graph = get_space_client(c.graph_space)
        else:
            graph = get_trs_graph_client()
        if kind == "entity":
            node_label = snapshot.get("_nodeLabel")
            if not node_label:
                raise ReviewValidationError("entity 候选缺 nodeLabel")
            candidate = self._coerce_to_schema(graph, node_label, candidate)
            # 实体走 nGQL INSERT VERTEX（列级 upsert 幂等）——REST /nodes/merge 会把
            # id/name/vid 当身份键从属性剥离，而 schema DDL 把 id/name 建成 NOT NULL，
            # merge 永远 400（与平台抽取 write_records 同一结论）
            import json as _json

            def _ngql_value(value: Any) -> str:
                if value is None:
                    return "NULL"
                if isinstance(value, bool):
                    return "true" if value else "false"
                if isinstance(value, (int, float)):
                    return str(value)
                return _json.dumps(str(value), ensure_ascii=False)

            from datetime import datetime as _dt

            props = dict(candidate)
            props.setdefault("id", c.object_id)
            now_str = _dt.now().strftime("%Y-%m-%d %H:%M:%S")
            props.setdefault("create_time", now_str)
            props.setdefault("update_time", now_str)
            props.setdefault("source_table", "manual_review")
            cols = list(props.keys())
            stmt = (
                f'INSERT VERTEX {node_label}({", ".join(cols)}) VALUES "{c.object_id}": '
                f"({', '.join(_ngql_value(props[col]) for col in cols)})"
            )
            graph.execute_write(stmt)
        elif kind == "relation":
            edge_type = snapshot.get("_edgeType")
            from_id = snapshot.get("_fromId")
            to_id = snapshot.get("_toId")
            if not (edge_type and from_id and to_id):
                raise ReviewValidationError("relation 候选缺 edgeType/fromId/toId")
            candidate = self._coerce_to_schema(graph, edge_type, candidate, is_edge=True)
            graph.create_edge(from_id, to_id, edge_type, candidate)
        else:
            raise ReviewValidationError(f"未知 kind: {kind}")

    def _coerce_to_schema(
        self,
        graph: Any,
        label: str,
        candidate: dict[str, Any],
        *,
        is_edge: bool = False,
    ) -> dict[str, Any]:
        """把 candidate 字段对齐到 tag/edge schema。

        - schema 里有的字段：string 列值转 string（NebulaGraph tag 属性多为
          string）；int/double 列保留数字字面量（转成字符串会被 Nebula 拒
          "The data type does not meet the requirements"）
        - schema 里有 ``extra_json``：多余字段塞进 extra_json（JSON 串），不丢数据
        - schema 里没有 extra_json：丢弃多余字段（记 warning）
        - schema 查询失败：原样发（让 trs-graph 报 400 暴露问题）
        """
        import json

        log = logger
        try:
            desc = graph.execute_query(
                f"DESCRIBE EDGE `{label}`" if is_edge else f"DESCRIBE TAG `{label}`"
            )
            records = (
                desc.records
                if hasattr(desc, "records")
                else (desc.get("records", []) if isinstance(desc, dict) else [])
            )
            schema_fields = {
                r.get("Field") for r in records if isinstance(r, dict) and r.get("Field")
            }
            column_types = {
                r.get("Field"): str(r.get("Type") or "").lower()
                for r in records
                if isinstance(r, dict) and r.get("Field")
            }
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "DESCRIBE %s %s 失败，原样灌图: %s", "EDGE" if is_edge else "TAG", label, exc
            )
            return {k: v if isinstance(v, str) else str(v) for k, v in candidate.items()}

        if not schema_fields:
            return {k: v if isinstance(v, str) else str(v) for k, v in candidate.items()}

        def _typed(key: str, value: Any) -> Any:
            col_type = column_types.get(key, "")
            if col_type.startswith(("int", "double", "float")):
                if isinstance(value, bool):
                    return int(value)
                if isinstance(value, (int, float)):
                    return value
                try:
                    return float(value) if col_type.startswith(("double", "float")) else int(value)
                except (TypeError, ValueError):
                    return value  # 无法解析按原样发，让图库报错暴露
            return value if isinstance(value, str) else str(value)

        mapped: dict[str, Any] = {}
        extras: dict[str, Any] = {}
        for k, v in candidate.items():
            if k in schema_fields:
                mapped[k] = _typed(k, v)
            else:
                extras[k] = v

        if extras:
            if "extra_json" in schema_fields:
                mapped["extra_json"] = json.dumps(extras, ensure_ascii=False)
            else:
                log.warning(
                    "candidate 有 %d 个字段不在 %s %s schema 里且无 extra_json 兜底，丢弃: %s",
                    len(extras),
                    "edge" if is_edge else "tag",
                    label,
                    list(extras),
                )
        return mapped

    def cancel(self, i, v, reason, a):
        _ = reason
        require_role(a, "reviewer" if a.platform_actor else "review_admin")
        return self.mutate(
            i, v, a, {"status": "CANCELLED", "completed_at": now()}, "CASE_CANCELLED", True
        )

    def delete_case(self, i, a):
        """物理删除未处理 case（连同草稿/决议/附件/审计一并删除，不可恢复）。

        仅非终态（OPEN/RERUN_FAILED 等未处理）可删——与可重跑同门控；
        例外与只读口径对齐：T_EXTRACT_FAIL 终态案绑定重跑执行非成功
        （误归「已完成」/滞留）时同样放行删除。其余已处理记录保留作历史。
        review_admin 专用。
        """
        require_role(a, "reviewer" if a.platform_actor else "review_admin")
        with self.sf() as s:
            c = self.need(s, i)
            self.require_case_access(a, c)
            if c.status in TERMINAL_STATUSES and not extract_fail_rerunnable(
                load(c.input_snapshot) or {},
                resolve_execution_statuses(
                    [(load(c.input_snapshot) or {}).get("rerunExecutionId")]
                ),
            ):
                raise ReviewConflictError("已处理的记录不可删除")
            s.execute(delete(ReviewDraft).where(ReviewDraft.case_id == i))
            s.execute(delete(ReviewDecision).where(ReviewDecision.case_id == i))
            s.execute(delete(ReviewEvidence).where(ReviewEvidence.case_id == i))
            s.execute(delete(ReviewAuditLog).where(ReviewAuditLog.case_id == i))
            s.delete(c)
            s.commit()
        return {"id": i, "deleted": True}

    def logs(self, i, a):
        with self.sf() as s:
            c = self.need(s, i)
            # 审计日志是读路径：查看档（共享空间只读可见）
            self.require_case_view(a, c)
            return [
                {
                    "eventType": x.event_type,
                    "actorId": x.actor_id,
                    "actorName": x.actor_name,
                    "requestId": x.request_id,
                    "oldStatus": x.old_status,
                    "newStatus": x.new_status,
                    "detail": load(x.detail),
                    "createdAt": utc_to_cst_str(x.created_at),
                }
                for x in s.scalars(
                    select(ReviewAuditLog)
                    .where(ReviewAuditLog.case_id == i)
                    .order_by(ReviewAuditLog.created_at)
                ).all()
            ]

    def evidence_upload(self, i, file_name, content_type, size, digest, a):
        if size < 1 or size > int(os.getenv("REVIEW_EVIDENCE_MAX_BYTES", "20971520")):
            raise ReviewValidationError("附件大小不合法")
        if len(digest) != 64 or any(ch not in "0123456789abcdefABCDEF" for ch in digest):
            raise ReviewValidationError("sha256 格式不合法")
        if content_type not in {
            x.strip()
            for x in os.getenv(
                "REVIEW_EVIDENCE_CONTENT_TYPES", "application/pdf,image/png,image/jpeg,text/plain"
            ).split(",")
        }:
            raise ReviewValidationError("附件类型不允许")
        safe = os.path.basename(file_name).replace("\\", "_")
        # 附件上传是写路径：走操作档校验，不能借道 get_case（那是查看档，共享空间放行）
        with self.sf() as s:
            self.require_case_access(a, self.need(s, i))
        eid = f"EVD-{uuid4().hex[:16].upper()}"
        key = f"{i}/{eid}/{safe}"
        st = self.storage()
        st.ensure_bucket()
        url = st.client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": st.bucket,
                "Key": key,
                "ContentType": content_type,
                "Metadata": {"sha256": digest.lower()},
            },
            ExpiresIn=900,
        )
        return {
            "evidenceId": eid,
            "bucket": st.bucket,
            "objectKey": key,
            "uploadUrl": url,
            "expiresIn": 900,
        }

    def evidence_complete(self, i, p, a):
        self.authorize_case(i, a)
        st = self.storage()
        # An authorized case must not become a route to another case's S3
        # evidence. These are the exact identifiers returned by upload-url.
        from service.business_access_control import rbac_enabled

        if rbac_enabled():
            safe_name = os.path.basename(p["fileName"]).replace("\\", "_")
            expected_key = f"{i}/{p['evidenceId']}/{safe_name}"
            if (
                p["bucket"] != st.bucket
                or p["objectKey"] != expected_key
                or not p["evidenceId"].startswith("EVD-")
                or any(char in p["evidenceId"] for char in "/\\")
            ):
                raise ReviewForbiddenError("附件不属于当前审核记录")
        head = st.client.head_object(Bucket=p["bucket"], Key=p["objectKey"])
        if (
            int(head.get("ContentLength", -1)) != int(p["sizeBytes"])
            or head.get("ContentType") != p["contentType"]
            or head.get("Metadata", {}).get("sha256", "").lower() != p["sha256"].lower()
        ):
            raise ReviewValidationError("附件完整性校验失败")
        with self.sf() as s:
            c = self.owned(s, i, a)
            x = ReviewEvidence(
                id=p["evidenceId"],
                case_id=i,
                file_name=p["fileName"],
                content_type=p["contentType"],
                size_bytes=p["sizeBytes"],
                sha256=p["sha256"],
                bucket=p["bucket"],
                object_key=p["objectKey"],
                source=p.get("source", ""),
                trust_level=p.get("trustLevel", "UNVERIFIED"),
                status="READY",
                uploaded_by=a.user_id,
                created_at=now(),
            )
            s.add(x)
            self.audit(s, c, a, "EVIDENCE_ADDED", c.status, c.status, {"evidenceId": x.id})
            s.commit()
            return {"id": x.id, "status": x.status}

    def storage(self):
        return S3Storage(
            endpoint_url=os.getenv("REVIEW_S3_ENDPOINT_URL", "http://127.0.0.1:9020"),
            access_key=os.getenv("REVIEW_S3_ACCESS_KEY", "minioadmin"),
            secret_key=os.getenv("REVIEW_S3_SECRET_KEY", "minioadmin"),
            region=os.getenv("REVIEW_S3_REGION", "us-east-1"),
            bucket=os.getenv("REVIEW_S3_BUCKET", "tech-kg-review-evidence"),
            secure=os.getenv("REVIEW_S3_SECURE", "false").lower() == "true",
        )

    def reclaim_expired(self, minutes=5):
        cutoff = now() - timedelta(minutes=minutes)
        actor = ReviewIdentity(
            "system", "system", frozenset({"review_admin"}), frozenset({"*"}), "", "reclaimer"
        )
        with self.sf() as s:
            rows = s.scalars(
                select(ReviewCase).where(
                    ReviewCase.status.in_(("CLAIMED", "IN_REVIEW")),
                    ReviewCase.heartbeat_at < cutoff,
                )
            ).all()
            for c in rows:
                old = c.status
                c.status = "OPEN"
                c.assignee_id = None
                c.assignee_name = None
                c.claimed_at = None
                c.heartbeat_at = None
                c.version += 1
                c.updated_at = now()
                self.audit(s, c, actor, "CLAIM_EXPIRED", old, "OPEN", {})
            s.commit()
            return len(rows)

    def need(self, s, i):
        c = s.get(ReviewCase, i)
        if not c:
            raise KeyError(i)
        return c

    def owned(self, s, i, a):
        c = self.need(s, i)
        self.require_case_access(a, c)
        if c.assignee_id != a.user_id and not a.has_any("review_admin"):
            raise ReviewForbiddenError("任务未由当前用户领取")
        return c

    def audit(self, s, c, a, e, old, new, d):
        s.add(
            ReviewAuditLog(
                case_id=c.id,
                event_type=e,
                actor_id=a.user_id,
                actor_name=a.user_name,
                request_id=a.request_id,
                old_status=old,
                new_status=new,
                detail=dump(d),
                created_at=now(),
            )
        )

    def case_dict(
        self,
        c,
        job_map: dict[str, str] | None = None,
        operate_spaces=None,
        exec_statuses: dict[str, str] | None = None,
    ):
        input_data = load(c.input_snapshot) or {}
        execution_id = input_data.get("executionId")
        # T_EXTRACT_FAIL 只读口径：执行概要成功（COMPLETED）才算「已完成」，
        # 否则按「重跑失败」返回（前端映射可重跑徽标/按钮）；exec_statuses 为
        # None（控制面不可达）时保留库内状态。
        effective_status = (
            effective_extract_fail_status(
                c.status, input_data.get("rerunExecutionId"), exec_statuses
            )
            if c.template_id == "T_EXTRACT_FAIL" and exec_statuses is not None
            else c.status
        )
        return {
            "id": c.id,
            "graphSpace": c.graph_space,
            # 操作档可见性：None=不设限（非 RBAC/管理员路径或刚通过操作校验）；
            # 列表传入操作档集合，共享空间（查看档可见）为 False，前端据此禁用操作
            "canOperate": operate_spaces is None or c.graph_space in operate_spaces,
            "sourceTaskId": c.source_task_id,
            "batchId": c.batch_id,
            # 图谱构建任务：产生该 case 的 job（job-xxx，前端「来源记录」跳 /graph-build/jobs）。
            # 优先建案时写入快照的 jobId；存量 case 靠 job_map（EXEC→job 批量解析）兜底。
            "jobId": input_data.get("jobId") or (job_map or {}).get(execution_id or ""),
            # 图谱构建ID：产生该 case 的抽取执行（EXEC-xxx，前端跳 /processing-instance）
            "executionId": execution_id,
            "workflowId": c.workflow_id,
            "nodeId": c.pipeline_step_id,
            "pipelineStepId": c.pipeline_step_id,
            # kg.custom.steps 流水线的 step id 是 manifest 自定义的（如 seed），
            # 不在标准 PIPELINE_STEPS 里——取不到时回退原值，别让队列接口 404
            "pipelineStepName": (PIPELINE_STEPS.get(c.pipeline_step_id) or {}).get(
                "name", c.pipeline_step_id
            ),
            "objectId": c.object_id,
            "objectType": c.object_type,
            "objectName": c.object_name,
            "errorType": c.error_type,
            "exceptionCode": c.exception_code,
            "category": c.category,
            "templateId": canonical_template(c.template_id),
            "domain": c.domain,
            "phase": c.phase,
            "riskLevel": _risk_label(c.risk_level),
            "scope": c.scope,
            "isolationScope": c.isolation_scope,
            "status": effective_status,
            "assigneeId": c.assignee_id,
            "assigneeName": c.assignee_name,
            "version": c.version,
            "slaClaimAt": utc_to_cst_str(c.sla_claim_at),
            "slaResolveAt": utc_to_cst_str(c.sla_resolve_at),
            "diagnosis": c.diagnosis,
            "sourceTable": c.source_table,
            "sourceRecordId": c.source_record_id,
            # 重跑轮次（00919：OPEN 待处理记录应为 attempt=1）：快照未写 = 首次失败；
            # 重跑仍失败建新案时快照带 attempt+1（与 list_rerun_failures 同口径）
            "attempt": int(input_data.get("attempt") or 1),
            "createdAt": utc_to_cst_str(c.created_at),
            "updatedAt": utc_to_cst_str(c.updated_at),
        }

    def detail(self, s, c, duplicate=False):
        input_data = load(c.input_snapshot) or {}
        # T_EXTRACT_FAIL 详情与队列同口径：按执行概要推导有效状态（只读）
        exec_statuses = (
            resolve_execution_statuses([input_data.get("rerunExecutionId")])
            if c.template_id == "T_EXTRACT_FAIL"
            else None
        )
        d = self.case_dict(
            c,
            resolve_job_ids([input_data.get("executionId")]),
            exec_statuses=exec_statuses,
        )
        dr = s.get(ReviewDraft, c.id)
        # 已裁决 case 的最终决议：详情回显裁决单选用（前端刷新后不再回落默认
        # “合并”——2026-10-15 处理记录“确认为新实体”刷新变“合并”的根因）
        decision_row = s.scalars(
            select(ReviewDecision)
            .where(ReviewDecision.case_id == c.id)
            .order_by(ReviewDecision.id.desc())
        ).first()
        reported = (load(c.candidate_snapshot) or {}).pop("reportedEvidence", [])
        files = [
            {
                "id": x.id,
                "fileName": x.file_name,
                "contentType": x.content_type,
                "sizeBytes": x.size_bytes,
                "sha256": x.sha256,
                "source": x.source,
                "trustLevel": x.trust_level,
                "status": x.status,
            }
            for x in s.scalars(
                select(ReviewEvidence)
                .where(ReviewEvidence.case_id == c.id)
                .order_by(ReviewEvidence.created_at)
            ).all()
        ]
        d.update(
            {
                "draft": load(dr.payload) if dr else {},
                "decision": (
                    {
                        "actionId": decision_row.action_id,
                        "result": load(decision_row.result) or {},
                        "note": decision_row.note,
                        "submittedBy": decision_row.submitted_by,
                        "decidedAt": (
                            utc_to_cst_str(decision_row.decided_at)
                            if decision_row.decided_at
                            else None
                        ),
                    }
                    if decision_row
                    else None
                ),
                "template": template_contract(c.template_id),
                "data": {
                    "input": input_data,
                    "candidate": load(c.candidate_snapshot),
                    "evidence": reported + files,
                    "source_record": input_data.get("source_record"),
                    "llm_input": input_data.get("llm_input"),
                    "llm_output": input_data.get("llm_output"),
                },
                "input": input_data,
                "candidate": load(c.candidate_snapshot),
                "evidence": reported + files,
                "consequence": {
                    "writeTarget": write_target(c.template_id),
                    "rerunStepId": c.pipeline_step_id,
                    "scope": c.isolation_scope,
                },
                "workflow": {
                    "workflowType": c.workflow_type,
                    "workflowId": c.workflow_id,
                    "runId": c.workflow_run_id,
                    "taskQueue": c.task_queue,
                },
                "duplicate": duplicate,
            }
        )
        return d


manual_review_service = ManualReviewService()
