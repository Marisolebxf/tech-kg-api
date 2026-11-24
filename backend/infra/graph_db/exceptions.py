"""Exceptions raised by the trs-graph repository layer."""

from __future__ import annotations

import re


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


_INTERNAL_PREFIX = re.compile(r"^(?:GET|POST|PUT|PATCH|DELETE)\s+\S+\s+->\s*\d*:?\s*")
_RESOURCE_MARKERS = ("watermark", "memory", "no extra session", "session pool")
_TIMEOUT_MARKERS = ("timeout", "timed out", "deadline")
_PUBLIC_DETAIL_LIMIT = 300


def public_graph_error(exc: Exception) -> tuple[str, int]:
    """面向调用方的图库错误：去掉内部路由/地址，资源与超时类只给通用提示。

    原始异常（含内存水位、内部地址等运维信息）只应进服务端日志。
    """
    raw = str(exc)
    lowered = raw.lower()
    if isinstance(exc, GraphConnectionError):
        return "图数据服务暂时不可用，请稍后重试", 503
    if any(marker in lowered for marker in _RESOURCE_MARKERS):
        return "图数据库资源紧张，请稍后重试", 503
    if any(marker in lowered for marker in _TIMEOUT_MARKERS):
        return "查询超时，请缩小查询范围后重试", 504
    detail = _INTERNAL_PREFIX.sub("", raw).strip()
    detail = re.sub(r"https?://\S+", "", detail)
    detail = re.sub(r"\b\d{1,3}(?:\.\d{1,3}){3}(?::\d+)?\b", "", detail).strip()
    return detail[:_PUBLIC_DETAIL_LIMIT] or "图数据查询失败", 400
