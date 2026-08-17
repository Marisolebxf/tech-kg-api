import pytest
from starlette.requests import Request

from biz.dependencies.internal_api import get_internal_api_auth_headers
from service.expert_indirect_relation_api import GraphQueryApiClient
from service.expert_paper_cooperation_api import GraphSearchApiClient


def _request(headers: list[tuple[bytes, bytes]]) -> Request:
    return Request({"type": "http", "headers": headers})


def test_internal_api_auth_forwards_only_credentials():
    request = _request(
        [
            (b"authorization", b"Bearer test-token"),
            (b"cookie", b"kg_session=test-session"),
            (b"x-forwarded-for", b"203.0.113.1"),
        ]
    )

    assert get_internal_api_auth_headers(request) == {
        "authorization": "Bearer test-token",
        "cookie": "kg_session=test-session",
    }


def test_internal_api_auth_omits_missing_credentials():
    assert get_internal_api_auth_headers(_request([])) == {}


@pytest.mark.asyncio
async def test_paper_graph_client_applies_forwarded_auth_headers():
    client = GraphSearchApiClient(
        "http://internal/api/v1",
        auth_headers={"cookie": "kg_session=test-session"},
    )
    try:
        assert client._client.headers["cookie"] == "kg_session=test-session"
    finally:
        await client._client.aclose()


@pytest.mark.asyncio
async def test_indirect_graph_client_applies_forwarded_auth_headers():
    client = GraphQueryApiClient(
        "http://internal/api/v1",
        auth_headers={"authorization": "Bearer test-token"},
    )
    try:
        assert client._client.headers["authorization"] == "Bearer test-token"
    finally:
        await client._client.aclose()
