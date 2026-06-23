"""Redis-backed cache and scheduler for expert direct relation demos."""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from redis import Redis
from redis.exceptions import RedisError

from app.schemas.entity_binding import ExpertRelationDemoResponse, ExpertRelationScenario
from app.services.entity_binding import EntityBindingService
from graph_db import connect, GraphDBConfig

logger = logging.getLogger(__name__)

DEFAULT_RELATION_TYPES = ("direct", "two_hop", "three_hop")
DEFAULT_DATA_SOURCES = ("all",)


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _build_service() -> EntityBindingService:
    config = GraphDBConfig.from_env(prefix="GRAPH_DB")
    if not os.environ.get("GRAPH_DB_BACKEND"):
        config.backend = "trs_graph"
    if config.backend == "trs_graph":
        if config.uri == "bolt://localhost:7687":
            config.uri = os.environ.get("GRAPH_DB_URI", "http://localhost:8090")
        if config.database == "neo4j":
            config.database = os.environ.get("GRAPH_DB_DATABASE", "entity_binding_demo")
    db = connect(config)
    try:
        return EntityBindingService(db)
    except Exception:
        db.close()
        raise


@dataclass
class CacheSnapshot:
    relation_type: str
    data_source: str
    updated_at: str
    source: str
    scenarios: list[dict[str, Any]]


