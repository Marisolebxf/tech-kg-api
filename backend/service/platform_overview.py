"""平台首页总览服务：图资产实时统计；图库不可用时诚实降级（显式占位，不回填演示数据）。"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from biz.schemas.platform_overview import (
    AssetChangeRow,
    AssetOverviewGroup,
    PlatformOverviewData,
    StructureItem,
    StructureMember,
)
from infra.graph_db import get_trs_graph_client
from infra.graph_db.client import is_known_no_index, is_no_index_error, mark_no_index
from service.day_change_ledger import (
    DAY_TZ as _DAY_TZ,
)
from service.day_change_ledger import (
    completed_in_day_tz as _completed_in_day_tz,
)
from service.day_change_ledger import (
    execution_space as _execution_space,
)
from service.day_change_ledger import (
    iter_record_outputs as _iter_record_outputs,
)
from service.day_change_ledger import (
    load_ledger_day,
)

# 今日新增图反查的单条查询读超时（秒）：反查任一环失败只是该执行退回聚合降级行，
# 不该用默认 30s 在共享图服务拥塞窗口里把总览冷算拖到分钟级（0924 实测 30s×2=60s+）。
_SWEEP_QUERY_TIMEOUT_SECONDS = float(os.getenv("PLATFORM_OVERVIEW_QUERY_TIMEOUT_SECONDS", "8"))
_MATCH_PAGE_SIZE = 1000
_MATCH_BUDGET_SECONDS = float(os.getenv("PLATFORM_OVERVIEW_MATCH_BUDGET_SECONDS", "8"))
# 计入昨日新增的终态集合（2026-10-14 口径）：ABNORMAL = 抽取完成但含行级失败
# 记录，图已写入；TERMINATED/CANCELED/FAILED 是中断终态，已落图的批次同样是
# 真实写入（gkx_verify_1 案例：中断执行写了数百万实体却整段不可见）——统一按
# written>0 过滤噪声，不再只认 COMPLETED/ABNORMAL。
_TERMINAL_STATUSES = ("COMPLETED", "ABNORMAL", "TERMINATED", "CANCELED", "FAILED")
# 逐对象反查闸门：控制库 written 合计超过该量时跳过该类图反查——百万级写入的
# LOOKUP 全窗扫描会长时间占住共享图会话池并把冷算拖到分钟级，聚合行 + 明确
# 提示比打爆图服务更诚实；阈值可用环境变量调节。
_LOOKUP_WRITTEN_LIMIT = int(os.getenv("PLATFORM_OVERVIEW_LOOKUP_WRITTEN_LIMIT", "100000"))

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class GraphStatsSnapshot:
    total_nodes: int
    total_edges: int
    nodes: dict[str, int]
    edges: dict[str, int]


class GraphStatsProvider(Protocol):
    def get_stats(self, space: str | None = None) -> GraphStatsSnapshot: ...


class TRSGraphStatsProvider:
    def get_stats(self, space: str | None = None) -> GraphStatsSnapshot:
        """读图统计；``space`` 给定时统计该空间（全局图空间选择器），否则默认空间单例。"""
        client: Any
        owned = False
        if space:
            # 显式空间：与写图/消歧 activity 同口径的临时 client（单例绑死默认空间）
            from infra.graph_db.client import TRSGraphClient
            from infra.graph_db.config import TRSGraphSettings

            settings = TRSGraphSettings.from_env()
            settings.space = space
            client = TRSGraphClient(settings)
            client.connect()
            owned = True
        else:
            client = get_trs_graph_client()
        try:
            return self._stats_via_client(client)
        finally:
            if owned:
                try:
                    client.close()
                except Exception:  # noqa: BLE001
                    logger.exception("关闭图客户端失败")

    def _stats_via_client(self, client: Any) -> GraphStatsSnapshot:
        # SHOW STATS：单条 nGQL 一次性返回所有 Tag/Edge 计数与总数（NebulaGraph 预计算，
        # 毫秒级）。比逐 label 调 node_count / 逐 edge_type 调 edge_count（N 次串行 HTTP，
        # 实测 ~57s）快 4 个数量级。SHOW STATS 需要 SUBMIT JOB STATS 已跑过。
        #
        # 走 stats_snapshot()（模块级 300s 快照 + 单飞，实体列表浏览同源）而非每次
        # 直查：总览缓存过期高频回源时不再每分钟多打一遍 SHOW STATS 挤占共享会话池
        # （0924 实测拥塞窗口内单次冷算被排队超时拖到 60s+）。统计本就只反映最近
        # 一次 SUBMIT JOB STATS，300s 滞后可接受。快照不可用才回退 REST 逐项计数。
        try:
            snap = client.stats_snapshot()
            nodes = dict(snap["tags"])
            edges = dict(snap["edges"])
            if not nodes and not edges:
                raise RuntimeError("SHOW STATS snapshot empty")
            return GraphStatsSnapshot(
                total_nodes=snap["total_nodes"],
                total_edges=snap["total_edges"],
                nodes=nodes,
                edges=edges,
            )
        except Exception as exc:
            logger.warning("SHOW STATS 快照不可用，回退 REST 逐项计数（会慢）: %s", exc)
            labels = client.labels()
            edge_types = client.edge_types()
            return GraphStatsSnapshot(
                total_nodes=client.node_count(),
                total_edges=client.edge_count(),
                nodes={label: client.node_count(label) for label in labels},
                edges={edge_type: client.edge_count(edge_type) for edge_type in edge_types},
            )


def _format_count(value: int) -> str:
    if value >= 100_000_000:
        return f"{value / 100_000_000:.2f} 亿"
    if value >= 10_000:
        return f"{value / 10_000:.2f} 万"
    return f"{value:,}"


@dataclass(frozen=True, slots=True)
class ExtractExecutionInfo:
    """统计日（昨日）一次完成执行的图反查描述（昨日新增明细按图内对象逐行展示）。

    执行 output 只带 written 计数、无逐对象清单；明细行改按 schemaKey 对应
    的 tag/边类型 + 时间窗（源表水位 ~ 完成时刻）反查图，拿到每个对象的
    name/source_table/写入时间。``fallback_rows`` 是反查失败时的聚合降级行
    （一次执行 × 每个来源表一行，旧口径）。
    """

    kind: str  # entity | relation
    schema_key: str
    schema_label: str
    completed_at: str  # YYYY-MM-DD HH:MM:SS
    window_lo: str  # 反查时间窗下界：源表读取起点水位最早值，缺省统计日起点
    # 反查时间窗上界：统计日（北京自然日）终点的图侧时刻，不用执行完成时刻——
    # 同日后续执行（如 chain 对同一批顶点的 upsert 改写）会把对象的 update_time
    # 推到本执行完成之后，按完成时刻封顶会把这些对象挡在窗外、退回聚合行
    window_hi: str = ""
    fallback_rows: list[AssetChangeRow] = field(default_factory=list)
    task_id: str | None = None
    job_id: str | None = None
    started_at: str = ""
    # 执行终态（COMPLETED/ABNORMAL/TERMINATED/…）：中断执行也计入昨日新增，
    # 明细行携带它，页面可对中断行标注「已中断/失败」
    status: str = ""


@dataclass(frozen=True, slots=True)
class DayChangesSnapshot:
    """昨日写图增量（来自工作流控制库，按图空间过滤）。

    2026-10-14 起页面按**聚合格式**展示：``*_rows`` 一行 = 一个写入块
    （统计日 × 空间 × kind × Schema × 执行 × 来源），``count`` 为该块 written
    精确计数，不再对图做逐对象反查（反查链路 ``enrich_day_rows_with_graph``
    保留在库、单测覆盖，恢复对象级明细时重新接线）。entity/relation_added
    为昨日完成执行的 ``output.sources[].written`` 合计——徽标与左下角合计
    直接用它，与行数（写入块数）是两个口径。running_count 为当前 RUNNING 执行数。
    """

    entity_added: int = 0
    relation_added: int = 0
    # 逐对象时代遗留标志：聚合格式下装配层不再依赖（快照来自控制库，读成即定局）；
    # 仍由反查链路内部维护，字段保留以免大改 enrich 语义
    entity_rows_exact: bool = False
    relation_rows_exact: bool = False
    running_count: int = 0
    entity_rows: list[AssetChangeRow] = field(default_factory=list)
    relation_rows: list[AssetChangeRow] = field(default_factory=list)
    entity_executions: list[ExtractExecutionInfo] = field(default_factory=list)
    relation_executions: list[ExtractExecutionInfo] = field(default_factory=list)
    # 统计日（日窗口时区自然日，YYYY-MM-DD）：随快照透出，页面「统计日」标签与
    # 缓存核对直接用它，不再靠前端自行推算「昨天」
    day: str = ""
    # 逐对象反查闸门标志（written 合计超 _LOOKUP_WRITTEN_LIMIT 时反查跳过）：
    # 聚合格式下反查不再接线，装配层不再读取；由 enrich 内部维护
    entity_gated: bool = False
    relation_gated: bool = False


class DayChangesProvider(Protocol):
    def get_day_changes(
        self, space: str | None = None, day: str | None = None
    ) -> DayChangesSnapshot: ...

    def running_count(self, space: str | None = None) -> int: ...


def _space_matches(record: dict[str, Any], target_space: str, default_space: str) -> bool:
    """执行归属当前空间：显式空间相等，或旧执行未记空间且当前即默认空间。"""
    space = _execution_space(record)
    return space == target_space or (not space and target_space == default_space)


def _written_of(output: dict[str, Any]) -> int:
    return sum(max(0, int(source.get("written") or 0)) for source in output.get("sources") or [])


# 「昨日新增」日窗口时区与时间归一/chain 环展开工具共享自 day_change_ledger
# （写账与读账同口径，防两处漂移）：北京自然日 00:00 翻日、环级 "+08:00" 偏移
# 优先 fromisoformat 完整解析、naive 串按 api 进程本地钟折算，细节见该模块。


def _day_boundary_utc(day: str, *, end: bool) -> str:
    """统计日（日窗口时区自然日）起/终点 → 图侧 UTC 时间串。

    图 update_time 按原始 UTC 字符串存储与比较，日界折算不随 api 进程时区走
    （否则非 UTC 宿主上窗口会整体平移 8h）。"""
    moment = datetime.strptime(day, "%Y-%m-%d").replace(
        hour=23 if end else 0,
        minute=59 if end else 0,
        second=59 if end else 0,
        tzinfo=_DAY_TZ,
    )
    return moment.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S")


def parse_execution_records(
    payloads: list[str],
    *,
    day: str,
    target_space: str,
    default_space: str,
) -> DayChangesSnapshot:
    """从控制库执行记录 JSON 解析统计日（昨日）写图增量（纯函数，便于单测）。

    只统计 ``target_space`` 空间的执行；未记录空间的旧执行按默认空间归属。
    聚合格式（2026-10-14 转正）：一行 = 一个写入块（执行 × 来源表），
    类型 = Schema 名、数量 = 该来源 written 计数、来源 = 物理源表名、
    时间 = 完成时刻；执行 output 无逐对象清单，不做对象级展示。
    """
    entity_added = 0
    relation_added = 0
    running = 0
    entity_rows: list[tuple[str, AssetChangeRow]] = []
    relation_rows: list[tuple[str, AssetChangeRow]] = []
    entity_execs: list[ExtractExecutionInfo] = []
    relation_execs: list[ExtractExecutionInfo] = []
    # 反查窗日界（图侧 UTC 串）：上界放宽到统计日终点——同日后续执行对同一批
    # 对象的改写仍落在窗内，对象不至于反查不到；下界缺水位时兜底用统计日起点
    day_start_graph = _day_boundary_utc(day, end=False)
    day_end_graph = _day_boundary_utc(day, end=True)
    for raw in payloads:
        try:
            record = json.loads(raw)
        except (TypeError, ValueError):
            continue
        if not isinstance(record, dict):
            continue
        if not _space_matches(record, target_space, default_space):
            continue
        status = str(record.get("status") or "")
        if status == "RUNNING":
            running += 1
            continue
        if status not in _TERMINAL_STATUSES:
            continue
        # 执行记录由 job 下发时携带 jobId（调度/手动/重跑都有）；非 job 来源的
        # 直跑/回填执行没有，行点击只能退列表页
        task_id = str(record.get("taskId") or "").strip() or None
        job_id = str(record.get("jobId") or "").strip() or None
        # 执行 ID（payload 自带 id）：行级跳转直达该次执行，任务页默认展示最新
        # 执行会张冠李戴（gkx_verify_1 实测：任务 20 次运行，昨日行点开看到的是今天的数）
        exec_id = str(record.get("id") or "").strip() or None
        # chain 执行按环展开：每环一个独立输出单元，统计日按环级完成时刻归属
        # （环在北京 23:59 完成、整链 00:05 跨日完成时，该环仍算前一天）
        for output, completed_at, started_at in _iter_record_outputs(record):
            completed_local = _completed_in_day_tz(completed_at)
            if completed_local is None or completed_local.strftime("%Y-%m-%d") != day:
                continue
            kind = str(output.get("kind") or "")
            written = _written_of(output)
            if kind not in ("entity", "relation") or written <= 0:
                continue
            schema_label = str(output.get("schemaLabel") or output.get("schemaKey") or "")
            # 聚合格式：数量列 = 该来源表的 written 精确计数；object/change 是逐对象
            # 时代的内部描述字段（不序列化），反查链路与单测仍在用
            schema_key = str(
                output.get("schemaKey") or schema_label or ("实体" if kind == "entity" else "关系")
            )
            display_label = schema_label or ("实体 Schema" if kind == "entity" else "关系 Schema")
            change = f"新增 {schema_key}"
            # 明细时间列与日窗口同时区：北京时刻展示（完成串是进程本地钟，折算后展示）
            completed_time = completed_local.strftime("%m-%d %H:%M:%S")
            target_rows = entity_rows if kind == "entity" else relation_rows
            # 一次执行绑定多个来源表时按表拆行（来源列各自取本表名），只出 written>0 的表
            exec_rows: list[AssetChangeRow] = []
            watermarks: list[str] = []
            for source in output.get("sources") or []:
                if not isinstance(source, dict):
                    continue
                source_written = max(0, int(source.get("written") or 0))
                if source_written <= 0:
                    continue
                row = AssetChangeRow(
                    type=display_label,
                    count=source_written,
                    object=f"{display_label} · {source_written:,} 条",
                    change=change,
                    source=str(source.get("table") or source.get("source") or "-"),
                    time=completed_time,
                    task_id=task_id,
                    job_id=job_id,
                    exec_id=exec_id,
                    is_aggregate=True,
                    exec_status=status,
                )
                target_rows.append((completed_at, row))
                exec_rows.append(row)
                # 反查窗口下界优先用开跑前的起点水位（startWatermark）：watermark 是
                # 跑完后的终值，取 min 后窗口会缩成最后一批同秒，写图时间落在窗口内的
                # 顶点/边查不全；旧执行没有 startWatermark 时退回 watermark。
                # 水位在 payload 里是 ISO 'T' 分隔而图侧 update_time 是空格分隔：
                # 字符串比较 'T'(0x54)>' '(0x20)，同日 T 格式水位会大于全部同日图值，
                # 当天跑的执行（cron fire/rerun 水位必是当天）反查恒 0 命中退聚合行，
                # 故统一规范成空格分隔再进窗口
                watermark = str(source.get("startWatermark") or source.get("watermark") or "")
                if watermark:
                    watermarks.append(watermark.replace("T", " ", 1))
            descriptor = ExtractExecutionInfo(
                kind=kind,
                schema_key=schema_key,
                schema_label=schema_label or display_label,
                completed_at=completed_at,
                # 源表水位（读取起点）必然早于写图时刻，作反查窗下界；缺省统计日起点
                window_lo=max(day_start_graph, min(watermarks)) if watermarks else day_start_graph,
                window_hi=day_end_graph,
                fallback_rows=exec_rows,
                task_id=task_id,
                job_id=job_id,
                started_at=started_at,
                status=status,
            )
            if kind == "entity":
                entity_added += written
                entity_execs.append(descriptor)
            else:
                relation_added += written
                relation_execs.append(descriptor)
    # 明细按完成时间倒序（最新写图在前）
    entity_rows.sort(key=lambda pair: pair[0], reverse=True)
    relation_rows.sort(key=lambda pair: pair[0], reverse=True)
    return DayChangesSnapshot(
        entity_added=entity_added,
        relation_added=relation_added,
        running_count=running,
        entity_rows=[row for _, row in entity_rows],
        relation_rows=[row for _, row in relation_rows],
        entity_executions=entity_execs,
        relation_executions=relation_execs,
        day=day,
    )


def _snapshot_from_ledger(
    day: str, target_space: str, default_space: str
) -> DayChangesSnapshot | None:
    """从写图台账（P1 写时记账）构造统计日快照；当日无账返回 None 回落现算。

    台账行自带精确计数（save_execution 覆盖式落账），聚合格式下直接成表——
    一行 = 一个写入块（执行 × 来源），count 即台账 object_count，无需再查图。
    图反查描述仍按（执行 × kind × Schema）聚合保留（反查链路未接线时的重接
    挂点）：window_hi 放宽到统计日终点、台账未记水位故 window_lo 退统计日起点。"""
    rows = load_ledger_day(day, target_space, default_space)
    if not rows:
        return None
    day_start_graph = _day_boundary_utc(day, end=False)
    day_end_graph = _day_boundary_utc(day, end=True)
    entity_added = 0
    relation_added = 0
    entity_rows: list[tuple[str, AssetChangeRow]] = []
    relation_rows: list[tuple[str, AssetChangeRow]] = []
    # （执行 × kind × Schema）聚合出反查描述；跨行共用的执行级字段取首行
    execs: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row_data in rows:
        kind = str(row_data.get("kind") or "")
        if kind not in ("entity", "relation"):
            continue
        schema_key = str(row_data.get("schema_key") or "")
        label = (
            str(row_data.get("schema_label") or "")
            or schema_key
            or ("实体" if kind == "entity" else "关系")
        )
        count = max(0, int(row_data.get("object_count") or 0))
        finished = str(row_data.get("finished_at") or "")
        if kind == "entity":
            entity_added += count
        else:
            relation_added += count
        row = AssetChangeRow(
            type=label,
            count=count,
            object=f"{label} · {count:,} 条",
            change=f"新增 {schema_key}",
            source=str(row_data.get("source") or "-"),
            time=finished[5:] if finished else "",
            task_id=row_data.get("task_id"),
            job_id=row_data.get("job_id"),
            exec_id=row_data.get("execution_id") or None,
            is_aggregate=True,
            exec_status=str(row_data.get("exec_status") or "") or None,
        )
        if kind == "entity":
            entity_rows.append((finished, row))
        else:
            relation_rows.append((finished, row))
        key = (str(row_data.get("execution_id") or ""), kind, schema_key)
        entry = execs.get(key)
        if entry is None:
            execs[key] = {
                "kind": kind,
                "schema_key": schema_key,
                "schema_label": label,
                "task_id": row_data.get("task_id"),
                "job_id": row_data.get("job_id"),
                "status": str(row_data.get("exec_status") or ""),
                "min_fin": finished or None,
                "max_fin": finished or None,
                "rows": [row],
            }
        else:
            entry["rows"].append(row)
            if finished:
                if not entry["max_fin"] or finished > entry["max_fin"]:
                    entry["max_fin"] = finished
                if not entry["min_fin"] or finished < entry["min_fin"]:
                    entry["min_fin"] = finished
    entity_execs: list[ExtractExecutionInfo] = []
    relation_execs: list[ExtractExecutionInfo] = []
    for entry in execs.values():
        max_fin = entry["max_fin"] or ""
        descriptor = ExtractExecutionInfo(
            kind=entry["kind"],
            schema_key=entry["schema_key"],
            schema_label=entry["schema_label"],
            completed_at=max_fin,
            window_lo=day_start_graph,
            window_hi=day_end_graph,
            fallback_rows=entry["rows"],
            task_id=entry["task_id"],
            job_id=entry["job_id"],
            started_at=entry["min_fin"] or max_fin,
            status=entry["status"],
        )
        if entry["kind"] == "entity":
            entity_execs.append(descriptor)
        else:
            relation_execs.append(descriptor)
    # 反查描述同样按完成时刻倒序（与明细行、enrich 内部排序口径一致）
    entity_execs.sort(key=lambda ex: ex.completed_at, reverse=True)
    relation_execs.sort(key=lambda ex: ex.completed_at, reverse=True)
    # 明细按完成时间倒序（最新写图在前），与现算路径同序
    entity_rows.sort(key=lambda pair: pair[0], reverse=True)
    relation_rows.sort(key=lambda pair: pair[0], reverse=True)
    return DayChangesSnapshot(
        entity_added=entity_added,
        relation_added=relation_added,
        # RUNNING 是实时指标（running_count() 独立短查）；台账只记已落库的账，
        # 此处 0 仅为占位，不进页面「N 个执行运行中」
        running_count=0,
        entity_rows=[row for _, row in entity_rows],
        relation_rows=[row for _, row in relation_rows],
        entity_executions=entity_execs,
        relation_executions=relation_execs,
        day=day,
    )


class WorkflowControlDayChangesProvider:
    """默认实现：从工作流控制库（techkg_control.workflow_executions）读昨日增量。

    覆盖平台唯一写图通道 ``kg.schema.extract`` 的执行记录；直连 ETL 脚本与
    T_DIRECT 审核直写不经过控制库，不计入（明细行口径即任务中心执行历史）。
    昨日是闭合窗口——统计日结束后不会再有新执行落进该窗口，结果按
    (空间, 日期) 进程内缓存到当天结束。聚合格式（2026-10-14）下快照只来自
    控制库（台账或 payload 现算），读成即定局、不再有「反查降级短缓存重试」
    的中间态；控制库不可读直接上抛，由总览装配层兜底占位。
    """

    # 抽取执行最长可跑数小时：取 7 天窗口兜住跨日完成的长执行
    _LOOKBACK_DAYS = 7

    def __init__(self) -> None:
        self._cached_day: str | None = None
        self._cached: dict[str | None, DayChangesSnapshot] = {}

    def _current_day(self) -> str:
        """统计日 = 日窗口时区（默认北京）自然日的昨天；北京 00:00 翻日。"""
        return (datetime.now(_DAY_TZ) - timedelta(days=1)).strftime("%Y-%m-%d")

    def get_day_changes(
        self, space: str | None = None, day: str | None = None
    ) -> DayChangesSnapshot:
        target_day = day or self._current_day()
        if day is None:
            # 默认当日路径：快照冻结到当天（跨日翻页旧缓存整体作废）
            if self._cached_day == target_day:
                cached = self._cached.get(space)
                if cached is not None:
                    return cached
            snapshot = self._load(target_day, space)
            if self._cached_day != target_day:
                # 跨日翻页：旧统计日的缓存整体作废
                self._cached_day = target_day
                self._cached = {}
            self._cached[space] = snapshot
            return snapshot
        # 指定统计日（历史日回看/验收核对）：现算即返，不进也不污染当日冻结缓存
        return self._load(target_day, space)

    def running_count(self, space: str | None = None) -> int:
        """当前 RUNNING 执行数（实时短查）：日快照缓存到当天结束，「N 个执行
        运行中」不能随快照冻结一整天；外层 60s 结果缓存内每次装配最多实查一次。"""
        from sqlalchemy import text

        from infra.graph_db.config import TRSGraphSettings
        from infra.workflow_mysql import get_workflow_engine

        target_space = space or TRSGraphSettings.from_env().space
        default_space = TRSGraphSettings.from_env().space
        now = datetime.now().astimezone()
        since = (now - timedelta(days=self._LOOKBACK_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
        engine = get_workflow_engine()
        with engine.connect() as connection:
            rows = connection.execute(
                text(
                    "SELECT payload FROM workflow_executions "
                    "WHERE status = 'RUNNING' AND started_at >= :since"
                ),
                {"since": since},
            ).fetchall()
        count = 0
        for row in rows:
            try:
                record = json.loads(row[0])
            except (TypeError, ValueError):
                continue
            if isinstance(record, dict) and _space_matches(record, target_space, default_space):
                count += 1
        return count

    def _load(self, day: str, space: str | None) -> DayChangesSnapshot:
        from sqlalchemy import text

        from infra.graph_db.config import TRSGraphSettings
        from infra.workflow_mysql import get_workflow_engine

        target_space = space or TRSGraphSettings.from_env().space
        default_space = TRSGraphSettings.from_env().space
        # P1 快路径：写图台账有当日账（save_execution 写时记账）则直接构造快照；
        # 台账无账（旧执行 / 未部署本代码的栈写入）回落 payload 现算，两条路径
        # 同口径。聚合格式（2026-10-14）下两路产出的写入块行即最终明细，**不再
        # 连图反查**——页面与图库彻底解耦，大写入日也不再有闸门/降级分支；
        # 反查链路（enrich_day_rows_with_graph 及其辅助）保留在库、单测覆盖，
        # 恢复对象级明细时在此重新接线。
        ledger_snapshot = _snapshot_from_ledger(day, target_space, default_space)
        if ledger_snapshot is not None:
            return ledger_snapshot
        now = datetime.now().astimezone()
        since = (now - timedelta(days=self._LOOKBACK_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
        engine = get_workflow_engine()
        with engine.connect() as connection:
            result = connection.execute(
                text(
                    "SELECT payload FROM workflow_executions "
                    "WHERE status IN ('COMPLETED', 'ABNORMAL', 'TERMINATED', 'CANCELED', "
                    "'FAILED', 'RUNNING') AND started_at >= :since"
                ),
                {"since": since},
            )
            payloads = [row[0] for row in result.fetchall()]
        return parse_execution_records(
            payloads,
            day=day,
            target_space=target_space,
            default_space=default_space,
        )


# ---- 昨日新增逐对象反查链路（2026-10-14 起未接线，单测覆盖保留能力） ----------
# 聚合格式转正后 _load 不再调用本节；页面不再做图反查。对象级明细若恢复
# （如 P2 后台收割式方案落地），在此把 enrich_day_rows_with_graph 接回 _load 即可。
_FETCH_PROP_BATCH = 50
# 顶点「对象名」取值候选：公共字段 name 优先，历史 ETL tag 无字面 name 时按
# 域定制键回退（Person=name_cn、Keyword=keyword、Paper=title_zh…）
_NAME_PROP_CANDIDATES = (
    "name",
    "name_cn",
    "name_zh",
    "name_en",
    "keyword",
    "title_zh",
    "title_en",
    "title",  # Project 无 name/title_zh，展示名就是 title
)


def _vertex_display_name(props: dict[str, Any], vid: str) -> str:
    for key in _NAME_PROP_CANDIDATES:
        value = props.get(key)
        if value:
            return str(value)
    return vid


def _time_short(value: Any, fallback: str) -> str:
    """识别时间带月日（MM-DD HH:MM:SS）：昨日窗口跨天后只剩时分秒有歧义。
    图侧时间戳按 api 进程钟（UTC）写入，展示前折算到日窗口时区（北京），
    与明细完成时刻同口径；解析失败退原串切片。"""
    raw = str(value or "").replace("T", " ", 1)
    local = _completed_in_day_tz(raw)
    if local is not None:
        return local.strftime("%m-%d %H:%M:%S")
    return raw[5:19] or fallback


def _utc_slice_local(utc_str: str) -> str:
    """UTC 完成串 → 日窗口时区的展示串；解析失败退原切片。"""
    local = _completed_in_day_tz(utc_str)
    return local.strftime("%m-%d %H:%M:%S") if local else utc_str[5:19]


def _flatten_vertex_props(vertex: Any) -> dict[str, Any]:
    """FETCH PROP ON * 返回的 vertex.properties 兼平铺/按 tag 嵌套两种形态。"""
    if not isinstance(vertex, dict):
        return {}
    props = vertex.get("properties")
    if not isinstance(props, dict):
        return {}
    if props and all(isinstance(value, dict) for value in props.values()):
        merged: dict[str, Any] = {}
        for grouped in props.values():
            merged.update(grouped)
        return merged
    return props


@dataclass(frozen=True, slots=True)
class GraphTimeProperty:
    name: str
    value_type: str


def _graph_time_prop(
    client: Any, kind: str, name: str, cache: dict[tuple[str, str], GraphTimeProperty | None]
) -> GraphTimeProperty | None:
    """时间字段优先使用 string/fixed_string，再支持 datetime 的类型化边界。

    string 源时间仍保留旧优先级；只有 datetime 字段的 Schema 也可反查，
    LOOKUP 不可执行时实体转 MATCH 分页。DESCRIBE 未返回 Type 时按 string 处理。
    """
    cache_key = (kind, name)
    if cache_key in cache:
        return cache[cache_key]
    try:
        statement = f"DESC TAG `{name}`" if kind == "entity" else f"DESC EDGE `{name}`"
        types = {
            str(rec.get("Field")): str(rec.get("Type") or "string").lower()
            for rec in client.execute_query(statement, timeout=_SWEEP_QUERY_TIMEOUT_SECONDS).records
        }
    except Exception:
        types = {}
    prop_name = next(
        (
            candidate
            for candidate in ("update_time", "create_time", "source_update_time")
            if types.get(candidate, "").startswith(("string", "fixed_string"))
        ),
        None,
    )
    if prop_name is None:
        prop_name = next(
            (
                name
                for name in ("update_time", "create_time", "source_update_time")
                if types.get(name) == "datetime"
            ),
            None,
        )
    prop = GraphTimeProperty(prop_name, types[prop_name]) if prop_name else None
    cache[cache_key] = prop
    return prop


def _time_window_predicate(
    prefix: str, prop: GraphTimeProperty, execution: ExtractExecutionInfo
) -> str:
    def literal(value: str) -> str:
        quoted = json.dumps(value, ensure_ascii=False)
        return f"datetime({quoted})" if prop.value_type == "datetime" else quoted

    return (
        f"{prefix}.`{prop.name}` >= {literal(execution.window_lo)} "
        f"AND {prefix}.`{prop.name}` <= {literal(execution.window_hi or execution.completed_at)}"
    )


def _match_entity_records(
    client: Any, tag: str, prop: GraphTimeProperty, execution: ExtractExecutionInfo
) -> list[dict[str, Any]] | None:
    """无索引时按标签分页取真实对象，再按时间窗过滤。

    旧图引擎的 MATCH WHERE 属性条件仍可能要求索引，兜底仅扫描标签，
    不使用附带全量 COUNT 的 REST 分页。未完成枚举时不能把部分页当成全部明细。
    """
    records: list[dict[str, Any]] = []
    deadline = time.monotonic() + _MATCH_BUDGET_SECONDS
    offset = 0
    try:
        while True:
            if time.monotonic() >= deadline:
                raise TimeoutError("昨日新增 MATCH 明细查询超出时间预算")
            page = client.execute_query(
                f"MATCH (v:`{tag}`) "
                f"RETURN id(v) AS vid, properties(v) AS props ORDER BY vid SKIP {offset} LIMIT {_MATCH_PAGE_SIZE}",
                timeout=min(_SWEEP_QUERY_TIMEOUT_SECONDS, max(0.1, deadline - time.monotonic())),
            ).records
            for record in page:
                props = record.get("props") or {}
                stamp = str(props.get(prop.name) or "").replace("T", " ", 1)[:19]
                if execution.window_lo <= stamp <= (execution.window_hi or execution.completed_at):
                    records.append(record)
            if len(page) < _MATCH_PAGE_SIZE:
                return records
            offset += len(page)
    except Exception:
        logger.warning("昨日新增逐对象反查失败 tag=%s，MATCH 明细未完整读取", tag, exc_info=True)
        return None


def _safe_identifier(name: str) -> str:
    return name.replace("`", "").strip()


def _safe_vid(vid: Any) -> str:
    return str(vid or "").replace('"', "").strip()


def _graph_row_execution(
    execution: ExtractExecutionInfo,
    props: dict[str, Any],
    time_prop: str | None,
    executions: list[ExtractExecutionInfo],
) -> ExtractExecutionInfo | None:
    """反查窗可能覆盖同 Schema 的多次执行，按来源和写图时间定位本行所属执行。

    不能把当前反查执行的 taskId/jobId 无条件贴到整日全部对象上；用执行起止
    时间区分同来源重跑。只有源数据时间或无时间时要求候选唯一；并发歧义不猜测。
    """
    source = str(props.get("source_table") or "")
    candidates = [
        item
        for item in executions
        if item.schema_key == execution.schema_key
        and (not source or any(row.source == source for row in item.fallback_rows))
    ]
    stamp = str(props.get(time_prop) or "").replace("T", " ", 1)[:19] if time_prop else ""
    if time_prop in ("update_time", "create_time") and stamp:
        timed = []
        for item in candidates:
            completed = _completed_in_day_tz(item.completed_at)
            if completed is None:
                continue
            completed_graph = completed.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S")
            started = _completed_in_day_tz(item.started_at)
            started_graph = (
                started.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S") if started else item.window_lo
            )
            if max(item.window_lo, started_graph) <= stamp <= completed_graph:
                timed.append(item)
        if len(timed) == 1:
            return timed[0]
        # 时间区间匹配歧义/落空时兜底：同 Schema+来源当日唯一执行直接归属——
        # 对象常被同日后续执行改写推出本执行窗口，唯一候选时不必再按时间猜；
        # 仍不唯一（并发歧义）才放弃，不猜测
        return candidates[0] if len(candidates) == 1 else None
    return candidates[0] if len(candidates) == 1 else None


def _entity_object_rows(
    client: Any,
    execution: ExtractExecutionInfo,
    schema_name: str,
    time_props: dict[tuple[str, str], GraphTimeProperty | None],
    schema_labels: dict[str, str],
    executions: list[ExtractExecutionInfo],
) -> tuple[list[AssetChangeRow] | None, list[str]]:
    """按 tag + 时间窗反查当日写入的实体顶点，逐对象一行；查不到返回 None 走聚合降级。"""
    tag = _safe_identifier(schema_name)
    time_spec = _graph_time_prop(client, "entity", tag, time_props)
    if not time_spec:
        logger.warning("昨日新增逐对象反查失败 tag=%s：没有可用写入时间字段", tag)
        return None, []
    time_prop = time_spec.name
    space = getattr(client, "space", "")
    # 无索引负缓存：-1005 是确定性失败（图服务侧还自动重试放大），TTL 内不再重发
    records = None
    if not (space and is_known_no_index(space, "lookup", f"{tag}.{time_prop}")):
        statement = (
            f"LOOKUP ON `{tag}` WHERE {_time_window_predicate(f'`{tag}`', time_spec, execution)} "
            "YIELD id(vertex) AS vid, properties(vertex) AS props"
        )
        try:
            records = client.execute_query(statement, timeout=_SWEEP_QUERY_TIMEOUT_SECONDS).records
        except Exception as exc:
            if space and is_no_index_error(exc):
                mark_no_index(space, "lookup", f"{tag}.{time_prop}")
    if records is None:
        records = _match_entity_records(client, tag, time_spec, execution)
    if records is None:
        return None, []
    # 数据类型/变更内容列都用单个 Schema 的目录中文名（与图谱资产构成图同口径），
    # 查不到目录名时退原 tag 名
    type_label = schema_labels.get(tag) or tag
    fallback_source = execution.fallback_rows[0].source if execution.fallback_rows else "-"
    rows: list[AssetChangeRow] = []
    vids: list[str] = []
    for record in records:
        props = record.get("props") or {}
        vid = _safe_vid(record.get("vid"))
        resolved = _graph_row_execution(execution, props, time_prop, executions)
        rows.append(
            AssetChangeRow(
                type=type_label,
                object=_vertex_display_name(props, vid),
                change=f"新增 {type_label}",
                source=str(props.get("source_table") or fallback_source),
                time=_time_short(props.get(time_prop), _utc_slice_local(execution.completed_at)),
                task_id=resolved.task_id if resolved else None,
                job_id=resolved.job_id if resolved else None,
                object_id=vid,
                # 归属不到唯一执行时退当前反查执行的终态（至少如实反映该窗口口径）
                exec_status=resolved.status if resolved else execution.status,
            )
        )
        vids.append(vid)
    # 查询成功即如实全量出行（含 0 命中：对象被统计日后的执行改写出窗/已删，
    # 不再造「Schema · N 条」聚合行）；结构性失败在上面已提前返回 None
    return rows, vids


def _relation_edges(
    client: Any,
    execution: ExtractExecutionInfo,
    edge_type: str,
    time_spec: GraphTimeProperty | None,
    seed_vids: list[str],
) -> tuple[list[tuple[str, str, dict[str, Any]]], bool]:
    """当日关系边收集：①边属性时间窗 LOOKUP（需边索引）②退而求其次从当日
    实体 vid 出发 GO BIDIRECT（边端点通常就是当日写入的实体）再按时间过滤。

    返回 (边清单, 是否完成枚举)：任一收集通道成功执行（哪怕 0 命中）即视为
    枚举完成；只有结构性失败（无索引且 GO 也执行不了）才让调用方退聚合行。"""
    edges: list[tuple[str, str, dict[str, Any]]] = []
    seen: set[tuple[str, str]] = set()
    enumerated = False
    window_hi = execution.window_hi or execution.completed_at
    time_prop = time_spec.name if time_spec else None

    def _collect(records: Any, *, window_filter: bool) -> None:
        for record in records:
            src = _safe_vid(record.get("src"))
            dst = _safe_vid(record.get("dst"))
            props = record.get("eprops") or {}
            # BIDIRECT 会把同一条边正反两个方向都吐回来：按无序 vid 对去重
            key = (src, dst) if src <= dst else (dst, src)
            if not src or not dst or key in seen:
                continue
            if window_filter and time_prop:
                stamp = str(props.get(time_prop) or "")
                if not (execution.window_lo <= stamp <= window_hi):
                    continue
            seen.add(key)
            edges.append((src, dst, props))

    if time_prop:
        space = getattr(client, "space", "")
        # 无索引负缓存：-1005 是确定性失败（图服务侧还自动重试放大），TTL 内不再重发
        if not (space and is_known_no_index(space, "lookup", f"{edge_type}.{time_prop}")):
            statement = (
                f"LOOKUP ON `{edge_type}` WHERE {_time_window_predicate(f'`{edge_type}`', time_spec, execution)} "
                "YIELD src(edge) AS src, dst(edge) AS dst, properties(edge) AS eprops"
            )
            try:
                _collect(
                    client.execute_query(statement, timeout=_SWEEP_QUERY_TIMEOUT_SECONDS).records,
                    window_filter=False,
                )
                enumerated = True
            except Exception as exc:
                if space and is_no_index_error(exc):
                    mark_no_index(space, "lookup", f"{edge_type}.{time_prop}")
                # 边类型无索引（400）→ 走 GO FROM 兜底
    if not edges and seed_vids and time_prop:
        # GO 兜底仅在边类型有时间属性可滤时使用：没有时间滤的 BIDIRECT 会把
        # 端点的全部历史边都算进「昨日新增」，宁可退聚合行也不出脏行
        vid_list = ", ".join(f'"{vid}"' for vid in seed_vids)
        statement = (
            f"GO FROM {vid_list} OVER `{edge_type}` BIDIRECT "
            "YIELD src(edge) AS src, dst(edge) AS dst, properties(edge) AS eprops"
        )
        try:
            _collect(
                client.execute_query(statement, timeout=_SWEEP_QUERY_TIMEOUT_SECONDS).records,
                window_filter=True,
            )
            enumerated = True
        except Exception:
            pass
    return edges, enumerated


def _endpoint_names(client: Any, vids: list[str]) -> dict[str, str]:
    """端点名批量反查：一次 FETCH 多个 vid。此前逐 vid 一次 FETCH、关系明细
    ~百次串行 HTTP 是图反查最大耗时（~2s），合并成每执行 1-2 次调用。"""
    names: dict[str, str] = {}
    for start in range(0, len(vids), _FETCH_PROP_BATCH):
        batch = vids[start : start + _FETCH_PROP_BATCH]
        vid_list = ", ".join(f'"{vid}"' for vid in batch)
        try:
            records = client.execute_query(
                f"FETCH PROP ON * {vid_list} YIELD vertex AS v",
                timeout=_SWEEP_QUERY_TIMEOUT_SECONDS,
            ).records
        except Exception:
            continue
        for record in records:
            vertex = record.get("v")
            if not isinstance(vertex, dict):
                continue
            vid = _safe_vid(vertex.get("id"))
            if vid:
                names[vid] = _vertex_display_name(_flatten_vertex_props(vertex), vid)
    return names


def _relation_object_rows(
    client: Any,
    execution: ExtractExecutionInfo,
    schema_name: str,
    time_props: dict[tuple[str, str], GraphTimeProperty | None],
    seed_vids: list[str],
    schema_labels: dict[str, str],
    executions: list[ExtractExecutionInfo],
) -> list[AssetChangeRow] | None:
    """按边类型反查当日关系边，具体对象 = 起点实体名 → 终点实体名。"""
    edge_type = _safe_identifier(schema_name)
    time_spec = _graph_time_prop(client, "relation", edge_type, time_props)
    time_prop = time_spec.name if time_spec else None
    edges, enumerated = _relation_edges(client, execution, edge_type, time_spec, seed_vids)
    if not edges:
        # 枚举完成但 0 命中：如实不出行（对象已被统计日后的执行改写出窗/删除），
        # 只有结构性失败（无法枚举）才退回聚合降级行
        return [] if enumerated else None
    endpoint_vids: list[str] = []
    for src, dst, _ in edges:
        for vid in (src, dst):
            if vid not in endpoint_vids:
                endpoint_vids.append(vid)
    names = _endpoint_names(client, endpoint_vids)
    # 数据类型/变更内容列都用单个 Schema 的目录中文名（与图谱资产构成图同口径），
    # 查不到目录名时退原边类型名
    type_label = schema_labels.get(edge_type) or edge_type
    fallback_source = execution.fallback_rows[0].source if execution.fallback_rows else "-"
    fallback_time = _utc_slice_local(execution.completed_at)
    rows: list[AssetChangeRow] = []
    for src, dst, edge_props in edges:
        resolved = _graph_row_execution(execution, edge_props, time_prop, executions)
        rows.append(
            AssetChangeRow(
                type=type_label,
                object=f"{names.get(src, src)} → {names.get(dst, dst)}",
                change=f"新增 {type_label}",
                source=str(edge_props.get("source_table") or fallback_source),
                time=_time_short(edge_props.get(time_prop), fallback_time)
                if time_prop
                else fallback_time,
                task_id=resolved.task_id if resolved else None,
                job_id=resolved.job_id if resolved else None,
                object_id=json.dumps([edge_type, src, dst], ensure_ascii=False),
                exec_status=resolved.status if resolved else execution.status,
            )
        )
    return rows


def _schema_names_by_key(schema_keys: list[str]) -> dict[str, str]:
    """schemaKey → schema 名（schema 名即图内 tag/边类型名），查控制库 schema 目录。"""
    if not schema_keys:
        return {}
    from sqlalchemy import text

    from infra.workflow_mysql import get_workflow_engine

    quoted = ", ".join(f"'{key.replace(chr(39), '')}'" for key in schema_keys)
    try:
        engine = get_workflow_engine()
        with engine.connect() as connection:
            rows = connection.execute(
                text(
                    "SELECT schema_key, name FROM kg_schema_definition WHERE schema_key IN ("
                    + quoted
                    + ")"
                )
            ).fetchall()
        return {str(row[0]): str(row[1]) for row in rows if row[1]}
    except Exception:
        logger.warning("昨日新增图反查：schema 名查询失败，明细行退回聚合展示", exc_info=True)
        return {}


def _schema_labels_by_name(space: str | None, kind: str) -> dict[str, str]:
    """图对象名 → Schema 目录中文名：当前图空间行优先，其余空间行兜底。

    「任何图空间都有真实分类」的关键——目录在共享控制库、跨空间共享；当前
    空间没登记的名字由别的空间同名 Schema 兜底，仍查不到的不进表，调用方回退
    用图内原名（tag/边类型名）。"""
    from sqlalchemy import text

    from infra.graph_db.config import TRSGraphSettings
    from infra.workflow_mysql import get_workflow_engine

    target = space or TRSGraphSettings.from_env().space
    try:
        engine = get_workflow_engine()
        with engine.connect() as connection:
            rows = connection.execute(
                text(
                    "SELECT name, label FROM kg_schema_definition "
                    "WHERE is_deleted = 0 AND kind = :kind "
                    "AND label IS NOT NULL AND label <> '' "
                    "ORDER BY (graph_space = :space) DESC, updated_at DESC"
                ),
                {"kind": kind, "space": target},
            ).fetchall()
    except Exception:
        logger.warning("Schema 目录中文名查询失败，回退用图内原名", exc_info=True)
        return {}
    labels: dict[str, str] = {}
    for name, label in rows:
        if name and label and str(name) not in labels:
            labels[str(name)] = str(label)
    return labels


def _connect_graph_for_space(space: str | None) -> Any:
    from infra.graph_db.client import TRSGraphClient
    from infra.graph_db.config import TRSGraphSettings

    settings = TRSGraphSettings.from_env()
    if space:
        settings.space = space
    client = TRSGraphClient(settings)
    client.connect()
    return client


def enrich_day_rows_with_graph(
    snapshot: DayChangesSnapshot,
    space: str | None,
    *,
    connect_client=None,
    schema_names: dict[str, str] | None = None,
    schema_labels: dict[str, str] | None = None,
) -> DayChangesSnapshot:
    """昨日新增明细按图内对象逐行展示：反查成功的执行用逐对象行替换聚合行。

    实体行：数据类型=单个 Schema 的目录中文名（与构成图同口径，查不到用图内
    原名）、具体对象=name 公共字段、来源=source_table 公共字段、变更内容=新增
    Schema 名、时间=写入时间。关系行：具体对象=起点实体名 → 终点实体名，其余
    同实体口径。图不可达、schema 名缺失、tag 无索引等任一环节失败都退回该执行
    的内部聚合行；无索引的实体先尝试 MATCH。``*_rows_exact`` 随之置位：
    完整读取时按真实记录计数，任一执行失败则页面提示明细未完整读取。
    """
    if not snapshot.entity_executions and not snapshot.relation_executions:
        return snapshot
    # 反查闸门：当日 written 合计超过阈值的类整体跳过逐对象反查——大写入日的
    # LOOKUP 全窗扫描会长时间占住共享图会话池并把冷算拖到分钟级；总量仍按
    # 控制库写图计数精确给出，明细退聚合行并明确提示。两类都闸住时连图都不必连。
    entity_gated = snapshot.entity_added > _LOOKUP_WRITTEN_LIMIT
    relation_gated = snapshot.relation_added > _LOOKUP_WRITTEN_LIMIT
    if entity_gated or relation_gated:
        logger.info(
            "昨日新增逐对象反查被闸门跳过 space=%s entity_written=%s relation_written=%s"
            " limit=%s，明细退聚合行",
            space,
            snapshot.entity_added,
            snapshot.relation_added,
            _LOOKUP_WRITTEN_LIMIT,
        )
    if entity_gated and relation_gated:
        return replace(snapshot, entity_gated=True, relation_gated=True)
    if schema_names is None:
        schema_names = _schema_names_by_key(
            [ex.schema_key for ex in [*snapshot.entity_executions, *snapshot.relation_executions]]
        )
    if schema_labels is None:
        schema_labels = {
            **_schema_labels_by_name(space, "entity"),
            **_schema_labels_by_name(space, "relation"),
        }
    if connect_client is None:
        connect_client = _connect_graph_for_space
    try:
        client = connect_client(space)
    except Exception:
        logger.warning("昨日新增图反查：图客户端连接失败，明细行退回聚合展示", exc_info=True)
        return replace(snapshot, entity_gated=entity_gated, relation_gated=relation_gated)
    time_props: dict[tuple[str, str], GraphTimeProperty | None] = {}
    # 闸住的类保留 parse 产出的聚合行；exact=False 交由装配端按闸门口径展示
    entity_rows: list[AssetChangeRow] = list(snapshot.entity_rows) if entity_gated else []
    seed_vids: list[str] = []
    entity_exact = not entity_gated
    try:
        entity_targets = (
            []
            if entity_gated
            else sorted(snapshot.entity_executions, key=lambda ex: ex.completed_at, reverse=True)
        )
        for execution in entity_targets:
            schema_name = schema_names.get(execution.schema_key)
            rows, vids = (
                _entity_object_rows(
                    client,
                    execution,
                    schema_name,
                    time_props,
                    schema_labels,
                    snapshot.entity_executions,
                )
                if schema_name
                else (None, [])
            )
            if rows is None:
                rows = list(execution.fallback_rows)
                entity_exact = False
            else:
                # 当日实体 vid 供关系边 GO FROM 兜底反查（边端点常为当日写入实体）
                seed_vids.extend(vids)
            entity_rows.extend(rows)
        relation_rows: list[AssetChangeRow] = list(snapshot.relation_rows) if relation_gated else []
        relation_exact = not relation_gated
        relation_targets = (
            []
            if relation_gated
            else sorted(snapshot.relation_executions, key=lambda ex: ex.completed_at, reverse=True)
        )
        for execution in relation_targets:
            schema_name = schema_names.get(execution.schema_key)
            rows = (
                _relation_object_rows(
                    client,
                    execution,
                    schema_name,
                    time_props,
                    seed_vids,
                    schema_labels,
                    snapshot.relation_executions,
                )
                if schema_name
                else None
            )
            if rows is None:
                relation_exact = False
                rows = list(execution.fallback_rows)
            relation_rows.extend(rows)
    finally:
        close = getattr(client, "close", None)
        if close is not None:
            try:
                close()
            except Exception:  # noqa: BLE001
                logger.exception("关闭昨日新增反查图客户端失败")
    # 同一对象常被当日多次执行触碰（重跑/补写），优先按 (类型, ID) 去重；
    # 执行按完成时间降序遍历，先到的行即最新一次写入的口径。随后统一按识别
    # 时间倒序全量展示（不截断：有多少条数据就展示多少条）
    entity_rows = _sort_rows_newest_first(_dedupe_rows(entity_rows))
    relation_rows = _sort_rows_newest_first(_dedupe_rows(relation_rows))
    return replace(
        snapshot,
        entity_rows=entity_rows,
        relation_rows=relation_rows,
        entity_rows_exact=entity_exact,
        relation_rows_exact=relation_exact,
        entity_gated=entity_gated,
        relation_gated=relation_gated,
    )


def _dedupe_rows(rows: list[AssetChangeRow]) -> list[AssetChangeRow]:
    """同一 (类型, ID) 只保留第一行；历史无 ID 行回退对象名。同名不同 ID 保留。"""
    seen: set[tuple[str, str]] = set()
    unique: list[AssetChangeRow] = []
    for row in rows:
        key = (row.type, row.object_id or row.object)
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
    return unique


def _sort_rows_newest_first(rows: list[AssetChangeRow]) -> list[AssetChangeRow]:
    """明细统一按识别时间倒序（最新在上，同秒稳定保序）；全量展示不截断。"""
    return sorted(rows, key=lambda row: row.time, reverse=True)


def _ratios(values: list[int]) -> list[int]:
    total = sum(values)
    if total <= 0:
        return [0 for _ in values]
    result = [round(value * 100 / total) for value in values]
    result[max(range(len(values)), key=values.__getitem__)] += 100 - sum(result)
    return result


def _member_names(members: list[tuple[str, int]], limit: int = 3) -> str:
    """分段 schema 小字：桶内真实成员名（按计数降序取前 N，超出加 +N）。

    取代写死的演示文案（Expert / Scholar 等——点名 schema 近半在图里不存在
    或零计数），让小字与图内实际标签/边名一致、随图变化；零计数成员不列
    （Paper1/Test 等测试残壳不进展示），桶空时给 -。
    """
    names = [name for name, _ in members]
    if not names:
        return "-"
    if len(names) <= limit:
        return " / ".join(names)
    return " / ".join(names[:limit]) + f" +{len(names) - limit}"


def _build_structure(
    counts: dict[str, int],
    *,
    entity: bool,
    labels: dict[str, str] | None = None,
) -> list[StructureItem]:
    """构成图按单个 Schema 出分段（2026-09-23 用户口径）：每个 tag/边类型一段，
    展示名取 Schema 目录中文名（当前空间行优先、跨空间兜底，查不到用原名），
    按数量降序取前 4，其余并入「其他实体/其他关系」固定最后；零计数不出段——
    任何图空间都只显示真实存在的分类，不再有固定的空桶。"""
    labels = labels or {}
    entries = sorted(
        ((name, max(0, int(count))) for name, count in counts.items()),
        key=lambda pair: (-pair[1], pair[0]),
    )
    entries = [(name, count) for name, count in entries if count > 0]
    tones = ("#2e90fa", "#7a5af8", "#12b76a", "#f79009", "#98a2b3")
    used_labels: set[str] = set()

    def _display(name: str) -> str:
        # 目录中文名可能重名（或与「其他」撞名）：先退图内原名，仍撞加序号
        label = labels.get(name) or name
        if label in used_labels:
            label = name
        suffix = 2
        while label in used_labels:
            label = f"{name}#{suffix}"
            suffix += 1
        used_labels.add(label)
        return label

    def _members(members: list[tuple[str, int]]) -> list[StructureMember]:
        # 成员展示名同分段口径取目录中文名；中文名撞车退图内原名保证前端 key 唯一
        used: set[str] = set()
        shown: list[StructureMember] = []
        for name, count in members:
            display = labels.get(name) or name
            if display in used:
                display = name
            used.add(display)
            shown.append(StructureMember(name=display, count=count))
        return shown

    # (展示名, 图内原名, 计数, 成员清单, 是否「其他」段)——前 4 单 Schema 各一段
    segments: list[tuple[str, str, int, list[tuple[str, int]], bool]] = [
        (_display(name), name, count, [(name, count)], False) for name, count in entries[:4]
    ]
    rest = entries[4:]
    if rest:
        segments.append(
            ("其他实体" if entity else "其他关系", "", sum(count for _, count in rest), rest, True)
        )
    ratios = _ratios([seg[2] for seg in segments])
    items: list[StructureItem] = []
    for position, (label, name, count, members, is_other) in enumerate(segments):
        shown = _members(members)
        items.append(
            StructureItem(
                label=label,
                schema=name or _member_names([(m.name, m.count) for m in shown]),
                # 成员清单（展示名=目录中文名）随响应下发，「其他」段悬浮浮窗列它
                members=shown,
                count=_format_count(count),
                ratio=ratios[position],
                tone=tones[position],
                is_other=is_other,
            )
        )
    return items


def _load_net_added_safe(space: str | None, day: str) -> tuple[dict[str, int | None], str]:
    """净新增差分读取的安全包装：任何失败降级为 null + 原因，绝不影响总览装配。"""
    try:
        from infra.graph_db.config import TRSGraphSettings
        from service.stats_daily_snapshot import load_net_added

        return load_net_added(space or TRSGraphSettings.from_env().space, day)
    except Exception:
        logger.warning("净新增读取失败 space=%s day=%s", space, day, exc_info=True)
        return {"entity": None, "relation": None}, "净新增暂不可读取，请稍后重试"


class PlatformOverviewService:
    """优先读取真实图统计；无法读取时进入诚实降级：显式占位，不回填演示数据。"""

    def __init__(
        self,
        stats_provider: GraphStatsProvider | None = None,
        changes_provider: DayChangesProvider | None = None,
    ) -> None:
        self._stats_provider = stats_provider or TRSGraphStatsProvider()
        self._changes_provider = changes_provider or WorkflowControlDayChangesProvider()
        self._cache_seconds = int(os.getenv("PLATFORM_OVERVIEW_CACHE_SECONDS", "60"))
        # 缓存按 (空间, 统计日) 隔离：总览随全局图空间选择器切换后 60s 内不串空间；
        # 指定历史日（day 查询参数）与默认当日互不挤占。三元组 (过期时刻, 写入
        # 时刻, 结果)——写入时刻供旧值硬上限判断
        self._cached: dict[tuple[str | None, str], tuple[float, float, PlatformOverviewData]] = {}
        # 旧值兜底硬上限：stale-while-revalidate 的后台刷新若卡死（图连接挂起等），
        # 旧值不能无限期顶下去（2026-10-14 dev2 事故：多 worker 各自的 per-space
        # 刷新锁被卡死线程占住，跨日仍返回前一天的装配结果）。超限后不等那把
        # 可能卡死的锁、在请求线程同步重算——计算幂等，并发重算只是浪费不是错误。
        self._stale_hard_limit = float(
            os.getenv("PLATFORM_OVERVIEW_STALE_HARD_LIMIT_SECONDS", "900")
        )
        self._compute_locks: dict[tuple[str | None, str], threading.Lock] = {}
        self._locks_guard = threading.Lock()

    def _lock_for(self, key: tuple[str | None, str]) -> threading.Lock:
        with self._locks_guard:
            return self._compute_locks.setdefault(key, threading.Lock())

    def get_overview(
        self, space: str | None = None, day: str | None = None
    ) -> PlatformOverviewData:
        key = (space, day or "")
        cached = self._cached.get(key)
        now = time.monotonic()
        if cached is not None and cached[0] > now:
            return cached[2]
        if cached is not None:
            if now - cached[1] > self._stale_hard_limit:
                # 硬上限兜底：不等可能卡死的后台刷新，直接同步重算并覆写缓存
                try:
                    result = self._compute_overview(space, day)
                except Exception:  # noqa: BLE001 - 重算失败继续沿用旧值，下一个请求再试
                    logger.warning(
                        "平台总览旧值超硬上限后同步重算失败 space=%s，继续沿用旧值",
                        space,
                        exc_info=True,
                    )
                    return cached[2]
                stamp = time.monotonic()
                self._cached[key] = (stamp + self._cache_seconds, stamp, result)
                return result
            # 过期：非阻塞抢刷新权，抢到即后台刷新，旧值立即返回
            lock = self._lock_for(key)
            if lock.acquire(blocking=False):
                threading.Thread(
                    target=self._refresh_in_background, args=(key, space, day, lock), daemon=True
                ).start()
            return cached[2]
        # 冷路径：per-key 单飞同步计算（等锁线程双检命中刚写入的结果）
        with self._lock_for(key):
            cached = self._cached.get(key)
            if cached is not None and cached[0] > time.monotonic():
                return cached[2]
            result = self._compute_overview(space, day)
            stamp = time.monotonic()
            self._cached[key] = (stamp + self._cache_seconds, stamp, result)
            return result

    def _refresh_in_background(
        self,
        key: tuple[str | None, str],
        space: str | None,
        day: str | None,
        lock: threading.Lock,
    ) -> None:
        try:
            result = self._compute_overview(space, day)
            stamp = time.monotonic()
            self._cached[key] = (stamp + self._cache_seconds, stamp, result)
        except Exception:  # noqa: BLE001 - 刷新失败保留旧值，下一个请求再试
            logger.warning(
                "平台总览后台刷新失败 space=%s day=%s，继续沿用旧值", space, day, exc_info=True
            )
        finally:
            lock.release()

    def _compute_overview(self, space: str | None, day: str | None = None) -> PlatformOverviewData:
        fallback = self._get_fallback_overview()
        try:
            stats = (
                self._stats_provider.get_stats(space) if space else self._stats_provider.get_stats()
            )
        except Exception as exc:
            logger.warning("首页图资产统计读取失败，进入诚实降级（占位不回填演示数据）: %s", exc)
            # 运行中执行数来自控制库、与图无关：仍实时短查，拿不到回 0（不用演示常数）
            try:
                running_live = self._changes_provider.running_count(space)
            except Exception:
                running_live = 0
            result = fallback.model_copy(
                update={
                    "platform_status": "图数据库暂不可用，页面已降级",
                    "pending_batch_count": running_live,
                    "updated_at": datetime.now(_DAY_TZ).strftime("%H:%M"),
                    "data_mode": "mock",
                    "data_sources": {"graphAssets": "unavailable", "dayChanges": "unavailable"},
                    "warnings": [
                        "图数据库统计不可用，资产总量、构成图与昨日新增明细暂时无法展示。"
                    ],
                    "asset_change_errors": {
                        "entity": "实体新增明细暂不可读取，请稍后重试",
                        "relation": "关系新增明细暂不可读取，请稍后重试",
                    },
                }
            )
        else:
            # 昨日新增来自工作流控制库（唯一写图通道 kg.schema.extract 的执行记录）；
            # 读不到时保持占位并给出警告，绝不回填虚构演示行
            changes: DayChangesSnapshot | None = None
            try:
                changes = self._changes_provider.get_day_changes(space, day=day)
            except Exception as exc:
                logger.warning("首页昨日新增读取失败（工作流控制库不可用）: %s", exc)
            if changes is not None:
                # 聚合格式（2026-10-14）：行 = 写入块（执行 × 来源），徽标与左下角
                # 合计按控制库 written 精确计数（台账/现算同口径），不再有反查闸门、
                # 逐对象行数对账与「未完整读取」中间态——控制库读成即定局。
                # 写入块行数与执行数同量级（几十封顶），全量透出不设上限——
                # 「行 count 求和 == 合计」因此成为无条件的构造保证。
                change_rows: dict[str, list[AssetChangeRow]] = {}
                change_totals: dict[str, int] = {}
                change_errors: dict[str, str] = {}
                for key, rows, written in (
                    ("entity", changes.entity_rows, changes.entity_added),
                    ("relation", changes.relation_rows, changes.relation_added),
                ):
                    change_rows[key] = rows
                    change_totals[key] = written
                entity_count = change_totals["entity"]
                relation_count = change_totals["relation"]
                # 有数才显示 +N；当日为 0 或读不到一律占位 --，标签统一不带括号说明
                added_label = "昨日新增"
                entity_added = f"+{_format_count(entity_count)}" if entity_count else "--"
                relation_added = f"+{_format_count(relation_count)}" if relation_count else "--"
                day_source = "workflow-control-live"
                extra_warnings = list(change_errors.values())
            else:
                added_label = "昨日新增"
                entity_added = "--"
                relation_added = "--"
                change_rows = {"entity": [], "relation": []}
                change_totals = {"entity": 0, "relation": 0}
                change_errors = {
                    "entity": "实体新增明细暂不可读取，请稍后重试",
                    "relation": "关系新增明细暂不可读取，请稍后重试",
                }
                day_source = "unavailable"
                extra_warnings = ["昨日新增暂时不可读：工作流控制库不可用。"]
            # 运行中执行数实时短查（不随日快照冻结一整天）；控制库不可读回退快照值
            try:
                running_live = self._changes_provider.running_count(space)
            except Exception:
                running_live = changes.running_count if changes is not None else 0
            # 净新增（2026-10-16）：相邻两日图统计快照差分，与总量同口径
            # （总量(D) − 总量(D−1) ≡ 净新增(D)，可直接对账）；快照缺失时值为
            # null、note 给原因，不编数。与昨日新增（写图记录口径）并排展示。
            net_target_day = (
                changes.day
                if changes is not None and changes.day
                else (day or (datetime.now(_DAY_TZ) - timedelta(days=1)).strftime("%Y-%m-%d"))
            )
            net_added, net_note = _load_net_added_safe(space, net_target_day)
            # 资产卡中心 = 真实体数（去重口径）：实体总量用 Space/vertices、
            # 关系总量用 Space/edges。构成图分段按 Schema(tag/边类型)计数、
            # 无法去重（需逐 vid 查标签），多标签顶点（如同一机构 vid 同挂
            # organization_base+Organization，dev2 实测两口径差 ~23 万）会让
            # 分段合计大于卡片总量——两个口径并存：卡片去重、分段按标签计数。
            entity_total = stats.total_nodes
            relation_total = stats.total_edges
            groups = [
                AssetOverviewGroup(
                    key="entity",
                    title="实体数据",
                    total=_format_count(entity_total),
                    total_label="实体总量",
                    added=entity_added,
                    added_label=added_label,
                ),
                AssetOverviewGroup(
                    key="relation",
                    title="关系数据",
                    total=_format_count(relation_total),
                    total_label="关系总量",
                    added=relation_added,
                    added_label=added_label,
                ),
            ]
            result = fallback.model_copy(
                update={
                    "platform_status": "图数据库连接正常",
                    "pending_batch_count": running_live,
                    # 更新时刻按日窗口时区（北京）展示：api 容器 UTC 钟曾让页面
                    # 显示成 UTC 时刻，与「昨日」窗口口径打架
                    "updated_at": datetime.now(_DAY_TZ).strftime("%H:%M"),
                    # 统计日随载荷透出：页面「统计日」标签直接用它，缓存异常时
                    # 用户一眼能看出展示的是哪一天
                    "stats_day": changes.day if changes is not None else "",
                    "asset_overview_groups": groups,
                    "asset_change_rows": change_rows,
                    "asset_change_totals": change_totals,
                    "asset_change_errors": change_errors,
                    "asset_net_added": net_added,
                    "asset_net_added_note": net_note,
                    "entity_structure": _build_structure(
                        stats.nodes, entity=True, labels=_schema_labels_by_name(space, "entity")
                    ),
                    "relation_structure": _build_structure(
                        stats.edges, entity=False, labels=_schema_labels_by_name(space, "relation")
                    ),
                    "data_mode": "partial",
                    "data_sources": {
                        "graphAssets": "trsgraph-live",
                        "dayChanges": day_source,
                    },
                    "warnings": [
                        "实体与关系统计来自图数据库实时接口。",
                        "昨日新增徽标与明细同口径：按当日任务写图记录计数，同一对象重复"
                        "写入（重跑重写、多 Schema 共写同一顶点）不去重；实体/关系总量"
                        "为图上去重存量，脚本等非任务通道写入只计入总量——两口径不同，"
                        "不能直接相减对账。运行中执行数来自工作流控制库。",
                        "净新增为相邻两日图统计快照差分（与总量同口径：总量(当日) 减 "
                        "总量(前一日) 即净新增）；当日值随采集时点更新、次日凌晨定局。",
                        *extra_warnings,
                    ],
                }
            )
        return result

    def _get_fallback_overview(self) -> PlatformOverviewData:
        """降级骨架：所有数据位显式占位、空表，绝不回填演示数据。

        图统计读取失败时以它为底做诚实降级；正常路径只借用字段结构，
        装配时逐项覆盖为真实值。
        """
        return PlatformOverviewData(
            platform_status="平台服务正常",
            pending_batch_count=0,
            updated_at=datetime.now(_DAY_TZ).strftime("%H:%M"),
            asset_overview_groups=[
                AssetOverviewGroup(
                    key="entity",
                    title="实体数据",
                    total="--",
                    total_label="实体总量",
                    added="--",
                    added_label="昨日新增",
                ),
                AssetOverviewGroup(
                    key="relation",
                    title="关系数据",
                    total="--",
                    total_label="关系总量",
                    added="--",
                    added_label="昨日新增",
                ),
            ],
            asset_change_rows={"entity": [], "relation": []},
            asset_change_totals={"entity": 0, "relation": 0},
            entity_structure=[],
            relation_structure=[],
        )
