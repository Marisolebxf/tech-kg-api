"""平台首页总览服务：图资产实时统计 + 尚未接入模块的显式降级数据。"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
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

EXPERT_ENTITY_LABEL = "专家 / 人才"
ORGANIZATION_ENTITY_LABEL = "机构 / 企业"

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
class TodayChangesSnapshot:
    """今日写图增量（来自工作流控制库，按图空间过滤）。

    entity/relation_added 为今日完成执行的 ``output.sources[].written`` 合计；
    running_count 为当前 RUNNING 执行数；*_rows 为新增明细行（按来源表拆分，
    一次执行绑定多个来源表时逐表一行）。
    """

    entity_added: int = 0
    relation_added: int = 0
    running_count: int = 0
    entity_rows: list[AssetChangeRow] = field(default_factory=list)
    relation_rows: list[AssetChangeRow] = field(default_factory=list)


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
        for source in output.get("sources") or []:
            if not isinstance(source, dict):
                continue
            source_written = max(0, int(source.get("written") or 0))
            if source_written <= 0:
                continue
            target_rows.append(
                (
                    completed_at,
                    AssetChangeRow(
                        type=display_label,
                        object=f"{display_label} · {source_written:,} 条",
                        change=change,
                        source=str(source.get("table") or source.get("source") or "-"),
                        time=completed_time,
                    ),
                )
            )
        if kind == "entity":
            entity_added += written
        else:
            relation_added += written
    # 明细按完成时间倒序（最新写图在前）
    entity_rows.sort(key=lambda pair: pair[0], reverse=True)
    relation_rows.sort(key=lambda pair: pair[0], reverse=True)
    return TodayChangesSnapshot(
        entity_added=entity_added,
        relation_added=relation_added,
        running_count=running,
        entity_rows=[row for _, row in entity_rows],
        relation_rows=[row for _, row in relation_rows],
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
        return parse_execution_records(
            payloads,
            today=now.strftime("%Y-%m-%d"),
            target_space=target_space,
            default_space=default_space,
        )


def _ratios(values: list[int]) -> list[int]:
    total = sum(values)
    if total <= 0:
        return [0 for _ in values]
    result = [round(value * 100 / total) for value in values]
    result[max(range(len(values)), key=values.__getitem__)] += 100 - sum(result)
    return result


# 五类分桶的关键字词表：英文 token（对名字 upper 后子串匹配）+ 中文关键字（upper 恒等，
# 直接子串匹配）。词表覆盖共享图 dev2/dev 空间的全部真实 tag/边名（2026-09-23 实测），
# 中文名暂未出现但 Schema 目录支持中文 label，一并兼容。泛化关联（RELATED_TO）、
# 关键词挂载（HAS_KEYWORD/Keyword）等五类之外的类型一律落「其他」。
_ENTITY_BUCKET_TOKENS: tuple[tuple[str, ...], ...] = (
    # 0 专家人才
    ("EXPERT", "SCHOLAR", "PERSON", "TALENT", "专家", "学者", "人才", "人物", "作者"),
    # 1 论文成果（报告/出版物属文献成果）
    (
        "PAPER",
        "JOURNAL",
        "ARTICLE",
        "THESIS",
        "PUBLICATION",
        "REPORT",
        "论文",
        "期刊",
        "文献",
        "成果",
        "报告",
        "出版物",
    ),
    # 2 机构企业
    (
        "ORGANIZATION",
        "ORGANISATION",
        "ENTERPRISE",
        "COMPANY",
        "INSTITUTE",
        "ACADEMY",
        "UNIVERSITY",
        "COLLEGE",
        "机构",
        "企业",
        "公司",
        "单位",
        "院所",
        "大学",
        "高校",
        "学院",
        "院",
        "校",
        "所",
    ),
    # 3 项目专利
    ("PROJECT", "PATENT", "项目", "专利", "课题"),
)

# 关系侧用扁平有序规则：复合词必须排在泛化词前面（如「作者单位」先于「作者」）。
_RELATION_BUCKET_RULES: tuple[tuple[str, int], ...] = (
    # 1 任职/就读/作者单位——复合词提前
    ("作者单位", 1),
    # 0 发表/引用/成果（REFERENCED_BY 引证、COAUTHOR 合著归此）
    *(
        (token, 0)
        for token in (
            "PUBLISH",
            "CITE",
            "CITATION",
            "REFERENCE",
            "AUTHOR",
            "OUTPUT",
            "发表",
            "出版",
            "引用",
            "引证",
            "合著",
            "撰写",
        )
    ),
    # 1 任职/就读（EXECUTIVE_OF 高管、LEGAL_REP_OF 法人、ALUMNI 校友）
    *(
        (token, 1)
        for token in (
            "WORK",
            "STUDI",
            "AFFILIAT",
            "EMPLOY",
            "EXECUTIVE",
            "LEGAL_REP",
            "ALUMN",
            "任职",
            "就职",
            "雇佣",
            "就业",
            "就读",
            "毕业",
            "校友",
            "单位",
            "法人",
            "高管",
            "董事",
        )
    ),
    # 2 项目/专利参与（INVOLVED_IN 参与、LEADS 主持、FUNDED_BY 资助、APPLIED_BY 申请）
    *(
        (token, 2)
        for token in (
            "PROJECT",
            "PATENT",
            "INVENT",
            "INVOLV",
            "LEAD",
            "FUND",
            "PARTICIP",
            "APPLI",
            "项目",
            "专利",
            "参与",
            "承担",
            "主持",
            "资助",
            "发明",
        )
    ),
    # 3 企业/产品/事件（产业链 CHAIN、股权治理 OWN/CONTROLLER/SHAREHOLDER、投融资 INVEST/ACQUIRE）
    *(
        (token, 3)
        for token in (
            "PRODUCT",
            "PRODUCE",
            "EVENT",
            "ENTERPRISE",
            "COMPANY",
            "INVEST",
            "ACQUIRE",
            "SUBSIDIARY",
            "SHAREHOLDER",
            "OWN",
            "CONTROLLER",
            "CHAIN",
            "NEWS",
            "UPSTREAM",
            "DOWNSTREAM",
            "企业",
            "产品",
            "事件",
            "投资",
            "融资",
            "收购",
            "股东",
            "控股",
            "供应",
            "供需",
            "合作",
            "产业链",
            "竞争",
        )
    ),
)


def _entity_bucket(name: str) -> int:
    normalized = name.upper()
    for bucket, tokens in enumerate(_ENTITY_BUCKET_TOKENS):
        if any(token in normalized for token in tokens):
            return bucket
    return 4


def _relation_bucket(name: str) -> int:
    normalized = name.upper()
    for token, bucket in _RELATION_BUCKET_RULES:
        if token in normalized:
            return bucket
    return 4


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
) -> list[StructureItem]:
    buckets = [0, 0, 0, 0, 0]
    members: list[list[tuple[str, int]]] = [[], [], [], [], []]
    classifier = _entity_bucket if entity else _relation_bucket
    for name, count in counts.items():
        count = max(0, int(count))
        index = classifier(name)
        buckets[index] += count
        if count > 0:
            members[index].append((name, count))
    ratios = _ratios(buckets)
    definitions = (
        [
            (EXPERT_ENTITY_LABEL, "#2e90fa"),
            ("论文成果", "#7a5af8"),
            (ORGANIZATION_ENTITY_LABEL, "#12b76a"),
            ("项目 / 专利", "#f79009"),
            ("其他实体", "#98a2b3"),
        ]
        if entity
        else [
            ("发表 / 引用 / 成果", "#165dff"),
            ("任职 / 就读 / 作者单位", "#2e90fa"),
            ("项目 / 专利参与", "#06aed4"),
            ("企业 / 产品 / 事件", "#7a5af8"),
            ("其他关系", "#98a2b3"),
        ]
    )
    return [
        StructureItem(
            label=label,
            schema=_member_names(sorted(members[index], key=lambda m: (-m[1], m[0]))),
            # 完整成员清单（含计数）随响应下发，供前端悬停中文标签时浮窗展示
            members=[
                StructureMember(name=name, count=count)
                for name, count in sorted(members[index], key=lambda m: (-m[1], m[0]))
            ],
            count=_format_count(buckets[index]),
            ratio=ratios[index],
            tone=tone,
        )
        for index, (label, tone) in enumerate(definitions)
    ]


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
            stats = self._stats_provider.get_stats(space)
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
            # 关系总量用 Space/edges。环形图分段按标签计数、无法去重（需逐
            # vid 查标签），多标签顶点（如同一机构 vid 同挂
            # organization_base+Organization，dev2 实测两口径差 ~23 万）会让
            # 分段合计大于中心数——两个口径并存：卡片去重、环形图中心取
            # Σ标签/Σ边类型计数（entity/relation_structure_total），与分段自洽。
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
                    "entity_structure": _build_structure(stats.nodes, entity=True),
                    "relation_structure": _build_structure(stats.edges, entity=False),
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
                        type=ORGANIZATION_ENTITY_LABEL,
                        object="华南智能芯片有限公司",
                        change="新增 Organization",
                        source="enterprise_profile",
                        time="10:30:13",
                    ),
                    AssetChangeRow(
                        type=EXPERT_ENTITY_LABEL,
                        object="周启航",
                        change="新增 Expert",
                        source="expert_profile",
                        time="10:30:18",
                    ),
                    AssetChangeRow(
                        type="论文成果",
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
                        type="任职关系",
                        object="周启航 → 中国科学院自动化研究所",
                        change="新增 WORKS_AT",
                        source="expert_employment",
                        time="10:30:22",
                    ),
                    AssetChangeRow(
                        type="成果关系",
                        object="周启航 → 多模态大模型知识推理方法研究",
                        change="新增 PUBLISH",
                        source="paper_author",
                        time="10:30:25",
                    ),
                    AssetChangeRow(
                        type="产品关系",
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
                    label=EXPERT_ENTITY_LABEL,
                    schema="Expert",
                    count="4,286 万",
                    ratio=34,
                    tone="#2e90fa",
                ),
                StructureItem(
                    label="论文成果",
                    schema="Paper",
                    count="2,931 万",
                    ratio=23,
                    tone="#7a5af8",
                ),
                StructureItem(
                    label=ORGANIZATION_ENTITY_LABEL,
                    schema="Organization",
                    count="2,164 万",
                    ratio=17,
                    tone="#12b76a",
                ),
                StructureItem(
                    label="项目 / 专利",
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
                    label="发表 / 引用 / 成果",
                    schema="PUBLISH / CITES / OUTPUT",
                    count="2.04 亿",
                    ratio=32,
                    tone="#165dff",
                ),
                StructureItem(
                    label="任职 / 就读 / 作者单位",
                    schema="WORKS_AT / STUDY_AT",
                    count="1.28 亿",
                    ratio=20,
                    tone="#2e90fa",
                ),
                StructureItem(
                    label="项目 / 专利参与",
                    schema="LEAD_PROJECT / INVENT_PATENT",
                    count="1.16 亿",
                    ratio=18,
                    tone="#06aed4",
                ),
                StructureItem(
                    label="企业 / 产品 / 事件",
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
