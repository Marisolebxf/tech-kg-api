import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_common_capability_metadata(async_client: AsyncClient) -> None:
    response = await async_client.get("/api/v1/common-capabilities/metadata")

    assert response.status_code == 200
    body = response.json()
    assert "entity_alignment" in body["capabilities"]
    assert "general" in body["entity_extraction_source_types"]


@pytest.mark.asyncio
async def test_entity_alignment_uses_builtin_examples(async_client: AsyncClient) -> None:
    response = await async_client.post("/api/v1/common-capabilities/entity-alignment", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["aligned_count"] > 0
    assert "details" in body


@pytest.mark.asyncio
async def test_entity_disambiguation_uses_builtin_kb(async_client: AsyncClient) -> None:
    response = await async_client.post(
        "/api/v1/common-capabilities/entity-disambiguation",
        json={
            "text": "苹果今天在发布会上推出了新款iPhone。",
            "mention": "苹果",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert "best_match" in body
    assert body["mention"] == "苹果"


@pytest.mark.asyncio
async def test_rule_relation_extraction(async_client: AsyncClient) -> None:
    response = await async_client.post(
        "/api/v1/common-capabilities/relation-extraction",
        json={
            "text": "马云创立了阿里巴巴集团，阿里巴巴集团位于浙江省杭州市。",
            "method": "rule",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["method"] == "rule"
    assert body["relations"]
