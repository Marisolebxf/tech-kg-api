"""平台 LLM 配置 application facade。"""

from __future__ import annotations

from sqlalchemy.orm import Session

from service.llm_config import LlmConfigService


class LlmConfigApplication:
    """薄封装：转发到 LlmConfigService。"""

    def __init__(self, session: Session) -> None:
        self._service = LlmConfigService(session)

    def list_configs(self, owner: str | None = None) -> list[dict]:
        return self._service.list_configs(owner=owner)

    def get_config(self, config_id: str) -> dict | None:
        return self._service.get_config(config_id)

    def create_config(self, payload: dict) -> dict:
        return self._service.create_config(payload)

    def update_config(self, config_id: str, payload: dict) -> dict | None:
        return self._service.update_config(config_id, payload)

    def delete_config(self, config_id: str) -> bool:
        return self._service.delete_config(config_id)

    def set_default(self, config_id: str) -> dict | None:
        return self._service.set_default(config_id)

    def test_connection(self, config_id: str) -> dict:
        return self._service.test_connection(config_id)
