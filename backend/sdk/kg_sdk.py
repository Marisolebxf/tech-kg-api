"""用户抽取脚本 SDK。

activity 在子进程外把"已解析的连接参数"（不是活对象）序列化进 ``KG_SCRIPT_CTX``
环境变量（两参 step 脚本同时合并进 ``ctx`` dict）。脚本里：

- 两参 ``step_fn(payload, ctx)``：``ctx`` 是 :class:`Context`（activity 已包装），
  直接 ``ctx.mysql`` / ``ctx.graph`` / ``ctx.llm`` ... 取懒构造客户端。
- 单参 ``workflow(payload)``：``from kg_sdk import current_context``，
  ``ctx = current_context()``（未配置时返回 None，脚本降级）。

未配置某选择器时对应属性返回 ``None``（与 ``infra.llm.get_llm_client`` 降级约定一致），
脚本应 ``if ctx.llm:`` 判空后再用。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

_UNSET = object()


@dataclass(frozen=True)
class ScriptConfig:
    """跨运行增量游标，由 activity 在 step 成功后写入。"""

    watermark: str | None = None
    checkpoint: dict[str, Any] | None = None


class Context:
    """用户脚本运行上下文：懒构造 mysql/graph/milvus/llm/embedding 客户端。

    Args:
        raw: activity 注入的 ctx dict。键：
            - mysql: {host, port, database, username, password}
            - graph: {base_url, space, api_key, timeout}
            - milvus: {uri, db_name, token, timeout}
            - llm: {api_key, base_url, model}
            - embedding: {api_key, base_url, model, dimensions}
            - watermark: str ISO | None
            - checkpoint: dict | None
            - stepId, attempt, prevOutputs, executionId, taskId, definitionId
    """

    def __init__(self, raw: dict[str, Any] | None) -> None:
        self._raw: dict[str, Any] = raw or {}
        self._mysql: Any = _UNSET
        self._graph: Any = _UNSET
        self._milvus: Any = _UNSET
        self._llm: Any = _UNSET
        self._embedding: Any = _UNSET
        self._config = ScriptConfig(
            watermark=self._raw.get("watermark"),
            checkpoint=self._raw.get("checkpoint"),
        )
        self.step_id: str | None = self._raw.get("stepId")
        self.attempt: int | None = self._raw.get("attempt")
        self.prev_outputs: dict[str, Any] = self._raw.get("prevOutputs") or {}
        self.execution_id: str | None = self._raw.get("executionId")
        self.task_id: str | None = self._raw.get("taskId")
        self.definition_id: str | None = self._raw.get("definitionId")

    @property
    def config(self) -> ScriptConfig:
        return self._config

    @property
    def mysql(self) -> Any:
        """:class:`infra.mysql.MySQLClient` 或 None（未选数据源）。"""
        if self._mysql is _UNSET:
            params = self._raw.get("mysql")
            if not params:
                self._mysql = None
            else:
                from infra.mysql import MySQLClient

                self._mysql = MySQLClient(
                    host=params.get("host"),
                    port=int(params.get("port", 3306)),
                    database=params.get("database") or None,
                    username=params.get("username"),
                    password=params.get("password", ""),
                )
        return self._mysql

    @property
    def graph(self) -> Any:
        """:class:`infra.graph_db.TRSGraphClient`（按所选图空间）或 None。"""
        if self._graph is _UNSET:
            params = self._raw.get("graph")
            if not params:
                self._graph = None
            else:
                from infra.graph_db import TRSGraphClient
                from infra.graph_db.config import TRSGraphSettings

                settings = TRSGraphSettings(
                    base_url=params.get("base_url", "http://localhost:8090"),
                    space=params.get("space", "dev"),
                    api_key=params.get("api_key"),
                    timeout=int(params.get("timeout", 30)),
                )
                self._graph = TRSGraphClient(settings)
                self._graph.connect()
        return self._graph

    @property
    def milvus(self) -> Any:
        """``pymilvus.MilvusClient``（按所选 Milvus 库）或 None。"""
        if self._milvus is _UNSET:
            params = self._raw.get("milvus")
            if not params:
                self._milvus = None
            else:
                from pymilvus import MilvusClient  # type: ignore[import-not-found]

                kwargs: dict[str, Any] = {
                    "uri": params.get("uri"),
                    "db_name": params.get("db_name", "default"),
                    "timeout": int(params.get("timeout", 30)),
                }
                if params.get("token"):
                    kwargs["token"] = params["token"]
                self._milvus = MilvusClient(**kwargs)
        return self._milvus

    @property
    def llm(self) -> Any:
        """:class:`infra.llm.LLMClient` 或 None（未选 LLM）。"""
        if self._llm is _UNSET:
            params = self._raw.get("llm")
            if not params or not params.get("api_key"):
                self._llm = None
            else:
                from infra.llm import LLMClient

                self._llm = LLMClient(
                    api_key=params["api_key"],
                    base_url=params.get("base_url"),
                    model=params.get("model"),
                )
        return self._llm

    @property
    def embedding(self) -> Any:
        """:class:`infra.llm.EmbeddingClient` 或 None（未选 embedding）。"""
        if self._embedding is _UNSET:
            params = self._raw.get("embedding")
            if not params or not params.get("api_key"):
                self._embedding = None
            else:
                from infra.llm import EmbeddingClient

                self._embedding = EmbeddingClient(
                    api_key=params["api_key"],
                    base_url=params.get("base_url"),
                    model=params.get("model"),
                    dimensions=params.get("dimensions"),
                )
        return self._embedding

    def to_dict(self) -> dict[str, Any]:
        """返回原始 ctx dict（调试用）。"""
        return dict(self._raw)


_current: Context | None = _UNSET


def current_context() -> Context | None:
    """单参脚本入口：读 ``KG_SCRIPT_CTX`` 环境变量构造 Context。

    未配置（legacy 运行 / 本地 dev）返回 None，脚本应自行降级。
    """
    global _current
    if _current is not _UNSET:
        return _current  # type: ignore[return-value]
    raw = os.environ.get("KG_SCRIPT_CTX")
    if not raw:
        _current = None
        return None
    try:
        _current = Context(json.loads(raw))
    except Exception:  # noqa: BLE001
        _current = None
    return _current  # type: ignore[return-value]


def reset_current_context() -> None:
    """测试用：清缓存。"""
    global _current
    _current = _UNSET
