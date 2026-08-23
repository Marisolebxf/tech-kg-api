import os

import pytest
from httpx import ASGITransport, AsyncClient

os.environ["AUTH_ENABLED"] = "false"
os.environ["AUTH_SESSION_BACKEND"] = "memory"
os.environ["WORKFLOW_DEMO_DATA_ENABLED"] = "true"


@pytest.fixture
async def async_client() -> AsyncClient:
    from main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
