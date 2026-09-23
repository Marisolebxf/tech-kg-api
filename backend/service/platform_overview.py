"""平台首页总览服务：图资产实时统计 + 尚未接入模块的显式降级数据。"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from typing import Any, Protocol

from biz.schemas.platform_overview import (
    AssetChangeRow,
    AssetOverviewGroup,
    LatestChange,
    ManagementRisk,
    PlatformOverviewData,
    StructureItem,
    StructureMember,
)
from infra.graph_db import get_trs_graph_client

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
        # 优先用 SHOW STATS：单条 nGQL 一次性返回所有 Tag/Edge 计数与总数（NebulaGraph 预计算，
        # 毫秒级）。比逐 label 调 node_count / 逐 edge_type 调 edge_count（N 次串行 HTTP，
        # 实测 ~57s）快 4 个数量级。SHOW STATS 需要 SUBMIT JOB STATS 已跑过；若返回空或抛错，
        # 回退到逐个计数。
        try:
            result = client.execute_query("SHOW STATS")
            nodes: dict[str, int] = {}
            edges: dict[str, int] = {}
            total_nodes = 0
            total_edges = 0
            for rec in result.records:
                rtype = rec.get("Type")
                name = rec.get("Name")
                count = int(rec.get("Count", 0) or 0)
                if rtype == "Tag" and name:
                    nodes[name] = count
                elif rtype == "Edge" and name:
                    edges[name] = count
                elif rtype == "Space":
                    if name == "vertices":
                        total_nodes = count
                    elif name == "edges":
                        total_edges = count
            if not nodes and not edges:
                raise RuntimeError("SHOW STATS returned no rows")
            return GraphStatsSnapshot(
                total_nodes=total_nodes or sum(nodes.values()),
                total_edges=total_edges or sum(edges.values()),
                nodes=nodes,
                edges=edges,
            )
        except Exception as exc:
            logger.warning("SHOW STATS 失败，先试统计快照缓存，再回退逐项计数: %s", exc)
            # ① 客户端 300s 统计快照缓存（模块级按空间共享：实体列表浏览等
            #    可能刚成功取过）——stats 任务卡死时总览仍能秒回
            try:
                snap = client.stats_snapshot()
                return GraphStatsSnapshot(
                    total_nodes=snap["total_nodes"],
                    total_edges=snap["total_edges"],
                    nodes=dict(snap["tags"]),
                    edges=dict(snap["edges"]),
                )
            except Exception:  # noqa: BLE001 — 缓存也没有才走 REST 逐项计数
                logger.warning("统计快照缓存不可用，回退 REST 逐项计数（会慢）")
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
    """当日一次完成执行的图反查描述（今日新增明细按图内对象逐行展示）。

    执行 output 只带 written 计数、无逐对象清单；明细行改按 schemaKey 对应
    的 tag/边类型 + 时间窗（源表水位 ~ 完成时刻）反查图，拿到每个对象的
    name/source_table/写入时间。``fallback_rows`` 是反查失败时的聚合降级行
    （一次执行 × 每个来源表一行，旧口径）。
    """

    kind: str  # entity | relation
    schema_key: str
    schema_label: str
    completed_at: str  # YYYY-MM-DD HH:MM:SS
    window_lo: str  # 反查时间窗下界：源表读取起点水位最早值，缺省当日 00:00:00
    fallback_rows: list[AssetChangeRow] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class TodayChangesSnapshot:
    """今日写图增量（来自工作流控制库，按图空间过滤）。

    entity/relation_added 为今日完成执行的 ``output.sources[].written`` 合计；
    running_count 为当前 RUNNING 执行数；*_rows 为新增明细行——图反查成功时
    为逐对象行（数据类型=五类桶、具体对象=name/两端名、来源=source_table），
    失败时退回 ``*_executions`` 里各执行携带的聚合降级行。
    """

    entity_added: int = 0
    relation_added: int = 0
    running_count: int = 0
    entity_rows: list[AssetChangeRow] = field(default_factory=list)
    relation_rows: list[AssetChangeRow] = field(default_factory=list)
    entity_executions: list[ExtractExecutionInfo] = field(default_factory=list)
    relation_executions: list[ExtractExecutionInfo] = field(default_factory=list)


class TodayChangesProvider(Protocol):
    def get_today_changes(self, space: str | None = None) -> TodayChangesSnapshot: ...


def _execution_space(record: dict[str, Any]) -> str:
    """执行记录的目标图空间：调度下发记 ``graph_space``、手动/重跑记 ``graphSpace``。"""
    payload = record.get("payload") or {}
    return str(payload.get("graph_space") or payload.get("graphSpace") or "")


def _written_of(output: dict[str, Any]) -> int:
    return sum(max(0, int(source.get("written") or 0)) for source in output.get("sources") or [])


def parse_execution_records(
    payloads: list[str],
    *,
    today: str,
    target_space: str,
    default_space: str,
) -> TodayChangesSnapshot:
    """从控制库执行记录 JSON 解析今日写图增量（纯函数，便于单测）。

    只统计 ``target_space`` 空间的执行；未记录空间的旧执行按默认空间归属。
    明细行列语义对齐 kgetl 演示行：类型 = Schema 名、变更内容 = 新增 + schemaKey、
    来源 = 物理源表名、时间 = 完成时刻；具体对象因执行 output 无逐对象清单，
    以「Schema 名 · N 条」聚合描述。
    """
    entity_added = 0
    relation_added = 0
    running = 0
    entity_rows: list[tuple[str, AssetChangeRow]] = []
    relation_rows: list[tuple[str, AssetChangeRow]] = []
    entity_execs: list[ExtractExecutionInfo] = []
    relation_execs: list[ExtractExecutionInfo] = []
    for raw in payloads:
        try:
            record = json.loads(raw)
        except (TypeError, ValueError):
            continue
        if not isinstance(record, dict):
            continue
        space = _execution_space(record)
        if space != target_space and not (not space and target_space == default_space):
            continue
        status = str(record.get("status") or "")
        if status == "RUNNING":
            running += 1
            continue
        if status != "COMPLETED":
            continue
        completed_at = str(record.get("completedAt") or "")
        if completed_at[:10] != today:
            continue
        output = record.get("output") or {}
        kind = str(output.get("kind") or "")
        written = _written_of(output)
        if kind not in ("entity", "relation") or written <= 0:
            continue
        schema_label = str(output.get("schemaLabel") or output.get("schemaKey") or "")
        # 明细行列语义对齐 kgetl 演示行：变更内容 = 新增 + Schema 英文标识（schemaKey），
        # 来源 = 物理源表名。执行 output 只携带 written 计数、无逐对象清单
        # （载荷 S3 中转默认关闭，无 records artifact 可查），故具体对象列降级为
        # 「Schema 名 · N 条」的诚实聚合描述，不编造对象名。
        schema_key = str(
            output.get("schemaKey") or schema_label or ("实体" if kind == "entity" else "关系")
        )
        display_label = schema_label or ("实体 Schema" if kind == "entity" else "关系 Schema")
        change = f"新增 {schema_key}"
        completed_time = completed_at[11:19] or "-"
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
                object=f"{display_label} · {source_written:,} 条",
                change=change,
                source=str(source.get("table") or source.get("source") or "-"),
                time=completed_time,
            )
            target_rows.append((completed_at, row))
            exec_rows.append(row)
            # 反查窗口下界优先用开跑前的起点水位（startWatermark）：watermark 是
            # 跑完后的终值，取 min 后窗口会缩成最后一批同秒，写图时间落在窗口内的
            # 顶点/边查不全；旧执行没有 startWatermark 时退回 watermark
            watermark = str(source.get("startWatermark") or source.get("watermark") or "")
            if watermark:
                watermarks.append(watermark)
        descriptor = ExtractExecutionInfo(
            kind=kind,
            schema_key=schema_key,
            schema_label=schema_label or display_label,
            completed_at=completed_at,
            # 源表水位（读取起点）必然早于写图时刻，作反查窗下界；缺省当日零点
            window_lo=min(watermarks) if watermarks else f"{completed_at[:10]} 00:00:00",
            fallback_rows=exec_rows,
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
    return TodayChangesSnapshot(
        entity_added=entity_added,
        relation_added=relation_added,
        running_count=running,
        entity_rows=[row for _, row in entity_rows],
        relation_rows=[row for _, row in relation_rows],
        entity_executions=entity_execs,
        relation_executions=relation_execs,
    )


class WorkflowControlTodayChangesProvider:
    """默认实现：从工作流控制库（techkg_control.workflow_executions）读今日增量。

    覆盖平台唯一写图通道 ``kg.schema.extract`` 的执行记录；直连 ETL 脚本与
    T_DIRECT 审核直写不经过控制库，不计入（明细行口径即任务中心执行历史）。
    """

    # 抽取执行最长可跑数小时：取 7 天窗口兜住跨日完成的长执行
    _LOOKBACK_DAYS = 7

    def get_today_changes(self, space: str | None = None) -> TodayChangesSnapshot:
        from sqlalchemy import text

        from infra.graph_db.config import TRSGraphSettings
        from infra.workflow_mysql import get_workflow_engine

        target_space = space or TRSGraphSettings.from_env().space
        default_space = TRSGraphSettings.from_env().space
        now = datetime.now().astimezone()
        since = (now - timedelta(days=self._LOOKBACK_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
        engine = get_workflow_engine()
        with engine.connect() as connection:
            result = connection.execute(
                text(
                    "SELECT payload FROM workflow_executions "
                    "WHERE status IN ('COMPLETED', 'RUNNING') AND started_at >= :since"
                ),
                {"since": since},
            )
            payloads = [row[0] for row in result.fetchall()]
        return enrich_today_rows_with_graph(
            parse_execution_records(
                payloads,
                today=now.strftime("%Y-%m-%d"),
                target_space=target_space,
                default_space=default_space,
            ),
            space,
        )


# ---- 今日新增明细行：按图内对象逐行展示（图反查） ------------------------------
# 单次执行的对象行/端点 vid 上限：防大时间窗把明细表与查询打爆（抽取 written
# 通常个位~百级；超限截断，行数语义见抽屉 footer）
_OBJECT_ROW_CAP = 50
_ENDPOINT_CAP = 40
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
)


def _vertex_display_name(props: dict[str, Any], vid: str) -> str:
    for key in _NAME_PROP_CANDIDATES:
        value = props.get(key)
        if value:
            return str(value)
    return vid


def _time_hhmmss(value: Any, fallback: str) -> str:
    return str(value or "")[11:19] or fallback


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


def _graph_time_prop(client: Any, kind: str, name: str, cache: dict[tuple[str, str], str | None]) -> str | None:
    """tag/边类型上可用的写入时间属性：update_time 优先，其次 create_time。"""
    cache_key = (kind, name)
    if cache_key in cache:
        return cache[cache_key]
    try:
        statement = f"DESC TAG `{name}`" if kind == "entity" else f"DESC EDGE `{name}`"
        fields = {rec.get("Field") for rec in client.execute_query(statement).records}
    except Exception:
        fields = set()
    prop = "update_time" if "update_time" in fields else ("create_time" if "create_time" in fields else None)
    cache[cache_key] = prop
    return prop


def _safe_identifier(name: str) -> str:
    return name.replace("`", "").strip()


def _safe_vid(vid: Any) -> str:
    return str(vid or "").replace('"', "").strip()


def _entity_object_rows(
    client: Any,
    execution: ExtractExecutionInfo,
    schema_name: str,
    time_props: dict[tuple[str, str], str | None],
    schema_labels: dict[str, str],
) -> tuple[list[AssetChangeRow] | None, list[str]]:
    """按 tag + 时间窗反查当日写入的实体顶点，逐对象一行；查不到返回 None 走聚合降级。"""
    tag = _safe_identifier(schema_name)
    time_prop = _graph_time_prop(client, "entity", tag, time_props)
    if not time_prop:
        return None, []
    statement = (
        f'LOOKUP ON `{tag}` WHERE `{tag}`.`{time_prop}` >= "{execution.window_lo}" '
        f'AND `{tag}`.`{time_prop}` <= "{execution.completed_at}" '
        "YIELD id(vertex) AS vid, properties(vertex) AS props"
    )
    try:
        records = client.execute_query(statement).records
    except Exception:
        # tag 无任何索引（LOOKUP 400）或属性形态不符——退回聚合行
        return None, []
    # 数据类型列 = 单个 Schema 的目录中文名（与图谱资产构成图同口径），查不到用原名
    type_label = schema_labels.get(tag) or tag
    fallback_source = execution.fallback_rows[0].source if execution.fallback_rows else "-"
    rows: list[AssetChangeRow] = []
    vids: list[str] = []
    for record in records[:_OBJECT_ROW_CAP]:
        props = record.get("props") or {}
        vid = _safe_vid(record.get("vid"))
        rows.append(
            AssetChangeRow(
                type=type_label,
                object=_vertex_display_name(props, vid),
                change=f"新增 {tag}",
                source=str(props.get("source_table") or fallback_source),
                time=_time_hhmmss(props.get(time_prop), execution.completed_at[11:19]),
            )
        )
        vids.append(vid)
    if not rows:
        return None, []
    return rows, vids


def _relation_edges(
    client: Any,
    execution: ExtractExecutionInfo,
    edge_type: str,
    time_prop: str | None,
    seed_vids: list[str],
) -> list[tuple[str, str, dict[str, Any]]]:
    """当日关系边收集：①边属性时间窗 LOOKUP（需边索引）②退而求其次从当日
    实体 vid 出发 GO BIDIRECT（边端点通常就是当日写入的实体）再按时间过滤。"""
    edges: list[tuple[str, str, dict[str, Any]]] = []
    seen: set[tuple[str, str]] = set()

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
                if not (execution.window_lo <= stamp <= execution.completed_at):
                    continue
            seen.add(key)
            edges.append((src, dst, props))

    if time_prop:
        statement = (
            f'LOOKUP ON `{edge_type}` WHERE `{edge_type}`.`{time_prop}` >= "{execution.window_lo}" '
            f'AND `{edge_type}`.`{time_prop}` <= "{execution.completed_at}" '
            "YIELD src(edge) AS src, dst(edge) AS dst, properties(edge) AS eprops"
        )
        try:
            _collect(client.execute_query(statement).records, window_filter=False)
        except Exception:
            pass  # 边类型无索引（400）→ 走 GO FROM 兜底
    if not edges and seed_vids:
        vid_list = ", ".join(f'"{vid}"' for vid in seed_vids[:_OBJECT_ROW_CAP])
        statement = (
            f"GO FROM {vid_list} OVER `{edge_type}` BIDIRECT "
            "YIELD src(edge) AS src, dst(edge) AS dst, properties(edge) AS eprops"
        )
        try:
            _collect(client.execute_query(statement).records, window_filter=True)
        except Exception:
            pass
    return edges


def _endpoint_names(client: Any, vids: list[str]) -> dict[str, str]:
    names: dict[str, str] = {}
    for vid in vids[:_ENDPOINT_CAP]:
        try:
            records = client.execute_query(f'FETCH PROP ON * "{vid}" YIELD vertex AS v').records
        except Exception:
            continue
        if records:
            names[vid] = _vertex_display_name(_flatten_vertex_props(records[0].get("v")), vid)
    return names


def _relation_object_rows(
    client: Any,
    execution: ExtractExecutionInfo,
    schema_name: str,
    time_props: dict[tuple[str, str], str | None],
    seed_vids: list[str],
    schema_labels: dict[str, str],
) -> list[AssetChangeRow] | None:
    """按边类型反查当日关系边，具体对象 = 起点实体名 → 终点实体名。"""
    edge_type = _safe_identifier(schema_name)
    time_prop = _graph_time_prop(client, "relation", edge_type, time_props)
    edges = _relation_edges(client, execution, edge_type, time_prop, seed_vids)
    if not edges:
        return None
    endpoint_vids: list[str] = []
    for src, dst, _ in edges:
        for vid in (src, dst):
            if vid not in endpoint_vids:
                endpoint_vids.append(vid)
    names = _endpoint_names(client, endpoint_vids)
    # 数据类型列 = 单个 Schema 的目录中文名（与图谱资产构成图同口径），查不到用原名
    type_label = schema_labels.get(edge_type) or edge_type
    fallback_source = execution.fallback_rows[0].source if execution.fallback_rows else "-"
    fallback_time = execution.completed_at[11:19]
    rows: list[AssetChangeRow] = []
    for src, dst, edge_props in edges[:_OBJECT_ROW_CAP]:
        rows.append(
            AssetChangeRow(
                type=type_label,
                object=f"{names.get(src, src)} → {names.get(dst, dst)}",
                change=f"新增 {edge_type}",
                source=str(edge_props.get("source_table") or fallback_source),
                time=_time_hhmmss(edge_props.get(time_prop), fallback_time) if time_prop else fallback_time,
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
                text("SELECT schema_key, name FROM kg_schema_definition WHERE schema_key IN (" + quoted + ")")
            ).fetchall()
        return {str(row[0]): str(row[1]) for row in rows if row[1]}
    except Exception:
        logger.warning("今日新增图反查：schema 名查询失败，明细行退回聚合展示", exc_info=True)
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


def enrich_today_rows_with_graph(
    snapshot: TodayChangesSnapshot,
    space: str | None,
    *,
    connect_client=None,
    schema_names: dict[str, str] | None = None,
    schema_labels: dict[str, str] | None = None,
) -> TodayChangesSnapshot:
    """今日新增明细按图内对象逐行展示：反查成功的执行用逐对象行替换聚合行。

    实体行：数据类型=单个 Schema 的目录中文名（与构成图同口径，查不到用图内
    原名）、具体对象=name 公共字段、来源=source_table 公共字段、变更内容=新增
    Schema 名、时间=写入时间。关系行：具体对象=起点实体名 → 终点实体名，其余
    同实体口径。图不可达、schema 名缺失、tag 无索引等任一环节失败都退回该执行
    的聚合降级行。
    """
    if not snapshot.entity_executions and not snapshot.relation_executions:
        return snapshot
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
        logger.warning("今日新增图反查：图客户端连接失败，明细行退回聚合展示", exc_info=True)
        return snapshot
    time_props: dict[tuple[str, str], str | None] = {}
    entity_rows: list[AssetChangeRow] = []
    seed_vids: list[str] = []
    try:
        for execution in sorted(snapshot.entity_executions, key=lambda ex: ex.completed_at, reverse=True):
            schema_name = schema_names.get(execution.schema_key)
            rows, vids = (
                _entity_object_rows(client, execution, schema_name, time_props, schema_labels)
                if schema_name
                else (None, [])
            )
            if rows is None:
                rows = list(execution.fallback_rows)
            else:
                # 当日实体 vid 供关系边 GO FROM 兜底反查（边端点常为当日写入实体）
                seed_vids.extend(vids)
            entity_rows.extend(rows)
        relation_rows: list[AssetChangeRow] = []
        for execution in sorted(snapshot.relation_executions, key=lambda ex: ex.completed_at, reverse=True):
            schema_name = schema_names.get(execution.schema_key)
            rows = (
                _relation_object_rows(
                    client, execution, schema_name, time_props, seed_vids, schema_labels
                )
                if schema_name
                else None
            )
            relation_rows.extend(rows if rows is not None else execution.fallback_rows)
    finally:
        close = getattr(client, "close", None)
        if close is not None:
            try:
                close()
            except Exception:  # noqa: BLE001
                logger.exception("关闭今日新增反查图客户端失败")
    return replace(snapshot, entity_rows=entity_rows, relation_rows=relation_rows)


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


class PlatformOverviewService:
    """优先读取真实图统计；无法读取时保留可演示、可识别的降级结果。"""

    def __init__(
        self,
        stats_provider: GraphStatsProvider | None = None,
        changes_provider: TodayChangesProvider | None = None,
    ) -> None:
        self._stats_provider = stats_provider or TRSGraphStatsProvider()
        self._changes_provider = changes_provider or WorkflowControlTodayChangesProvider()
        self._cache_seconds = int(os.getenv("PLATFORM_OVERVIEW_CACHE_SECONDS", "60"))
        # 缓存按空间隔离：总览随全局图空间选择器切换后 60s 内不串空间
        self._cached: dict[str | None, tuple[float, PlatformOverviewData]] = {}

    def get_overview(self, space: str | None = None) -> PlatformOverviewData:
        now = time.monotonic()
        cached = self._cached.get(space)
        if cached is not None and cached[0] > now:
            return cached[1]

        fallback = self._get_fallback_overview()
        try:
            stats = (
                self._stats_provider.get_stats(space) if space else self._stats_provider.get_stats()
            )
        except Exception as exc:
            logger.warning("首页图资产统计读取失败，使用降级数据: %s", exc)
            result = fallback.model_copy(
                update={
                    "platform_status": "图数据库暂不可用，页面已降级",
                    "updated_at": datetime.now().strftime("%H:%M"),
                    "data_mode": "mock",
                    "data_sources": {
                        "graphAssets": "demo-fallback",
                        "todayChanges": "demo-fallback",
                        "managementRisks": "demo-fallback",
                    },
                    "warnings": [
                        "图数据库统计不可用，资产总量和结构正在展示降级数据。",
                        "今日变化和管理风险等待任务中心持久化接口接入。",
                    ],
                }
            )
        else:
            # 今日新增来自工作流控制库（唯一写图通道 kg.schema.extract 的执行记录）；
            # 读不到时保持占位并给出警告，绝不回填虚构演示行
            changes: TodayChangesSnapshot | None = None
            try:
                changes = self._changes_provider.get_today_changes(space)
            except Exception as exc:
                logger.warning("首页今日新增读取失败（工作流控制库不可用）: %s", exc)
            if changes is not None:
                # 有数才显示 +N；当日为 0 或读不到一律占位 --，标签统一不带括号说明
                added_label = "今日新增"
                entity_added = (
                    f"+{_format_count(changes.entity_added)}" if changes.entity_added else "--"
                )
                relation_added = (
                    f"+{_format_count(changes.relation_added)}" if changes.relation_added else "--"
                )
                change_rows = dict(fallback.asset_change_rows)
                change_rows["entity"] = changes.entity_rows
                change_rows["relation"] = changes.relation_rows
                today_source = "workflow-control-live"
                extra_warnings: list[str] = []
            else:
                added_label = "今日新增"
                entity_added = "--"
                relation_added = "--"
                change_rows = dict(fallback.asset_change_rows)
                change_rows["entity"] = []
                change_rows["relation"] = []
                today_source = "demo-fallback"
                extra_warnings = ["今日新增暂时不可读：工作流控制库不可用。"]
            # 资产卡中心 = 真实体数（去重口径）：实体总量用 Space/vertices、
            # 关系总量用 Space/edges。构成图分段按 Schema(tag/边类型)计数、
            # 无法去重（需逐 vid 查标签），多标签顶点（如同一机构 vid 同挂
            # organization_base+Organization，dev2 实测两口径差 ~23 万）会让
            # 分段合计大于中心数——两个口径并存：卡片去重、分段合计取
            # ΣSchema 计数（entity/relation_structure_total），与分段自洽。
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
                AssetOverviewGroup(
                    key="property",
                    title="属性值数据",
                    total="--",
                    total_label="属性值总量（统计接口待接入）",
                    added="--",
                    added_label="今日新增",
                ),
            ]
            result = fallback.model_copy(
                update={
                    "platform_status": "图数据库连接正常",
                    "pending_batch_count": changes.running_count if changes else 0,
                    "updated_at": datetime.now().strftime("%H:%M"),
                    "asset_overview_groups": groups,
                    "asset_change_rows": change_rows,
                    "entity_structure": _build_structure(
                        stats.nodes, entity=True, labels=_schema_labels_by_name(space, "entity")
                    ),
                    "relation_structure": _build_structure(
                        stats.edges, entity=False, labels=_schema_labels_by_name(space, "relation")
                    ),
                    # 环形图中心 = 各分段之和（Σ标签/Σ边类型计数），与分段自洽
                    "entity_structure_total": _format_count(sum(stats.nodes.values())),
                    "relation_structure_total": _format_count(sum(stats.edges.values())),
                    "data_mode": "partial",
                    "data_sources": {
                        "graphAssets": "trsgraph-live",
                        "todayChanges": today_source,
                        "managementRisks": "demo-fallback",
                    },
                    "warnings": [
                        "实体与关系统计来自图数据库实时接口。",
                        "今日新增与运行中执行数来自工作流控制库（按抽取写图计数）。",
                        "属性值统计和管理风险等待任务中心接口接入。",
                        *extra_warnings,
                    ],
                }
            )
        self._cached[space] = (now + self._cache_seconds, result)
        return result

    def _get_fallback_overview(self) -> PlatformOverviewData:
        return PlatformOverviewData(
            platform_status="平台服务正常",
            pending_batch_count=2,
            updated_at="10:30",
            asset_overview_groups=[
                AssetOverviewGroup(
                    key="entity",
                    title="实体数据",
                    total="1.28 亿",
                    total_label="实体总量",
                    added="--",
                    added_label="今日新增",
                ),
                AssetOverviewGroup(
                    key="relation",
                    title="关系数据",
                    total="6.42 亿",
                    total_label="关系总量",
                    added="--",
                    added_label="今日新增",
                ),
                AssetOverviewGroup(
                    key="property",
                    title="属性值数据",
                    total="18.76 亿",
                    total_label="属性值总量",
                    added="--",
                    added_label="今日新增",
                ),
            ],
            asset_change_rows={
                "entity": [
                    AssetChangeRow(
                        type="组织机构",
                        object="华南智能芯片有限公司",
                        change="新增 Organization",
                        source="enterprise_profile",
                        time="10:30:13",
                    ),
                    AssetChangeRow(
                        type="科技专家",
                        object="周启航",
                        change="新增 Expert",
                        source="expert_profile",
                        time="10:30:18",
                    ),
                    AssetChangeRow(
                        type="论文",
                        object="《多模态大模型知识推理方法研究》",
                        change="新增 Paper",
                        source="paper_record",
                        time="10:30:21",
                    ),
                    AssetChangeRow(
                        type="产品 / 技术产品",
                        object="边缘推理芯片 X7",
                        change="新增 Product",
                        source="enterprise_product",
                        time="10:30:26",
                    ),
                ],
                "relation": [
                    AssetChangeRow(
                        type="专家任职",
                        object="周启航 → 中国科学院自动化研究所",
                        change="新增 WORKS_AT",
                        source="expert_employment",
                        time="10:30:22",
                    ),
                    AssetChangeRow(
                        type="论文引用",
                        object="周启航 → 多模态大模型知识推理方法研究",
                        change="新增 PUBLISH",
                        source="paper_author",
                        time="10:30:25",
                    ),
                    AssetChangeRow(
                        type="企业关联",
                        object="华南智能芯片 → 边缘推理芯片 X7",
                        change="新增 HAS_PRODUCT",
                        source="enterprise_product",
                        time="10:30:29",
                    ),
                ],
                "property": [
                    AssetChangeRow(
                        type="企业属性",
                        object="华南智能芯片·注册资本",
                        change="新增 registered_capital",
                        source="enterprise_profile",
                        time="10:30:14",
                    ),
                    AssetChangeRow(
                        type="企业属性",
                        object="华南智能芯片·上市状态",
                        change="更新 listing_status",
                        source="enterprise_profile",
                        time="10:30:16",
                    ),
                    AssetChangeRow(
                        type="论文属性",
                        object="P202607140018·发表时间",
                        change="新增 publish_date",
                        source="paper_record",
                        time="10:30:23",
                    ),
                    AssetChangeRow(
                        type="关系属性",
                        object="WORKS_AT_20418·置信度",
                        change="更新 confidence",
                        source="graph_alignment",
                        time="10:30:31",
                    ),
                ],
            },
            latest_changes=[
                LatestChange(
                    time="10:30",
                    type="更新",
                    domain="机构域",
                    title="清华大学机构属性更新完成",
                    detail="机构简称与统一标识已完成标准化更新",
                    impact="处理实例 PI-20260714-0002",
                    to="/processing-instance/PI-20260714-0002",
                ),
                LatestChange(
                    time="10:18",
                    type="对齐",
                    domain="人才域",
                    title="陈卓候选专家实体完成对齐",
                    detail="机构别名经人工确认后，候选实体已合并至标准专家实体",
                    impact="处理实例 PI-20260713-0008",
                    to="/processing-instance/PI-20260713-0008",
                ),
                LatestChange(
                    time="10:13",
                    type="新增",
                    domain="人才域",
                    title="张明远标准专家实体构建完成",
                    detail="完成来源读取、Schema 映射、实体标准化与图谱入库",
                    impact="处理实例 PI-20260714-0001",
                    to="/processing-instance/PI-20260714-0001",
                ),
                LatestChange(
                    time="09:48",
                    type="质量",
                    domain="论文域",
                    title="重复论文成果记录等待确认",
                    detail="同一 paper_id 对应三条来源记录，需要人工确认主记录",
                    impact="处理实例 PI-20260714-0007",
                    to="/processing-instance/PI-20260714-0007",
                ),
                LatestChange(
                    time="昨日",
                    type="Schema",
                    domain="全域",
                    title="统一 Schema v1.8 已发布",
                    detail="确认 11 个首版必落实体、42 个标准事实关系和 9 类候选实体",
                    impact="所有新建批次使用 v1.8",
                    to="/schema",
                ),
            ],
            management_risks=[
                ManagementRisk(
                    title="大模型抽取流程已阻断",
                    detail="PI-20260714-0101 · 326 条受影响 · 张建图",
                    detail_to="/processing-instance/PI-20260714-0101",
                    review_to="/manual-review/task/PI-20260714-0101",
                ),
                ManagementRisk(
                    title="Schema 批量映射失败",
                    detail="PI-20260714-0102 · 1,284 条任务受影响 · 张建图",
                    detail_to="/processing-instance/PI-20260714-0102",
                    review_to="/manual-review/task/PI-20260714-0102",
                ),
                ManagementRisk(
                    title="张明远候选实体存在冲突",
                    detail="PI-20260714-0004 · 实体对齐 · 王审核",
                    detail_to="/processing-instance/PI-20260714-0004",
                    review_to="/manual-review/task/PI-20260714-0004",
                ),
            ],
            entity_structure=[
                StructureItem(
                    label="科技专家",
                    schema="Expert",
                    count="4,286 万",
                    ratio=34,
                    tone="#2e90fa",
                ),
                StructureItem(
                    label="论文",
                    schema="Paper",
                    count="2,931 万",
                    ratio=23,
                    tone="#7a5af8",
                ),
                StructureItem(
                    label="组织机构",
                    schema="Organization",
                    count="2,164 万",
                    ratio=17,
                    tone="#12b76a",
                ),
                StructureItem(
                    label="项目",
                    schema="Project / Patent",
                    count="1,438 万",
                    ratio=11,
                    tone="#f79009",
                ),
                StructureItem(
                    label="其他实体",
                    schema="Event / Product / Field",
                    count="1,901 万",
                    ratio=15,
                    tone="#98a2b3",
                ),
            ],
            relation_structure=[
                StructureItem(
                    label="论文引用",
                    schema="PUBLISH / CITES / OUTPUT",
                    count="2.04 亿",
                    ratio=32,
                    tone="#165dff",
                ),
                StructureItem(
                    label="专家任职",
                    schema="WORKS_AT / STUDY_AT",
                    count="1.28 亿",
                    ratio=20,
                    tone="#2e90fa",
                ),
                StructureItem(
                    label="项目参与",
                    schema="LEAD_PROJECT / INVENT_PATENT",
                    count="1.16 亿",
                    ratio=18,
                    tone="#06aed4",
                ),
                StructureItem(
                    label="企业关联",
                    schema="HAS_PRODUCT / HAS_EVENT",
                    count="0.92 亿",
                    ratio=14,
                    tone="#7a5af8",
                ),
                StructureItem(
                    label="其他关系",
                    schema="产业链 / 推理关系",
                    count="1.02 亿",
                    ratio=16,
                    tone="#98a2b3",
                ),
            ],
        )
