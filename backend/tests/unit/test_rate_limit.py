"""按身份固定窗口频控：额度、窗口重置、身份隔离与环境变量覆盖。"""

import pytest
from fastapi import HTTPException

from infra import rate_limit
from infra.rate_limit import RateLimit, configured_limit, enforce_rate_limit


@pytest.fixture(autouse=True)
def memory_backend(monkeypatch):
    monkeypatch.setenv("AUTH_SESSION_BACKEND", "memory")
    rate_limit.reset_memory_counters()
    yield
    rate_limit.reset_memory_counters()


async def test_blocks_after_limit_and_isolates_identities():
    limit = RateLimit(2, 60)
    await enforce_rate_limit("t", "a", limit)
    await enforce_rate_limit("t", "a", limit)
    with pytest.raises(HTTPException) as exc:
        await enforce_rate_limit("t", "a", limit)
    assert exc.value.status_code == 429
    assert int(exc.value.headers["Retry-After"]) >= 1
    await enforce_rate_limit("t", "b", limit)
    await enforce_rate_limit("other", "a", limit)


async def test_cost_consumes_multiple_units():
    with pytest.raises(HTTPException):
        await enforce_rate_limit("t", "a", RateLimit(10, 60), cost=11)


async def test_window_resets(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(rate_limit.time, "monotonic", lambda: clock[0])
    limit = RateLimit(1, 10)
    await enforce_rate_limit("t", "a", limit)
    with pytest.raises(HTTPException):
        await enforce_rate_limit("t", "a", limit)
    clock[0] += 11
    await enforce_rate_limit("t", "a", limit)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("", RateLimit(5, 60)),
        ("30/10", RateLimit(30, 10)),
        ("30", RateLimit(30, 60)),
        ("0", None),
        ("abc", RateLimit(5, 60)),
        ("-1/60", RateLimit(5, 60)),
    ],
)
def test_env_override(monkeypatch, raw, expected):
    monkeypatch.setenv("RATE_LIMIT_SOME_BUCKET", raw)
    assert configured_limit("some-bucket", RateLimit(5, 60)) == expected
