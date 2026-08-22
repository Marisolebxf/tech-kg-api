import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def async_client() -> AsyncClient:
    from main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
