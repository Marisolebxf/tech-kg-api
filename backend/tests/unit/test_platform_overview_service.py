from service.platform_overview import (
    GraphStatsSnapshot,
    PlatformOverviewService,
    TRSGraphStatsProvider,
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
