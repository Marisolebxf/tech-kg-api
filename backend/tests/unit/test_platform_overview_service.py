import time

import pytest

from service.platform_overview import (
    DayChangesSnapshot,
    GraphStatsSnapshot,
    PlatformOverviewService,
    TRSGraphStatsProvider,
    enrich_day_rows_with_graph,
    parse_execution_records,
)


@pytest.fixture(autouse=True)
def _clear_no_index_cache():
    # 无索引负缓存是模块级 TTL 状态：enrich 用例会登记 (dev2, lookup, tag.prop)，
    # 不清理会串到后续用例——「二次反查跳过 LOOKUP」与「LOOKUP 必发」的断言互相打架。
    client_mod = __import__("infra.graph_db.client", fromlist=["_no_index_cache"])
    client_mod._no_index_cache.clear()
    yield
    client_mod._no_index_cache.clear()


class FakeStatsProvider:
    def __init__(self) -> None:
        self.calls = 0
        self.spaces: list[str | None] = []

    def get_stats(self, space: str | None = None) -> GraphStatsSnapshot:
        self.calls += 1
        self.spaces.append(space)
        return GraphStatsSnapshot(
            total_nodes=128_000_000,
            total_edges=642_000_000,
            nodes={
                "Expert": 42_000_000,
                "Paper": 29_000_000,
                "Organization": 21_000_000,
                "Project": 14_000_000,
                "Topic": 22_000_000,
            },
            edges={
                "PUBLISH": 204_000_000,
                "WORKS_AT": 128_000_000,
                "INVENT_PATENT": 116_000_000,
                "HAS_PRODUCT": 92_000_000,
                "RELATED_TO": 102_000_000,
            },
        )


class FailingStatsProvider:
    def get_stats(self, space: str | None = None) -> GraphStatsSnapshot:
        raise RuntimeError("graph unavailable")


class FakeChangesProvider:
    """控制库统计日（昨日）增量替身：固定返回可断言的写图计数与明细行。"""

    def __init__(self, snapshot: DayChangesSnapshot | None = None) -> None:
        self.snapshot = snapshot or DayChangesSnapshot()
        self.spaces: list[str | None] = []

    def get_day_changes(self, space: str | None = None) -> DayChangesSnapshot:
        self.spaces.append(space)
        return self.snapshot

    def running_count(self, space: str | None = None) -> int:
        return self.snapshot.running_count


class FailingChangesProvider:
    def get_day_changes(self, space: str | None = None) -> DayChangesSnapshot:
        raise RuntimeError("control db unavailable")

    def running_count(self, space: str | None = None) -> int:
        raise RuntimeError("control db unavailable")


def test_overview_uses_live_graph_totals_and_explicit_partial_mode() -> None:
    provider = FakeStatsProvider()
    service = PlatformOverviewService(stats_provider=provider)

    result = service.get_overview()

    assert result.platform_status == "图数据库连接正常"
    assert result.data_mode == "partial"
    assert result.data_sources["graphAssets"] == "trsgraph-live"
    # 资产卡只有实体/关系两类（属性值占位卡已随演示数据清理删除）
    assert [group.key for group in result.asset_overview_groups] == ["entity", "relation"]
    assert result.asset_overview_groups[0].total == "1.28 亿"
    assert result.asset_overview_groups[1].total == "6.42 亿"
    assert sum(item.ratio for item in result.entity_structure) == 100
    assert sum(item.ratio for item in result.relation_structure) == 100

    # 同一服务实例在缓存时间内不会重复扫描全部标签和边类型。
    assert service.get_overview() is result
    assert provider.calls == 1


def test_overview_total_is_deduped_with_multi_tag_vertices() -> None:
    """多标签顶点时资产卡中心仍是去重真实体数，不跟分段虚高。

    dev2 实测（2026-09-23）：SHOW STATS 的 Space/vertices=29.48 万（去重 vid），
    Σ每标签计数=52.53 万（同一机构 vid 同挂 organization_base+Organization 双标签
    被计两次）。中心用去重数——实体总量就是实体数；环形图分段按标签计数无法
    去重，分段合计大于中心数属口径差异，不是数据错误。"""
    stats = GraphStatsSnapshot(
        total_nodes=294_800,
        total_edges=544_600,
        nodes={
            "Person": 32_000,
            "Organization": 10_000,
            "organization_base": 230_700,
            "Keyword": 29_988,
            "Paper": 17_600,
        },
        edges={"EMPLOYED_BY": 380_000, "AUTHOR": 120_000, "RELATED_TO": 44_600},
    )

    class MultiTagStatsProvider:
        def get_stats(self, space: str | None = None) -> GraphStatsSnapshot:
            return stats

    result = PlatformOverviewService(
        stats_provider=MultiTagStatsProvider(), changes_provider=FakeChangesProvider()
    ).get_overview()

    # 中心总量 = 去重 vid / 边总数（真实体数），Σ标签计数 32.03 万不冒充实体总量
    assert result.asset_overview_groups[0].total == "29.48 万"  # 294,800 ≠ Σ标签 32.03 万
    assert result.asset_overview_groups[1].total == "54.46 万"  # 544,600
    # 分段仍按标签计数：实体分段合计 32.03 万 > 卡片 29.48 万（多标签顶点重复计入）
    assert sum(item.ratio for item in result.entity_structure) == 100


def test_structure_orders_per_schema_top4_then_other() -> None:
    """构成图展示序（2026-09-23 用户口径）：按单个 Schema 出分段、数量降序取前 4，
    其余并入「其他实体/其他关系」固定第 5 位；零计数 Schema 不出段——任何图空间
    都只显示真实存在的分类，不再有固定空桶。目录中文名查不到时回退图内原名。"""
    from service.platform_overview import _build_structure

    # 6 个非零 Schema 降序取前 4；Event+News 并入「其他实体」；Organization 零计数不列
    entity = _build_structure(
        {
            "Keyword": 50,
            "Person": 30,
            "Paper": 15,
            "Project": 5,
            "Event": 4,
            "News": 3,
            "Organization": 0,
        },
        entity=True,
    )
    assert [item.label for item in entity] == ["Keyword", "Person", "Paper", "Project", "其他实体"]
    assert [item.ratio for item in entity] == [46, 28, 14, 5, 7]
    other = entity[4]
    assert other.count == "7"  # Event 4 + News 3
    assert [(m.name, m.count) for m in other.members] == [("Event", 4), ("News", 3)]
    # 只有「其他」段带 is_other 标记（前端只对它开悬浮浮窗）
    assert [item.is_other for item in entity] == [False, False, False, False, True]

    # 非零分类 ≤ 4 时不造「其他」段（不出现死数据）
    relation = _build_structure(
        {"RELATED_TO": 40, "CITES": 35, "EXECUTIVE_OF": 20, "INVOLVED_IN": 5}, entity=False
    )
    assert [item.label for item in relation] == [
        "RELATED_TO",
        "CITES",
        "EXECUTIVE_OF",
        "INVOLVED_IN",
    ]
    assert [item.ratio for item in relation] == [40, 35, 20, 5]
    assert [item.is_other for item in relation] == [False, False, False, False]


