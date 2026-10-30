"""Query-driven native indexes. DDL/rebuild runs outside request threads.

Redis coordinates the eight API workers. Connection secrets stay in memory.
Only structured, validated tag/field requirements can reach this service.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from redis import Redis

from infra.graph_db.exceptions import GraphRequestError

logger = logging.getLogger(__name__)
IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")
PREFIX = "techkg:auto-index:v1:"
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="graph-index")
_pending: set[str] = set()
_pending_lock = threading.Lock()
_stopping = threading.Event()
_redis_client: Redis | None = None


def enabled() -> bool:
    return os.getenv("TRS_GRAPH_AUTO_INDEX_ENABLED", "true").lower() in {"true", "1", "yes", "on"}


def _redis() -> Redis:
    global _redis_client
    if _redis_client is None:
        from config.auth import AuthSettings

        _redis_client = Redis.from_url(
            AuthSettings.from_env().redis_url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=3,
        )
    return _redis_client


def _identity(settings: Any, label: str, fields: tuple[str, ...]) -> str:
    payload = [settings.base_url.rstrip("/"), settings.space, label, fields]
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False).encode()).hexdigest()


def _save(store: Any, key: str, data: dict, ttl: int) -> None:
    store.set(PREFIX + "job:" + key, json.dumps(data, ensure_ascii=False), ex=ttl)


def request_indexes(settings: Any, label: str, fields: list[str]) -> bool:
    """True: ready/disabled; False: queued/building. Existing SQL permissions are unchanged."""
    if not enabled():
        return True
    fields_tuple = tuple(sorted(set(fields)))
    if not IDENTIFIER.fullmatch(label) or any(not IDENTIFIER.fullmatch(f) for f in fields_tuple):
        raise GraphRequestError("Invalid index requirement", status_code=400)
    if len(fields_tuple) > 16:
        raise GraphRequestError("Too many index fields", status_code=400)
    key = _identity(settings, label, fields_tuple)
    store = _redis()
    try:
        raw = store.get(PREFIX + "job:" + key)
        data = json.loads(raw) if raw else None
        if data:
            if data["status"] == "ready":
                return True
            if data["status"] == "failed":
                raise GraphRequestError(
                    "图索引维护失败，请稍后重试：" + data.get("error", ""), status_code=503
                )
            return False
        with _pending_lock:
            if key in _pending:
                return False
            if len(_pending) >= 128:
                raise GraphRequestError("图索引维护队列已满，请稍后重试", status_code=503)
            data = {
                "space": settings.space,
                "baseUrl": settings.base_url.rstrip("/"),
                "label": label,
                "fields": list(fields_tuple),
                "status": "queued",
            }
            # A crashed worker's reservation expires; the next query can resubmit.
            if not store.set(PREFIX + "job:" + key, json.dumps(data), nx=True, ex=60):
                return False
            _pending.add(key)
            try:
                _executor.submit(_run, settings.model_copy(deep=True), label, fields_tuple, key)
            except Exception:
                _pending.discard(key)
                store.delete(PREFIX + "job:" + key)
                raise
        return False
    except GraphRequestError:
        raise
    except Exception as exc:
        # Without the shared state we cannot prove that a rebuild is complete.
        logger.warning("Auto-index coordination unavailable: %s", type(exc).__name__)
        raise GraphRequestError("图索引维护状态暂不可用，请稍后重试", status_code=503) from exc


def _columns(row: dict) -> tuple[str, ...]:
    cols = row.get("Columns") or []
    if isinstance(cols, str):
        cols = cols.strip("[]").split(",") if cols.strip("[]") else []
    return tuple(str(c).strip().strip(' "`') for c in cols)


def reconcile(
    client: Any, label: str, fields: tuple[str, ...], heartbeat=lambda: None
) -> list[str]:
    """Idempotently reuse/create indexes, wait for rebuild, and EXPLAIN each LOOKUP."""
    heartbeat()
    schema = client.execute_read(f"DESCRIBE TAG `{label}`").records
    types = {str(r["Field"]): str(r["Type"]).lower() for r in schema}
    for field in fields:
        if field not in types:
            raise ValueError(f"Field does not exist: {label}.{field}")
        typ = types[field]
        if not (
            typ in {"string", "bool", "int8", "int16", "int32", "int64", "int", "float", "double"}
            or re.fullmatch(r"fixed_string\(\d+\)", typ)
        ):
            raise ValueError(f"Unsupported native index type: {typ}")
    heartbeat()
    existing = client.execute_read("SHOW TAG INDEXES").records
    heartbeat()
    status_rows = client.execute_read("SHOW TAG INDEX STATUS").records
    statuses = {str(r.get("Name", "")): str(r.get("Index Status", "")).upper() for r in status_rows}
    result = []
    deadline = time.monotonic() + float(os.getenv("TRS_GRAPH_AUTO_INDEX_BUILD_TIMEOUT", "900"))
    for requested in [()] if not fields else [(f,) for f in fields]:
        heartbeat()
        matching = next(
            (
                str(r["Index Name"])
                for r in existing
                if str(r.get("By Tag")) == label and _columns(r) == requested
            ),
            None,
        )
        name = (
            matching
            or "auto_" + hashlib.sha256(json.dumps([label, requested]).encode()).hexdigest()[:24]
        )
        field = requested[0] if requested else None
        column = ""
        if field:
            column = f"`{field}`" + ("(256)" if types[field] == "string" else "")
        if matching is None:
            client.execute_query(f"CREATE TAG INDEX IF NOT EXISTS `{name}` ON `{label}`({column})")
        if statuses.get(name) != "FINISHED":
            submitted = False
            job_id = None
            retries = 0
            while time.monotonic() < deadline:
                heartbeat()
                if not submitted:
                    try:
                        submission = client.execute_query(f"REBUILD TAG INDEX `{name}`")
                        job_id = next(
                            (
                                int(value)
                                for row in submission.records
                                for key, value in row.items()
                                if "job" in key.lower() and str(value).isdigit()
                            ),
                            None,
                        )
                        submitted = True
                    except GraphRequestError as exc:
                        message = str(exc).lower()
                        if "building" in message or "running" in message:
                            submitted = True
                        elif not any(t in message for t in ["not found", "not exist", "not ready"]):
                            raise
                if job_id is not None:
                    rows = client.execute_read(f"SHOW JOB {job_id}").records
                    status = str(rows[0].get("Status", "")).upper() if rows else ""
                else:
                    rows = client.execute_read("SHOW TAG INDEX STATUS").records
                    status = next(
                        (
                            str(r.get("Index Status", "")).upper()
                            for r in rows
                            if str(r.get("Name")) == name
                        ),
                        "",
                    )
                if submitted and status == "FINISHED":
                    break
                if status in {"FAILED", "STOPPED"}:
                    errors = {str(r.get("Error Code", "")) for r in rows} - {"", "SUCCEEDED"}
                    transient = {"E_INDEX_NOT_FOUND", "E_LEADER_CHANGED", "E_RPC_FAILURE"}
                    if errors and errors <= transient and retries < 8:
                        retries += 1
                        logger.warning(
                            "Retrying transient rebuild: index=%s job=%s errors=%s",
                            name,
                            job_id,
                            sorted(errors),
                        )
                        submitted, job_id = False, None
                        time.sleep(min(2**retries, 15))
                        continue
                    raise RuntimeError(
                        f"Index rebuild {status}: {name}; job={job_id}; errors={sorted(errors)}"
                    )
                time.sleep(2)
            else:
                raise TimeoutError(f"Index rebuild timed out: {name}")
        predicate = ""
        if field:
            typ = types[field]
            literal = '""' if "string" in typ else "false" if typ == "bool" else "0"
            predicate = f" WHERE `{label}`.`{field}` == {literal}"
        # LOOKUP requires a native index. The current REST converter does not export planDesc.
        client.execute_explain(f"LOOKUP ON `{label}`{predicate} YIELD id(vertex) AS vid")
        result.append(name)
    return result


def _run(settings: Any, label: str, fields: tuple[str, ...], key: str) -> None:
    from infra.graph_db.client import TRSGraphClient

    client = None
    store = _redis()
    data = {
        "space": settings.space,
        "baseUrl": settings.base_url.rstrip("/"),
        "label": label,
        "fields": list(fields),
        "status": "building",
    }
    instance = hashlib.sha256(settings.base_url.rstrip("/").encode()).hexdigest()
    lock = store.lock(PREFIX + "instance:" + instance, timeout=120, blocking_timeout=5)
    acquired = False
    try:
        acquired = lock.acquire()
        if not acquired:
            # Do not overwrite another worker's building/ready result.
            # The queued reservation expires and a later query can resubmit.
            return
        raw = store.get(PREFIX + "job:" + key)
        if raw and json.loads(raw).get("status") == "ready":
            return

        def heartbeat():
            if _stopping.is_set():
                raise InterruptedError("Index maintenance is shutting down")
            lock.extend(120, replace_ttl=True)
            _save(store, key, data, 120)

        heartbeat()
        client = TRSGraphClient(settings)
        client.connect()
        data["indexNames"] = reconcile(client, label, fields, heartbeat)
        data.update(status="ready", explainAccepted=True, completedAt=time.time())
        _save(store, key, data, 3600)
    except Exception as exc:
        data.update(status="failed", error=str(exc)[:400])
        logger.exception("Index maintenance failed: space=%s tag=%s", settings.space, label)
        try:
            _save(store, key, data, 30)
        except Exception:
            logger.warning("Could not save index failure")
    finally:
        if client is not None:
            client.close()
        if acquired:
            try:
                lock.release()
            except Exception:
                logger.warning("Index lease already expired")
        with _pending_lock:
            _pending.discard(key)


def list_status(settings: Any) -> list[dict]:
    store = _redis()
    jobs = []
    for key in store.scan_iter(match=PREFIX + "job:*", count=100):
        raw = store.get(key)
        if not raw:
            continue
        row = json.loads(raw)
        if row.get("space") == settings.space and row.get("baseUrl") == settings.base_url.rstrip(
            "/"
        ):
            jobs.append({k: v for k, v in row.items() if k != "baseUrl"})
    return sorted(jobs, key=lambda row: (row["label"], row["fields"]))


def invalidate(settings: Any, label: str, fields: list[str]) -> None:
    try:
        _redis().delete(PREFIX + "job:" + _identity(settings, label, tuple(sorted(set(fields)))))
    except Exception:
        logger.warning("Could not invalidate auto-index status")


def stop() -> None:
    if enabled():
        _stopping.set()
        _executor.shutdown(wait=False, cancel_futures=True)
