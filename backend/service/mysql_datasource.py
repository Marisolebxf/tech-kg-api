"""平台 MySQL 数据源 service：CRUD + 测试连接 + 列库 + 解析连接参数。"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from dao.mysql_datasource import MysqlDatasourceDAO
from db_model.mysql_datasource import MysqlDatasource
from infra.mysql import MySQLClient

logger = logging.getLogger(__name__)


def _mask_password(password: str) -> str:
    if not password:
        return ""
    if len(password) <= 8:
        return "•" * len(password)
    return f"••••••••{password[-4:]}"


def _to_out(cfg: MysqlDatasource) -> dict[str, Any]:
    return {
        "id": cfg.id,
        "name": cfg.name,
        "description": cfg.description,
        "host": cfg.host,
        "port": cfg.port,
        "defaultDatabase": cfg.default_database,
        "username": cfg.username,
        "owner": cfg.owner,
        "isDefault": cfg.is_default,
        "status": cfg.status,
        "hasPassword": bool(cfg.password),
        "passwordMasked": _mask_password(cfg.password),
        "createdAt": cfg.created_at,
        "updatedAt": cfg.updated_at,
    }


class MysqlDatasourceService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._dao = MysqlDatasourceDAO(session)

    def list_configs(self, owner: str | None = None) -> list[dict[str, Any]]:
        rows = self._dao.list(order_by=MysqlDatasource.updated_at.desc(), limit=1000)
        if owner is not None:
            rows = [r for r in rows if r.owner == owner]
        return [_to_out(r) for r in rows]

    def get_config(self, config_id: str) -> dict[str, Any] | None:
        row = self._dao.get(config_id)
        return _to_out(row) if row else None

    def create_config(self, payload: dict[str, Any]) -> dict[str, Any]:
        now = datetime.utcnow()
        config_id = f"MYSQL-{uuid.uuid4().hex[:8].upper()}"
        row = self._dao.create(
            id=config_id,
            name=payload["name"],
            description=payload.get("description", ""),
            host=payload["host"],
            port=int(payload.get("port", 3306)),
            default_database=payload.get("defaultDatabase", payload.get("default_database", "")),
            username=payload["username"],
            password=payload.get("password", ""),
            owner=payload.get("owner", ""),
            is_default=bool(payload.get("isDefault", payload.get("is_default", False))),
            status=payload.get("status", "正常"),
            created_at=now,
            updated_at=now,
        )
        if row.is_default:
            self._dao.clear_other_defaults(row.id, owner=row.owner)
        return _to_out(row)

    def update_config(self, config_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        row = self._dao.get(config_id)
        if row is None:
            return None
        updates: dict[str, Any] = {"updated_at": datetime.utcnow()}
        for field in (
            "name",
            "description",
            "host",
            "port",
            "default_database",
            "username",
            "owner",
            "is_default",
            "status",
        ):
            camel = "".join([field.split("_")[0]] + [w.capitalize() for w in field.split("_")[1:]])
            if field in payload and payload[field] is not None:
                updates[field] = payload[field]
            elif camel in payload and payload[camel] is not None:
                updates[field] = payload[camel]
        if "port" in updates:
            updates["port"] = int(updates["port"])
        new_pwd = payload.get("password")
        if new_pwd:
            updates["password"] = new_pwd
        updated = self._dao.update(config_id, **updates)
        if updated and updated.is_default:
            self._dao.clear_other_defaults(updated.id, owner=updated.owner)
        return _to_out(updated) if updated else None

    def delete_config(self, config_id: str) -> bool:
        row = self._dao.get(config_id)
        if row is None:
            return False
        if row.is_default:
            logger.warning("删除默认 MySQL 数据源 %s，删除后无默认生效（回退 env）", config_id)
        return self._dao.delete(config_id)

    def set_default(self, config_id: str) -> dict[str, Any] | None:
        row = self._dao.get(config_id)
        if row is None:
            return None
        self._dao.clear_other_defaults(config_id, owner=row.owner)
        updated = self._dao.update(config_id, is_default=True, updated_at=datetime.utcnow())
        return _to_out(updated) if updated else None

    def test_connection(self, config_id: str) -> dict[str, Any]:
        row = self._dao.get(config_id)
        if row is None:
            return {"ok": False, "latencyMs": None, "error": "数据源不存在"}
        start = time.perf_counter()
        try:
            client = MySQLClient(
                host=row.host,
                port=row.port,
                database=row.default_database or None,
                username=row.username,
                password=row.password,
            )
            ok = client.health_check()
            client.dispose()
            latency_ms = int((time.perf_counter() - start) * 1000)
            return {"ok": ok, "latencyMs": latency_ms, "error": None}
        except Exception as exc:  # noqa: BLE001
            latency_ms = int((time.perf_counter() - start) * 1000)
            logger.warning("MySQL 测试连接失败 id=%s: %s", config_id, exc)
            return {"ok": False, "latencyMs": latency_ms, "error": str(exc)}

    def list_databases(self, config_id: str) -> list[str]:
        """列出该数据源可访问的库（SHOW DATABASES）。连接失败返回 []。"""
        row = self._dao.get(config_id)
        if row is None:
            return []
        client = MySQLClient(
            host=row.host,
            port=row.port,
            database=None,
            username=row.username,
            password=row.password,
        )
        try:
            with client.engine.connect() as conn:
                rows = conn.execute(text("SHOW DATABASES")).fetchall()
            return [r[0] for r in rows if r[0] not in ("information_schema",)]
        except Exception as exc:  # noqa: BLE001
            logger.warning("列库失败 id=%s: %s", config_id, exc)
            return []
        finally:
            client.dispose()


def get_mysql_settings_by_id(config_id: str | None) -> dict[str, Any] | None:
    """供 activity 解析：按 id 查 MysqlDatasource 并返回连接参数 dict。

    不走请求作用域，独立短连接。配置不存在返回 None（SDK ctx.mysql 为 None）。
    """
    if not config_id:
        return None
    from infra.mysql import create_session

    session = create_session()
    try:
        row = MysqlDatasourceDAO(session).get(config_id)
        if row is None:
            return None
        return {
            "host": row.host,
            "port": row.port,
            "database": row.default_database,
            "username": row.username,
            "password": row.password,
        }
    finally:
        session.close()
