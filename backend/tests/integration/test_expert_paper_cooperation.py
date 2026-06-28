import pytest


@pytest.mark.asyncio
async def test_expert_paper_cooperation_validation(async_client) -> None:
    response = await async_client.post(
        "/api/v1/kg-construction/expert-paper-cooperation-relations/demo/structured-result",
        json={
            "dataSource": "knowledge_graph",
            "expertAId": "COOP-SCH001",
            "expertBId": "COOP-SCH001",
            "startTime": "2021-01-01",
            "endTime": "2024-12-31",
        },
    )

    assert response.status_code == 422
    assert "expertAId 和 expertBId 不能相同" in response.text
