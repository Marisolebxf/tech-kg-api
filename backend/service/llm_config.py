"""平台 LLM 配置 service：CRUD + 测试连接 + 当前生效配置查询。"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime
from typing import Any

from openai import OpenAI
from sqlalchemy.orm import Session

from dao.llm_config import LlmConfigDAO
from db_model.llm_config import LlmConfig
from infra.llm import (
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    DEFAULT_TIMEOUT,
    LLMClient,
    reset_llm_client,
)

logger = logging.getLogger(__name__)


def _mask_api_key(api_key: str) -> str:
    if not api_key:
        return ""
    if len(api_key) <= 8:
        return "•" * len(api_key)
    return f"••••••••{api_key[-4:]}"


def _to_out(cfg: LlmConfig) -> dict:
    return {
        "id": cfg.id,
        "name": cfg.name,
        "description": cfg.description,
        "base_url": cfg.base_url,
        "model": cfg.model,
        "owner": cfg.owner,
        "is_default": cfg.is_default,
        "status": cfg.status,
        "has_api_key": bool(cfg.api_key),
        "api_key_masked": _mask_api_key(cfg.api_key),
        "created_at": cfg.created_at,
        "updated_at": cfg.updated_at,
    }


class LlmConfigService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._dao = LlmConfigDAO(session)

    def list_configs(self, owner: str | None = None) -> list[dict]:
        rows = self._dao.list(order_by=LlmConfig.updated_at.desc(), limit=1000)
        if owner is not None:
            rows = [r for r in rows if r.owner == owner]
        return [_to_out(r) for r in rows]

    def get_config(self, config_id: str) -> dict | None:
        row = self._dao.get(config_id)
        return _to_out(row) if row else None

    def create_config(self, payload: dict) -> dict:
        now = datetime.utcnow()
        config_id = f"LLM-{uuid.uuid4().hex[:8].upper()}"
        row = self._dao.create(
            id=config_id,
            name=payload["name"],
            description=payload.get("description", ""),
            base_url=payload["base_url"],
            api_key=payload.get("api_key", ""),
            model=payload["model"],
            owner=payload.get("owner", ""),
            is_default=bool(payload.get("is_default", False)),
            status=payload.get("status", "正常"),
            created_at=now,
            updated_at=now,
        )
        if row.is_default:
            self._dao.clear_other_defaults(row.id, owner=row.owner)
        reset_llm_client()
        return _to_out(row)

    def update_config(self, config_id: str, payload: dict) -> dict | None:
        row = self._dao.get(config_id)
        if row is None:
            return None
        updates: dict = {"updated_at": datetime.utcnow()}
        for field in ("name", "description", "base_url", "model", "owner", "is_default", "status"):
            if field in payload and payload[field] is not None:
                updates[field] = payload[field]
        # api_key 为空字符串或 None 时保留原值
        new_key = payload.get("api_key")
        if new_key:
            updates["api_key"] = new_key
        updated = self._dao.update(config_id, **updates)
        if updated and updated.is_default:
            self._dao.clear_other_defaults(updated.id, owner=updated.owner)
        reset_llm_client()
        return _to_out(updated) if updated else None

    def delete_config(self, config_id: str) -> bool:
        row = self._dao.get(config_id)
        if row is None:
            return False
        if row.is_default:
            logger.warning("删除默认 LLM 配置 %s，删除后无默认配置生效（将回退 env）", config_id)
        ok = self._dao.delete(config_id)
        if ok:
            reset_llm_client()
        return ok

    def set_default(self, config_id: str) -> dict | None:
        row = self._dao.get(config_id)
        if row is None:
            return None
        self._dao.clear_other_defaults(config_id, owner=row.owner)
        updated = self._dao.update(config_id, is_default=True, updated_at=datetime.utcnow())
        reset_llm_client()
        return _to_out(updated) if updated else None

    def test_connection(self, config_id: str) -> dict:
        row = self._dao.get(config_id)
        if row is None:
            return {"ok": False, "latency_ms": None, "error": "配置不存在"}
        if not row.api_key:
            return {"ok": False, "latency_ms": None, "error": "未配置 API Key"}
        start = time.perf_counter()
        try:
            client = OpenAI(
                api_key=row.api_key,
                base_url=row.base_url,
                timeout=DEFAULT_TIMEOUT,
            )
            client.chat.completions.create(
                model=row.model,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=1,
                extra_body={"thinking": {"type": "disabled"}},
            )
            latency_ms = int((time.perf_counter() - start) * 1000)
            return {"ok": True, "latency_ms": latency_ms, "error": None}
        except Exception as exc:  # noqa: BLE001
            latency_ms = int((time.perf_counter() - start) * 1000)
            logger.warning("LLM 测试连接失败 id=%s: %s", config_id, exc)
            return {"ok": False, "latency_ms": latency_ms, "error": str(exc)}

    def get_active_config(self) -> LlmConfig | None:
        """返回当前默认 LLM 配置；DB 无记录时返回 None（由调用方回退 env）。"""
        return self._dao.get_default()


def get_active_llm_config() -> LlmConfig | None:
    """供非请求上下文（如 infra.llm.get_llm_client）使用的入口：独立短连接。"""
    from infra.mysql import create_session

    session = create_session()
    try:
        return LlmConfigDAO(session).get_default()
    finally:
        session.close()


def resolve_llm_settings() -> tuple[str, str, str] | None:
    """返回 (api_key, base_url, model)。DB 优先，DB 无记录回退 env。无任何配置返回 None。"""
    import os

    cfg = get_active_llm_config()
    if cfg is not None:
        return cfg.api_key, cfg.base_url, cfg.model
    api_key = os.getenv("LLM_API_KEY") or os.getenv("ZHIPUAI_API_KEY")
    if not api_key:
        return None
    return (
        api_key,
        os.getenv("LLM_BASE_URL", DEFAULT_BASE_URL),
        os.getenv("LLM_MODEL", DEFAULT_MODEL),
    )


def get_llm_client_by_id(config_id: str) -> LLMClient | None:
    """按 id 查 LlmConfig 并构造临时 LLMClient，供作业 activity 使用。

    不走进程单例（``infra.llm.get_llm_client``），每次按需构造。配置不存在或缺 api_key
    时返回 None，由调用方回退全局默认。
    """
    from infra.mysql import create_session

    session = create_session()
    try:
        row = LlmConfigDAO(session).get(config_id)
        if row is None or not row.api_key:
            return None
        return LLMClient(api_key=row.api_key, base_url=row.base_url, model=row.model)
    finally:
        session.close()


def get_llm_settings_by_id(config_id: str | None) -> dict[str, Any] | None:
    """供 activity 解析：按 id 查 LlmConfig 返回参数 dict（api_key/base_url/model）。

    配置不存在或缺 api_key 返回 None（SDK ctx.llm 为 None，回退全局默认）。
    """
    if not config_id:
        return None
    from infra.mysql import create_session

    session = create_session()
    try:
        row = LlmConfigDAO(session).get(config_id)
        if row is None or not row.api_key:
            return None
        return {"api_key": row.api_key, "base_url": row.base_url, "model": row.model}
    finally:
        session.close()
