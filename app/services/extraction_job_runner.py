"""Scheduled worker for extraction persistence jobs."""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any

from redis import Redis
from redis.exceptions import RedisError

from app.services.entity_extraction_writer import persist_extraction_job
from app.services.extraction_task_store import task_store
from app.services.relation_extraction_writer import persist_relation_extraction_job

logger = logging.getLogger(__name__)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ExtractionJobRunner:
    """Poll queued extraction jobs and execute them in a background worker."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._worker_thread: threading.Thread | None = None
        self._redis: Redis | None = None
        self._redis_disabled_until = 0.0
        self._memory_queue: deque[dict[str, Any]] = deque()
        self._poll_seconds = max(1, int(os.getenv("EXTRACTION_JOB_POLL_SECONDS", "5")))
        self._redis_retry_seconds = max(10, int(os.getenv("EXTRACTION_JOB_REDIS_RETRY_SECONDS", "60")))
        self._redis_ttl_seconds = max(300, int(os.getenv("EXTRACTION_JOB_TTL_SECONDS", "86400")))

    @property
    def queue_key(self) -> str:
        return os.getenv("EXTRACTION_JOB_REDIS_KEY", "techkg:extraction:jobs")

    def _redis_client(self) -> Redis | None:
        now = time.time()
        if self._redis is not None:
            return self._redis
        if now < self._redis_disabled_until:
            return None

        redis_url = os.getenv("EXTRACTION_JOB_REDIS_URL", "").strip() or os.getenv("REDIS_URL", "").strip()
        if not redis_url:
            host = os.getenv("REDIS_HOST", "127.0.0.1").strip()
            port = os.getenv("REDIS_PORT", "6379").strip()
            db = os.getenv("REDIS_DB", "0").strip()
            password = os.getenv("REDIS_PASSWORD", "").strip()
            redis_url = f"redis://{host}:{port}/{db}"
            if password:
                redis_url = f"redis://:{password}@{host}:{port}/{db}"

        try:
            socket_timeout = max(float(os.getenv("REDIS_SOCKET_TIMEOUT", "2.5")), self._poll_seconds + 5.0)
            client = Redis.from_url(
                redis_url,
                decode_responses=True,
                socket_connect_timeout=float(os.getenv("REDIS_CONNECT_TIMEOUT", "1.5")),
                socket_timeout=socket_timeout,
                health_check_interval=int(os.getenv("REDIS_HEALTH_CHECK_INTERVAL", "30")),
                retry_on_timeout=True,
            )
            client.ping()
            self._redis = client
            logger.info("Extraction job runner connected to Redis: %s", redis_url)
            return self._redis
        except Exception as exc:
            self._redis = None
            self._redis_disabled_until = now + self._redis_retry_seconds
            logger.warning("Redis unavailable for extraction job runner, using memory queue: %s", exc)
            return None

    def _encode(self, job: dict[str, Any]) -> str:
        return json.dumps(job, ensure_ascii=False)

    def _decode(self, payload: str) -> dict[str, Any]:
        raw = json.loads(payload)
        return raw if isinstance(raw, dict) else {}

    def _push_memory(self, job: dict[str, Any]) -> None:
        with self._lock:
            self._memory_queue.append(job)

    def _pop_memory(self) -> dict[str, Any] | None:
        with self._lock:
            if not self._memory_queue:
                return None
            return self._memory_queue.popleft()

    def enqueue_entity_job(self, *, task_id: str, source_type: str, text: str, entities: list[dict[str, Any]]) -> None:
        job = {
            "job_type": "entity_extraction",
            "task_id": task_id,
            "source_type": source_type,
            "text": text,
            "entities": entities,
            "queued_at": _utc_now(),
        }
        self._enqueue(job)

    def enqueue_relation_job(
        self,
        *,
        task_id: str,
        method: str,
        text: str,
        entities: list[dict[str, Any]],
        relations: list[dict[str, Any]],
    ) -> None:
        job = {
            "job_type": "relation_extraction",
            "task_id": task_id,
            "method": method,
            "text": text,
            "entities": entities,
            "relations": relations,
            "queued_at": _utc_now(),
        }
        self._enqueue(job)

    def _enqueue(self, job: dict[str, Any]) -> None:
        client = self._redis_client()
        if client is None:
            self._push_memory(job)
            return
        try:
            client.lpush(self.queue_key, self._encode(job))
            client.expire(self.queue_key, self._redis_ttl_seconds)
        except RedisError as exc:
            self._redis = None
            self._redis_disabled_until = time.time() + self._redis_retry_seconds
            logger.warning("Enqueue extraction job to Redis failed, falling back to memory: %s", exc)
            self._push_memory(job)

    def _pop_redis_job(self) -> dict[str, Any] | None:
        client = self._redis_client()
        if client is None:
            return None
        try:
            item = client.brpop(self.queue_key, timeout=self._poll_seconds)
            if not item:
                return None
            _, payload = item
            return self._decode(payload)
        except RedisError as exc:
            self._redis = None
            self._redis_disabled_until = time.time() + self._redis_retry_seconds
            logger.warning("Pop extraction job from Redis failed, switching to memory queue: %s", exc)
            return None
        except Exception as exc:
            logger.warning("Invalid extraction job payload from Redis: %s", exc)
            return None

    def _process_entity_job(self, job: dict[str, Any]) -> None:
        task_id = str(job.get("task_id", ""))
        source_type = str(job.get("source_type", "general"))
        text = str(job.get("text", ""))
        entities = list(job.get("entities", []))
        task_store().upsert(
            task_id,
            task_kind="entity_extraction",
            status="running",
            started_at=_utc_now(),
            error="",
            execution_backend="scheduled_worker",
        )
        try:
            result = persist_extraction_job(
                task_id=task_id,
                source_type=source_type,
                source_text=text,
                entities=entities,
            )
            task_store().upsert(
                task_id,
                task_kind="entity_extraction",
                status="succeeded",
                finished_at=result.get("finished_at", _utc_now()),
                written_entities=int(result.get("entity_written", 0)),
                job_node_id=str(result.get("job_node_id", "")),
                source_hash=str(result.get("source_hash", "")),
                storage_backend="redis" if self._redis is not None else "memory",
                execution_backend="scheduled_worker",
                error="",
            )
        except Exception as exc:
            task_store().upsert(
                task_id,
                task_kind="entity_extraction",
                status="failed",
                finished_at=_utc_now(),
                execution_backend="scheduled_worker",
                storage_backend="redis" if self._redis is not None else "memory",
                error=str(exc),
            )

    def _process_relation_job(self, job: dict[str, Any]) -> None:
        task_id = str(job.get("task_id", ""))
        method = str(job.get("method", "rule"))
        text = str(job.get("text", ""))
        entities = list(job.get("entities", []))
        relations = list(job.get("relations", []))
        task_store().upsert(
            task_id,
            task_kind="relation_extraction",
            status="running",
            started_at=_utc_now(),
            error="",
            execution_backend="scheduled_worker",
        )
        try:
            result = persist_relation_extraction_job(
                task_id=task_id,
                method=method,
                source_text=text,
                entities=entities,
                relations=relations,
            )
            task_store().upsert(
                task_id,
                task_kind="relation_extraction",
                status="succeeded",
                finished_at=result.get("finished_at", _utc_now()),
                written_entities=int(result.get("entity_written", 0)),
                written_relations=int(result.get("relation_written", 0)),
                job_node_id=str(result.get("job_node_id", "")),
                source_hash=str(result.get("source_hash", "")),
                storage_backend="redis" if self._redis is not None else "memory",
                execution_backend="scheduled_worker",
                error="",
            )
        except Exception as exc:
            task_store().upsert(
                task_id,
                task_kind="relation_extraction",
                status="failed",
                finished_at=_utc_now(),
                execution_backend="scheduled_worker",
                storage_backend="redis" if self._redis is not None else "memory",
                error=str(exc),
            )

    def _process_job(self, job: dict[str, Any]) -> None:
        job_type = str(job.get("job_type", "")).strip()
        if job_type == "entity_extraction":
            self._process_entity_job(job)
        elif job_type == "relation_extraction":
            self._process_relation_job(job)
        else:
            logger.warning("Unknown extraction job type: %s", job_type)

    def start_scheduler(self) -> None:
        if self._worker_thread and self._worker_thread.is_alive():
            return
        self._stop_event.clear()
        self._worker_thread = threading.Thread(target=self._run_scheduler, name="extraction-job-runner", daemon=True)
        self._worker_thread.start()
        logger.info("Extraction job runner started (poll every %s seconds)", self._poll_seconds)

    def stop_scheduler(self) -> None:
        self._stop_event.set()
        thread = self._worker_thread
        if thread and thread.is_alive():
            thread.join(timeout=2)
        self._worker_thread = None

    def _run_scheduler(self) -> None:
        while not self._stop_event.is_set():
            job = self._pop_redis_job()
            if job is None:
                job = self._pop_memory()
            if job is None:
                continue
            try:
                self._process_job(job)
            except Exception as exc:
                logger.exception("Extraction job execution failed: %s", exc)


_JOB_RUNNER = ExtractionJobRunner()


def start_extraction_job_runner() -> None:
    _JOB_RUNNER.start_scheduler()


def stop_extraction_job_runner() -> None:
    _JOB_RUNNER.stop_scheduler()


def enqueue_entity_extraction_job(*, task_id: str, source_type: str, text: str, entities: list[dict[str, Any]]) -> None:
    _JOB_RUNNER.enqueue_entity_job(task_id=task_id, source_type=source_type, text=text, entities=entities)


def enqueue_relation_extraction_job(
    *,
    task_id: str,
    method: str,
    text: str,
    entities: list[dict[str, Any]],
    relations: list[dict[str, Any]],
) -> None:
    _JOB_RUNNER.enqueue_relation_job(
        task_id=task_id,
        method=method,
        text=text,
        entities=entities,
        relations=relations,
    )
