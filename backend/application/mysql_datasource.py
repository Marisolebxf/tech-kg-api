"""平台 MySQL 数据源 application facade。"""

from __future__ import annotations

from sqlalchemy.orm import Session

from service.mysql_datasource import MysqlDatasourceService


class MysqlDatasourceApplication:
    """薄封装：转发到 MysqlDatasourceService。"""

    def __init__(self, session: Session) -> None:
        self._service = MysqlDatasourceService(session)

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

    def list_databases(self, config_id: str) -> list[str]:
        return self._service.list_databases(config_id)

    def list_tables(self, config_id: str, database: str | None = None) -> list[dict]:
        return self._service.list_tables(config_id, database)

    def list_columns(self, config_id: str, table: str, database: str | None = None) -> list[dict]:
        return self._service.list_columns(config_id, table, database)
