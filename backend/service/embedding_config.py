"""平台 embedding 模型配置 service：CRUD + 测试连接 + 解析参数。"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from openai import OpenAI
from sqlalchemy.orm import Session

from dao.embedding_config import EmbeddingConfigDAO
from db_model.embedding_config import EmbeddingConfig
from infra.llm import DEFAULT_TIMEOUT, EmbeddingClient

logger = logging.getLogger(__name__)


def _mask_api_key(api_key: str) -> str:
    if not api_key:
        return ""
    if len(api_key) <= 8:
        return "•" * len(api_key)
    return f"••••••••{api_key[-4:]}"


def _ping_embedding(base_url: str, model: str, api_key: str) -> dict[str, Any]:
    """真实调用一次 embeddings 验证连通性；返回 {ok, latencyMs, error}。"""
    start = time.perf_counter()

    def result(ok: bool, error: str | None) -> dict[str, Any]:
        return {"ok": ok, "latencyMs": int((time.perf_counter() - start) * 1000), "error": error}

    try:
        client = OpenAI(api_key=api_key, base_url=base_url, timeout=DEFAULT_TIMEOUT)
        client.embeddings.create(model=model, input="ping")
        return result(True, None)
    except Exception as exc:  # noqa: BLE001
        logger.warning("embedding 连接验证失败 base_url=%s model=%s: %s", base_url, model, exc)
        return result(False, str(exc))


def _to_out(cfg: EmbeddingConfig) -> dict[str, Any]:
    return {
        "id": cfg.id,
        "name": cfg.name,
        "description": cfg.description,
        "baseUrl": cfg.base_url,
        "model": cfg.model,
        "dimensions": cfg.dimensions,
        "owner": cfg.owner,
        "isDefault": cfg.is_default,
        "status": cfg.status,
        "hasApiKey": bool(cfg.api_key),
        "apiKeyMasked": _mask_api_key(cfg.api_key),
        "createdAt": cfg.created_at,
        "updatedAt": cfg.updated_at,
    }


class EmbeddingConfigService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._dao = EmbeddingConfigDAO(session)

    def list_configs(self, owner: str | None = None) -> list[dict[str, Any]]:
        rows = self._dao.list(order_by=EmbeddingConfig.updated_at.desc(), limit=1000)
        if owner is not None:
            rows = [r for r in rows if r.owner == owner]
        return [_to_out(r) for r in rows]

    def get_config(self, config_id: str) -> dict[str, Any] | None:
        row = self._dao.get(config_id)
        return _to_out(row) if row else None

    def create_config(self, payload: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(UTC)
        config_id = f"EMB-{uuid.uuid4().hex[:8].upper()}"
        row = self._dao.create(
            id=config_id,
            name=payload["name"],
            description=payload.get("description", ""),
            base_url=payload.get("base_url") or payload.get("baseUrl", ""),
            api_key=payload.get("api_key", payload.get("apiKey", "")),
            model=payload["model"],
            dimensions=payload.get("dimensions"),
            owner=payload.get("owner", ""),
            is_default=bool(payload.get("is_default", payload.get("isDefault", False))),
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
        updates: dict[str, Any] = {"updated_at": datetime.now(UTC)}
        for field in (
            "name",
            "description",
            "base_url",
            "model",
            "dimensions",
            "owner",
            "is_default",
            "status",
        ):
            camel = "".join([field.split("_")[0]] + [w.capitalize() for w in field.split("_")[1:]])
            if field in payload and payload[field] is not None:
                updates[field] = payload[field]
            elif camel in payload and payload[camel] is not None:
                updates[field] = payload[camel]
        new_key = payload.get("api_key") or payload.get("apiKey")
        if new_key:
            updates["api_key"] = new_key
        updated = self._dao.update(config_id, **updates)
        if updated and updated.is_default:
            self._dao.clear_other_defaults(updated.id, owner=updated.owner)
        return _to_out(updated) if updated else None

    def delete_config(self, config_id: str) -> bool:
        row = self._dao.get(config_id)
        if row is None:
            return False
        if row.is_default:
            logger.warning("删除默认 embedding 配置 %s，删除后无默认生效（回退 env）", config_id)
        return self._dao.delete(config_id)

    def set_default(self, config_id: str) -> dict[str, Any] | None:
        row = self._dao.get(config_id)
        if row is None:
            return None
        self._dao.clear_other_defaults(config_id, owner=row.owner)
        updated = self._dao.update(config_id, is_default=True, updated_at=datetime.now(UTC))
        return _to_out(updated) if updated else None

    def test_connection(self, config_id: str) -> dict[str, Any]:
        row = self._dao.get(config_id)
        if row is None:
            return {"ok": False, "latencyMs": None, "error": "配置不存在"}
        if not row.api_key:
            return {"ok": False, "latencyMs": None, "error": "未配置 API Key"}
        return _ping_embedding(row.base_url, row.model, row.api_key)

    def verify_connection(self, base_url: str, model: str, api_key: str) -> dict[str, Any]:
        """未保存前的验证：直接用弹窗里的原始参数探活。"""
        if not api_key:
            return {"ok": False, "latencyMs": None, "error": "未填写 API Key"}
        return _ping_embedding(base_url, model, api_key)


def get_embedding_settings_by_id(config_id: str | None) -> dict[str, Any] | None:
    """供 activity 解析：按 id 查 EmbeddingConfig 并返回参数 dict。配置不存在返回 None。"""
    if not config_id:
        return None
    from infra.mysql import create_session

    session = create_session()
    try:
        row = EmbeddingConfigDAO(session).get(config_id)
        if row is None:
            return None
        return {
            "api_key": row.api_key,
            "base_url": row.base_url,
            "model": row.model,
            "dimensions": row.dimensions,
        }
    finally:
        session.close()


def get_embedding_client_by_id(config_id: str | None) -> EmbeddingClient | None:
    """按 id 构造临时 EmbeddingClient，供作业 activity 使用。配置不存在或缺 key 返回 None。"""
    settings = get_embedding_settings_by_id(config_id)
    if settings is None or not settings["api_key"]:
        return None
    return EmbeddingClient(
        api_key=settings["api_key"],
        base_url=settings["base_url"],
        model=settings["model"],
        dimensions=settings.get("dimensions"),
    )