def test_structure_uses_schema_catalog_chinese_labels() -> None:
    """展示名取 Schema 目录中文名（空间行优先、跨空间兜底）；重名时退图内原名防撞 key。"""
    from service.platform_overview import _build_structure

    entity = _build_structure(
        {"Keyword": 50, "Person": 30, "Paper": 15, "Project": 5, "Event": 4},
        entity=True,
        labels={
            "Keyword": "技术主题",
            "Person": "科技专家",
            "Paper": "论文",
            "Project": "项目",
            "Event": "事件",
        },
    )
    assert [item.label for item in entity] == ["技术主题", "科技专家", "论文", "项目", "其他实体"]
    # 单 Schema 段：schema 字段=图内原名；成员展示名取目录中文名（悬浮浮窗列它）
    assert entity[0].schema_name == "Keyword"
    assert [(m.name, m.count) for m in entity[0].members] == [("技术主题", 50)]
    # 「其他」段：schema 摘要与成员都显示目录中文名
    assert entity[4].schema_name == "事件"
    assert [(m.name, m.count) for m in entity[4].members] == [("事件", 4)]

    # 两个 Schema 的目录中文名撞车：分段展示名退图内原名保证唯一；单成员段内无撞车
    dup = _build_structure({"A": 10, "B": 5}, entity=True, labels={"A": "论文", "B": "论文"})
    assert [item.label for item in dup] == ["论文", "B"]
    assert [(m.name, m.count) for m in dup[1].members] == [("论文", 5)]
    # 「其他」段成员中文名互撞时后者退图内原名，保证 v-for key 唯一
    clash = _build_structure(
        {"A": 10, "Q": 9, "R": 8, "S": 7, "B": 5, "C": 1},
        entity=True,
        labels={"B": "报告", "C": "报告"},
    )
    assert clash[4].label == "其他实体"
    assert [(m.name, m.count) for m in clash[4].members] == [("报告", 5), ("C", 1)]


def test_overview_builds_structure_with_catalog_labels_for_space(monkeypatch) -> None:
    """装配处把当前图空间传给目录中文名查询（空间行优先），构成图分段用它做展示名。"""
    import service.platform_overview as overview

    fetched: list[tuple[str | None, str]] = []

    def _fake_labels(space, kind):
        fetched.append((space, kind))
        if kind == "entity":
            return {"Keyword": "技术主题", "Person": "科技专家", "Paper": "论文"}
        return {"RELATED_TO": "泛化关联"}

    monkeypatch.setattr(overview, "_schema_labels_by_name", _fake_labels)
    stats = GraphStatsSnapshot(
        total_nodes=100,
        total_edges=100,
        nodes={"Keyword": 50, "Person": 30, "Paper": 20},
        edges={"RELATED_TO": 9},
    )

    class LabeledStatsProvider:
        def get_stats(self, space: str | None = None) -> GraphStatsSnapshot:
            return stats

    result = PlatformOverviewService(
        stats_provider=LabeledStatsProvider(), changes_provider=FakeChangesProvider()
    ).get_overview(space="dev2")

    assert ("dev2", "entity") in fetched
    assert ("dev2", "relation") in fetched
    assert [item.label for item in result.entity_structure] == ["技术主题", "科技专家", "论文"]
    assert [item.label for item in result.relation_structure] == ["泛化关联"]


def test_structure_segments_are_per_schema_with_members() -> None:
    """每个 Schema 一段：schema 字段=图内原名、members 只含自己；零计数不出段，
    并列计数按名字稳定排序（AUTHORED_BY 先于 PUBLISH）。"""
    from service.platform_overview import _build_structure

    entity = _build_structure(
        {"Paper": 50, "Report": 30, "Journal": 15, "Publication": 5, "Paper1": 0}, entity=True
    )
    # 零计数 Paper1 不出段；4 个非零 Schema 恰好用满前 4，无「其他」段
    assert [item.label for item in entity] == ["Paper", "Report", "Journal", "Publication"]
    assert [(m.name, m.count) for m in entity[0].members] == [("Paper", 50)]

    relation = _build_structure(
        {"CITES": 60, "COAUTHOR_WITH": 30, "AUTHORED_BY": 5, "PUBLISH": 5, "OUTPUT_OF": 0},
        entity=False,
    )
    assert [item.label for item in relation] == ["CITES", "COAUTHOR_WITH", "AUTHORED_BY", "PUBLISH"]


def test_overview_cache_is_isolated_per_space() -> None:
    """总览随全局图空间查询（00918）：不同空间各自缓存、不串数据。"""
    provider = FakeStatsProvider()
    service = PlatformOverviewService(stats_provider=provider)

    first = service.get_overview("gaoxing_test")
    assert provider.spaces == ["gaoxing_test"]

    # 同空间命中缓存；切空间重新读该空间统计
    assert service.get_overview("gaoxing_test") is first
    service.get_overview("techkg")
    assert provider.spaces == ["gaoxing_test", "techkg"]

    # 缺省空间（env 默认）与显式空间互不干扰
    service.get_overview()
    assert provider.spaces == ["gaoxing_test", "techkg", None]


def test_overview_degrades_honestly_when_graph_is_unavailable() -> None:
    """图统计不可用：全部数据位显式占位/空表，绝不回填演示数据；运行数仍实查控制库。"""
    changes = FakeChangesProvider(DayChangesSnapshot(running_count=4))
    result = PlatformOverviewService(
        stats_provider=FailingStatsProvider(), changes_provider=changes
    ).get_overview()

    assert result.data_mode == "mock"
    assert result.data_sources["graphAssets"] == "unavailable"
    assert result.data_sources["dayChanges"] == "unavailable"
    assert "降级" in result.platform_status
    assert result.warnings
    # 卡片占位、构成图与明细空表——不再有 1.28 亿/6.42 亿 演示总量与演示分段
    assert [group.total for group in result.asset_overview_groups] == ["--", "--"]
    assert result.entity_structure == []
    assert result.relation_structure == []
    assert result.asset_change_rows == {"entity": [], "relation": []}
    assert result.asset_change_totals == {"entity": 0, "relation": 0}
    # 运行中执行数与图无关：仍按控制库实时计数（不再是演示常数 2）
    assert result.pending_batch_count == 4


def test_stats_provider_prefers_cached_snapshot_when_show_stats_fails() -> None:
    """SHOW STATS 报错（如 stats 任务卡死）时先吃 300s 快照缓存，不逐项 REST 计数。"""

    class BrokenShowStatsClient:
        def execute_query(self, query: str):
            raise RuntimeError("stats job running")

        def stats_snapshot(self):
            return {
                "tags": {"Expert": 3, "Paper": 4},
                "edges": {"PUBLISH": 5},
                "total_nodes": 7,
                "total_edges": 5,
            }

    snapshot = TRSGraphStatsProvider()._stats_via_client(BrokenShowStatsClient())
    assert snapshot.total_nodes == 7
    assert snapshot.total_edges == 5
    assert snapshot.nodes == {"Expert": 3, "Paper": 4}
    assert snapshot.edges == {"PUBLISH": 5}


