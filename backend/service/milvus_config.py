"""平台 Milvus 配置 service：CRUD + 测试连接 + 列库 + 解析连接参数。"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from dao.milvus_config import MilvusConfigDAO
from db_model.milvus_config import MilvusConfig

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 30


def _mask_token(token: str) -> str:
    if not token:
        return ""
    if len(token) <= 8:
        return "•" * len(token)
    return f"••••••••{token[-4:]}"


def _to_out(cfg: MilvusConfig) -> dict[str, Any]:
    return {
        "id": cfg.id,
        "name": cfg.name,
        "description": cfg.description,
        "uri": cfg.uri,
        "defaultDb": cfg.default_db,
        "owner": cfg.owner,
        "isDefault": cfg.is_default,
        "status": cfg.status,
        "hasToken": bool(cfg.token),
        "tokenMasked": _mask_token(cfg.token),
        "createdAt": cfg.created_at,
        "updatedAt": cfg.updated_at,
    }


def _build_client(cfg: MilvusConfig, db_name: str | None = None):
    """按配置行构造临时 pymilvus.MilvusClient（非单例）。uri 为空回退 env。"""
    from infra.milvus import MilvusSettings, _load_milvus_client_cls

    if cfg.uri:
        uri = cfg.uri
        token = cfg.token or None
    else:
        env_settings = MilvusSettings.from_env()
        uri = env_settings.client_uri
        token = env_settings.token
    MilvusClient = _load_milvus_client_cls()
    kwargs: dict[str, Any] = {
        "uri": uri,
        "db_name": db_name or cfg.default_db or "default",
        "timeout": _DEFAULT_TIMEOUT,
    }
    if token:
        kwargs["token"] = token
    return MilvusClient(**kwargs)


class MilvusConfigService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._dao = MilvusConfigDAO(session)

    def list_configs(self) -> list[dict[str, Any]]:
        rows = self._dao.list(order_by=MilvusConfig.updated_at.desc(), limit=1000)
        return [_to_out(r) for r in rows]

    def get_config(self, config_id: str) -> dict[str, Any] | None:
        row = self._dao.get(config_id)
        return _to_out(row) if row else None

    def create_config(self, payload: dict[str, Any]) -> dict[str, Any]:
        now = datetime.utcnow()
        config_id = f"MILVUS-{uuid.uuid4().hex[:8].upper()}"
        row = self._dao.create(
            id=config_id,
            name=payload["name"],
            description=payload.get("description", ""),
            uri=payload.get("uri", ""),
            token=payload.get("token", ""),
            default_db=payload.get("defaultDb", payload.get("default_db", "default")),
            owner=payload.get("owner", ""),
            is_default=bool(payload.get("isDefault", payload.get("is_default", False))),
            status=payload.get("status", "正常"),
            created_at=now,
            updated_at=now,
        )
        if row.is_default:
            self._dao.clear_other_defaults(row.id)
        return _to_out(row)

    def update_config(self, config_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        row = self._dao.get(config_id)
        if row is None:
            return None
        updates: dict[str, Any] = {"updated_at": datetime.utcnow()}
        for field in (
            "name",
            "description",
            "uri",
            "token",
            "default_db",
            "owner",
            "is_default",
            "status",
        ):
            camel = "".join([field.split("_")[0]] + [w.capitalize() for w in field.split("_")[1:]])
            if field in payload and payload[field] is not None:
                updates[field] = payload[field]
            elif camel in payload and payload[camel] is not None:
                updates[field] = payload[camel]
        new_token = payload.get("token")
        if new_token:
            updates["token"] = new_token
        updated = self._dao.update(config_id, **updates)
        if updated and updated.is_default:
            self._dao.clear_other_defaults(updated.id)
        return _to_out(updated) if updated else None

    def delete_config(self, config_id: str) -> bool:
        row = self._dao.get(config_id)
        if row is None:
            return False
        if row.is_default:
            logger.warning("删除默认 Milvus 配置 %s，删除后无默认生效（回退 env）", config_id)
        return self._dao.delete(config_id)

    def set_default(self, config_id: str) -> dict[str, Any] | None:
        row = self._dao.get(config_id)
        if row is None:
            return None
        self._dao.clear_other_defaults(config_id)
        updated = self._dao.update(config_id, is_default=True, updated_at=datetime.utcnow())
        return _to_out(updated) if updated else None

    def test_connection(self, config_id: str) -> dict[str, Any]:
        row = self._dao.get(config_id)
        if row is None:
            return {"ok": False, "latencyMs": None, "error": "配置不存在"}
        start = time.perf_counter()
        try:
            client = _build_client(row)
            client.list_databases()
            try:
                client.close()
            except Exception:  # noqa: BLE001
                pass
            latency_ms = int((time.perf_counter() - start) * 1000)
            return {"ok": True, "latencyMs": latency_ms, "error": None}
        except Exception as exc:  # noqa: BLE001
            latency_ms = int((time.perf_counter() - start) * 1000)
            logger.warning("Milvus 测试连接失败 id=%s: %s", config_id, exc)
            return {"ok": False, "latencyMs": latency_ms, "error": str(exc)}

    def list_databases(self, config_id: str) -> list[str]:
        """列出该 Milvus 配置可访问的库。连接失败返回 []。"""
        row = self._dao.get(config_id)
        if row is None:
            return []
        try:
            client = _build_client(row)
            dbs = list(client.list_databases())
            try:
                client.close()
            except Exception:  # noqa: BLE001
                pass
            return dbs
        except Exception as exc:  # noqa: BLE001
            logger.warning("列库失败 id=%s: %s", config_id, exc)
            return []


def get_milvus_settings_by_id(config_id: str | None) -> dict[str, Any] | None:
    """供 activity 解析：按 id 查 MilvusConfig 并返回连接参数 dict。

    uri 为空时回退 env。配置不存在返回 None（SDK ctx.milvus 为 None）。
    """
    if not config_id:
        return None
    from infra.mysql import create_session

    session = create_session()
    try:
        row = MilvusConfigDAO(session).get(config_id)
        if row is None:
            return None
        if row.uri:
            return {
                "uri": row.uri,
                "token": row.token or None,
                "db_name": row.default_db or "default",
                "timeout": _DEFAULT_TIMEOUT,
            }
        # uri 为空回退 env
        from infra.milvus import MilvusSettings

        env_settings = MilvusSettings.from_env()
        return {
            "uri": env_settings.client_uri,
            "token": env_settings.token,
            "db_name": row.default_db or env_settings.db_name,
            "timeout": env_settings.timeout,
        }
    finally:
        session.close()
