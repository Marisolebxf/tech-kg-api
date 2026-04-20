"""
API 接口测试
使用 scholars.json / papers_cn.json 中的真实字段作为测试数据
"""
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def _assert_ok(response, path: str = "") -> None:
    assert response.status_code == 200, (
        f"{path} expected 200, got {response.status_code}: {response.text}"
    )


# ── 基础接口测试 ──────────────────────────────────────────────────────────

def test_hello():
    response = client.get("/hello")
    _assert_ok(response, "GET /hello")
    assert response.json() == {"message": "Hello, Tech KG!"}


def test_api_root():
    response = client.get("/api")
    _assert_ok(response, "GET /api")
    assert response.json()["message"] == "API is running"


# ── 实体对齐与消歧测试 ────────────────────────────────────────────────────

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


# ── 实体抽取测试 ──────────────────────────────────────────────────────────

def test_extract_work_experience_zh():
    """工作经历（中文）- 来自 scholars.json 张伟"""
    resp = client.post("/api/v1/entity/extraction", json={
        "text": "2010年—至今，北京大学计算机科学与技术系，教授",
        "source_type": "work"
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["source_type"] == "work"
    assert "entity_count" in data
    assert "entities" in data
    assert isinstance(data["entities"], list)


def test_extract_work_experience_en():
    """工作经历（英文）- 来自 scholars.json 张伟"""
    resp = client.post("/api/v1/entity/extraction", json={
        "text": "2010–present, Professor, Department of Computer Science and Technology, Peking University",
        "source_type": "work"
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["source_type"] == "work"
    assert isinstance(data["entities"], list)


def test_extract_education_zh():
    """教育背景（中文）- 来自 scholars.json 张伟"""
    resp = client.post("/api/v1/entity/extraction", json={
        "text": "2001年至2006年就读于北京大学计算机科学与技术系，获计算机科学博士学位",
        "source_type": "education"
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["source_type"] == "education"
    assert isinstance(data["entities"], list)


def test_extract_abstract():
    """论文摘要 - 来自 papers_cn.json"""
    resp = client.post("/api/v1/entity/extraction", json={
        "text": "提出一种多源异构科技数据融合框架，整合中文论文、专利、项目等多类型数据，构建统一的科技知识图谱，在实体对齐和关系抽取上取得显著效果",
        "source_type": "abstract"
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["source_type"] == "abstract"
    assert isinstance(data["entities"], list)


def test_extract_general():
    """通用模式"""
    resp = client.post("/api/v1/entity/extraction", json={
        "text": "张伟在北京大学发表了关于目标检测的论文，获国家自然科学基金资助",
        "source_type": "general"
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["source_type"] == "general"


def test_extract_empty_text():
    """空文本应返回 400"""
    resp = client.post("/api/v1/entity/extraction", json={
        "text": "",
        "source_type": "work"
    })
    assert resp.status_code == 400


def test_extract_invalid_source_type():
    """非法 source_type 应返回 400"""
    resp = client.post("/api/v1/entity/extraction", json={
        "text": "2010年—至今，北京大学，教授",
        "source_type": "invalid_type"
    })
    assert resp.status_code == 400


def test_extract_default_source_type():
    """不传 source_type 默认使用 general"""
    resp = client.post("/api/v1/entity/extraction", json={
        "text": "张伟，北京大学教授，研究方向为计算机视觉"
    })
    assert resp.status_code == 200
    assert resp.json()["source_type"] == "general"