def test_stats_provider_rest_fallback_when_cache_missing() -> None:
    """缓存也没有才回退 REST 逐项计数（原兜底行为不变）。"""

    class NoStatsClient:
        def execute_query(self, query: str):
            raise RuntimeError("stats job running")

        def stats_snapshot(self):
            raise RuntimeError("no cache")

        def labels(self):
            return ["Expert"]

        def edge_types(self):
            return ["PUBLISH"]

        def node_count(self, label=None):
            return 3

        def edge_count(self, edge_type=None):
            return 5

    snapshot = TRSGraphStatsProvider()._stats_via_client(NoStatsClient())
    assert snapshot.total_nodes == 3
    assert snapshot.total_edges == 5
    assert snapshot.nodes == {"Expert": 3}
    assert snapshot.edges == {"PUBLISH": 5}


def test_overview_uses_control_plane_day_changes() -> None:
    """昨日新增/运行中执行数来自工作流控制库，明细行替换演示数据。"""
    from biz.schemas.platform_overview import AssetChangeRow

    entity_rows = [
        AssetChangeRow(
            type="审测挂件",
            object="审测挂件 · 61 条",
            change="新增 review-widget-64d0d5",
            source="techkg_e2e_liz.review_widgets",
            time="10:30:00",
        )
    ]
    changes = FakeChangesProvider(
        DayChangesSnapshot(
            entity_added=61,
            relation_added=7,
            running_count=3,
            entity_rows=entity_rows,
            relation_rows=[],
        )
    )
    service = PlatformOverviewService(stats_provider=FakeStatsProvider(), changes_provider=changes)

    result = service.get_overview("dev2")

    # 控制库查询随全局图空间选择器传递（与图统计同空间口径）
    assert changes.spaces == ["dev2"]
    entity = result.asset_overview_groups[0]
    assert entity.added == "+61"
    assert entity.added_label == "昨日新增"
    assert result.asset_overview_groups[1].added == "+7"
    assert result.pending_batch_count == 3
    assert result.data_sources["dayChanges"] == "workflow-control-live"
    assert result.asset_change_rows["entity"] == entity_rows
    assert result.asset_change_rows["relation"] == []
    # 数值合计与徽标同源（Σwritten），与明细行数解耦：抽屉用它展示
    # 「共 N 条 · 展示前 n 条」，行数受单执行 50 条上限截断
    assert result.asset_change_totals == {"entity": 61, "relation": 7}
    # 经响应模型真实序列化（驼峰别名字段已声明，不是 model_copy 透传的裸属性）
    import json

    serialized = json.loads(result.model_dump_json(by_alias=True))
    assert serialized["assetChangeTotals"] == {"entity": 61, "relation": 7}
    assert len(result.asset_change_rows["entity"]) == 1
    assert len(result.asset_change_rows["relation"]) == 0
    # 属性值占位卡与演示行已删：明细只剩实体/关系两类
    assert set(result.asset_change_rows) == {"entity", "relation"}


def test_overview_badge_counts_graph_rows_when_lookup_exact() -> None:
    """徽标与抽屉同数：图反查逐对象成功（exact）时徽标/合计=明细行数——控制库
    written 只数 COMPLETED/ABNORMAL 的抽取，时间窗反查圈住的是图内昨日真实
    写入对象（ewrdf 实测 written 合计 +4 vs 图内 13 条）；反查降级才回退
    written 合计。"""
    from biz.schemas.platform_overview import AssetChangeRow

    entity_rows = [
        AssetChangeRow(
            type="专家",
            object=f"专家{index:02d}",
            change="新增 expert",
            source="ewrdf_test.t_expert",
            time="10-10 04:20:02",
        )
        for index in range(1, 14)
    ]
    result = PlatformOverviewService(
        stats_provider=FakeStatsProvider(),
        changes_provider=FakeChangesProvider(
            DayChangesSnapshot(
                entity_added=4,
                relation_added=0,
                entity_rows_exact=True,
                entity_rows=entity_rows,
            )
        ),
    ).get_overview("ewrdf")

    assert result.asset_overview_groups[0].added == "+13"  # 与抽屉 13 行同数
    assert result.asset_change_totals == {"entity": 13, "relation": 0}

    degraded = PlatformOverviewService(
        stats_provider=FakeStatsProvider(),
        changes_provider=FakeChangesProvider(
            DayChangesSnapshot(entity_added=4, relation_added=0, entity_rows=entity_rows)
        ),
    ).get_overview("ewrdf")
    assert degraded.asset_overview_groups[0].added == "+4"  # exact=False 回退 written 合计
    assert degraded.asset_change_totals == {"entity": 4, "relation": 0}


def test_overview_running_count_is_live_not_frozen_in_day_snapshot() -> None:
    """「N 个执行运行中」实时短查：日快照缓存一整天，快照里的 running_count
    不能把运行数冻住——面板以装配时的实时计数为准；控制库不可读回退快照值。"""

    class _LiveRunningProvider(FakeChangesProvider):
        def running_count(self, space: str | None = None) -> int:
            return 5

    result = PlatformOverviewService(
        stats_provider=FakeStatsProvider(),
        changes_provider=_LiveRunningProvider(DayChangesSnapshot(entity_added=2, running_count=3)),
    ).get_overview("dev2")
    # 实时计数 5 覆盖快照冻结值 3
    assert result.pending_batch_count == 5

    class _BrokenRunningProvider(FakeChangesProvider):
        def running_count(self, space: str | None = None) -> int:
            raise RuntimeError("control db down")

    fallback = PlatformOverviewService(
        stats_provider=FakeStatsProvider(),
        changes_provider=_BrokenRunningProvider(DayChangesSnapshot(running_count=3)),
    ).get_overview("dev2")
    # 实时短查失败：回退快照值，不显示 0 假象
    assert fallback.pending_batch_count == 3


def test_day_changes_provider_caches_closed_window_until_day_rolls() -> None:
    """昨日是闭合窗口：同统计日同空间只冷算一次（秒级图反查每 worker 每天
    最多付一次），跨日翻页后重算并整体作废旧统计日缓存。"""
    from service.platform_overview import DayChangesSnapshot, WorkflowControlDayChangesProvider

    days = ["2026-09-23", "2026-09-23", "2026-09-23", "2026-09-24"]
    loads: list[tuple[str, str | None]] = []

    class _FrozenProvider(WorkflowControlDayChangesProvider):
        def _current_day(self) -> str:
            return days.pop(0)

        def _load(self, day: str, space: str | None) -> DayChangesSnapshot:
            loads.append((day, space))
            return DayChangesSnapshot(entity_added=len(loads))

    provider = _FrozenProvider()
    first = provider.get_day_changes("dev2")
    assert provider.get_day_changes("dev2") is first  # 同日同空间命中缓存，不重算
    provider.get_day_changes("techkg")  # 同日另一空间各自冷算
    assert loads == [("2026-09-23", "dev2"), ("2026-09-23", "techkg")]
    provider.get_day_changes("dev2")  # 翻日后旧缓存作废、重新冷算
    assert loads[-1] == ("2026-09-24", "dev2")


