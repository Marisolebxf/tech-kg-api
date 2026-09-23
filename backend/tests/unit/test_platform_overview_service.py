from service.platform_overview import (
    GraphStatsSnapshot,
    PlatformOverviewService,
    TodayChangesSnapshot,
    TRSGraphStatsProvider,
    parse_execution_records,
)


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
    """控制库今日增量替身：固定返回可断言的写图计数与明细行。"""

    def __init__(self, snapshot: TodayChangesSnapshot | None = None) -> None:
        self.snapshot = snapshot or TodayChangesSnapshot()
        self.spaces: list[str | None] = []

    def get_today_changes(self, space: str | None = None) -> TodayChangesSnapshot:
        self.spaces.append(space)
        return self.snapshot


class FailingChangesProvider:
    def get_today_changes(self, space: str | None = None) -> TodayChangesSnapshot:
        raise RuntimeError("control db unavailable")


def test_overview_uses_live_graph_totals_and_explicit_partial_mode() -> None:
    provider = FakeStatsProvider()
    service = PlatformOverviewService(stats_provider=provider)

    result = service.get_overview()

    assert result.platform_status == "图数据库连接正常"
    assert result.data_mode == "partial"
    assert result.data_sources["graphAssets"] == "trsgraph-live"
    assert result.asset_overview_groups[0].total == "1.28 亿"
    assert result.asset_overview_groups[1].total == "6.42 亿"
    assert result.asset_overview_groups[2].total == "--"
    assert sum(item.ratio for item in result.entity_structure) == 100
    assert sum(item.ratio for item in result.relation_structure) == 100

    # 同一服务实例在缓存时间内不会重复扫描全部标签和边类型。
    assert service.get_overview() is result
    assert provider.calls == 1


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


def test_overview_marks_demo_fallback_when_graph_is_unavailable() -> None:
    result = PlatformOverviewService(stats_provider=FailingStatsProvider()).get_overview()

    assert result.data_mode == "mock"
    assert result.data_sources["graphAssets"] == "demo-fallback"
    assert "降级" in result.platform_status
    assert result.warnings


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


def test_overview_uses_control_plane_today_changes() -> None:
    """今日新增/运行中执行数来自工作流控制库，明细行替换演示数据。"""
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
        TodayChangesSnapshot(
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
    assert entity.added_label == "今日新增"
    assert result.asset_overview_groups[1].added == "+7"
    assert result.pending_batch_count == 3
    assert result.data_sources["todayChanges"] == "workflow-control-live"
    assert result.asset_change_rows["entity"] == entity_rows
    assert result.asset_change_rows["relation"] == []
    # 属性值卡片仍为占位演示行（前端不展示该分组）
    assert result.asset_change_rows["property"]


def test_overview_shows_placeholder_when_no_today_changes() -> None:
    """控制库可读但当日写图为 0：显示 -- 而非 +0，数据源仍标记真实。"""
    result = PlatformOverviewService(
        stats_provider=FakeStatsProvider(), changes_provider=FakeChangesProvider()
    ).get_overview()

    assert result.asset_overview_groups[0].added == "--"
    assert result.asset_overview_groups[0].added_label == "今日新增"
    assert result.asset_overview_groups[1].added == "--"
    assert result.asset_overview_groups[1].added_label == "今日新增"
    assert result.data_sources["todayChanges"] == "workflow-control-live"


def test_overview_tolerates_control_plane_failure() -> None:
    """控制库不可读时占位 + 警告，绝不回填虚构演示行。"""
    result = PlatformOverviewService(
        stats_provider=FakeStatsProvider(), changes_provider=FailingChangesProvider()
    ).get_overview()

    assert result.asset_overview_groups[0].added == "--"
    assert result.asset_overview_groups[0].added_label == "今日新增"
    assert result.asset_overview_groups[1].added == "--"
    assert result.asset_change_rows["entity"] == []
    assert result.asset_change_rows["relation"] == []
    assert result.pending_batch_count == 0
    assert result.data_sources["todayChanges"] == "demo-fallback"
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


def test_parse_execution_records_aggregates_today_by_kind_and_space() -> None:
    snapshot = parse_execution_records(
        [
            _execution_record(written=5, completed_at="2026-09-22 10:30:00"),
            _execution_record(
                kind="relation",
                written=2,
                trigger="RERUN",
                completed_at="2026-09-22 11:00:00",
            ),
            # 昨日完成：不计入今日
            _execution_record(written=99, completed_at="2026-09-21 23:59:59"),
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
        today="2026-09-22",
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
    assert row.time == "10:30:00"
    assert len(snapshot.relation_rows) == 1
    assert snapshot.relation_rows[0].source == "techkg_e2e_liz.review_widgets"


def test_parse_execution_records_space_key_variants_and_default_bucket() -> None:
    # 手动/重跑执行的 payload 记 graphSpace（驼峰），同样按空间过滤
    assert (
        parse_execution_records(
            [_execution_record(payload_space_key="graphSpace")],
            today="2026-09-22",
            target_space="dev2",
            default_space="dev2",
        ).entity_added
        == 5
    )
    # 未记录空间的历史执行归属默认空间；查询非默认空间时排除
    assert (
        parse_execution_records(
            [_execution_record(payload_space=None)],
            today="2026-09-22",
            target_space="dev2",
            default_space="dev2",
        ).entity_added
        == 5
    )
    assert (
        parse_execution_records(
            [_execution_record(payload_space=None)],
            today="2026-09-22",
            target_space="gaoxing_test",
            default_space="dev2",
        ).entity_added
        == 0
    )


def test_parse_execution_records_sorts_rows_by_completion_desc() -> None:
    snapshot = parse_execution_records(
        [
            _execution_record(written=1, completed_at="2026-09-22 09:00:00"),
            _execution_record(written=2, completed_at="2026-09-22 18:00:00"),
        ],
        today="2026-09-22",
        target_space="dev2",
        default_space="dev2",
    )

    assert [row.time for row in snapshot.entity_rows] == ["18:00:00", "09:00:00"]


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
        today="2026-09-22",
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
    assert {row.time for row in snapshot.entity_rows} == {"10:30:00"}


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
        today="2026-09-22",
        target_space="dev2",
        default_space="dev2",
    )

    # 倒序排列：11:00（schemaKey/schemaLabel 均缺）在前，10:30（仅缺 schemaKey）在后
    assert snapshot.entity_rows[0].change == "新增 实体"
    assert snapshot.entity_rows[0].type == "实体 Schema"
    assert snapshot.entity_rows[1].change == "新增 审测挂件"
