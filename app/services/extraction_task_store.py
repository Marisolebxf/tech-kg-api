"""Redis-backed task registry for extraction jobs with in-memory fallback."""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any

from redis import Redis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_default(value: Any) -> Any:
    if isinstance(value, set):
        return list(value)
    return str(value)


class ExtractionTaskStore:
    """Store extraction task metadata in Redis and keep an in-memory fallback."""

    TERMINAL_STATUSES = {"succeeded", "failed", "cancelled"}

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._records: dict[str, dict[str, Any]] = {}
        self._redis: Redis | None = None
        self._redis_disabled_until = 0.0
        self._stop_event = threading.Event()
        self._scheduler_thread: threading.Thread | None = None
        self._flush_seconds = max(10, int(os.getenv("EXTRACTION_TASK_FLUSH_SECONDS", "30")))
        self._redis_retry_seconds = max(10, int(os.getenv("EXTRACTION_TASK_REDIS_RETRY_SECONDS", "60")))
        self._redis_ttl_seconds = max(300, int(os.getenv("EXTRACTION_TASK_TTL_SECONDS", "86400")))

    @property
    def cache_prefix(self) -> str:
        return os.getenv("EXTRACTION_TASK_REDIS_PREFIX", "techkg:extraction:task")

    def _task_key(self, task_id: str) -> str:
        return f"{self.cache_prefix}:{task_id}"

    def _redis_client(self) -> Redis | None:
        now = time.time()
        if self._redis is not None:
            return self._redis
        if now < self._redis_disabled_until:
            return None

        redis_url = os.getenv("EXTRACTION_TASK_REDIS_URL", "").strip() or os.getenv("REDIS_URL", "").strip()
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
            logger.info("Extraction task store connected to Redis: %s", redis_url)
            return self._redis
        except Exception as exc:
            self._redis = None
            self._redis_disabled_until = now + self._redis_retry_seconds
            logger.warning("Redis unavailable for extraction task store, using memory fallback: %s", exc)
            return None

    def _encode(self, record: dict[str, Any]) -> str:
        return json.dumps(record, ensure_ascii=False, default=_json_default)

    def _decode(self, payload: str) -> dict[str, Any]:
        raw = json.loads(payload)
        return raw if isinstance(raw, dict) else {}

    def _write_to_redis(self, task_id: str, record: dict[str, Any]) -> bool:
        client = self._redis_client()
        if client is None:
            return False
        try:
            client.set(self._task_key(task_id), self._encode(record), ex=self._redis_ttl_seconds)
            return True
        except RedisError as exc:
            self._redis = None
            self._redis_disabled_until = time.time() + self._redis_retry_seconds
            logger.warning("Write extraction task to Redis failed, memory fallback kept: %s", exc)
            return False

    def _read_from_redis(self, task_id: str) -> dict[str, Any] | None:
        client = self._redis_client()
        if client is None:
            return None
        try:
            payload = client.get(self._task_key(task_id))
            if not payload:
                return None
            record = self._decode(payload)
            with self._lock:
                self._records[task_id] = record
            return record
        except RedisError as exc:
            self._redis = None
            self._redis_disabled_until = time.time() + self._redis_retry_seconds
            logger.warning("Read extraction task from Redis failed, memory fallback will be used: %s", exc)
            return None
        except Exception as exc:
            logger.warning("Invalid extraction task payload for %s: %s", task_id, exc)
            return None

    def upsert(self, task_id: str, **fields: Any) -> dict[str, Any]:
        fields.pop("task_id", None)
        with self._lock:
            record = self._records.setdefault(task_id, {})
            record.update(fields)
            record["task_id"] = task_id
            record["updated_at"] = _utc_now()
            self._records[task_id] = record
            payload = dict(record)
        written = self._write_to_redis(task_id, payload)
        with self._lock:
            payload["storage_backend"] = "redis" if written else "memory"
            payload["updated_at"] = _utc_now()
            self._records[task_id] = dict(payload)
        if written:
            self._write_to_redis(task_id, payload)
        return payload

    def get(self, task_id: str) -> dict[str, Any]:
        with self._lock:
            record = self._records.get(task_id)
            if record is not None:
                return dict(record)
        record = self._read_from_redis(task_id)
        return dict(record) if record else {}

    def snapshot(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            return {task_id: dict(record) for task_id, record in self._records.items()}

    def flush_to_redis(self) -> None:
        with self._lock:
            records = list(self._records.items())
        for task_id, record in records:
            self._write_to_redis(task_id, record)

    def start_scheduler(self) -> None:
        if self._scheduler_thread and self._scheduler_thread.is_alive():
            return
        self._stop_event.clear()
        self.flush_to_redis()
        self._scheduler_thread = threading.Thread(target=self._run_scheduler, name="extraction-task-store", daemon=True)
        self._scheduler_thread.start()
        logger.info("Extraction task store scheduler started (every %s seconds)", self._flush_seconds)

    def stop_scheduler(self) -> None:
        self._stop_event.set()
        thread = self._scheduler_thread
        if thread and thread.is_alive():
            thread.join(timeout=2)
        self._scheduler_thread = None

    def _run_scheduler(self) -> None:
        while not self._stop_event.wait(self._flush_seconds):
            try:
                self.flush_to_redis()
            except Exception as exc:
                logger.exception("Extraction task store scheduler flush failed: %s", exc)


_TASK_STORE = ExtractionTaskStore()


def start_extraction_task_store_scheduler() -> None:
    _TASK_STORE.start_scheduler()


def stop_extraction_task_store_scheduler() -> None:
    _TASK_STORE.stop_scheduler()


def task_store() -> ExtractionTaskStore:
    return _TASK_STORE