def test_overview_shows_placeholder_when_no_day_changes() -> None:
    """控制库可读但统计日写图为 0：显示 -- 而非 +0，数据源仍标记真实。"""
    result = PlatformOverviewService(
        stats_provider=FakeStatsProvider(), changes_provider=FakeChangesProvider()
    ).get_overview()

    assert result.asset_overview_groups[0].added == "--"
    assert result.asset_overview_groups[0].added_label == "昨日新增"
    assert result.asset_overview_groups[1].added == "--"
    assert result.asset_overview_groups[1].added_label == "昨日新增"
    assert result.data_sources["dayChanges"] == "workflow-control-live"


def test_overview_tolerates_control_plane_failure() -> None:
    """控制库不可读时占位 + 警告，绝不回填虚构演示行。"""
    result = PlatformOverviewService(
        stats_provider=FakeStatsProvider(), changes_provider=FailingChangesProvider()
    ).get_overview()

    assert result.asset_overview_groups[0].added == "--"
    assert result.asset_overview_groups[0].added_label == "昨日新增"
    assert result.asset_overview_groups[1].added == "--"
    assert result.asset_change_rows["entity"] == []
    assert result.asset_change_rows["relation"] == []
    assert result.pending_batch_count == 0
    assert result.data_sources["dayChanges"] == "unavailable"
    assert any("控制库不可用" in warning for warning in result.warnings)


def _execution_record(
    *,
    status: str = "COMPLETED",
    completed_at: str = "2026-09-22 10:30:00",
    kind: str = "entity",
    written: int = 5,
    payload_space: str | None = "dev2",
    payload_space_key: str = "graph_space",
    schema_label: str = "审测挂件",
    schema_key: str = "review-widget-64d0d5",
    table: str = "techkg_e2e_liz.review_widgets",
    trigger: str = "SCHEDULE",
    sources: list[dict] | None = None,
) -> str:
    import json

    record: dict = {
        "status": status,
        "completedAt": completed_at,
        "triggerSource": trigger,
        "payload": {payload_space_key: payload_space} if payload_space else {},
        "output": {
            "kind": kind,
            "schemaLabel": schema_label,
            "schemaKey": schema_key,
            "sources": sources if sources is not None else [{"table": table, "written": written}],
        },
    }
    return json.dumps(record, ensure_ascii=False)


def test_parse_execution_records_aggregates_day_by_kind_and_space() -> None:
    snapshot = parse_execution_records(
        [
            _execution_record(written=5, completed_at="2026-09-22 10:30:00"),
            _execution_record(
                kind="relation",
                written=2,
                trigger="RERUN",
                completed_at="2026-09-22 11:00:00",
            ),
            # 前一日完成：不计入统计日（北京口径：UTC 16:00 后完成=北京次日，
            # 用 05:00 保证两套日历都属 09-21）
            _execution_record(written=99, completed_at="2026-09-21 05:00:00"),
            # 其他空间：不计入
            _execution_record(payload_space="other_space"),
            # 写入 0：不产生明细行也不计数
            _execution_record(written=0),
            # 运行中：计入 running_count
            _execution_record(status="RUNNING", completed_at=""),
            # 坏数据：跳过不炸
            "not-a-json",
            "[]",
        ],
        day="2026-09-22",
        target_space="dev2",
        default_space="dev2",
    )

    assert snapshot.entity_added == 5
    assert snapshot.relation_added == 2
    assert snapshot.running_count == 1
    assert len(snapshot.entity_rows) == 1
    row = snapshot.entity_rows[0]
    assert row.type == "审测挂件"
    assert row.object == "审测挂件 · 5 条"
    assert row.change == "新增 review-widget-64d0d5"
    assert row.source == "techkg_e2e_liz.review_widgets"
    assert row.time == "09-22 18:30:00"  # 完成时刻按北京展示（UTC+8），带月日（跨天歧义）
    assert len(snapshot.relation_rows) == 1
    assert snapshot.relation_rows[0].source == "techkg_e2e_liz.review_widgets"


def test_parse_execution_records_space_key_variants_and_default_bucket() -> None:
    # 手动/重跑执行的 payload 记 graphSpace（驼峰），同样按空间过滤
    assert (
        parse_execution_records(
            [_execution_record(payload_space_key="graphSpace")],
            day="2026-09-22",
            target_space="dev2",
            default_space="dev2",
        ).entity_added
        == 5
    )
    # 未记录空间的历史执行归属默认空间；查询非默认空间时排除
    assert (
        parse_execution_records(
            [_execution_record(payload_space=None)],
            day="2026-09-22",
            target_space="dev2",
            default_space="dev2",
        ).entity_added
        == 5
    )
    assert (
        parse_execution_records(
            [_execution_record(payload_space=None)],
            day="2026-09-22",
            target_space="gaoxing_test",
            default_space="dev2",
        ).entity_added
        == 0
    )


def test_parse_execution_records_sorts_rows_by_completion_desc() -> None:
    """北京日窗口：完成时刻（UTC）折算北京后归属统计日，展示也按北京时刻。"""
    snapshot = parse_execution_records(
        [
            _execution_record(written=1, completed_at="2026-09-22 09:00:00"),  # 北京 17:00
            _execution_record(written=2, completed_at="2026-09-22 07:00:00"),  # 北京 15:00
            # UTC 16:00 后完成 = 北京次日，不属统计日 2026-09-22
            _execution_record(written=99, completed_at="2026-09-22 18:00:00"),
        ],
        day="2026-09-22",
        target_space="dev2",
        default_space="dev2",
    )

    assert [row.time for row in snapshot.entity_rows] == ["09-22 17:00:00", "09-22 15:00:00"]


def test_parse_execution_records_splits_rows_by_source() -> None:
    """一次执行绑定多个来源表时逐表拆行，written=0 的表不出行也不计数。"""
    snapshot = parse_execution_records(
        [
            _execution_record(
                written=5,
                completed_at="2026-09-22 10:30:00",
                sources=[
                    {"table": "techkg_e2e_liz.review_widgets", "written": 3},
                    {"table": "techkg_e2e_liz.review_edges", "written": 2},
                    {"table": "techkg_e2e_liz.empty_source", "written": 0},
                ],
            )
        ],
        day="2026-09-22",
        target_space="dev2",
        default_space="dev2",
    )

    assert snapshot.entity_added == 5
    assert [(row.source, row.object) for row in snapshot.entity_rows] == [
        ("techkg_e2e_liz.review_widgets", "审测挂件 · 3 条"),
        ("techkg_e2e_liz.review_edges", "审测挂件 · 2 条"),
    ]
    # 变更内容与识别时间在同一执行的各行保持一致
    assert {row.change for row in snapshot.entity_rows} == {"新增 review-widget-64d0d5"}
    assert {row.time for row in snapshot.entity_rows} == {"09-22 18:30:00"}


