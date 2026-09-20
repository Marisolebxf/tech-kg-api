from __future__ import annotations

import asyncio
import time

import pytest

from biz.handler import entity_search as entity_search_handler
from infra.entity_response_cache import EntityResponseCache, build_cache_key
from infra.redis import MemoryJsonStore


@pytest.mark.asyncio
async def test_shared_store_serves_second_worker(monkeypatch: pytest.MonkeyPatch) -> None:
    store = MemoryJsonStore()
    monkeypatch.setattr("infra.entity_response_cache.get_json_store", lambda: store)
    key = build_cache_key("browse", space="dev2", limit=10, offset=0)
    worker_a = EntityResponseCache(namespace="entity:test", ttl_seconds=60)
    worker_b = EntityResponseCache(namespace="entity:test", ttl_seconds=60)

    await worker_a.put(key, '{"data":{"items":[1]}}')

    assert await worker_b.get(key) == '{"data":{"items":[1]}}'


@pytest.mark.asyncio
async def test_clear_invalidates_shared_and_local_entries(monkeypatch: pytest.MonkeyPatch) -> None:
    store = MemoryJsonStore()
    monkeypatch.setattr("infra.entity_response_cache.get_json_store", lambda: store)
    key = build_cache_key("search", space="dev2", keyword="张三")
    worker_a = EntityResponseCache(namespace="entity:test-clear", ttl_seconds=60)
    worker_b = EntityResponseCache(namespace="entity:test-clear", ttl_seconds=60)
    await worker_a.put(key, '{"data":{"items":[]}}')
    assert await worker_b.get(key) is not None

    await worker_a.clear()
    worker_b.clear_local()

    assert await worker_b.get(key) is None


def test_cache_key_is_stable_and_does_not_expose_keyword() -> None:
    first = build_cache_key("search", keyword="张三", space="dev2")
    second = build_cache_key("search", space="dev2", keyword="张三")

    assert first == second
    assert "张三" not in first


@pytest.mark.asyncio
async def test_cold_concurrent_browse_requests_are_collapsed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = MemoryJsonStore()
    monkeypatch.setattr("infra.entity_response_cache.get_json_store", lambda: store)
    cache = EntityResponseCache(namespace="entity:test-collapse", ttl_seconds=60)
    monkeypatch.setattr(entity_search_handler, "_browse_cache", cache)
    monkeypatch.setattr(entity_search_handler, "_request_locks", {})
    monkeypatch.setattr(entity_search_handler, "_request_locks_guard", asyncio.Lock())

    class FakeApplication:
        calls = 0

        def browse(self, **kwargs):
            self.calls += 1
            time.sleep(0.05)
            return {
                "items": [],
                "offset": kwargs["offset"],
                "limit": kwargs["limit"],
                "total": 0,
                "entityType": kwargs["entity_type"],
                "mode": "browse",
            }

    application = FakeApplication()
    monkeypatch.setattr(entity_search_handler, "_application", lambda session: application)
    query = {
        "space": "dev2",
        "entity_type": None,
        "limit": 10,
        "offset": 0,
    }

    first, second = await asyncio.gather(
        entity_search_handler._load_browse_payload(object(), **query),
        entity_search_handler._load_browse_payload(object(), **query),
    )

    assert application.calls == 1
    assert {first[1], second[1]} == {False, True}
    assert first[0] == second[0]
