from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def _assert_ok(response, path: str = "") -> None:
    assert response.status_code == 200, (
        f"{path} expected 200, got {response.status_code}: {response.text}"
    )


def test_hello():
    response = client.get("/hello")
    _assert_ok(response, "GET /hello")
    assert response.json() == {"message": "Hello, Tech KG!"}


def test_api_root():
    response = client.get("/api")
    _assert_ok(response, "GET /api")
    assert response.json()["message"] == "API is running"


def test_entity_alignment_default():
    response = client.post("/api/v1/entity/alignment", json={})
    _assert_ok(response, "POST /api/v1/entity/alignment")
    data = response.json()
    assert data["count_a"] == 7
    assert data["aligned_count"] >= 1
    assert len(data["details"]) == 7


def test_entity_disambiguation_default():
    response = client.post(
        "/api/v1/entity/disambiguation",
        json={
            "text": "苹果今天在发布会上推出了新款iPhone 16。",
            "mention": "苹果",
        },
    )
    _assert_ok(response, "POST /api/v1/entity/disambiguation")
    data = response.json()
    assert data["is_nil"] is False, data
    assert data["linked_entity_id"] == "KB001", data


def test_entity_alignment_empty_lists_use_defaults():
    response = client.post(
        "/api/v1/entity/alignment",
        json={"kg_a": [], "kg_b": []},
    )
    _assert_ok(response, "POST alignment empty lists")
    data = response.json()
    assert data["count_a"] == 7
    assert data["count_b"] == 8


def test_entity_disambiguation_empty_kb_uses_default():
    response = client.post(
        "/api/v1/entity/disambiguation",
        json={
            "text": "苹果今天在发布会上推出了新款iPhone 16。",
            "mention": "苹果",
            "kb": [],
        },
    )
    _assert_ok(response, "POST disambiguation kb=[]")
    data = response.json()
    assert data["is_nil"] is False, data
    assert data["linked_entity_id"] == "KB001", data


# ============================================================
# 关系抽取接口测试
# ============================================================


def test_relation_extraction_rule():
    response = client.post(
        "/api/v1/relation/extraction",
        json={
            "text": "马云创立了阿里巴巴集团，阿里巴巴集团位于浙江省杭州市。",
            "method": "rule",
        },
    )
    _assert_ok(response, "POST /api/v1/relation/extraction")
    data = response.json()
    assert data["method"] == "rule"
    assert len(data["entities"]) >= 2
    assert len(data["relations"]) >= 1
    rel_triples = [(r["head"]["text"], r["relation"], r["tail"]["text"]) for r in data["relations"]]
    assert ("马云", "创立", "阿里巴巴集团") in rel_triples


def test_relation_extraction_multi_relations():
    text = (
        "任正非创立了华为技术有限公司，华为技术有限公司位于广东省深圳市。"
        "孟晚舟担任华为技术有限公司的CFO。"
        "华为技术有限公司推出了鸿蒙操作系统产品。"
    )
    response = client.post(
        "/api/v1/relation/extraction",
        json={"text": text, "method": "rule"},
    )
    _assert_ok(response, "POST extraction multi")
    data = response.json()
    assert len(data["relations"]) >= 3
    rel_types = {r["relation"] for r in data["relations"]}
    assert "创立" in rel_types
    assert "位于" in rel_types


def test_relation_extraction_default_method():
    response = client.post(
        "/api/v1/relation/extraction",
        json={"text": "马云创立了阿里巴巴集团"},
    )
    _assert_ok(response, "POST extraction default method")
    data = response.json()
    assert data["method"] == "rule"
    assert len(data["relations"]) >= 1


def test_batch_relation_extraction():
    response = client.post(
        "/api/v1/relation/extraction/batch",
        json={
            "texts": [
                "马云创立了阿里巴巴集团",
                "任正非创立了华为技术有限公司",
            ],
            "method": "rule",
        },
    )
    _assert_ok(response, "POST /api/v1/relation/extraction/batch")
    data = response.json()
    assert data["count"] == 2
    assert len(data["results"]) == 2
    assert data["entity_count"] >= 4
    assert data["relation_count"] >= 2


def test_relation_examples():
    response = client.get("/api/v1/relation/examples")
    _assert_ok(response, "GET /api/v1/relation/examples")
    data = response.json()
    assert len(data) == 3
    assert data[0]["title"] == "科技企业"
