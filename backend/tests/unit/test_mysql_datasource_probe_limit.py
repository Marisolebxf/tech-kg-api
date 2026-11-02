"""Probe quotas are enforced offline and fail closed without production Redis."""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import service.mysql_datasource_probe_limit as limiter


@pytest.fixture(autouse=True)
def isolated_state(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("AUTH_SESSION_BACKEND", "memory")
    monkeypatch.delenv("MYSQL_DATASOURCE_PROBE_USER_LIMIT", raising=False)
    monkeypatch.delenv("MYSQL_DATASOURCE_PROBE_GLOBAL_LIMIT", raising=False)
    monkeypatch.setattr(limiter.time, "monotonic", lambda: 100.0)
    with limiter._memory_lock:
        limiter._memory_counts.clear()

    def no_network(_url):
        raise AssertionError("Tests must not contact Redis")

    monkeypatch.setattr(limiter, "_redis_client", no_network)
    yield
    with limiter._memory_lock:
        limiter._memory_counts.clear()


def _assert_denied(user_id, status_code, retry_after):
    with pytest.raises(HTTPException) as error:
        limiter.consume_mysql_datasource_probe(user_id)
    assert error.value.status_code == status_code
    assert error.value.headers == {"Retry-After": str(retry_after)}
    return error.value


def test_user_limit_is_shared_across_datasource_ids_and_expires(monkeypatch):
    for _ in range(5):
        limiter.consume_mysql_datasource_probe("actor-1")
    _assert_denied("actor-1", 429, 60)
    limiter.consume_mysql_datasource_probe("actor-2")
    monkeypatch.setattr(limiter.time, "monotonic", lambda: 159.2)
    _assert_denied("actor-1", 429, 1)
    monkeypatch.setattr(limiter.time, "monotonic", lambda: 160.0)
    limiter.consume_mysql_datasource_probe("actor-1")


def test_global_limit_cannot_be_bypassed_by_changing_actor():
    for number in range(30):
        limiter.consume_mysql_datasource_probe("actor-" + str(number))
    _assert_denied("fresh-actor", 429, 60)
    # A rejected new identity must not allocate a new memory entry.
    assert len(limiter._memory_counts) == 31


def test_denied_user_probe_does_not_consume_global_quota():
    for _ in range(5):
        limiter.consume_mysql_datasource_probe("noisy-actor")
    for _ in range(8):
        _assert_denied("noisy-actor", 429, 60)
    for number in range(25):
        limiter.consume_mysql_datasource_probe("actor-" + str(number))
    _assert_denied("actor-after-global-limit", 429, 60)


def test_concurrent_memory_probes_reserve_only_five_user_slots():
    def attempt(_):
        try:
            limiter.consume_mysql_datasource_probe("same-actor")
            return 200
        except HTTPException as error:
            return error.status_code

    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(attempt, range(60)))
    assert results.count(200) == 5
    assert results.count(429) == 55
    assert limiter._memory_counts["mysql-datasource-probes:{all}:global"][1] == 5


def test_expired_memory_keys_are_cleaned_before_capacity_check(monkeypatch):
    monkeypatch.setattr(limiter, "_MAX_MEMORY_KEYS", 2)
    limiter._memory_counts["old-key"] = (99.0, 4)
    limiter.consume_mysql_datasource_probe("actor")
    assert len(limiter._memory_counts) == 2
    assert "old-key" not in limiter._memory_counts


def test_full_memory_counter_fails_closed_without_evicting_live_quota(monkeypatch):
    monkeypatch.setattr(limiter, "_MAX_MEMORY_KEYS", 2)
    limiter.consume_mysql_datasource_probe("actor-1")
    before = dict(limiter._memory_counts)
    _assert_denied("actor-2", 503, 60)
    assert limiter._memory_counts == before


@pytest.mark.parametrize("app_env", ["prod", "production", "staging", "", "unknown"])
def test_production_memory_auth_setting_does_not_enable_local_fallback(monkeypatch, app_env):
    monkeypatch.setenv("APP_ENV", app_env)
    _assert_denied("actor", 503, 60)
    assert limiter._memory_counts == {}


@pytest.mark.parametrize("app_env", ["test", "dev", "development", "local", " TEST "])
def test_explicit_local_memory_backend_is_allowed(monkeypatch, app_env):
    monkeypatch.setenv("APP_ENV", app_env)
    limiter.consume_mysql_datasource_probe("actor")
    assert len(limiter._memory_counts) == 2


@pytest.mark.parametrize("backend", ["redis", "", "unexpected"])
def test_local_environment_without_explicit_memory_still_requires_redis(monkeypatch, backend):
    monkeypatch.setenv("AUTH_SESSION_BACKEND", backend)
    _assert_denied("actor", 503, 60)
    assert limiter._memory_counts == {}


