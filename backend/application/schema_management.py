"""Schema 管理应用编排层。"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from sqlalchemy.orm import Session

from infra.s3 import S3Storage
from service.schema_management import SchemaManagementService


class SchemaManagementApplication:
    def __init__(self, session: Session, storage: S3Storage | None = None) -> None:
        self._service = SchemaManagementService(session, storage=storage)

    def overview(self) -> dict[str, Any]:
        return self._service.overview()

    def list_schemas(self, **kwargs) -> dict[str, Any]:
        return self._service.list_schemas(**kwargs)

    def get_schema(self, schema_id: str, user_id: str | None, **kwargs) -> dict[str, Any]:
        return self._service.get_schema(schema_id, user_id, **kwargs)

    def topology(self, user_id: str | None, **kwargs) -> dict[str, Any]:
        return self._service.topology(user_id, **kwargs)

    def create_entity(self, **kwargs) -> dict[str, Any]:
        return self._service.create_entity(**kwargs)

    def create_relation(self, **kwargs) -> dict[str, Any]:
        return self._service.create_relation(**kwargs)

    def delete_schema(self, schema_id: str, user_id: str, **kwargs) -> dict[str, Any]:
        return self._service.delete_schema(schema_id, user_id, **kwargs)

    def replace_script(self, **kwargs) -> dict[str, Any]:
        return self._service.replace_script(**kwargs)

    def get_script(self, schema_id: str):
        return self._service.get_script(schema_id)

    def verify_and_save_script(self, **kwargs) -> Iterator[dict[str, Any]]:
        return self._service.verify_and_save_script(**kwargs)

    def get_script_content(self, schema_id: str) -> dict[str, Any]:
        return self._service.get_script_content(schema_id)
