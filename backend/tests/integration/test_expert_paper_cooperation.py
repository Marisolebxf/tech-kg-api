import pytest

from biz.handler import expert_paper_cooperation as handler

ENDPOINT = "/api/v1/kg-construction/expert-paper-cooperation-relations/demo/structured-result"
VALID_PAYLOAD = {
    "dataSource": "knowledge_graph",
    "expertAId": "4P566No1",
    "expertBId": "d492835p",
    "startTime": "2021-01-01",
    "endTime": "2024-12-31",
}


def _structured_result(**overrides):
    result = {
        "structuredResult": {
            "authorList": ["沈定刚", "廖术"],
            "authorUnits": ["上海科技大学", "上海科技大学"],
            "cooperationTimeRange": {
                "startYear": 2021,
                "endYear": 2023,
                "displayText": "2021 - 2023",
            },
            "paperTopics": ["AI for Life Science", "Medical Image Segmentation"],
            "cooperationPaperCount": 6,
            "journalLevelCount": {"JCR-Q1": 2},
            "conferenceLevelCount": {},
            "citation": {"total": 83, "max": 57},
            "cooperationFrequency": 6,
            "academicImpactScore": 57.8,
            "stableTeamMembers": ["Yaozong Gao"],
            "coreCollaborators": ["Yaozong Gao", "Yiqiang Zhan"],
            "sharedContribution": ["联合论文产出"],
        }
    }
    result["structuredResult"].update(overrides)
    return result


@pytest.mark.asyncio
async def test_expert_paper_cooperation_returns_structured_result(async_client, monkeypatch):
    monkeypatch.setattr(
        handler.application,
        "build_structured_result_only",
        lambda body: _structured_result(),
    )

    response = await async_client.post(ENDPOINT, json=VALID_PAYLOAD)

    assert response.status_code == 200
    data = response.json()
    assert data["structuredResult"]["authorList"] == ["沈定刚", "廖术"]
    assert data["structuredResult"]["cooperationPaperCount"] == 6


@pytest.mark.parametrize(
    ("payload_patch", "expected_message"),
    [
        ({"expertAId": ""}, "String should have at least 1 character"),
        ({"expertAId": "   "}, "String should have at least 1 character"),
        ({"expertAId": "BAD ID!"}, "String should match pattern"),
        ({"expertAId": "A" * 65}, "String should have at most 64 characters"),
        ({"expertBId": "4P566No1"}, "expertAId 和 expertBId 不能相同"),
        ({"startTime": "2024/01/01"}, "String should match pattern"),
        ({"startTime": "2024-99-99"}, "时间格式错误"),
        ({"startTime": "2025-01-01", "endTime": "2024-12-31"}, "startTime 不能晚于 endTime"),
        ({"dataSource": "unknown"}, "Input should be"),
    ],
)
@pytest.mark.asyncio
async def test_expert_paper_cooperation_rejects_invalid_payloads(
    async_client,
    payload_patch,
    expected_message,
):
    payload = {**VALID_PAYLOAD, **payload_patch}

    response = await async_client.post(ENDPOINT, json=payload)

    # 当前项目全局 RequestValidationError 处理器使用业务 code=422 包装返回。
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 422
    assert data["success"] is False
    assert expected_message in response.text


@pytest.mark.asyncio
async def test_expert_paper_cooperation_rejects_missing_required_field(async_client):
    payload = VALID_PAYLOAD.copy()
    payload.pop("expertBId")

    response = await async_client.post(ENDPOINT, json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 422
    assert data["success"] is False
    assert "Field required" in response.text


@pytest.mark.asyncio
async def test_expert_paper_cooperation_returns_404_for_unknown_expert(async_client, monkeypatch):
    def raise_not_found(body):
        raise ValueError("gkx_local 中不存在输入的专家ID，请使用 dwd_scholar.scholar_id")

    monkeypatch.setattr(handler.application, "build_structured_result_only", raise_not_found)

    response = await async_client.post(ENDPOINT, json=VALID_PAYLOAD)

    assert response.status_code == 404
    assert "不存在输入的专家ID" in response.text


@pytest.mark.asyncio
async def test_expert_paper_cooperation_handles_empty_result(async_client, monkeypatch):
    monkeypatch.setattr(
        handler.application,
        "build_structured_result_only",
        lambda body: _structured_result(
            paperTopics=[],
            cooperationPaperCount=0,
            journalLevelCount={},
            conferenceLevelCount={},
            citation={"total": 0, "max": 0},
            cooperationFrequency=0,
            academicImpactScore=0,
            stableTeamMembers=[],
            coreCollaborators=[],
            sharedContribution=[],
        ),
    )

    response = await async_client.post(ENDPOINT, json=VALID_PAYLOAD)

    assert response.status_code == 200
    data = response.json()["structuredResult"]
    assert data["cooperationPaperCount"] == 0
    assert data["paperTopics"] == []
    assert data["coreCollaborators"] == []


@pytest.mark.asyncio
async def test_expert_paper_cooperation_returns_500_for_service_error(async_client, monkeypatch):
    def raise_runtime_error(body):
        raise RuntimeError("database timeout")

    monkeypatch.setattr(handler.application, "build_structured_result_only", raise_runtime_error)

    response = await async_client.post(ENDPOINT, json=VALID_PAYLOAD)

    assert response.status_code == 500
    assert "专家论文合作关系结构化结果生成失败" in response.text