def test_parse_execution_records_change_falls_back_without_schema_key() -> None:
    """schemaKey 缺失时变更内容回退 schemaLabel，再缺回退实体/关系。"""
    snapshot = parse_execution_records(
        [
            _execution_record(
                schema_key="",
                completed_at="2026-09-22 10:30:00",
                sources=[{"table": "techkg_e2e_liz.t1", "written": 1}],
            ),
            _execution_record(
                schema_key="",
                schema_label="",
                completed_at="2026-09-22 11:00:00",
                sources=[{"table": "techkg_e2e_liz.t2", "written": 1}],
            ),
        ],
        day="2026-09-22",
        target_space="dev2",
        default_space="dev2",
    )

    # 倒序排列：11:00（schemaKey/schemaLabel 均缺）在前，10:30（仅缺 schemaKey）在后
    assert snapshot.entity_rows[0].change == "新增 实体"
    assert snapshot.entity_rows[0].type == "实体 Schema"
    assert snapshot.entity_rows[1].change == "新增 审测挂件"


class _GraphResult:
    def __init__(self, records: list[dict]) -> None:
        self.records = records


class _ScriptedGraphClient:
    """按语句片段脚本的假图客户端：命中返回预设 records，预设异常则抛出。"""

    def __init__(self, scripts: list[tuple[str, list[dict] | Exception]]) -> None:
        self._scripts = scripts
        self.queries: list[str] = []
        self.closed = False
        # 反查负缓存按 (space, kind, name) 键控，替身声明与用例一致的空间
        self.space = "dev2"

    def execute_query(self, statement: str, timeout: float | None = None) -> _GraphResult:
        self.queries.append(statement)
        for fragment, response in self._scripts:
            if fragment in statement:
                if isinstance(response, Exception):
                    raise response
                return _GraphResult(response)
        raise AssertionError(f"unexpected query: {statement}")

    def close(self) -> None:
        self.closed = True


def test_parse_execution_records_collects_graph_lookup_descriptors() -> None:
    snapshot = parse_execution_records(
        [
            _execution_record(
                written=3,
                completed_at="2026-09-23 03:41:54",
                sources=[
                    {
                        "table": "techkg_e2e_liz.review_widgets",
                        "written": 3,
                        "watermark": "2026-09-23 03:41:50",
                        "startWatermark": "2026-09-23 03:00:24",
                    }
                ],
            ),
            _execution_record(
                kind="relation",
                schema_key="review-linked-196fe7",
                schema_label="审测关联",
                written=3,
                completed_at="2026-09-23 03:45:52",
            ),
        ],
        day="2026-09-23",
        target_space="dev2",
        default_space="dev2",
    )

    entity_exec = snapshot.entity_executions[0]
    assert entity_exec.schema_key == "review-widget-64d0d5"
    # 反查窗下界优先取开跑前起点水位（startWatermark），而非跑完后的 watermark 终值
    assert entity_exec.window_lo == "2026-09-23 03:00:24"
    assert entity_exec.completed_at == "2026-09-23 03:41:54"
    # 反查窗上界 = 统计日（北京自然日）终点的图侧 UTC 时刻：同日后续执行的改写
    # 不至于把对象挡在窗外；比本执行完成时刻（03:41:54）更宽
    assert entity_exec.window_hi == "2026-09-23 15:59:59"
    assert [row.object for row in entity_exec.fallback_rows] == ["审测挂件 · 3 条"]

    relation_exec = snapshot.relation_executions[0]
    assert relation_exec.schema_key == "review-linked-196fe7"
    # 无水位退统计日起点（北京 09-23 00:00 = UTC 09-22 16:00，图侧时钟）
    assert relation_exec.window_lo == "2026-09-22 16:00:00"
    assert relation_exec.window_hi == "2026-09-23 15:59:59"


def test_enrich_day_rows_lists_graph_objects_per_vertex() -> None:
    """昨日新增明细改逐对象行：实体=Schema 目录中文名+name+source_table，关系=两端实体名。"""
    snapshot = parse_execution_records(
        [
            _execution_record(
                written=3,
                completed_at="2026-09-23 03:41:54",
                sources=[
                    {
                        "table": "techkg_e2e_liz.review_widgets",
                        "written": 3,
                        "watermark": "2026-09-23 03:00:24",
                    }
                ],
            ),
            _execution_record(
                kind="relation",
                schema_key="review-linked-196fe7",
                schema_label="审测关联",
                written=3,
                completed_at="2026-09-23 03:45:52",
                sources=[
                    {
                        "table": "techkg_e2e_liz.review_widgets",
                        "written": 3,
                        "watermark": "2026-09-23 03:44:46",
                    }
                ],
            ),
        ],
        day="2026-09-23",
        target_space="dev2",
        default_space="dev2",
    )
    widget_props = {
        "source_table": "techkg_e2e_liz.review_widgets",
        "update_time": "2026-09-23 03:00:35",
    }
    client = _ScriptedGraphClient(
        [
            (
                "DESC TAG `ReviewWidget`",
                [
                    {"Field": "name", "Type": "string"},
                    {"Field": "source_table", "Type": "string"},
                    {"Field": "update_time", "Type": "string"},
                ],
            ),
            (
                "LOOKUP ON `ReviewWidget`",
                [
                    {"vid": "rwxT-0923-01", "props": {"name": "总览造数-实体01", **widget_props}},
                    {"vid": "rwxT-0923-02", "props": {"name": "总览造数-实体02", **widget_props}},
                ],
            ),
            (
                "DESC EDGE `REVIEW_LINKED`",
                [
                    {"Field": "source_table", "Type": "string"},
                    {"Field": "update_time", "Type": "string"},
                ],
            ),
            ("LOOKUP ON `REVIEW_LINKED`", RuntimeError("There is no index to use at runtime")),
            (
                "GO FROM",
                [
                    {
                        "src": "rwxT-0923-01",
                        "dst": "rwxT-0923-02",
                        "eprops": {
                            "source_table": "techkg_e2e_liz.review_widgets",
                            "update_time": "2026-09-23 03:44:48",
                        },
                    },
                    # BIDIRECT 把同一条边反向再吐一遍：按无序 vid 对去重
                    {
                        "src": "rwxT-0923-02",
                        "dst": "rwxT-0923-01",
                        "eprops": {
                            "source_table": "techkg_e2e_liz.review_widgets",
                            "update_time": "2026-09-23 03:44:48",
                        },
                    },
                    {
                        "src": "rwxT-0923-02",
                        "dst": "rwxT-0923-03",
                        "eprops": {
                            "source_table": "techkg_e2e_liz.review_widgets",
                            "update_time": "2026-09-23 03:44:48",
                        },
                    },
                ],
            ),
            (
                # 端点名批量反查：一次 FETCH 带全部 vid（此前逐 vid 一次）
                "FETCH PROP ON *",
                [
                    {
                        "v": {
                            "id": "rwxT-0923-01",
                            "labels": ["ReviewWidget"],
                            "properties": {"name": "总览造数-实体01"},
                        }
                    },
                    {
                        "v": {
                            "id": "rwxT-0923-02",
                            "labels": ["ReviewWidget"],
                            "properties": {"name": "总览造数-实体02"},
                        }
                    },
                    {
                        "v": {
                            "id": "rwxT-0923-03",
                            "labels": ["ReviewWidget"],
                            "properties": {"name": "总览造数-实体03"},
                        }
                    },
                ],
            ),
        ],
    )

    result = enrich_day_rows_with_graph(
        snapshot,
        "dev2",
        connect_client=lambda space: client,
        schema_names={
            "review-widget-64d0d5": "ReviewWidget",
            "review-linked-196fe7": "REVIEW_LINKED",
        },
        schema_labels={"ReviewWidget": "审测挂件", "REVIEW_LINKED": "审测关联"},
    )

    # 实体行：数据类型=单个 Schema 的目录中文名（与构成图同口径）、对象=name 公共
    # 字段、来源=source_table 公共字段、时间=逐对象写入时间（非执行完成时刻）
    assert [(row.type, row.object, row.change) for row in result.entity_rows] == [
        ("审测挂件", "总览造数-实体01", "新增 审测挂件"),
        ("审测挂件", "总览造数-实体02", "新增 审测挂件"),
    ]
    assert result.entity_rows[0].source == "techkg_e2e_liz.review_widgets"
    assert result.entity_rows[0].time == "09-23 11:00:35"  # 图侧 UTC 时间戳折算北京展示
    # 关系行：边类型无索引 LOOKUP 失败 → GO FROM 当日实体 vid 兜底，无序对去重后 2 条
    assert [(row.type, row.object) for row in result.relation_rows] == [
        ("审测关联", "总览造数-实体01 → 总览造数-实体02"),
        ("审测关联", "总览造数-实体02 → 总览造数-实体03"),
    ]
    assert result.relation_rows[0].change == "新增 审测关联"
    assert result.relation_rows[0].source == "techkg_e2e_liz.review_widgets"
    assert result.relation_rows[0].time == "09-23 11:44:48"
    # 快照保留控制库 written 合计；两类反查均为逐对象行（关系 LOOKUP 无索引走
    # GO FROM 兜底也算枚举完成）——exact 置位后装配层改按行数计徽标
    assert result.entity_added == 3
    assert result.relation_added == 3
    assert result.entity_rows_exact is True
    assert result.relation_rows_exact is True
    # 端点名只发一次批量 FETCH（合并此前逐 vid 的串行调用）
    fetch_calls = [q for q in client.queries if q.startswith("FETCH PROP ON *")]
    assert len(fetch_calls) == 1
    assert client.closed is True