class ExpertDirectDemoCache:
    """Redis + memory cache with scheduled refresh and live fallback."""

    def __init__(self) -> None:
        self._redis: Redis | None = None
        self._redis_disabled_until = 0.0
        self._memory_snapshots: dict[str, CacheSnapshot] = {}
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._scheduler_thread: threading.Thread | None = None
        self._refresh_seconds = max(30, int(os.getenv("EXPERT_DIRECT_CACHE_REFRESH_SECONDS", "300")))
        self._redis_retry_seconds = max(10, int(os.getenv("EXPERT_DIRECT_REDIS_RETRY_SECONDS", "60")))
        self._redis_ttl_seconds = max(60, int(os.getenv("EXPERT_DIRECT_CACHE_TTL_SECONDS", "1800")))

    @property
    def cache_prefix(self) -> str:
        return os.getenv("EXPERT_DIRECT_CACHE_PREFIX", "techkg:binding:expert-direct")

    def _cache_key(self, relation_type: str, data_source: str) -> str:
        normalized_relation = (relation_type or "two_hop").strip().lower()
        normalized_source = (data_source or "all").strip().lower()
        return f"{self.cache_prefix}:{normalized_relation}:{normalized_source}:v1"

    def _redis_client(self) -> Redis | None:
        now = time.time()
        if self._redis is not None:
            return self._redis
        if now < self._redis_disabled_until:
            return None

        redis_url = os.getenv("REDIS_URL", "").strip()
        if not redis_url:
            host = os.getenv("REDIS_HOST", "127.0.0.1").strip()
            port = os.getenv("REDIS_PORT", "6379").strip()
            db = os.getenv("REDIS_DB", "0").strip()
            password = os.getenv("REDIS_PASSWORD", "").strip()
            redis_url = f"redis://{host}:{port}/{db}"
            if password:
                redis_url = f"redis://:{password}@{host}:{port}/{db}"

        try:
            client = Redis.from_url(
                redis_url,
                decode_responses=True,
                socket_connect_timeout=float(os.getenv("REDIS_CONNECT_TIMEOUT", "1.5")),
                socket_timeout=float(os.getenv("REDIS_SOCKET_TIMEOUT", "2.5")),
                health_check_interval=int(os.getenv("REDIS_HEALTH_CHECK_INTERVAL", "30")),
                retry_on_timeout=True,
            )
            client.ping()
            self._redis = client
            logger.info("Expert direct cache connected to Redis: %s", redis_url)
            return self._redis
        except Exception as exc:
            self._redis_disabled_until = now + self._redis_retry_seconds
            self._redis = None
            logger.warning("Redis unavailable for expert direct cache, using memory fallback: %s", exc)
            return None

    def _load_from_redis(self, relation_type: str, data_source: str) -> CacheSnapshot | None:
        client = self._redis_client()
        if client is None:
            return None
        key = self._cache_key(relation_type, data_source)
        try:
            payload = client.get(key)
            if not payload:
                return None
            raw = json.loads(payload)
            scenarios = raw.get("scenarios") or []
            if not isinstance(scenarios, list):
                scenarios = []
            snapshot = CacheSnapshot(
                relation_type=str(raw.get("relation_type") or relation_type),
                data_source=str(raw.get("data_source") or data_source),
                updated_at=str(raw.get("updated_at") or _utc_now_text()),
                source="redis",
                scenarios=scenarios,
            )
            with self._lock:
                self._memory_snapshots[key] = snapshot
            return snapshot
        except RedisError as exc:
            self._redis_disabled_until = time.time() + self._redis_retry_seconds
            self._redis = None
            logger.warning("Read expert direct cache from Redis failed, falling back to memory: %s", exc)
        except Exception as exc:
            logger.warning("Invalid expert direct cache payload for %s: %s", key, exc)
        return None

    def _store_to_redis(self, snapshot: CacheSnapshot) -> None:
        client = self._redis_client()
        if client is None:
            return
        key = self._cache_key(snapshot.relation_type, snapshot.data_source)
        payload = json.dumps(
            {
                "relation_type": snapshot.relation_type,
                "data_source": snapshot.data_source,
                "updated_at": snapshot.updated_at,
                "source": snapshot.source,
                "scenarios": snapshot.scenarios,
            },
            ensure_ascii=False,
        )
        try:
            client.set(key, payload, ex=self._redis_ttl_seconds)
        except RedisError as exc:
            self._redis_disabled_until = time.time() + self._redis_retry_seconds
            self._redis = None
            logger.warning("Write expert direct cache to Redis failed, memory snapshot kept: %s", exc)

    def _store_snapshot(self, snapshot: CacheSnapshot) -> None:
        key = self._cache_key(snapshot.relation_type, snapshot.data_source)
        with self._lock:
            self._memory_snapshots[key] = snapshot
        self._store_to_redis(snapshot)

    def _snapshot_from_memory(self, relation_type: str, data_source: str) -> CacheSnapshot | None:
        key = self._cache_key(relation_type, data_source)
        with self._lock:
            return self._memory_snapshots.get(key)

    def _build_snapshot_dicts(
        self,
        relation_type: str,
        data_source: str,
        *,
        prefer_service: bool = True,
    ) -> CacheSnapshot:
        scenarios: list[ExpertRelationScenario] = []
        source = "fallback"
        if prefer_service:
            try:
                service = _build_service()
                try:
                    scenarios = service.build_expert_direct_relation_scenarios(data_source=data_source, relation_type=relation_type)
                    source = "live"
                finally:
                    service.db.close()
            except Exception as exc:
                logger.warning(
                    "Build expert direct cache snapshot with live service failed, using static fallback data: %s",
                    exc,
                )

        if not scenarios:
            scenarios = EntityBindingService._build_fallback_expert_relation_scenarios()

        scenario_dicts = [scenario.model_dump(mode="json") for scenario in scenarios]
        return CacheSnapshot(
            relation_type=(relation_type or "two_hop").strip().lower(),
            data_source=(data_source or "all").strip().lower(),
            updated_at=_utc_now_text(),
            source=source,
            scenarios=scenario_dicts,
        )

    def refresh_snapshot(self, relation_type: str, data_source: str = "all") -> CacheSnapshot:
        snapshot = self._build_snapshot_dicts(relation_type, data_source, prefer_service=True)
        self._store_snapshot(snapshot)
        logger.info(
            "Refreshed expert direct cache snapshot relation_type=%s data_source=%s source=%s size=%s",
            snapshot.relation_type,
            snapshot.data_source,
            snapshot.source,
            len(snapshot.scenarios),
        )
        return snapshot

    def refresh_default_snapshots(self) -> None:
        for relation_type in DEFAULT_RELATION_TYPES:
            for data_source in DEFAULT_DATA_SOURCES:
                try:
                    self.refresh_snapshot(relation_type, data_source)
                except Exception as exc:
                    logger.exception(
                        "Failed to refresh expert direct cache snapshot relation_type=%s data_source=%s: %s",
                        relation_type,
                        data_source,
                        exc,
                    )

    def get_snapshot(self, relation_type: str, data_source: str = "all") -> CacheSnapshot:
        snapshot = self._load_from_redis(relation_type, data_source)
        if snapshot is not None:
            return snapshot
        snapshot = self._snapshot_from_memory(relation_type, data_source)
        if snapshot is not None:
            return snapshot
        snapshot = self._build_snapshot_dicts(relation_type, data_source, prefer_service=True)
        self._store_snapshot(snapshot)
        return snapshot

    def build_response(
        self,
        relation_type: str,
        *,
        data_source: str = "all",
        expert_a_id: str | None = None,
        expert_b_id: str | None = None,
        institution: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
    ) -> ExpertRelationDemoResponse:
        query_params = {
            "dataSource": (data_source or "all").strip().lower(),
            "expertAId": (expert_a_id or "").strip(),
            "expertBId": (expert_b_id or "").strip(),
            "institution": (institution or "").strip(),
            "relationType": (relation_type or "two_hop").strip(),
            "startTime": (start_time or "").strip(),
            "endTime": (end_time or "").strip(),
        }
        snapshot = self.get_snapshot(query_params["relationType"], query_params["dataSource"])
        scenarios = [ExpertRelationScenario.model_validate(item) for item in snapshot.scenarios]
        filtered = EntityBindingService.filter_expert_direct_relation_scenarios(scenarios, query_params)
        for scenario in filtered:
            scenario.api_example["query_params"] = query_params
            scenario.api_example["cache_source"] = snapshot.source
            scenario.api_example["cache_updated_at"] = snapshot.updated_at
        return ExpertRelationDemoResponse(scenarios=filtered)

    def start_scheduler(self) -> None:
        if self._scheduler_thread and self._scheduler_thread.is_alive():
            return
        self._stop_event.clear()
        self.refresh_default_snapshots()
        self._scheduler_thread = threading.Thread(target=self._run_scheduler, name="expert-direct-cache", daemon=True)
        self._scheduler_thread.start()
        logger.info("Expert direct cache scheduler started (every %s seconds)", self._refresh_seconds)

    def stop_scheduler(self) -> None:
        self._stop_event.set()
        thread = self._scheduler_thread
        if thread and thread.is_alive():
            thread.join(timeout=2)
        self._scheduler_thread = None

    def _run_scheduler(self) -> None:
        while not self._stop_event.wait(self._refresh_seconds):
            try:
                self.refresh_default_snapshots()
            except Exception as exc:
                logger.exception("Expert direct cache scheduler refresh failed: %s", exc)


_EXPERT_DIRECT_CACHE = ExpertDirectDemoCache()


def start_expert_direct_cache_scheduler() -> None:
    _EXPERT_DIRECT_CACHE.start_scheduler()


def stop_expert_direct_cache_scheduler() -> None:
    _EXPERT_DIRECT_CACHE.stop_scheduler()


def get_expert_direct_relation_demo_cached(
    *,
    relation_type: str,
    data_source: str = "all",
    expert_a_id: str | None = None,
    expert_b_id: str | None = None,
    institution: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
) -> ExpertRelationDemoResponse:
    return _EXPERT_DIRECT_CACHE.build_response(
        relation_type=relation_type,
        data_source=data_source,
        expert_a_id=expert_a_id,
        expert_b_id=expert_b_id,
        institution=institution,
        start_time=start_time,
        end_time=end_time,
    )
