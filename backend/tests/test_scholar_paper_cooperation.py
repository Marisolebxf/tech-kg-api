from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


REQUEST_BODY = {
    "dataSource": "knowledge_graph",
    "expertAId": "COOP-SCH001",
    "expertBId": "COOP-SCH002",
    "startTime": "2021-01-01",
    "endTime": "2024-12-31",
}


def test_scholar_paper_cooperation_demo_analyze_from_mysql():
    response = client.post("/api/v1/scholar-paper-cooperation/demo/analyze", json=REQUEST_BODY)

    assert response.status_code == 200
    data = response.json()
    assert data["taskName"] == "科技专家论文合作关系"
    assert data["apiResultExample"]["sourceMode"] == "mysql_demo_tables"
    assert data["structuredResult"]["authorList"] == ["陈建国", "刘芳"]
    assert data["structuredResult"]["authorUnits"] == ["清华大学", "北京大学"]
    assert data["structuredResult"]["cooperationPaperCount"] == 4
    assert data["structuredResult"]["citation"] == {"total": 225, "max": 88}
    assert data["structuredResult"]["paperTopics"][:3] == ["社区发现", "核心团队", "学术图谱"]
    assert data["papers"]
    assert data["stableTeam"]["teamFlag"] is True
    assert data["coreCollaborators"]


def test_scholar_paper_cooperation_structured_result_only():
    response = client.post("/api/v1/scholar-paper-cooperation/demo/structured-result", json=REQUEST_BODY)

    assert response.status_code == 200
    data = response.json()
    assert "structuredResult" in data
    assert data["structuredResult"]["cooperationTimeRange"]["displayText"] == "2021 - 2024"
    assert data["structuredResult"]["cooperationFrequency"] == 4


def test_scholar_paper_cooperation_demo_rejects_same_expert():
    response = client.post(
        "/api/v1/scholar-paper-cooperation/demo/analyze",
        json={"dataSource": "knowledge_graph", "expertAId": "COOP-SCH001", "expertBId": "COOP-SCH001"},
    )

    assert response.status_code == 422


def test_scholar_paper_cooperation_mysql_analyze():
    response = client.post("/api/v1/scholar-paper-cooperation/mysql/analyze", json=REQUEST_BODY)

    assert response.status_code == 200
    data = response.json()
    assert data["apiResultExample"]["sourceMode"] == "mysql_demo_tables"
    assert data["structuredResult"]["stableTeamName"]
    assert data["sharedContribution"]["tags"]


def test_scholar_paper_cooperation_graph_view():
    response = client.post("/api/v1/scholar-paper-cooperation/demo/graph-view", json=REQUEST_BODY)

    assert response.status_code == 200
    data = response.json()
    assert data["source"]["mode"] == "mysql_demo_graph_view"
    assert len(data["nodes"]) == 6
    assert len(data["edges"]) == 6
    assert data["metrics"]["paperCount"] == 4
    assert data["nodes"][0]["label"] == "专家A：陈建国"
