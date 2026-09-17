"""TRSAlgorithmClient — async graph-algorithm job client for trs-graph-service.

Wraps POST /api/v1/algorithms/{algorithm} (NebulaGraph Algorithm via Spark),
job polling (GET /jobs/{jobId}) and result fetching (GET /jobs/{jobId}/result).
Construction and error handling mirror TRSGraphClient in this package.

Merge note: on merge into tech-kg-api, copy this single file to
backend/infra/graph_db/algorithm_client.py unchanged — its imports already
resolve against the real config/exceptions modules. AlgorithmJob/AlgorithmResult
can later move into models.py and the AlgorithmJob*Error classes into
exceptions.py; field names are already merge-compatible.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, cast

import httpx

from infra.graph_db.config import TRSGraphSettings
from infra.graph_db.exceptions import (
    GraphConnectionError,
    GraphNotFoundError,
    GraphRepoError,
    GraphRequestError,
)

_ALGORITHMS_BASE = "/api/v1/algorithms"

logger = logging.getLogger("infra.graph_db")

# =================================================================
# Algorithm registry
# =================================================================

# Wire (camelCase) algorithm parameter names, verified against the
# BaseAlgorithmRequest subclasses' algorithmParameters() on the server.
_ALGORITHM_PARAMS: dict[str, set[str]] = {
    "pagerank": {"maxIter", "resetProb"},
    "louvain": {"maxIter", "internalIter", "tol"},
    "kcore": {"maxIter", "degree"},
    "labelpropagation": {"maxIter"},
    "connectedcomponent": {"maxIter"},
    "stronglyconnectedcomponent": {"maxIter"},
    "trianglecount": set(),
    "graphtrianglecount": set(),
    "degreestatic": set(),
    "betweenness": {"maxIter"},
    "closeness": set(),
    "clusteringcoefficient": {"type"},
    "jaccard": {"tol"},
    "shortestpaths": {"landmarks"},
    "bfs": {"root", "maxIter"},
    "dfs": {"root", "maxIter"},
    "hanp": {"hopAttenuation", "maxIter", "preference"},
    "node2vec": {
        "maxIter",
        "lr",
        "dim",
        "window",
        "walkLength",
        "numWalks",
        "p",
        "q",
        "directed",
    },
}

# Algorithm parameters the server rejects the request without (@NotBlank).
_ALGORITHM_REQUIRED: dict[str, set[str]] = {
    "shortestpaths": {"landmarks"},
    "bfs": {"root"},
    "dfs": {"root"},
}

_VALID_SINKS = {"csv", "text", "nebula"}
_VALID_WRITE_TYPES = {"insert", "update"}

_CAMEL_RE = re.compile(r"_([a-z0-9])")

# =================================================================
# Exceptions
# =================================================================


class AlgorithmJobBusyError(GraphRequestError):
    """HTTP 429: another Spark job is already running (one at a time)."""


class AlgorithmJobFailedError(GraphRepoError):
    """An algorithm job reached terminal status "failed".

    The full AlgorithmJob snapshot (error, driver_state, log_tail) is attached
    as ``job`` for post-mortem inspection.
    """

    def __init__(self, message: str, *, job: AlgorithmJob) -> None:
        super().__init__(message)
        self.job = job


class AlgorithmJobTimeoutError(GraphRepoError):
    """wait_for_job() exceeded its deadline before a terminal status."""

    def __init__(self, message: str, *, job_id: str, last_status: str | None = None) -> None:
        super().__init__(message)
        self.job_id = job_id
        self.last_status = last_status


# =================================================================
# Response models
# =================================================================


@dataclass
class AlgorithmJob:
    """A submitted graph-algorithm job (submit response or poll snapshot).

    ``created_at`` / ``started_at`` / ``finished_at`` are ISO instants from the
    server; ``driver_state`` is the Spark driver state (RUNNING / FINISHED /
    ERROR / FAILED / KILLED / UNKNOWN) and only appears on poll responses.
    """

    job_id: str
    status: str  # "running" | "succeeded" | "failed"
    created_at: str | None = None
    started_at: str | None = None
    submission_id: str | None = None
    driver_state: str | None = None
    error: str | None = None
    finished_at: str | None = None
    log_tail: str | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @property
    def is_running(self) -> bool:
        return self.status == "running"

    @property
    def is_succeeded(self) -> bool:
        return self.status == "succeeded"

    @property
    def is_failed(self) -> bool:
        return self.status == "failed"

    @property
    def is_done(self) -> bool:
        return self.status != "running"

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> AlgorithmJob:
        """Build from a submit (202) or job-status (200) JSON body."""
        return cls(
            job_id=str(data.get("jobId", "")),
            status=str(data.get("status", "")),
            created_at=data.get("createdAt"),
            started_at=data.get("startedAt"),
            submission_id=data.get("submissionId"),
            driver_state=data.get("driverState"),
            error=data.get("error"),
            finished_at=data.get("finishedAt"),
            log_tail=data.get("logTail"),
            raw=data,
        )


@dataclass
class AlgorithmResult:
    """Result of a succeeded job; the shape depends on the sink used at submit.

    csv:    rows is a list of {header: cell} dicts (cells are strings), count
            is the total row count before the server cap (10000 rows), and
            truncated is True when rows were capped. Use csv_rows.
    text:   rows is a list of raw output lines; count is the pre-cap total.
            Use text_lines.
    nebula: message/space/tag confirm the write-back into NebulaGraph — the
            data lives in the graph, query it with the graph client.
    """

    job_id: str
    sink: str
    rows: list[Any] = field(default_factory=list)
    count: int | None = None
    truncated: bool | None = None  # csv only
    message: str | None = None  # nebula only
    space: str | None = None  # nebula only
    tag: str | None = None  # nebula only
    raw: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @property
    def csv_rows(self) -> list[dict[str, str]]:
        """Rows as header->cell dicts; raises if the sink is not "csv"."""
        if self.sink != "csv":
            raise GraphRequestError(
                f"result sink is {self.sink!r}, not 'csv'",
                status_code=409,
                body=json.dumps(self.raw, ensure_ascii=False),
            )
        return cast("list[dict[str, str]]", self.rows)

    @property
    def text_lines(self) -> list[str]:
        """Rows as raw lines; raises if the sink is not "text"."""
        if self.sink != "text":
            raise GraphRequestError(
                f"result sink is {self.sink!r}, not 'text'",
                status_code=409,
                body=json.dumps(self.raw, ensure_ascii=False),
            )
        return cast("list[str]", self.rows)

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> AlgorithmResult:
        """Build from a job-result (200) JSON body."""
        return cls(
            job_id=str(data.get("jobId", "")),
            sink=str(data.get("sink", "")),
            rows=list(data.get("rows", [])),
            count=data.get("count"),
            truncated=data.get("truncated"),
            message=data.get("message"),
            space=data.get("space"),
            tag=data.get("tag"),
            raw=data,
        )


# =================================================================
# Helpers
# =================================================================


def _to_camel(name: str) -> str:
    """Convert 'max_iter' to 'maxIter'; already-camel keys pass through."""
    return _CAMEL_RE.sub(lambda m: m.group(1).upper(), name)


def _error_detail(body: str) -> str | None:
    """Extract '<error>: <message>' from a GlobalExceptionHandler JSON body.

    Returns None when the body is not a JSON object (nothing to add).
    """
    try:
        data = json.loads(body)
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    error = data.get("error")
    message = data.get("message")
    if message:
        return f"{error}: {message}" if error else str(message)
    return str(error) if error else None


def _algorithm_endpoint(algorithm: str) -> str:
    """Normalize and validate an algorithm name; return the wire name."""
    name = algorithm.strip().lower()
    if name not in _ALGORITHM_PARAMS:
        raise ValueError(
            f"unknown algorithm: {algorithm!r}; expected one of: "
            + ", ".join(sorted(_ALGORITHM_PARAMS))
        )
    return name


def _build_body(
    labels: list[str],
    params: dict[str, Any],
    *,
    sink: str,
    tag: str | None,
    write_type: str,
    weight_cols: list[str] | None,
    has_weight: bool,
    encode_id: bool,
    partition_num: int,
) -> dict[str, Any]:
    """Assemble the camelCase request body, dropping None algorithm params.

    Mirrors the server's own validation so programming errors fail before any
    HTTP call (the server would reject them with 400 anyway).
    """
    if not labels or any(not isinstance(item, str) or not item.strip() for item in labels):
        raise ValueError("labels must be a non-empty list of non-blank strings")
    if sink not in _VALID_SINKS:
        raise ValueError(f"sink must be one of {sorted(_VALID_SINKS)}, got {sink!r}")
    if write_type not in _VALID_WRITE_TYPES:
        raise ValueError(
            f"write_type must be one of {sorted(_VALID_WRITE_TYPES)}, got {write_type!r}"
        )
    if sink == "nebula" and (tag is None or not tag.strip()):
        raise ValueError("tag is required when sink is 'nebula'")
    if has_weight:
        if not weight_cols:
            raise ValueError("weight_cols is required when has_weight is True")
        if len(weight_cols) != len(labels):
            raise ValueError(
                f"weight_cols length ({len(weight_cols)}) must match labels length ({len(labels)})"
            )
    if not 1 <= partition_num <= 10000:
        raise ValueError(f"partition_num must be between 1 and 10000, got {partition_num}")

    body: dict[str, Any] = {
        "labels": list(labels),
        "hasWeight": has_weight,
        "sink": sink,
        "writeType": write_type,
        "encodeId": encode_id,
        "partitionNum": partition_num,
    }
    if weight_cols is not None:
        body["weightCols"] = list(weight_cols)
    if tag is not None:
        body["tag"] = tag
    for key, value in params.items():
        if value is not None:
            body[key] = value
    return body


def _parse_job(data: dict[str, Any]) -> AlgorithmJob:
    return AlgorithmJob.from_payload(data)


def _parse_result(data: dict[str, Any]) -> AlgorithmResult:
    return AlgorithmResult.from_payload(data)


# =================================================================
# Client
# =================================================================


class TRSAlgorithmClient:
    """Async graph-algorithm job client over trs-graph-service.

    Mirrors TRSGraphClient's construction contract (settings plus an optional
    httpx transport test seam). Algorithm jobs are heavyweight Spark
    computations, so they get a dedicated class alongside the CRUD repository.

    Every submit method shares these keyword-only common options (the server's
    BaseAlgorithmRequest fields):

        sink: result destination — "csv" (default), "text" or "nebula".
        tag: Nebula tag to write results to; required when sink="nebula".
        write_type: how nebula results are written — "insert" or "update".
        weight_cols: per-label weight property; required when has_weight is
            True, and its length must equal len(labels).
        has_weight: compute over weighted edges.
        encode_id: encode vertex ids before computing.
        partition_num: Spark partition count, 1..10000.

    Algorithm-specific parameters are keyword-only and default to None —
    None means "omit from the request so the server applies its default".

    Submitting returns an AlgorithmJob with status "running"; poll it with
    wait_for_job(), then fetch rows with get_result() — or use run() to do
    submit + wait + fetch in one call. Only one job may run at a time
    service-wide; submitting while one runs raises AlgorithmJobBusyError.

    Args:
        settings: Connection settings.
        transport: Optional httpx transport (test seam for MockTransport).
    """

    def __init__(
        self,
        settings: TRSGraphSettings,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._settings = settings
        self._transport = transport
        self._client: httpx.Client | None = None

    # ----- connection lifecycle -----

    def connect(self) -> None:
        if self._client is not None:
            return
        headers = {"X-Graph-Space": self._settings.space}
        if self._settings.api_key:
            headers["X-API-Key"] = self._settings.api_key
        self._client = httpx.Client(
            base_url=self._settings.base_url,
            headers=headers,
            timeout=self._settings.timeout,
            transport=self._transport,
        )
        try:
            resp = self._client.get("/health")
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            self._client.close()
            self._client = None
            raise GraphConnectionError(
                f"Cannot connect to trs-graph-service at {self._settings.base_url}"
            ) from exc
        logger.info(
            "Connected to TRS Graph algorithms API at %s (space: %s)",
            self._settings.base_url,
            self._settings.space,
        )

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None
        logger.info("Disconnected from TRS Graph algorithms API")

    def is_connected(self) -> bool:
        if self._client is None:
            return False
        try:
            resp = self._client.get("/health")
            resp.raise_for_status()
            return resp.json().get("status") == "UP"
        except Exception:
            return False

    # ----- internal HTTP helper -----

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> httpx.Response:
        if self._client is None:
            raise GraphConnectionError("Not connected — call connect() first")
        try:
            resp = self._client.request(method, path, json=json, params=params)
        except httpx.HTTPError as exc:
            raise GraphConnectionError(f"Request failed: {method} {path}") from exc
        if resp.status_code == 404:
            detail = _error_detail(resp.text)
            suffix = f": {detail}" if detail else ""
            raise GraphNotFoundError(f"{method} {path} -> 404{suffix}")
        if not resp.is_success:
            detail = _error_detail(resp.text)
            suffix = f": {detail}" if detail else ""
            message = f"{method} {path} -> {resp.status_code}{suffix}"
            if resp.status_code == 429:
                raise AlgorithmJobBusyError(message, status_code=429, body=resp.text)
            raise GraphRequestError(message, status_code=resp.status_code, body=resp.text)
        return resp

    # ==================================================================
    # Submitting jobs
    # ===================================================================

    def _submit(
        self,
        algorithm: str,
        labels: list[str],
        params: dict[str, Any],
        *,
        sink: str,
        tag: str | None,
        write_type: str,
        weight_cols: list[str] | None,
        has_weight: bool,
        encode_id: bool,
        partition_num: int,
    ) -> AlgorithmJob:
        body = _build_body(
            labels,
            params,
            sink=sink,
            tag=tag,
            write_type=write_type,
            weight_cols=weight_cols,
            has_weight=has_weight,
            encode_id=encode_id,
            partition_num=partition_num,
        )
        resp = self._request("POST", f"{_ALGORITHMS_BASE}/{algorithm}", json=body)
        return _parse_job(resp.json())

    def submit(
        self,
        algorithm: str,
        labels: list[str],
        *,
        sink: str = "csv",
        tag: str | None = None,
        write_type: str = "update",
        weight_cols: list[str] | None = None,
        has_weight: bool = False,
        encode_id: bool = False,
        partition_num: int = 1,
        **params: Any,
    ) -> AlgorithmJob:
        """Submit a job by algorithm name ('pagerank', 'bfs', ...).

        params are keyword-only algorithm parameters and accept snake_case
        (preferred, e.g. max_iter) or camelCase (maxIter) keys. Unknown
        algorithms, unknown parameters or missing required ones raise
        ValueError before any HTTP call.
        """
        name = _algorithm_endpoint(algorithm)
        camel = {_to_camel(key): value for key, value in params.items()}
        allowed = _ALGORITHM_PARAMS[name]
        unknown = set(camel) - allowed
        if unknown:
            raise ValueError(
                f"{name} does not accept {sorted(unknown)}; allowed params: "
                + (", ".join(sorted(allowed)) or "(none)")
            )
        missing = {key for key in _ALGORITHM_REQUIRED.get(name, set()) if camel.get(key) is None}
        if missing:
            raise ValueError(f"{name} requires {sorted(missing)}")
        return self._submit(
            name,
            labels,
            camel,
            sink=sink,
            tag=tag,
            write_type=write_type,
            weight_cols=weight_cols,
            has_weight=has_weight,
            encode_id=encode_id,
            partition_num=partition_num,
        )

    def pagerank(
        self,
        labels: list[str],
        *,
        max_iter: int | None = None,
        reset_prob: float | None = None,
        sink: str = "csv",
        tag: str | None = None,
        write_type: str = "update",
        weight_cols: list[str] | None = None,
        has_weight: bool = False,
        encode_id: bool = False,
        partition_num: int = 1,
    ) -> AlgorithmJob:
        """Submit a PageRank job — vertex importance (output: ``pagerank``).

        Common options and the job lifecycle are documented on the class.
        """
        return self._submit(
            "pagerank",
            labels,
            {"maxIter": max_iter, "resetProb": reset_prob},
            sink=sink,
            tag=tag,
            write_type=write_type,
            weight_cols=weight_cols,
            has_weight=has_weight,
            encode_id=encode_id,
            partition_num=partition_num,
        )

    def louvain(
        self,
        labels: list[str],
        *,
        max_iter: int | None = None,
        internal_iter: int | None = None,
        tol: float | None = None,
        sink: str = "csv",
        tag: str | None = None,
        write_type: str = "update",
        weight_cols: list[str] | None = None,
        has_weight: bool = False,
        encode_id: bool = False,
        partition_num: int = 1,
    ) -> AlgorithmJob:
        """Submit a Louvain job — community detection (output: ``louvain``)."""
        return self._submit(
            "louvain",
            labels,
            {"maxIter": max_iter, "internalIter": internal_iter, "tol": tol},
            sink=sink,
            tag=tag,
            write_type=write_type,
            weight_cols=weight_cols,
            has_weight=has_weight,
            encode_id=encode_id,
            partition_num=partition_num,
        )

    def kcore(
        self,
        labels: list[str],
        *,
        max_iter: int | None = None,
        degree: int | None = None,
        sink: str = "csv",
        tag: str | None = None,
        write_type: str = "update",
        weight_cols: list[str] | None = None,
        has_weight: bool = False,
        encode_id: bool = False,
        partition_num: int = 1,
    ) -> AlgorithmJob:
        """Submit a K-Core job — k-core decomposition (output: ``kcore``)."""
        return self._submit(
            "kcore",
            labels,
            {"maxIter": max_iter, "degree": degree},
            sink=sink,
            tag=tag,
            write_type=write_type,
            weight_cols=weight_cols,
            has_weight=has_weight,
            encode_id=encode_id,
            partition_num=partition_num,
        )

    def labelpropagation(
        self,
        labels: list[str],
        *,
        max_iter: int | None = None,
        sink: str = "csv",
        tag: str | None = None,
        write_type: str = "update",
        weight_cols: list[str] | None = None,
        has_weight: bool = False,
        encode_id: bool = False,
        partition_num: int = 1,
    ) -> AlgorithmJob:
        """Submit a Label Propagation job — community detection (output: ``lpa``)."""
        return self._submit(
            "labelpropagation",
            labels,
            {"maxIter": max_iter},
            sink=sink,
            tag=tag,
            write_type=write_type,
            weight_cols=weight_cols,
            has_weight=has_weight,
            encode_id=encode_id,
            partition_num=partition_num,
        )

    def connected_component(
        self,
        labels: list[str],
        *,
        max_iter: int | None = None,
        sink: str = "csv",
        tag: str | None = None,
        write_type: str = "update",
        weight_cols: list[str] | None = None,
        has_weight: bool = False,
        encode_id: bool = False,
        partition_num: int = 1,
    ) -> AlgorithmJob:
        """Submit a Connected Component job — weakly connected (output: ``cc``)."""
        return self._submit(
            "connectedcomponent",
            labels,
            {"maxIter": max_iter},
            sink=sink,
            tag=tag,
            write_type=write_type,
            weight_cols=weight_cols,
            has_weight=has_weight,
            encode_id=encode_id,
            partition_num=partition_num,
        )

    def strongly_connected_component(
        self,
        labels: list[str],
        *,
        max_iter: int | None = None,
        sink: str = "csv",
        tag: str | None = None,
        write_type: str = "update",
        weight_cols: list[str] | None = None,
        has_weight: bool = False,
        encode_id: bool = False,
        partition_num: int = 1,
    ) -> AlgorithmJob:
        """Submit a Strongly Connected Component job (output: ``scc``)."""
        return self._submit(
            "stronglyconnectedcomponent",
            labels,
            {"maxIter": max_iter},
            sink=sink,
            tag=tag,
            write_type=write_type,
            weight_cols=weight_cols,
            has_weight=has_weight,
            encode_id=encode_id,
            partition_num=partition_num,
        )

    def triangle_count(
        self,
        labels: list[str],
        *,
        sink: str = "csv",
        tag: str | None = None,
        write_type: str = "update",
        weight_cols: list[str] | None = None,
        has_weight: bool = False,
        encode_id: bool = False,
        partition_num: int = 1,
    ) -> AlgorithmJob:
        """Submit a Triangle Count job — per-vertex (output: ``trianglecount``)."""
        return self._submit(
            "trianglecount",
            labels,
            {},
            sink=sink,
            tag=tag,
            write_type=write_type,
            weight_cols=weight_cols,
            has_weight=has_weight,
            encode_id=encode_id,
            partition_num=partition_num,
        )

    def graph_triangle_count(
        self,
        labels: list[str],
        *,
        sink: str = "csv",
        tag: str | None = None,
        write_type: str = "update",
        weight_cols: list[str] | None = None,
        has_weight: bool = False,
        encode_id: bool = False,
        partition_num: int = 1,
    ) -> AlgorithmJob:
        """Submit a Graph Triangle Count job — whole-graph (output: ``count``)."""
        return self._submit(
            "graphtrianglecount",
            labels,
            {},
            sink=sink,
            tag=tag,
            write_type=write_type,
            weight_cols=weight_cols,
            has_weight=has_weight,
            encode_id=encode_id,
            partition_num=partition_num,
        )

    def degree_static(
        self,
        labels: list[str],
        *,
        sink: str = "csv",
        tag: str | None = None,
        write_type: str = "update",
        weight_cols: list[str] | None = None,
        has_weight: bool = False,
        encode_id: bool = False,
        partition_num: int = 1,
    ) -> AlgorithmJob:
        """Submit a Degree Statistics job (output: ``degree``/``inDegree``/``outDegree``)."""
        return self._submit(
            "degreestatic",
            labels,
            {},
            sink=sink,
            tag=tag,
            write_type=write_type,
            weight_cols=weight_cols,
            has_weight=has_weight,
            encode_id=encode_id,
            partition_num=partition_num,
        )

    def betweenness(
        self,
        labels: list[str],
        *,
        max_iter: int | None = None,
        sink: str = "csv",
        tag: str | None = None,
        write_type: str = "update",
        weight_cols: list[str] | None = None,
        has_weight: bool = False,
        encode_id: bool = False,
        partition_num: int = 1,
    ) -> AlgorithmJob:
        """Submit a Betweenness Centrality job — key-node mining (output: ``betweenness``)."""
        return self._submit(
            "betweenness",
            labels,
            {"maxIter": max_iter},
            sink=sink,
            tag=tag,
            write_type=write_type,
            weight_cols=weight_cols,
            has_weight=has_weight,
            encode_id=encode_id,
            partition_num=partition_num,
        )

    def closeness(
        self,
        labels: list[str],
        *,
        sink: str = "csv",
        tag: str | None = None,
        write_type: str = "update",
        weight_cols: list[str] | None = None,
        has_weight: bool = False,
        encode_id: bool = False,
        partition_num: int = 1,
    ) -> AlgorithmJob:
        """Submit a Closeness Centrality job — node influence (output: ``closeness``)."""
        return self._submit(
            "closeness",
            labels,
            {},
            sink=sink,
            tag=tag,
            write_type=write_type,
            weight_cols=weight_cols,
            has_weight=has_weight,
            encode_id=encode_id,
            partition_num=partition_num,
        )

    def clustering_coefficient(
        self,
        labels: list[str],
        *,
        coefficient_type: str | None = None,
        sink: str = "csv",
        tag: str | None = None,
        write_type: str = "update",
        weight_cols: list[str] | None = None,
        has_weight: bool = False,
        encode_id: bool = False,
        partition_num: int = 1,
    ) -> AlgorithmJob:
        """Submit a Clustering Coefficient job (output: ``clustercoefficient``).

        coefficient_type: "local" (default) or "global" aggregation.
        """
        return self._submit(
            "clusteringcoefficient",
            labels,
            {"type": coefficient_type},
            sink=sink,
            tag=tag,
            write_type=write_type,
            weight_cols=weight_cols,
            has_weight=has_weight,
            encode_id=encode_id,
            partition_num=partition_num,
        )

    def jaccard(
        self,
        labels: list[str],
        *,
        tol: float | None = None,
        sink: str = "csv",
        tag: str | None = None,
        write_type: str = "update",
        weight_cols: list[str] | None = None,
        has_weight: bool = False,
        encode_id: bool = False,
        partition_num: int = 1,
    ) -> AlgorithmJob:
        """Submit a Jaccard Similarity job — neighbourhood similarity (output: ``jaccard``)."""
        return self._submit(
            "jaccard",
            labels,
            {"tol": tol},
            sink=sink,
            tag=tag,
            write_type=write_type,
            weight_cols=weight_cols,
            has_weight=has_weight,
            encode_id=encode_id,
            partition_num=partition_num,
        )

    def shortest_paths(
        self,
        labels: list[str],
        *,
        landmarks: str,
        sink: str = "csv",
        tag: str | None = None,
        write_type: str = "update",
        weight_cols: list[str] | None = None,
        has_weight: bool = False,
        encode_id: bool = False,
        partition_num: int = 1,
    ) -> AlgorithmJob:
        """Submit a Shortest Paths job from landmark vertices (output: ``shortestpath``).

        landmarks: comma-separated vertex ids, e.g. "1,3" (required).
        """
        return self._submit(
            "shortestpaths",
            labels,
            {"landmarks": landmarks},
            sink=sink,
            tag=tag,
            write_type=write_type,
            weight_cols=weight_cols,
            has_weight=has_weight,
            encode_id=encode_id,
            partition_num=partition_num,
        )

    def bfs(
        self,
        labels: list[str],
        *,
        root: str,
        max_iter: int | None = None,
        sink: str = "csv",
        tag: str | None = None,
        write_type: str = "update",
        weight_cols: list[str] | None = None,
        has_weight: bool = False,
        encode_id: bool = False,
        partition_num: int = 1,
    ) -> AlgorithmJob:
        """Submit a BFS job from a root vertex (output: ``bfs``).

        root: the start vertex id (required).
        """
        return self._submit(
            "bfs",
            labels,
            {"root": root, "maxIter": max_iter},
            sink=sink,
            tag=tag,
            write_type=write_type,
            weight_cols=weight_cols,
            has_weight=has_weight,
            encode_id=encode_id,
            partition_num=partition_num,
        )

    def dfs(
        self,
        labels: list[str],
        *,
        root: str,
        max_iter: int | None = None,
        sink: str = "csv",
        tag: str | None = None,
        write_type: str = "update",
        weight_cols: list[str] | None = None,
        has_weight: bool = False,
        encode_id: bool = False,
        partition_num: int = 1,
    ) -> AlgorithmJob:
        """Submit a DFS job from a root vertex (output: ``dfs``).

        root: the start vertex id (required).
        """
        return self._submit(
            "dfs",
            labels,
            {"root": root, "maxIter": max_iter},
            sink=sink,
            tag=tag,
            write_type=write_type,
            weight_cols=weight_cols,
            has_weight=has_weight,
            encode_id=encode_id,
            partition_num=partition_num,
        )

    def hanp(
        self,
        labels: list[str],
        *,
        hop_attenuation: float | None = None,
        max_iter: int | None = None,
        preference: float | None = None,
        sink: str = "csv",
        tag: str | None = None,
        write_type: str = "update",
        weight_cols: list[str] | None = None,
        has_weight: bool = False,
        encode_id: bool = False,
        partition_num: int = 1,
    ) -> AlgorithmJob:
        """Submit a HANP job — label propagation with hop attenuation (output: ``hanp``)."""
        return self._submit(
            "hanp",
            labels,
            {"hopAttenuation": hop_attenuation, "maxIter": max_iter, "preference": preference},
            sink=sink,
            tag=tag,
            write_type=write_type,
            weight_cols=weight_cols,
            has_weight=has_weight,
            encode_id=encode_id,
            partition_num=partition_num,
        )

    def node2vec(
        self,
        labels: list[str],
        *,
        max_iter: int | None = None,
        lr: float | None = None,
        dim: int | None = None,
        window: int | None = None,
        walk_length: int | None = None,
        num_walks: int | None = None,
        p: float | None = None,
        q: float | None = None,
        directed: bool | None = None,
        sink: str = "csv",
        tag: str | None = None,
        write_type: str = "update",
        weight_cols: list[str] | None = None,
        has_weight: bool = False,
        encode_id: bool = False,
        partition_num: int = 1,
    ) -> AlgorithmJob:
        """Submit a Node2Vec job — node embeddings via random walks (output: ``node2vec``)."""
        return self._submit(
            "node2vec",
            labels,
            {
                "maxIter": max_iter,
                "lr": lr,
                "dim": dim,
                "window": window,
                "walkLength": walk_length,
                "numWalks": num_walks,
                "p": p,
                "q": q,
                "directed": directed,
            },
            sink=sink,
            tag=tag,
            write_type=write_type,
            weight_cols=weight_cols,
            has_weight=has_weight,
            encode_id=encode_id,
            partition_num=partition_num,
        )

    # ==================================================================
    # Job lifecycle
    # ===================================================================

    def get_job(self, job_id: str) -> AlgorithmJob:
        """Fetch a job's status snapshot; GraphNotFoundError for unknown jobs."""
        resp = self._request("GET", f"{_ALGORITHMS_BASE}/jobs/{job_id}")
        return _parse_job(resp.json())

    def get_result(self, job_id: str) -> AlgorithmResult:
        """Fetch a succeeded job's result.

        Raises GraphNotFoundError (404: unknown job, or no result directory —
        e.g. the sink was nebula, or the service restarted) and
        GraphRequestError (409: the job is still running or has failed —
        wait_for_job() first).
        """
        resp = self._request("GET", f"{_ALGORITHMS_BASE}/jobs/{job_id}/result")
        return _parse_result(resp.json())

    def wait_for_job(
        self,
        job_id: str,
        *,
        timeout_s: float = 600.0,
        poll_interval_s: float = 5.0,
    ) -> AlgorithmJob:
        """Poll a job until it reaches a terminal status; return the final job.

        Raises AlgorithmJobFailedError (the snapshot on .job carries error,
        driver_state and log_tail) when the job failed,
        AlgorithmJobTimeoutError when timeout_s elapses first, and
        GraphNotFoundError if the job vanishes (service restart).
        """
        if timeout_s <= 0 or poll_interval_s <= 0:
            raise ValueError("timeout_s and poll_interval_s must be positive")
        deadline = time.monotonic() + timeout_s
        while True:
            job = self.get_job(job_id)
            if job.is_failed:
                reason = job.error or job.driver_state or "unknown error"
                raise AlgorithmJobFailedError(f"algorithm job {job_id} failed: {reason}", job=job)
            if job.is_succeeded:
                return job
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise AlgorithmJobTimeoutError(
                    f"algorithm job {job_id} did not reach a terminal status "
                    f"within {timeout_s}s (last status: {job.status})",
                    job_id=job_id,
                    last_status=job.status,
                )
            sleep_for = min(poll_interval_s, remaining)
            logger.debug("job %s still %s; polling again in %.1fs", job_id, job.status, sleep_for)
            time.sleep(sleep_for)

    def run(
        self,
        algorithm: str,
        labels: list[str],
        *,
        timeout_s: float = 600.0,
        poll_interval_s: float = 5.0,
        sink: str = "csv",
        tag: str | None = None,
        write_type: str = "update",
        weight_cols: list[str] | None = None,
        has_weight: bool = False,
        encode_id: bool = False,
        partition_num: int = 1,
        **params: Any,
    ) -> AlgorithmResult:
        """Submit a job, wait for it and fetch its result in one call.

        Works for every sink — nebula returns the write-back confirmation
        body. AlgorithmJobBusyError / AlgorithmJobFailedError /
        AlgorithmJobTimeoutError propagate from the submit and wait steps.
        """
        job = self.submit(
            algorithm,
            labels,
            sink=sink,
            tag=tag,
            write_type=write_type,
            weight_cols=weight_cols,
            has_weight=has_weight,
            encode_id=encode_id,
            partition_num=partition_num,
            **params,
        )
        self.wait_for_job(job.job_id, timeout_s=timeout_s, poll_interval_s=poll_interval_s)
        return self.get_result(job.job_id)

    # ==================================================================
    # Health
    # ===================================================================

    def health(self) -> dict[str, Any]:
        """Graph-computing subsystem health: {'status': 'UP', 'activeJobs': int}."""
        resp = self._request("GET", f"{_ALGORITHMS_BASE}/health")
        return resp.json()


__all__ = [
    "TRSAlgorithmClient",
    "AlgorithmJob",
    "AlgorithmResult",
    "AlgorithmJobBusyError",
    "AlgorithmJobFailedError",
    "AlgorithmJobTimeoutError",
]
