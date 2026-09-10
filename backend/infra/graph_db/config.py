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
