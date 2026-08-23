"""Helpers for authenticated calls to protected APIs in the same service."""

from __future__ import annotations

from fastapi import Request

_FORWARDED_AUTH_HEADERS = ("authorization", "cookie")


def get_internal_api_auth_headers(request: Request) -> dict[str, str]:
    """Return only credentials required by a same-service internal API call."""
    headers: dict[str, str] = {}
    for name in _FORWARDED_AUTH_HEADERS:
        value = request.headers.get(name)
        if value:
            headers[name] = value
    return headers
