"""Schema 管理应用编排层。"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from infra.s3 import S3Storage
from service.schema_management import SchemaManagementService
from service.workflow_operations import WorkflowOperationsService, workflow_operations_service


class SchemaManagementApplication:
    def __init__(
        self,
        session: Session,
        storage: S3Storage | None = None,
        workflows: WorkflowOperationsService = workflow_operations_service,
    ) -> None:
        self._service = SchemaManagementService(session, storage=storage)
        self._workflows = workflows

    @property
    def storage(self) -> S3Storage:
        return self._service.storage

    def overview(self) -> dict[str, Any]:
        return self._service.overview()

    def list_schemas(self, **kwargs) -> dict[str, Any]:
        return self._service.list_schemas(**kwargs)

    def get_schema(self, schema_id: str, user_id: str | None) -> dict[str, Any]:
        return self._service.get_schema(schema_id, user_id)

    def topology(self, user_id: str | None) -> dict[str, Any]:
        return self._service.topology(user_id)

    def create_entity(self, **kwargs) -> dict[str, Any]:
        return self._service.create_entity(**kwargs)

    def create_relation(self, **kwargs) -> dict[str, Any]:
        return self._service.create_relation(**kwargs)

    def delete_schema(self, schema_id: str, user_id: str) -> dict[str, Any]:
        return self._service.delete_schema(schema_id, user_id)

    def replace_script(self, **kwargs) -> dict[str, Any]:
        return self._service.replace_script(**kwargs)

    def get_script(self, schema_id: str):
        return self._service.get_script(schema_id)

    def start_script_validation(self, **kwargs) -> dict[str, Any]:
        return self._service.start_script_validation(**kwargs)

    def get_script_validation(self, validation_id: str, user_id: str) -> dict[str, Any]:
        return self._service.get_script_validation(validation_id, user_id)

    def run_script_validation(self, validation_id: str) -> dict[str, Any]:
        return self._service.run_script_validation(validation_id)

    async def execute_schema(
        self, schema_id: str, user_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        context = self._service.execution_context(schema_id, user_id)
        return await self._workflows.trigger_schema_execution(payload=payload, **context)
