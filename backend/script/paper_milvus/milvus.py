"""Milvus 客户端封装（进程级单例）。

从 ``MILVUS_*`` 环境变量读取连接参数，通过 pymilvus ``MilvusClient`` 暴露一个
统一的 handle 供上层脚本使用；不做 collection 级抽象，各领域自行 create /
drop / index。

环境变量
--------
- ``MILVUS_URI``       — 默认 ``http://127.0.0.1:19531``（本项目 docker-compose 部署端口）
- ``MILVUS_TOKEN``     — 可选，认证 token（Zilliz Cloud / 部署带鉴权时使用）
- ``MILVUS_DB_NAME``   — 默认 ``default``
- ``MILVUS_TIMEOUT``   — 默认 30（秒）

用法::

    from script.paper_milvus.milvus import get_milvus_client

    client = get_milvus_client()
    client.list_collections()
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Any

logger = logging.getLogger(__name__)


_DEFAULT_URI = "http://127.0.0.1:19531"
_DEFAULT_DB = "default"
_DEFAULT_TIMEOUT = 30

_client_lock = threading.Lock()
_client: Any = None


def _load_milvus_client_cls():
    """延迟导入 ``pymilvus.MilvusClient``。

    pymilvus 是可选重量级依赖（携带 protobuf、grpcio 等），非必要模块不引入。
    """
    from pymilvus import MilvusClient  # type: ignore

    return MilvusClient


def get_milvus_client() -> Any:
    """返回进程共享的 :class:`pymilvus.MilvusClient` 实例。"""
    global _client
    if _client is not None:
        return _client
    with _client_lock:
        if _client is not None:
            return _client
        milvus_client_class = _load_milvus_client_cls()
        uri = os.environ.get("MILVUS_URI", _DEFAULT_URI)
        token = os.environ.get("MILVUS_TOKEN") or None
        db_name = os.environ.get("MILVUS_DB_NAME", _DEFAULT_DB)
        timeout = int(os.environ.get("MILVUS_TIMEOUT", _DEFAULT_TIMEOUT))
        logger.info("Connecting to Milvus uri=%s db=%s", uri, db_name)
        kwargs: dict[str, Any] = {"uri": uri, "db_name": db_name, "timeout": timeout}
        if token:
            kwargs["token"] = token
        _client = milvus_client_class(**kwargs)
    return _client


def reset_milvus_client() -> None:
    """测试用：释放单例（下次调用重新建连接）。"""
    global _client
    with _client_lock:
        if _client is not None:
            try:
                _client.close()
            except Exception:  # noqa: BLE001
                pass
        _client = None
