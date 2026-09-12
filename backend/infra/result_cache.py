"""HTTP 响应级 JSON 缓存：固定入参命中后直接返回预序列化 JSON 串。

高并发（500 并发）下 FastAPI 的 ``response_model`` 序列化（jsonable_encoder，Python 递归）
会阻塞事件循环成为瓶颈。命中缓存时返回 ``Response(预序列化 JSON 串)``，零序列化。

进程内 dict + GIL 保护（dict get/set 在 CPython 原子），不加锁避免 500 并发争锁。
TTL 由 ``RESULT_CACHE_TTL`` 环境变量控制（压测设 600s，稳态不过期）。
"""

from __future__ import annotations

import os
import time

_TTL = float(os.getenv("RESULT_CACHE_TTL", "60"))
_store: dict[str, tuple[float, str]] = {}


def get_cached_json(key: str) -> str | None:
    """命中返回预序列化 JSON 串，未命中/过期返回 None。"""
    entry = _store.get(key)
    if entry and entry[0] > time.monotonic():
        return entry[1]
    return None


def set_cached_json(key: str, json_str: str) -> None:
    _store[key] = (time.monotonic() + _TTL, json_str)


def clear() -> None:
    _store.clear()


def discard_prefix(prefix: str) -> None:
    """按键前缀清除缓存（写接口修改数据后让对应 GET 列表立即失效）。"""
    for key in [k for k in _store if k.split("?", 1)[0] == prefix]:
        _store.pop(key, None)
