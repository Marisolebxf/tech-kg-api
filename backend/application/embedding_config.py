"""平台 embedding 模型配置 application facade。"""

from __future__ import annotations

from sqlalchemy.orm import Session

from service.embedding_config import EmbeddingConfigService


class EmbeddingConfigApplication:
    """薄封装：转发到 EmbeddingConfigService。"""

    def __init__(self, session: Session) -> None:
        self._service = EmbeddingConfigService(session)

    def list_configs(self, owner: str | None = None) -> list[dict]:
        return self._service.list_configs(owner=owner)

    def get_config(self, config_id: str) -> dict | None:
        return self._service.get_config(config_id)

    def create_config(self, payload: dict, *, scope_owner: str | None = None) -> dict:
        return self._service.create_config(payload, scope_owner=scope_owner)

    def update_config(
        self, config_id: str, payload: dict, *, scope_owner: str | None = None
    ) -> dict | None:
        return self._service.update_config(config_id, payload, scope_owner=scope_owner)

    def delete_config(self, config_id: str) -> bool:
        return self._service.delete_config(config_id)

    def set_default(self, config_id: str, *, scope_owner: str | None = None) -> dict | None:
        return self._service.set_default(config_id, scope_owner=scope_owner)

    def test_connection(self, config_id: str) -> dict:
        return self._service.test_connection(config_id)

    def verify_connection(self, base_url: str, model: str, api_key: str) -> dict:
        return self._service.verify_connection(base_url, model, api_key)
