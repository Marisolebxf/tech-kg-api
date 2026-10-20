"""Configuration for the trs-graph repository, loaded from TRS_GRAPH_* env vars."""

from __future__ import annotations

import os

from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()


class TRSGraphSettings(BaseModel):
    """Connection settings for trs-graph-service.

    交付侧取值（docs/k8s-bkg/K8s部署文档.md §七 02-configmap/03-secret）均与
    《图数据库平台（TRS Graph）K8s 部署文档》一一对应，改任一侧需同步：
    - base_url ← 其 §五.8 Service trs-graph-service 的名称 + 8090 端口（同命名空间 ClusterDNS）
    - api_key  ← 其 §五.3 Secret trsgraph-secret 的 api-key-hash 对应明文（X-API-Key 头携带明文）
    - space    ← 其 §六 数据初始化创建的图空间名（X-Graph-Space 头；storaged 单副本，
                 建空间须 replica_factor=1，见 GRAPH_SPACE_REPLICA_FACTOR）
    """

    base_url: str = "http://localhost:8090"
    space: str = "dev"
    api_key: str | None = None
    timeout: int = 30

    @classmethod
    def from_env(cls, prefix: str = "TRS_GRAPH") -> TRSGraphSettings:
        """Load settings from ``<prefix>_*`` environment variables."""

        def env(name: str) -> str | None:
            return os.environ.get(f"{prefix}_{name}")

        return cls(
            base_url=env("BASE_URL") or "http://localhost:8090",
            space=env("SPACE") or "dev",
            api_key=env("API_KEY") or None,
            timeout=int(env("TIMEOUT") or 30),
        )


def _env_value(name: str) -> str | None:
    """读取环境变量；空串/纯空白视为未设置（compose 传空默认值时保持关闭）。"""
    value = os.environ.get(name)
    if value is None:
        return None
    return value.strip() or None


def business_plane_settings(request_space: str | None = None) -> TRSGraphSettings | None:
    """九大业务数据面的独立图连接（TRS_GRAPH_BUSINESS_*）。

    未设置 ``TRS_GRAPH_BUSINESS_BASE_URL`` 时返回 None —— 业务面与平台面共用
    ``TRS_GRAPH_*`` 同一连接（默认行为，改此模块前后的表现完全一致）。设置后
    其余字段逐项回退 ``TRS_GRAPH_*``；``TRS_GRAPH_BUSINESS_SPACE`` 用于远端集群
    空间名与本栈请求空间名不一致时的映射（如远端 dev ↔ 本栈请求 dev2），
    未设置时沿用请求空间名，保证空间下拉切换语义不变。
    """
    base_url = _env_value("TRS_GRAPH_BUSINESS_BASE_URL")
    if base_url is None:
        return None
    fallback = TRSGraphSettings.from_env()
    timeout_raw = _env_value("TRS_GRAPH_BUSINESS_TIMEOUT")
    return TRSGraphSettings(
        base_url=base_url,
        space=_env_value("TRS_GRAPH_BUSINESS_SPACE") or request_space or fallback.space,
        api_key=_env_value("TRS_GRAPH_BUSINESS_API_KEY") or fallback.api_key,
        timeout=int(timeout_raw) if timeout_raw else fallback.timeout,
    )