def test_graph_time_prop_skips_datetime_columns() -> None:
    """专利路径：update_time/create_time 是 datetime 型列（字符串边界比较会
    Column type error，datetime("...") 字面量又索引失效查空），反查时间属性
    跳过它们退到 string 型 source_update_time，时间窗 LOOKUP 语句也用它。"""
    snapshot = parse_execution_records(
        [
            _execution_record(
                schema_key="patent-2f0c",
                schema_label="专利",
                written=1,
                completed_at="2026-09-24 02:10:00",
                sources=[
                    {
                        "table": "gkx_element.patent",
                        "written": 1,
                        "watermark": "2026-09-24 02:09:58",
                        "startWatermark": "2026-09-24 02:00:01",
                    }
                ],
            )
        ],
        day="2026-09-24",
        target_space="dev2",
        default_space="dev2",
    )
    client = _ScriptedGraphClient(
        [
            (
                "DESC TAG `Patent`",
                [
                    {"Field": "name", "Type": "string"},
                    {"Field": "update_time", "Type": "datetime"},
                    {"Field": "create_time", "Type": "datetime"},
                    {"Field": "source_update_time", "Type": "string"},
                ],
            ),
            (
                "LOOKUP ON `Patent`",
                [
                    {
                        "vid": "patent_CN-A",
                        "props": {
                            "name": "一种数据处理方法",
                            "source_update_time": "2026-09-24 02:05:30",
                        },
                    }
                ],
            ),
        ]
    )

    result = enrich_day_rows_with_graph(
        snapshot,
        "dev2",
        connect_client=lambda space: client,
        schema_names={"patent-2f0c": "Patent"},
        schema_labels={"Patent": "专利"},
    )

    # 时间窗 LOOKUP 用 string 型 source_update_time（datetime 列不进 WHERE）
    lookup = next(q for q in client.queries if q.startswith("LOOKUP ON `Patent`"))
    assert '`Patent`.`source_update_time` >= "2026-09-24 02:00:01"' in lookup
    assert "`Patent`.`update_time`" not in lookup  # datetime 型 update_time 被跳过
    row = result.entity_rows[0]
    assert (row.type, row.object, row.change) == ("专利", "一种数据处理方法", "新增 专利")
    assert row.time == "09-24 10:05:30"  # 逐对象写入时间取自 source_update_time（北京展示）


def test_vertex_display_name_falls_back_to_title() -> None:
    """Project 无 name/title_zh，展示名退 title；候选序内更靠前的键优先。"""
    from service.platform_overview import _vertex_display_name

    assert (
        _vertex_display_name({"title": "面向城域网的全光交换方法"}, "proj-1")
        == "面向城域网的全光交换方法"
    )
    assert _vertex_display_name({"title_zh": "中文题名", "title": "兜底"}, "p-2") == "中文题名"
    assert _vertex_display_name({}, "vid-x") == "vid-x"


def test_dedupe_rows_keeps_first_occurrence() -> None:
    """当日多次执行触碰同一对象（重跑/补写），明细按 (类型, 对象) 去重保序。"""
    from service.platform_overview import AssetChangeRow, _dedupe_rows

    def row(obj: str, time: str) -> AssetChangeRow:
        return AssetChangeRow(type="专利", object=obj, change="新增 专利", source="-", time=time)

    rows = [row("熔丝元件", "20:01:00"), row("旋转电机", "20:01:01"), row("熔丝元件", "20:05:00")]
    deduped = _dedupe_rows(rows)
    # 第一行（最新执行的口径）保留，后到的同对象行丢弃，顺序不变
    assert [(r.object, r.time) for r in deduped] == [
        ("熔丝元件", "20:01:00"),
        ("旋转电机", "20:01:01"),
    ]


def test_sort_rows_newest_first_keeps_all_rows() -> None:
    """明细统一按识别时间倒序（最新在上、同秒稳定保序），全量保留不截断
    （2026-10-10 用户口径：有多少条数据就展示多少条，不再有展示上限）。"""
    from service.platform_overview import AssetChangeRow, _sort_rows_newest_first

    def row(obj: str, time: str) -> AssetChangeRow:
        return AssetChangeRow(type="专利", object=obj, change="新增 专利", source="-", time=time)

    rows = [
        row("熔丝元件", "09-23 20:01:00"),
        row("旋转电机", "09-23 20:03:00"),
        row("散热基板", "09-23 20:02:00"),
    ]
    assert [r.object for r in _sort_rows_newest_first(rows)] == [
        "旋转电机",
        "散热基板",
        "熔丝元件",
    ]
    # 远超旧上限（50）也全量保留
    many = [row(f"对象{i:03d}", f"09-23 20:00:{i % 60:02d}") for i in range(120)]
    assert len(_sort_rows_newest_first(many)) == 120
    tied = [row("对象B", "09-23 20:03:00"), row("对象A", "09-23 20:03:00")]
    assert [r.object for r in _sort_rows_newest_first(tied)] == ["对象B", "对象A"]


