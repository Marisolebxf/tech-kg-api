"""GET 列表接口的结果缓存辅助：按 前缀+查询参数 命中预序列化 JSON 直接返回。

与九大业务模块的 result_cache 用法一致（``infra/result_cache.py``），这里适配 GET 查询参数键。
命中时返回 ``Response(预序列化 JSON)``，跳过 ``response_model`` 序列化与下游查询
（MySQL/SQLite/S3），平台治理类列表接口在 500 并发下不再逐请求访问存储层。
TTL 沿用 ``RESULT_CACHE_TTL``；对应写接口修改数据后调用 :func:`invalidate` 主动失效。
"""

from __future__ import annotations

import json
from urllib.parse import urlencode

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import Response

from infra import result_cache


def _key(prefix: str, request: Request) -> str:
    """缓存键 = 前缀 + 排序后的查询参数串（不同分页/筛选各自成键）。"""
    qs = urlencode(sorted(request.query_params.multi_items()))
    return f"{prefix}?{qs}" if qs else prefix


def try_get(prefix: str, request: Request) -> Response | None:
    """命中返回预序列化 Response，未命中返回 None（由接口正常执行后 :func:`store`）。"""
    cached = result_cache.get_cached_json(_key(prefix, request))
    if cached is not None:
        return Response(content=cached, media_type="application/json")
    return None


def store(prefix: str, request: Request, payload: dict) -> Response:
    """序列化并存缓存，返回与命中路径一致的 Response。

    separators 用紧凑风格，与 FastAPI 原生 JSONResponse 输出一致
    （默认风格的 ``"code": 200`` 带空格，会破坏调用方按 ``"code":200`` 断言）。
    payload 先过 jsonable_encoder，datetime 等类型与 response_model 路径序列化一致。
    """
    encoded = jsonable_encoder(payload)
    body = json.dumps(encoded, ensure_ascii=False, separators=(",", ":"))
    result_cache.set_cached_json(_key(prefix, request), body)
    return Response(content=body, media_type="application/json")


def invalidate(prefix: str) -> None:
    """写接口修改数据后，按前缀清掉对应列表的全部缓存键。"""
    result_cache.discard_prefix(prefix)
