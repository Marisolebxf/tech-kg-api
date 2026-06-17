"""Exceptions raised by the trs-graph repository layer."""

from __future__ import annotations


class GraphRepoError(Exception):
    """Base class for all graph repository errors."""


class GraphConnectionError(GraphRepoError):
    """Raised when the trs-graph-service is unreachable or not connected."""


class GraphNotFoundError(GraphRepoError):
    """Raised on HTTP 404 from trs-graph-service."""


class GraphRequestError(GraphRepoError):
    """Raised on non-2xx (non-404) HTTP responses from trs-graph-service."""

    def __init__(self, message: str, *, status_code: int, body: str = "") -> None:
        super().__init__(message)
        self.status_code = status_code
        self.body = body
