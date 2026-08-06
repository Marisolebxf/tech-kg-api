from service.platform_overview import GraphStatsSnapshot, PlatformOverviewService


class FakeStatsProvider:
    def __init__(self) -> None:
        self.calls = 0

    def get_stats(self) -> GraphStatsSnapshot:
        self.calls += 1
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
    def get_stats(self) -> GraphStatsSnapshot:
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


def test_overview_marks_demo_fallback_when_graph_is_unavailable() -> None:
    result = PlatformOverviewService(stats_provider=FailingStatsProvider()).get_overview()

    assert result.data_mode == "mock"
    assert result.data_sources["graphAssets"] == "demo-fallback"
    assert "降级" in result.platform_status
    assert result.warnings
