import pytest
from httpx import ASGITransport, AsyncClient

from main import app


@pytest.fixture
async def async_client() -> AsyncClient:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
