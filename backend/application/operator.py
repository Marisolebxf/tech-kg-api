"""算子注册服务应用层。"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

import httpx

from service.operator_registry import REGISTRY, OperatorKind, OperatorRegistry

logger = logging.getLogger(__name__)


class OperatorApplication:
    def __init__(self, registry: OperatorRegistry | None = None) -> None:
        self.registry = registry or REGISTRY

    def list(self, kind: OperatorKind | None = None) -> list[dict[str, Any]]:
        return [manifest.to_dict() for manifest in self.registry.list(kind)]

    def get(self, name: str) -> dict[str, Any]:
        return self.registry.get(name).to_dict()

    async def create(
        self,
        *,
        name: str,
        version: str,
        kind: OperatorKind,
        source: str,
        description: str,
    ) -> dict[str, Any]:
        manifest = self.registry.create(
            name=name,
            version=version,
            kind=kind,
            source=source,
            description=description,
        )
        await self.broadcast_reload()
        return manifest.to_dict()

    async def update(
        self,
        *,
        name: str,
        version: str,
        kind: OperatorKind,
        source: str,
        description: str,
    ) -> dict[str, Any]:
        manifest = self.registry.update(
            name=name,
            version=version,
            kind=kind,
            source=source,
            description=description,
        )
        await self.broadcast_reload()
        return manifest.to_dict()

    async def delete(self, name: str) -> None:
        self.registry.delete(name)
        await self.broadcast_reload()

    async def invoke(
        self, name: str, data: list[dict[str, Any]], ctx: dict[str, Any]
    ) -> dict[str, Any]:
        result = await self.registry.invoke(name, data, ctx)
        return {"operator": self.registry.get(name).to_dict(), "data": result, "count": len(result)}

    def reload_all(self) -> list[str]:
        return self.registry.sync_from_store()

    def sync_user_operators(self, bundles: list[dict[str, Any]], *, replace: bool) -> list[str]:
        return self.registry.sync_user_operators(bundles, replace=replace)

    async def broadcast_reload(self) -> None:
        """通知不共享文件系统的 worker；失败不回滚控制面的成功注册。"""
        raw_uris = os.getenv("OPERATOR_WORKER_BASE_URIS", "")
        base_uris = [uri.strip().rstrip("/") for uri in raw_uris.split(",") if uri.strip()]
        if not base_uris:
            return

        payload = (
            None
            if self.registry.has_shared_store
            else {"operators": self.registry.export_user_operators(), "replace": True}
        )

        headers: dict[str, str] = {}
        token = os.getenv("OPERATOR_RELOAD_TOKEN")
        if token:
            headers["X-Operator-Reload-Token"] = token

        async with httpx.AsyncClient(timeout=5.0) as client:
            results = await asyncio.gather(
                *(
                    client.post(
                        f"{base_uri}/internal/operators/reload",
                        headers=headers,
                        json=payload,
                    )
                    for base_uri in base_uris
                ),
                return_exceptions=True,
            )
        for base_uri, result in zip(base_uris, results, strict=True):
            if isinstance(result, Exception):
                logger.warning("通知 worker %s 重载算子失败: %s", base_uri, result)
            elif result.is_error:
                logger.warning("通知 worker %s 重载算子失败: HTTP %s", base_uri, result.status_code)
