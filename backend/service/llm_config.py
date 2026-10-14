"""平台 LLM 配置 service：CRUD + 测试连接 + 当前生效配置查询。"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException
from openai import OpenAI
from sqlalchemy import select
from sqlalchemy.orm import Session

from dao.llm_config import LlmConfigDAO
from db_model.llm_config import LlmConfig
from infra.llm import (
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    DEFAULT_TIMEOUT,
    reset_llm_client,
    thinking_extra_body,
)
from service.llm_defaults import (
    config_business,
    guard_default_removal,
    public_default,
    resolve_default_config,
)
from utils.time_display import utc_to_cst_str

logger = logging.getLogger(__name__)


def _utcnow_naive() -> datetime:
    """Return a UTC timestamp compatible with the existing naive SQL columns."""
    return datetime.now(UTC).replace(tzinfo=None)


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
        "baseUrl": cfg.base_url,
        "model": cfg.model,
        "owner": cfg.owner,
        "isDefault": cfg.is_default,
        "status": cfg.status,
        "hasApiKey": bool(cfg.api_key),
        "apiKeyMasked": _mask_api_key(cfg.api_key),
        "createdAt": utc_to_cst_str(cfg.created_at),
        "updatedAt": utc_to_cst_str(cfg.updated_at),
    }


def _ping_llm(base_url: str, model: str, api_key: str) -> dict:
    """真实调用一次 chat completion 验证连通性；返回 {ok, latencyMs, error}。"""
    start = time.perf_counter()

    def result(ok: bool, error: str | None) -> dict:
        return {"ok": ok, "latencyMs": int((time.perf_counter() - start) * 1000), "error": error}

    try:
        client = OpenAI(api_key=api_key, base_url=base_url, timeout=DEFAULT_TIMEOUT)
        client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=1,
            extra_body=thinking_extra_body(model),
        )
        return result(True, None)
    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM 连接验证失败 base_url=%s model=%s: %s", base_url, model, exc)
        return result(False, str(exc))


class LlmConfigService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._dao = LlmConfigDAO(session)

    def list_configs(self, owner: str | None = None) -> list[dict]:
        rows = list(self._session.scalars(select(LlmConfig).order_by(LlmConfig.updated_at.desc())))
        if owner is not None:
            rows = [r for r in rows if r.owner == owner]
        return [_to_out(r) for r in rows]

    def get_config(self, config_id: str) -> dict | None:
        row = self._dao.get(config_id)
        return _to_out(row) if row else None

    def create_config(self, payload: dict, *, scope_owner: str | None = None) -> dict:
        if payload.get("is_default") and not payload.get("api_key"):
            raise HTTPException(409, "未配置 API Key 的语言模型不能设为默认")
        if payload.get("is_default") and payload.get("_business_id"):
            raise HTTPException(403, "公共默认只能选择公共语言模型")
        if payload.get("is_default") and payload.get("status") == "停用":
            raise HTTPException(409, "停用的语言模型不能设为默认")
        now = _utcnow_naive()
        config_id = f"LLM-{uuid.uuid4().hex[:8].upper()}"
        # Register visibility in the same commit as the configuration itself.
        if "_business_id" in payload:
            from db_model.config_ownership import ConfigOwnership

            self._session.add(
                ConfigOwnership(
                    config_kind="llm", config_id=config_id, business_id=payload["_business_id"]
                )
            )
        if payload.get("is_default"):
            list(
                self._session.scalars(
                    select(LlmConfig)
                    .order_by(LlmConfig.id)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
            )
        row = LlmConfig(
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
        self._session.add(row)
        self._session.flush()
        if row.is_default:
            for other in self._session.scalars(select(LlmConfig).where(LlmConfig.id != row.id)):
                other.is_default = False
        self._session.commit()
        reset_llm_client()
        return _to_out(row)

    def update_config(
        self, config_id: str, payload: dict, *, scope_owner: str | None = None
    ) -> dict | None:
        if payload.get("is_default"):
            rows = list(
                self._session.scalars(
                    select(LlmConfig)
                    .order_by(LlmConfig.id)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
            )
            row = next((item for item in rows if item.id == config_id), None)
        else:
            row = self._session.scalar(
                select(LlmConfig)
                .where(LlmConfig.id == config_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        if row is None:
            return None
        if payload.get("status") == "停用":
            guard_default_removal(self._session, config_id)
        if payload.get("is_default") and not (payload.get("api_key") or row.api_key):
            raise HTTPException(409, "未配置 API Key 的语言模型不能设为默认")
        if payload.get("is_default") and config_business(self._session, config_id):
            raise HTTPException(403, "公共默认只能选择公共语言模型")
        if payload.get("is_default") and payload.get("status", row.status) == "停用":
            raise HTTPException(409, "停用的语言模型不能设为默认")
        updates: dict = {"updated_at": _utcnow_naive()}
        for field in ("name", "description", "base_url", "model", "owner", "is_default", "status"):
            if field in payload and payload[field] is not None:
                updates[field] = payload[field]
        # api_key 为空字符串或 None 时保留原值
        new_key = payload.get("api_key")
        if new_key:
            updates["api_key"] = new_key
        if updates.get("is_default"):
            for other in self._session.scalars(
                select(LlmConfig)
                .order_by(LlmConfig.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            ):
                other.is_default = other.id == config_id
        for key, value in updates.items():
            setattr(row, key, value)
        self._session.commit()
        updated = row
        reset_llm_client()
        return _to_out(updated) if updated else None

    def delete_config(self, config_id: str) -> bool:
        row = self._dao.get(config_id)
        if row is None:
            return False
        guard_default_removal(self._session, config_id)
        ok = self._dao.delete(config_id)
        if ok:
            reset_llm_client()
        return ok

    def set_default(self, config_id: str, *, scope_owner: str | None = None) -> dict | None:
        row = self._dao.get(config_id)
        if row is None:
            return None
        if config_business(self._session, config_id):
            raise HTTPException(403, "公共默认只能选择公共语言模型")
        if row.status == "停用":
            raise HTTPException(409, "停用的语言模型不能设为默认")
        return self.update_config(config_id, {"is_default": True})

    def test_connection(self, config_id: str) -> dict:
        row = self._dao.get(config_id)
        if row is None:
            return {"ok": False, "latencyMs": None, "error": "配置不存在"}
        if not row.api_key:
            self._record_probe_status(config_id, row.status, False)
            return {"ok": False, "latencyMs": None, "error": "未配置 API Key"}
        result = _ping_llm(row.base_url, row.model, row.api_key)
        self._record_probe_status(config_id, row.status, bool(result.get("ok")))
        return result

    def _record_probe_status(self, config_id: str, current_status: str, ok: bool) -> None:
        """探活结果落库（失败→异常 / 成功→正常）：徽标与探活结果一致，刷新不回跳；停用态不覆盖（启停只由人工切换）。"""
        if current_status == "停用":
            return
        self._dao.update(config_id, status="正常" if ok else "异常")

    def verify_connection(self, base_url: str, model: str, api_key: str) -> dict:
        """未保存前的验证：直接用弹窗里的原始参数探活。"""
        if not api_key:
            return {"ok": False, "latencyMs": None, "error": "未填写 API Key"}
        return _ping_llm(base_url, model, api_key)

    def get_active_config(self) -> LlmConfig | None:
        """返回当前默认 LLM 配置；DB 无记录时返回 None（由调用方回退 env）。"""
        return public_default(self._session)


def get_active_llm_config() -> LlmConfig | None:
    """供非请求上下文（如 infra.llm.get_llm_client）使用的入口：独立短连接。"""
    from infra.mysql import create_session

    session = create_session()
    try:
        return public_default(session)
    finally:
        session.close()


def resolve_llm_settings(
    business_id: str | None = None, config_id: str | None = None
) -> tuple[str, str, str] | None:
    """Resolve explicit > business > public; only an unset default falls back to env."""
    import os

    from infra.mysql import create_session

    with create_session() as session:
        cfg = resolve_default_config(session, business_id, config_id)
        if cfg is not None:
            return cfg.api_key, cfg.base_url, cfg.model
    env_key = os.getenv("LLM_API_KEY") or os.getenv("ZHIPUAI_API_KEY")
    if not env_key:
        return None
    return (
        env_key,
        os.getenv("LLM_BASE_URL", DEFAULT_BASE_URL),
        os.getenv("LLM_MODEL", DEFAULT_MODEL),
    )


def get_llm_settings_by_id(
    config_id: str | None, business_id: str | None = None
) -> dict[str, Any] | None:
    """Explicit model lookup; invalid selected models never silently fall back."""
    if not config_id:
        return None
    settings = resolve_llm_settings(business_id=business_id, config_id=config_id)
    if settings is None:
        return None
    api_key, base_url, model = settings
    return {"api_key": api_key, "base_url": base_url, "model": model}
