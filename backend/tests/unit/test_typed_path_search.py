import asyncio
import time
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from biz.handler import graph_search
from infra.graph_db.models import GraphNode

app = FastAPI()
app.include_router(graph_search.router, prefix="/api/v1")
client = TestClient(app)
ENDPOINT = "/api/v1/graph-search/paths/search"


def _payload() -> dict:
    return {
        "sourceId": "person_A",
        "targetId": "person_B",
        "steps": [
            {
                "edgeType": "AUTHORED_BY",
                "direction": "in",
                "targetLabel": "Paper",
                "targetFilters": [
                    {
                        "property": "publication_year",
                        "operator": "gte",
                        "value": "2021",
                    }
                ],
            },
            {
                "edgeType": "AUTHORED_BY",
                "direction": "out",
                "targetLabel": "Person",
            },
        ],
        "limit": 20,
        "offset": 0,
        "space": "dev",
    }


def test_typed_path_query_contains_direction_type_and_filter() -> None:
    body = graph_search.TypedPathSearchRequest(**_payload())

    query = graph_search._build_typed_path_query(body)

    assert "(n0)<-[e0:`AUTHORED_BY`]-(n1:`Paper`)" in query
    assert "(n1:`Paper`)-[e1:`AUTHORED_BY`]->(n2:`Person`)" in query
    assert 'n1.`Paper`.`publication_year` >= "2021"' in query
    assert 'id(n2) == "person_B"' in query
    assert "SKIP 0 LIMIT 20" in query


def test_typed_path_api_returns_all_path_parts(monkeypatch) -> None:
    class FakeGraphClient:
        queries = []

        def get_node(self, node_id):
            return GraphNode(
                id=node_id,
                labels=["Person"],
                properties={"name_zh": "专家A"},
            )

        def execute_read(self, query):
            self.queries.append(query)
            if "count(*) AS total" in query:
                return SimpleNamespace(records=[{"total": 1}])
            return SimpleNamespace(
                records=[
                    {
                        "node_0_id": "person_A",
                        "node_0_properties": {"name_zh": "专家A"},
                        "node_1_id": "paper_1",
                        "node_1_properties": {"publication_year": "2023"},
                        "node_2_id": "person_B",
                        "node_2_properties": {"name_zh": "专家B"},
                        "edge_0_properties": {"citations": 12},
                        "edge_0_rank": 0,
                        "edge_1_properties": {"citations": 12},
                        "edge_1_rank": 0,
                    }
                ]
            )

    monkeypatch.setattr(graph_search, "_get_client", lambda space=None: FakeGraphClient())

    response = client.post(ENDPOINT, json=_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["total"] == 1
    assert any('id(n0) == "person_A"' in query for query in FakeGraphClient.queries)
    assert any('id(n2) == "person_B"' in query for query in FakeGraphClient.queries)
    path = body["data"]["items"][0]
    assert [node["id"] for node in path["nodes"]] == [
        "person_A",
        "paper_1",
        "person_B",
    ]
    assert path["edges"][0]["source"] == "paper_1"
    assert path["edges"][0]["target"] == "person_A"
    assert path["edges"][1]["source"] == "paper_1"
    assert path["edges"][1]["target"] == "person_B"


def test_typed_path_api_rejects_unsafe_identifier() -> None:
    payload = _payload()
    payload["steps"][0]["edgeType"] = "AUTHORED_BY); DELETE VERTEX"

    response = client.post(ENDPOINT, json=payload)

    assert response.status_code == 422
    assert "String should match pattern" in response.text


def test_typed_path_api_skips_count_when_disabled(monkeypatch) -> None:
    class FakeGraphClient:
        queries = []

        def get_node(self, node_id):
            return GraphNode(id=node_id, labels=["Person"], properties={})

        def execute_read(self, query):
            self.queries.append(query)
            if "count(*) AS total" in query:
                return SimpleNamespace(records=[{"total": 99}])
            return SimpleNamespace(records=[])

    monkeypatch.setattr(graph_search, "_get_client", lambda space=None: FakeGraphClient())
    payload = _payload()
    payload["countTotal"] = False

    response = client.post(ENDPOINT, json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    # 未要求统计时不得执行全量 count 聚合，total 如实返回 -1（未统计）
    assert not any("count(*) AS total" in query for query in FakeGraphClient.queries)
    assert any("SKIP 0 LIMIT 20" in query for query in FakeGraphClient.queries)
    assert body["data"]["total"] == -1


async def test_typed_path_handler_does_not_block_event_loop(monkeypatch) -> None:
    """三个同步图调用必须离开事件循环线程执行（to_thread），否则整个 worker 冻结。"""

    class SlowGraphClient:
        def get_node(self, node_id):
            time.sleep(0.15)  # 模拟同步 httpx 网络等待
            return GraphNode(id=node_id, labels=["Person"], properties={})

        def execute_read(self, query):
            time.sleep(0.15)
            if "count(*) AS total" in query:
                return SimpleNamespace(records=[{"total": 0}])
            return SimpleNamespace(records=[])

    monkeypatch.setattr(graph_search, "_get_client", lambda space=None: SlowGraphClient())
    actor = SimpleNamespace(is_admin=True, user_id="tester")

    ticks = 0

    async def heartbeat() -> None:
        nonlocal ticks
        while True:
            await asyncio.sleep(0.02)
            ticks += 1

    heartbeat_task = asyncio.create_task(heartbeat())
    try:
        started = time.monotonic()
        response = await graph_search.search_typed_paths(
            graph_search.TypedPathSearchRequest(**_payload()),
            actor,
        )
        elapsed = time.monotonic() - started
    finally:
        heartbeat_task.cancel()

    assert response.success is True
    # get_node + 数据查询 + count 查询各 sleep 0.15s，串行总耗时 >= 0.45s；
    # 若同步调用留在事件循环线程上，心跳协程全程得不到调度（ticks≈0）。
    assert elapsed >= 0.45
    assert ticks >= 10, f"事件循环在图查询期间被阻塞：心跳仅跳动 {ticks} 次"