def test_enrich_day_rows_no_object_truncation() -> None:
    """单次执行反查命中超旧对象上限（50）的对象也全量出行：不再截断。"""
    snapshot = parse_execution_records(
        [
            _execution_record(
                written=80,
                completed_at="2026-09-23 03:41:54",
                sources=[
                    {
                        "table": "techkg_e2e_liz.review_widgets",
                        "written": 80,
                        "startWatermark": "2026-09-23 03:00:24",
                    }
                ],
            )
        ],
        day="2026-09-23",
        target_space="dev2",
        default_space="dev2",
    )
    client = _ScriptedGraphClient(
        [
            (
                "DESC TAG `ReviewWidget`",
                [{"Field": "name", "Type": "string"}, {"Field": "update_time", "Type": "string"}],
            ),
            (
                "LOOKUP ON `ReviewWidget`",
                [
                    {
                        "vid": f"rwxT-{i:03d}",
                        "props": {
                            "name": f"总览造数-实体{i:03d}",
                            "source_table": "techkg_e2e_liz.review_widgets",
                            "update_time": "2026-09-23 03:00:35",
                        },
                    }
                    for i in range(80)
                ],
            ),
        ]
    )

    result = enrich_day_rows_with_graph(
        snapshot,
        "dev2",
        connect_client=lambda space: client,
        schema_names={"review-widget-64d0d5": "ReviewWidget"},
        schema_labels={"ReviewWidget": "审测挂件"},
    )

    assert len(result.entity_rows) == 80
    assert {row.object for row in result.entity_rows} == {
        f"总览造数-实体{i:03d}" for i in range(80)
    }


def test_enrich_day_rows_lookup_upper_bound_is_day_end_not_completion() -> None:
    """反查窗上界用统计日终点（图侧 UTC）而非执行完成时刻：同日后续执行对同一批
    对象的 upsert 改写（update_time 晚于本执行完成时刻）仍落在窗内、能出实名行。"""
    snapshot = parse_execution_records(
        [
            _execution_record(
                written=2,
                completed_at="2026-09-23 03:41:54",
                sources=[
                    {
                        "table": "techkg_e2e_liz.review_widgets",
                        "written": 2,
                        "startWatermark": "2026-09-23 03:00:24",
                    }
                ],
            )
        ],
        day="2026-09-23",
        target_space="dev2",
        default_space="dev2",
    )
    client = _ScriptedGraphClient(
        [
            (
                "DESC TAG `ReviewWidget`",
                [{"Field": "name", "Type": "string"}, {"Field": "update_time", "Type": "string"}],
            ),
            (
                "LOOKUP ON `ReviewWidget`",
                [
                    {
                        # 改写时刻 05:14 晚于执行完成 03:41:54，但仍在统计日内
                        "vid": "rwxT-rewrite-01",
                        "props": {
                            "name": "被后续执行改写的对象",
                            "source_table": "techkg_e2e_liz.review_widgets",
                            "update_time": "2026-09-23 05:14:07",
                        },
                    }
                ],
            ),
        ]
    )

    result = enrich_day_rows_with_graph(
        snapshot,
        "dev2",
        connect_client=lambda space: client,
        schema_names={"review-widget-64d0d5": "ReviewWidget"},
        schema_labels={"ReviewWidget": "审测挂件"},
    )

    lookup = next(q for q in client.queries if q.startswith("LOOKUP ON `ReviewWidget`"))
    assert '`ReviewWidget`.`update_time` >= "2026-09-23 03:00:24"' in lookup
    assert '`ReviewWidget`.`update_time` <= "2026-09-23 15:59:59"' in lookup
    assert "03:41:54" not in lookup  # 完成时刻不再作窗上界
    assert [row.object for row in result.entity_rows] == ["被后续执行改写的对象"]


def test_enrich_day_rows_lookup_lower_bound_normalizes_iso_watermark() -> None:
    """反查窗下界水位规范化：payload 里 startWatermark 是 ISO 'T' 分隔而图侧
    update_time 是空格分隔，字符串比较 'T'>' ' 会让同日水位大于全部同日图值——
    当天跑的执行（cron fire/rerun 水位必是当天）反查恒 0 命中、退「Schema · N 条」
    聚合行（dev2 ewrdf 实测「专家 · 2 条」）。须统一成空格分隔再进窗口。"""
    snapshot = parse_execution_records(
        [
            _execution_record(
                written=2,
                completed_at="2026-09-23 03:41:54",
                sources=[
                    {
                        "table": "techkg_e2e_liz.review_widgets",
                        "written": 2,
                        "startWatermark": "2026-09-23T03:00:24",
                    }
                ],
            )
        ],
        day="2026-09-23",
        target_space="dev2",
        default_space="dev2",
    )

    # 解析层：window_lo 已规范成空格分隔
    assert snapshot.entity_executions[0].window_lo == "2026-09-23 03:00:24"

    client = _ScriptedGraphClient(
        [
            (
                "DESC TAG `ReviewWidget`",
                [{"Field": "name", "Type": "string"}, {"Field": "update_time", "Type": "string"}],
            ),
            (
                "LOOKUP ON `ReviewWidget`",
                [
                    {
                        "vid": "rwxT-wm-01",
                        "props": {
                            "name": "同日水位对象",
                            "source_table": "techkg_e2e_liz.review_widgets",
                            "update_time": "2026-09-23 03:20:02",
                        },
                    }
                ],
            ),
        ]
    )

    result = enrich_day_rows_with_graph(
        snapshot,
        "dev2",
        connect_client=lambda space: client,
        schema_names={"review-widget-64d0d5": "ReviewWidget"},
        schema_labels={"ReviewWidget": "审测挂件"},
    )

    lookup = next(q for q in client.queries if q.startswith("LOOKUP ON `ReviewWidget`"))
    # 语句层：下界是空格格式，不得把 'T' 带进比较串
    assert '`ReviewWidget`.`update_time` >= "2026-09-23 03:00:24"' in lookup
    assert "2026-09-23T03:00:24" not in lookup
    assert [row.object for row in result.entity_rows] == ["同日水位对象"]


def test_enrich_day_rows_zero_hit_lookup_lists_no_aggregate_row() -> None:
    """LOOKUP 执行成功但 0 命中（对象被统计日后的执行改写出窗/删除）：如实不出行，
    不再退「Schema · N 条」聚合行——用户口径：不需要聚合，有多少条展示多少条。"""
    snapshot = parse_execution_records(
        [_execution_record(written=2, completed_at="2026-09-23 03:41:54")],
        day="2026-09-23",
        target_space="dev2",
        default_space="dev2",
    )
    client = _ScriptedGraphClient(
        [
            (
                "DESC TAG `ReviewWidget`",
                [{"Field": "name", "Type": "string"}, {"Field": "update_time", "Type": "string"}],
            ),
            ("LOOKUP ON `ReviewWidget`", []),
        ]
    )

    result = enrich_day_rows_with_graph(
        snapshot,
        "dev2",
        connect_client=lambda space: client,
        schema_names={"review-widget-64d0d5": "ReviewWidget"},
        schema_labels={"ReviewWidget": "审测挂件"},
    )

    assert result.entity_rows == []
    # 快照保留 written 合计；exact=True 时装配按行数 0 展示 --（与空抽屉一致）
    assert result.entity_added == 2
    assert result.entity_rows_exact is True