@pytest.mark.parametrize(
    "setting,value",
    [
        ("MYSQL_DATASOURCE_PROBE_USER_LIMIT", "0"),
        ("MYSQL_DATASOURCE_PROBE_USER_LIMIT", "-1"),
        ("MYSQL_DATASOURCE_PROBE_USER_LIMIT", "61"),
        ("MYSQL_DATASOURCE_PROBE_GLOBAL_LIMIT", "601"),
        ("MYSQL_DATASOURCE_PROBE_USER_LIMIT", ""),
        ("MYSQL_DATASOURCE_PROBE_GLOBAL_LIMIT", "1.0"),
        ("MYSQL_DATASOURCE_PROBE_USER_LIMIT", "true"),
        ("MYSQL_DATASOURCE_PROBE_USER_LIMIT", "999999999999999999999"),
        ("MYSQL_DATASOURCE_PROBE_GLOBAL_LIMIT", "５"),
    ],
)
def test_invalid_limits_cannot_disable_guard(monkeypatch, setting, value):
    monkeypatch.setenv(setting, value)
    _assert_denied("actor", 503, 60)
    assert limiter._memory_counts == {}


def test_valid_configured_limits(monkeypatch):
    monkeypatch.setenv("MYSQL_DATASOURCE_PROBE_USER_LIMIT", " 2 ")
    monkeypatch.setenv("MYSQL_DATASOURCE_PROBE_GLOBAL_LIMIT", "3")
    limiter.consume_mysql_datasource_probe("actor-1")
    limiter.consume_mysql_datasource_probe("actor-1")
    _assert_denied("actor-1", 429, 60)
    limiter.consume_mysql_datasource_probe("actor-2")
    _assert_denied("actor-3", 429, 60)


@pytest.mark.parametrize("user_id", [None, "", "   ", 1, "x" * 513])
def test_trusted_nonempty_actor_id_is_required(user_id):
    _assert_denied(user_id, 503, 60)


class FakeRedis:
    def __init__(self, result=(1, 0)):
        self.result = result
        self.calls = []

    def eval(self, *args):
        self.calls.append(args)
        return self.result


def _use_redis(monkeypatch, fake):
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.setattr(
        limiter.AuthSettings,
        "from_env",
        lambda: SimpleNamespace(redis_url="redis://:hidden@cache.invalid/0"),
    )
    urls = []

    def client(url):
        urls.append(url)
        return fake

    monkeypatch.setattr(limiter, "_redis_client", client)
    return urls


def test_redis_reserves_both_quotas_in_one_atomic_eval_with_expiry(monkeypatch):
    fake = FakeRedis()
    urls = _use_redis(monkeypatch, fake)
    limiter.consume_mysql_datasource_probe("actor:private-id")
    assert urls == ["redis://:hidden@cache.invalid/0"]
    assert len(fake.calls) == 1
    script, number_of_keys, user_key, global_key, user_limit, global_limit, window = fake.calls[0]
    assert number_of_keys == 2
    assert (user_limit, global_limit, window) == (5, 30, 60)
    assert "actor:private-id" not in user_key
    assert re.search(r"\{([^}]+)\}", user_key).group(1) == re.search(
        r"\{([^}]+)\}", global_key
    ).group(1)
    assert "EXPIRE" in script
    assert limiter._memory_counts == {}


def test_redis_exhausted_quota_returns_retry_after(monkeypatch):
    fake = FakeRedis([0, 37])
    _use_redis(monkeypatch, fake)
    _assert_denied("actor", 429, 37)


@pytest.mark.parametrize("result", [None, 1, [], [1], [2, 0], [1, 3], [0, 0], [0, 61], [True, 0]])
def test_unexpected_redis_results_fail_closed(monkeypatch, result):
    _use_redis(monkeypatch, FakeRedis(result))
    _assert_denied("actor", 503, 60)


def test_redis_error_does_not_expose_credentials_or_fall_back(monkeypatch, caplog):
    class UnavailableRedis:
        def eval(self, *args):
            raise RuntimeError("connect redis://:sensitive-password@internal-cache:6379")

    _use_redis(monkeypatch, UnavailableRedis())
    error = _assert_denied("actor", 503, 60)
    assert "sensitive-password" not in str(error.detail) + caplog.text
    assert "internal-cache" not in str(error.detail) + caplog.text
    assert limiter._memory_counts == {}


def test_auth_settings_configuration_error_is_sanitized(monkeypatch, caplog):
    monkeypatch.setenv("APP_ENV", "prod")

    def bad_settings():
        raise ValueError("redis://:settings-secret@private-server/0")

    monkeypatch.setattr(limiter.AuthSettings, "from_env", bad_settings)
    error = _assert_denied("actor", 503, 60)
    assert "settings-secret" not in str(error.detail) + caplog.text
    assert "private-server" not in str(error.detail) + caplog.text
