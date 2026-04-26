from fastapi.testclient import TestClient

from app.main import app
from app.services.graphrag_demo import _cosine_similarity, _fallback_answer, _hash_embedding


client = TestClient(app)


def test_graphrag_overview_route():
    response = client.get("/api/v1/graphrag/demo/overview")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Neo4j GraphRAG Demo"
    assert "DemoChunk" in data["graph_schema"]["nodes"]
    assert len(data["sample_questions"]) >= 3


def test_hash_embedding_is_deterministic():
    left = _hash_embedding("GraphRAG 和 Neo4j")
    right = _hash_embedding("GraphRAG 和 Neo4j")
    assert left == right
    assert len(left) == 32


def test_cosine_similarity_self_is_high():
    vector = _hash_embedding("多跳检索与图扩展")
    score = _cosine_similarity(vector, vector)
    assert score > 0.99


def test_fallback_answer_handles_empty_chunks():
    answer = _fallback_answer("GraphRAG 是什么？", [])
    assert "没有召回" in answer