def test_enrich_day_rows_relation_zero_hit_no_aggregate_row() -> None:
    """关系边 LOOKUP 成功 0 命中：同样不退聚合行（枚举完成即如实空）。"""
    snapshot = parse_execution_records(
        [
            _execution_record(
                kind="relation",
                schema_key="review-linked-196fe7",
                schema_label="审测关联",
                written=2,
                completed_at="2026-09-23 03:45:52",
            )
        ],
        day="2026-09-23",
        target_space="dev2",
        default_space="dev2",
    )
    client = _ScriptedGraphClient(
        [
            (
                "DESC EDGE `REVIEW_LINKED`",
                [
                    {"Field": "source_table", "Type": "string"},
                    {"Field": "update_time", "Type": "string"},
                ],
            ),
            ("LOOKUP ON `REVIEW_LINKED`", []),
        ]
    )

    result = enrich_day_rows_with_graph(
        snapshot,
        "dev2",
        connect_client=lambda space: client,
        schema_names={"review-linked-196fe7": "REVIEW_LINKED"},
        schema_labels={"REVIEW_LINKED": "审测关联"},
    )

    assert result.relation_rows == []
    assert result.relation_added == 2
    assert result.relation_rows_exact is True


def test_enrich_day_rows_relation_without_time_prop_keeps_aggregate() -> None:
    """边类型没有任何 string 时间属性：GO BIDIRECT 没法滤时间（会把端点全部历史边
    都算进昨日新增），不做兜底反查，退聚合降级行。"""
    snapshot = parse_execution_records(
        [
            _execution_record(
                kind="relation",
                schema_key="review-linked-196fe7",
                schema_label="审测关联",
                written=2,
                completed_at="2026-09-23 03:45:52",
            )
        ],
        day="2026-09-23",
        target_space="dev2",
        default_space="dev2",
    )
    client = _ScriptedGraphClient(
        [
            ("DESC EDGE `REVIEW_LINKED`", [{"Field": "source_table", "Type": "string"}]),
        ]
    )

    result = enrich_day_rows_with_graph(
        snapshot,
        "dev2",
        connect_client=lambda space: client,
        schema_names={"review-linked-196fe7": "REVIEW_LINKED"},
        schema_labels={"REVIEW_LINKED": "审测关联"},
    )

    assert [row.object for row in result.relation_rows] == ["审测关联 · 2 条"]
    assert result.relation_rows_exact is False  # 聚合降级行不可作计数
    assert not [q for q in client.queries if q.startswith("GO FROM")]


def test_enrich_today_rows_falls_back_to_aggregate_when_graph_unavailable() -> None:
    snapshot = parse_execution_records(
        [_execution_record(written=5, completed_at="2026-09-22 10:30:00")],
        day="2026-09-22",
        target_space="dev2",
        default_space="dev2",
    )

    def _boom(space: str | None):
        raise RuntimeError("graph down")

    result = enrich_day_rows_with_graph(
        snapshot,
        "dev2",
        connect_client=_boom,
        schema_names={"review-widget-64d0d5": "ReviewWidget"},
        schema_labels={},
    )
    # 图不可达：保留聚合降级行，不空转
    assert [row.object for row in result.entity_rows] == ["审测挂件 · 5 条"]
    assert result.entity_rows_exact is False


def test_enrich_today_rows_falls_back_when_tag_has_no_index() -> None:
    snapshot = parse_execution_records(
        [_execution_record(written=5, completed_at="2026-09-22 10:30:00")],
        day="2026-09-22",
        target_space="dev2",
        default_space="dev2",
    )
    client = _ScriptedGraphClient(
        [
            (
                "DESC TAG `ReviewWidget`",
                [{"Field": "name", "Type": "string"}, {"Field": "update_time", "Type": "string"}],
            ),
            ("LOOKUP ON `ReviewWidget`", RuntimeError("There is no index to use at runtime")),
        ]
    )

    result = enrich_day_rows_with_graph(
        snapshot,
        "dev2",
        connect_client=lambda space: client,
        schema_names={"review-widget-64d0d5": "ReviewWidget"},
        schema_labels={},
    )
    # tag 无索引（LOOKUP 400）：退回聚合行
    assert [row.object for row in result.entity_rows] == ["审测挂件 · 5 条"]
    assert result.entity_rows_exact is False
    assert client.closed is True


def test_enrich_today_rows_skips_repeat_lookup_after_no_index_error() -> None:
    """同 tag 多次执行反查：首次 LOOKUP -1005 登记负缓存后，后续执行不再重发
    注定失败的语句（共享图服务侧每条失败语句还会自动重试 4 次放大负载）。"""
    snapshot = parse_execution_records(
        [
            _execution_record(written=2, completed_at="2026-09-23 03:41:54"),
            _execution_record(written=3, completed_at="2026-09-23 04:10:00"),
        ],
        day="2026-09-23",
        target_space="dev2",
        default_space="dev2",
    )
    client = _ScriptedGraphClient(
        [
            ("DESC TAG `ReviewWidget`", [{"Field": "name"}, {"Field": "update_time"}]),
            ("LOOKUP ON `ReviewWidget`", RuntimeError("There is no index to use at runtime")),
        ]
    )

    result = enrich_day_rows_with_graph(
        snapshot,
        "dev2",
        connect_client=lambda space: client,
        schema_names={"review-widget-64d0d5": "ReviewWidget"},
        schema_labels={},
    )

    lookup_count = sum(1 for q in client.queries if q.startswith("LOOKUP ON `ReviewWidget`"))
    assert lookup_count == 1  # 第二次执行命中负缓存，不发任何图查询
    assert [row.object for row in result.entity_rows] == [
        "审测挂件 · 3 条",  # 明细按完成时刻倒序，04:10 在前
        "审测挂件 · 2 条",
    ]


def test_overview_serves_stale_value_and_refreshes_in_background() -> None:
    """缓存过期先回旧值、后台线程刷新（stale-while-revalidate）：共享图服务
    拥塞窗口里页面秒回旧值，绝不把 30s 级排队超时暴露给用户。"""
    provider = FakeStatsProvider()
    service = PlatformOverviewService(
        stats_provider=provider, changes_provider=FakeChangesProvider()
    )
    first = service.get_overview("dev2")
    assert provider.calls == 1

    # 把缓存条目拨成过期（模拟 TTL 到期后的下一次进页）
    _, data = service._cached["dev2"]
    service._cached["dev2"] = (time.monotonic() - 1, data)

    started = time.perf_counter()
    again = service.get_overview("dev2")
    assert again is first  # 旧值立即返回，不等图查询
    assert time.perf_counter() - started < 1.0

    for _ in range(100):  # 等后台线程写回新值
        if service._cached["dev2"][1] is not first:
            break
        time.sleep(0.02)
    assert provider.calls == 2
    assert service.get_overview("dev2") is not first  # 新值已入缓存
