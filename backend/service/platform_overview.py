"""平台首页总览服务：图资产实时统计 + 尚未接入模块的显式降级数据。"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from biz.schemas.platform_overview import (
    AssetChangeRow,
    AssetOverviewGroup,
    LatestChange,
    ManagementRisk,
    PlatformOverviewData,
    StructureItem,
)
from infra.graph_db import get_trs_graph_client

EXPERT_ENTITY_LABEL = '专家 / 人才'
ORGANIZATION_ENTITY_LABEL = '机构 / 企业'

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class GraphStatsSnapshot:
    total_nodes: int
    total_edges: int
    nodes: dict[str, int]
    edges: dict[str, int]


class GraphStatsProvider(Protocol):
    def get_stats(self) -> GraphStatsSnapshot: ...


class TRSGraphStatsProvider:
    def get_stats(self) -> GraphStatsSnapshot:
        client = get_trs_graph_client()
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
            logger.warning("SHOW STATS 失败，回退到逐 label/edge_type 计数（会慢）: %s", exc)
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


def _ratios(values: list[int]) -> list[int]:
    total = sum(values)
    if total <= 0:
        return [0 for _ in values]
    result = [round(value * 100 / total) for value in values]
    result[max(range(len(values)), key=values.__getitem__)] += 100 - sum(result)
    return result


def _entity_bucket(name: str) -> int:
    normalized = name.upper()
    if any(token in normalized for token in ("EXPERT", "SCHOLAR", "PERSON", "TALENT")):
        return 0
    if any(token in normalized for token in ("PAPER", "JOURNAL", "ARTICLE", "THESIS")):
        return 1
    if any(
        token in normalized
        for token in ("ORGANIZATION", "ORGANISATION", "ENTERPRISE", "COMPANY", "INSTITUTE")
    ):
        return 2
    if any(token in normalized for token in ("PROJECT", "PATENT")):
        return 3
    return 4


def _relation_bucket(name: str) -> int:
    normalized = name.upper()
    if any(token in normalized for token in ("PUBLISH", "CITE", "AUTHOR", "OUTPUT")):
        return 0
    if any(token in normalized for token in ("WORK", "STUDY", "AFFILIAT", "EMPLOY")):
        return 1
    if any(token in normalized for token in ("PROJECT", "PATENT", "INVENT")):
        return 2
    if any(token in normalized for token in ("PRODUCT", "EVENT", "ENTERPRISE", "COMPANY")):
        return 3
    return 4


def _build_structure(
    counts: dict[str, int],
    *,
    entity: bool,
) -> list[StructureItem]:
    buckets = [0, 0, 0, 0, 0]
    classifier = _entity_bucket if entity else _relation_bucket
    for name, count in counts.items():
        buckets[classifier(name)] += max(0, int(count))
    ratios = _ratios(buckets)
    definitions = (
        [
            (EXPERT_ENTITY_LABEL, "Expert / Scholar", "#2e90fa"),
            ("论文成果", "Paper / Journal", "#7a5af8"),
            (ORGANIZATION_ENTITY_LABEL, "Organization / Enterprise", "#12b76a"),
            ("项目 / 专利", "Project / Patent", "#f79009"),
            ("其他实体", "Other", "#98a2b3"),
        ]
        if entity
        else [
            ("发表 / 引用 / 成果", "PUBLISH / CITES / OUTPUT", "#165dff"),
            ("任职 / 就读 / 作者单位", "WORKS_AT / STUDY_AT", "#2e90fa"),
            ("项目 / 专利参与", "LEAD_PROJECT / INVENT_PATENT", "#06aed4"),
            ("企业 / 产品 / 事件", "HAS_PRODUCT / HAS_EVENT", "#7a5af8"),
            ("其他关系", "Other", "#98a2b3"),
        ]
    )
    return [
        StructureItem(
            label=label,
            schema=schema,
            count=_format_count(buckets[index]),
            ratio=ratios[index],
            tone=tone,
        )
        for index, (label, schema, tone) in enumerate(definitions)
    ]


class PlatformOverviewService:
    """优先读取真实图统计；无法读取时保留可演示、可识别的降级结果。"""

    def __init__(self, stats_provider: GraphStatsProvider | None = None) -> None:
        self._stats_provider = stats_provider or TRSGraphStatsProvider()
        self._cache_seconds = int(os.getenv("PLATFORM_OVERVIEW_CACHE_SECONDS", "60"))
        self._cached: tuple[float, PlatformOverviewData] | None = None

    def get_overview(self) -> PlatformOverviewData:
        now = time.monotonic()
        if self._cached is not None and self._cached[0] > now:
            return self._cached[1]

        fallback = self._get_fallback_overview()
        try:
            stats = self._stats_provider.get_stats()
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
            groups = [
                AssetOverviewGroup(
                    key="entity",
                    title="实体数据",
                    total=_format_count(stats.total_nodes),
                    total_label="实体总量",
                    added="--",
                    added_label="今日新增（任务中心待接入）",
                ),
                AssetOverviewGroup(
                    key="relation",
                    title="关系数据",
                    total=_format_count(stats.total_edges),
                    total_label="关系总量",
                    added="--",
                    added_label="今日新增（任务中心待接入）",
                ),
                AssetOverviewGroup(
                    key="property",
                    title="属性值数据",
                    total="--",
                    total_label="属性值总量（统计接口待接入）",
                    added="--",
                    added_label="今日新增及更新（任务中心待接入）",
                ),
            ]
            result = fallback.model_copy(
                update={
                    "platform_status": "图数据库连接正常",
                    "updated_at": datetime.now().strftime("%H:%M"),
                    "asset_overview_groups": groups,
                    "entity_structure": _build_structure(stats.nodes, entity=True),
                    "relation_structure": _build_structure(stats.edges, entity=False),
                    "data_mode": "partial",
                    "data_sources": {
                        "graphAssets": "trsgraph-live",
                        "todayChanges": "demo-fallback",
                        "managementRisks": "demo-fallback",
                    },
                    "warnings": [
                        "实体与关系统计来自图数据库实时接口。",
                        "属性值、今日变化和管理风险等待任务中心接口接入。",
                    ],
                }
            )
        self._cached = (now + self._cache_seconds, result)
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
                    added="+1,183.6 万",
                    added_label="今日新增",
                ),
                AssetOverviewGroup(
                    key="relation",
                    title="关系数据",
                    total="6.42 亿",
                    total_label="关系总量",
                    added="+2,040 万",
                    added_label="今日新增",
                ),
                AssetOverviewGroup(
                    key="property",
                    title="属性值数据",
                    total="18.76 亿",
                    total_label="属性值总量",
                    added="+3,264 万",
                    added_label="今日新增及更新",
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
