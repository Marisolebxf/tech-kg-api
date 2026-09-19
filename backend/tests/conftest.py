import os

import pytest
from httpx import ASGITransport, AsyncClient

os.environ["AUTH_ENABLED"] = "false"
os.environ["APP_ENV"] = "test"
os.environ["AUTH_ALLOW_INSECURE_DEV_CONTEXT"] = "true"
os.environ["API_DOCS_ENABLED"] = "true"
os.environ["AUTH_SESSION_BACKEND"] = "memory"
os.environ["USER_CENTER_PORTAL_COOKIE_LOGIN_ENABLED"] = "false"
# 脚本对象可用性探测保持"探测即实时"语义（生产默认 30s 缓存，见
# service/schema_management.py 的 _SCRIPT_OBJECT_CACHE）
os.environ["SCHEMA_SCRIPT_AVAILABLE_CACHE_TTL_SECONDS"] = "0"


@pytest.fixture
async def async_client() -> AsyncClient:
    from main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
