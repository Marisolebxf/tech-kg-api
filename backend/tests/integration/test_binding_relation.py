from fastapi.testclient import TestClient


def test_binding_index(async_client: TestClient) -> None:
    response = async_client.get("/")

    assert response.status_code == 200
    assert "科技专家关系推理平台" in response.text or "知识图谱平台" in response.text


def test_binding_two_hop_and_three_hop_are_different(async_client: TestClient) -> None:
    two_hop_response = async_client.get("/api/v1/binding/expert-direct-two-hop", params={"dataSource": "all"})
    three_hop_response = async_client.get("/api/v1/binding/expert-direct-three-hop", params={"dataSource": "all"})

    assert two_hop_response.status_code == 200
    assert three_hop_response.status_code == 200

    two_hop = two_hop_response.json()["scenarios"]
    three_hop = three_hop_response.json()["scenarios"]

    assert two_hop
    assert three_hop
    assert [item["key"] for item in two_hop] != [item["key"] for item in three_hop]


def test_binding_relation_default(async_client: TestClient) -> None:
    response = async_client.get("/api/v1/binding/expert-direct-relation")

    assert response.status_code == 200
    payload = response.json()
    assert "scenarios" in payload
    assert len(payload["scenarios"]) >= 1
