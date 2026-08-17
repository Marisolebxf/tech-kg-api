"""Service-to-service authentication for graph-build integration."""

import hashlib
import hmac
import os
import time

from fastapi import Header, HTTPException


async def require_graph_service(
    authorization: str | None = Header(None),
    x_service_timestamp: str | None = Header(None, alias="X-Service-Timestamp"),
    x_service_signature: str | None = Header(None, alias="X-Service-Signature"),
) -> str:
    token = os.getenv("GRAPH_BUILD_SERVICE_TOKEN", "")
    if not token:
        raise HTTPException(503, "GRAPH_BUILD_SERVICE_TOKEN 未配置")
    if authorization and hmac.compare_digest(authorization, f"Bearer {token}"):
        return "graph-build"
    if x_service_timestamp and x_service_signature:
        try:
            ts = int(x_service_timestamp)
        except ValueError:
            raise HTTPException(401, "服务时间戳无效") from None
        if abs(int(time.time()) - ts) > int(os.getenv("REVIEW_SERVICE_CLOCK_SKEW_SECONDS", "300")):
            raise HTTPException(401, "服务签名已过期")
        expected = hmac.new(
            token.encode(), x_service_timestamp.encode(), hashlib.sha256
        ).hexdigest()
        if hmac.compare_digest(expected, x_service_signature):
            return "graph-build"
    raise HTTPException(401, "图谱构建服务认证失败")
