"""Schema 管理业务逻辑。"""

from __future__ import annotations

import ast
import hashlib
import logging
import os
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from dao.schema_management import SchemaManagementDAO
from db_model.schema_management import GraphSchemaDefinition, GraphSchemaScript
from infra.s3 import S3Storage, get_schema_s3_storage

logger = logging.getLogger(__name__)


class SchemaManagementError(Exception):
    """Schema 管理领域错误。"""


class SchemaNotFoundError(SchemaManagementError):
    pass


class SchemaConflictError(SchemaManagementError):
    pass


class SchemaPermissionError(SchemaManagementError):
    pass


class SchemaScriptError(SchemaManagementError):
    pass


class SchemaStorageError(SchemaManagementError):
    pass


def max_script_bytes() -> int:
    return int(os.getenv("SCHEMA_SCRIPT_MAX_BYTES", str(10 * 1024 * 1024)))


def _schema_admin_user_ids() -> set[str]:
    return {
        item.strip()
        for item in os.getenv("SCHEMA_ADMIN_USER_IDS", "schema-admin").split(",")
        if item.strip()
    }


def _iso(value: datetime | date | None) -> str | None:
    return value.isoformat() if value else None


def _safe_filename(filename: str) -> str:
    name = Path(filename).name
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name) or "schema.py"


class SchemaManagementService:
    def __init__(self, session: Session, storage: S3Storage | None = None) -> None:
        self._session = session
        self._dao = SchemaManagementDAO(session)
        self._storage = storage or get_schema_s3_storage()

    def overview(self) -> dict[str, Any]:
        stats = self._dao.stats()
        return {
            "currentVersion": os.getenv("SCHEMA_CATALOG_VERSION", "tech-kg-schema-v1.8"),
            "environment": os.getenv("SCHEMA_CATALOG_ENVIRONMENT", "生产中"),
            "releasedAt": os.getenv("SCHEMA_CATALOG_RELEASED_AT", "2026-07-11"),
            "entityTypes": stats["entity_count"],
            "coreEntityTypes": stats["core_count"],
            "relationTypes": stats["relation_count"],
            "factRelationTypes": stats["fact_count"],
            "inferredRelationTypes": stats["inferred_count"],
            "propertyFields": stats["property_count"],
            "requiredFields": stats["required_count"],
            "constraintRules": stats["constraint_count"],
            "sourceMappings": stats["mapping_count"],
        }

    def list_schemas(
        self,
        *,
        kind: str | None,
        keyword: str | None,
        page: int,
        page_size: int,
        user_id: str | None,
        include_details: bool = False,
    ) -> dict[str, Any]:
        user_id = user_id.strip() if user_id else None
        items, total = self._dao.list(kind=kind, keyword=keyword, page=page, page_size=page_size)
        return {
            "items": [
                self._serialize(item, user_id=user_id, detail=include_details) for item in items
            ],
            "total": total,
            "page": page,
            "pageSize": page_size,
        }

    def get_schema(self, schema_id: str, user_id: str | None) -> dict[str, Any]:
        user_id = user_id.strip() if user_id else None
        definition = self._require_schema(schema_id)
        return self._serialize(definition, user_id=user_id, detail=True)

    def topology(self, user_id: str | None) -> dict[str, Any]:
        user_id = user_id.strip() if user_id else None
        definitions = self._dao.list_all()
        nodes = [
            self._serialize(item, user_id=user_id, detail=False)
            for item in definitions
            if item.kind == "entity"
        ]
        edges = [
            {
                **self._serialize(item, user_id=user_id, detail=False),
                "sourceSchemaId": item.source_schema_id,
                "targetSchemaId": item.target_schema_id,
            }
            for item in definitions
            if item.kind == "relation"
        ]
        return {"nodes": nodes, "edges": edges}

    def create_entity(
        self,
        *,
        payload: dict[str, Any],
        user_id: str,
        filename: str,
        content_type: str | None,
        script_data: bytes,
    ) -> dict[str, Any]:
        return self._create(
            kind="entity",
            payload=payload,
            user_id=user_id,
            filename=filename,
            content_type=content_type,
            script_data=script_data,
        )

    def create_relation(
        self,
        *,
        payload: dict[str, Any],
        user_id: str,
        filename: str,
        content_type: str | None,
        script_data: bytes,
    ) -> dict[str, Any]:
        source_id = payload.get("source_schema_id")
        target_id = payload.get("target_schema_id")
        source = self._dao.get_entity(source_id) if source_id else None
        target = self._dao.get_entity(target_id) if target_id else None
        if source_id and source is None:
            raise SchemaConflictError("关系起点必须引用已存在的实体 Schema")
        if target_id and target is None:
            raise SchemaConflictError("关系终点必须引用已存在的实体 Schema")
        if not source_id or not target_id:
            raise SchemaConflictError("用户新建关系的起点和终点必须是已存在的实体 Schema")
        payload["source_expression"] = payload.get("source_expression") or source.name
        payload["target_expression"] = payload.get("target_expression") or target.name
        return self._create(
            kind="relation",
            payload=payload,
            user_id=user_id,
            filename=filename,
            content_type=content_type,
            script_data=script_data,
        )

    def replace_script(
        self,
        *,
        schema_id: str,
        user_id: str,
        filename: str,
        content_type: str | None,
        script_data: bytes,
    ) -> dict[str, Any]:
        user_id = user_id.strip()
        if not user_id or len(user_id) > 128:
            raise SchemaPermissionError("X-User-Id 不能为空且不能超过 128 个字符")
        definition = self._require_schema(schema_id)
        if definition.is_system and user_id not in _schema_admin_user_ids():
            raise SchemaPermissionError("只有 Schema 管理员可以更换系统 Schema 脚本")
        if not definition.is_system and definition.created_by != user_id:
            raise SchemaPermissionError("只能更换自己创建的 Schema 脚本")

        self._validate_script(filename, script_data)
        object_key = (
            f"schemas/{definition.kind}/{schema_id}/{uuid4().hex}-{_safe_filename(filename)}"
        )
        old_script = self._script_snapshot(definition.script)
        stored = None
        try:
            try:
                stored = self._storage.put_bytes(
                    object_key, script_data, content_type or "text/x-python"
                )
            except Exception as exc:
                raise SchemaStorageError("上传 Schema Python 脚本失败") from exc
            self._dao.save_script(
                definition,
                script={
                    "bucket": stored.bucket,
                    "object_key": stored.object_key,
                    "original_filename": Path(filename).name,
                    "content_type": content_type or "text/x-python",
                    "size_bytes": len(script_data),
                    "etag": stored.etag,
                    "sha256": hashlib.sha256(script_data).hexdigest(),
                    "uploaded_by": user_id,
                },
            )
            self._session.commit()
        except Exception:
            self._session.rollback()
            if stored:
                self._delete_uploaded_quietly(stored.bucket, stored.object_key)
            raise

        cleanup_succeeded = True
        if old_script and old_script["object_key"] != stored.object_key:
            try:
                self._storage.delete_object(old_script["bucket"], old_script["object_key"])
            except Exception:
                cleanup_succeeded = False
                logger.exception("旧 Schema 脚本清理失败: %s", schema_id)
        result = self._serialize(self._require_schema(schema_id), user_id=user_id, detail=True)
        result["previousScriptCleanupSucceeded"] = cleanup_succeeded
        return result

    def delete_schema(self, schema_id: str, user_id: str) -> dict[str, Any]:
        user_id = user_id.strip()
        if not user_id:
            raise SchemaPermissionError("X-User-Id 不能为空")
        definition = self._require_schema(schema_id)
        if definition.is_system:
            raise SchemaPermissionError("系统原有 Schema 不允许删除")
        if definition.created_by != user_id:
            raise SchemaPermissionError("只能删除自己创建的 Schema")
        if definition.kind == "entity":
            references = self._dao.referenced_relation_names(schema_id)
            if references:
                raise SchemaConflictError(
                    f"该实体 Schema 仍被关系引用，请先删除关系: {', '.join(references[:5])}"
                )

        script = self._script_snapshot(definition.script)
        self._dao.delete(definition)
        self._session.commit()

        cleanup_succeeded = True
        if script:
            try:
                self._storage.delete_object(script["bucket"], script["object_key"])
            except Exception:
                cleanup_succeeded = False
                logger.exception("Schema 已删除，但 S3 脚本清理失败: %s", schema_id)
        return {"id": schema_id, "deleted": True, "scriptCleanupSucceeded": cleanup_succeeded}

    def get_script(self, schema_id: str) -> tuple[GraphSchemaScript, Any]:
        definition = self._require_schema(schema_id)
        if definition.script is None:
            raise SchemaNotFoundError("该 Schema 没有关联的 Python 脚本")
        try:
            body = self._storage.get_object(definition.script.bucket, definition.script.object_key)
        except Exception as exc:
            raise SchemaStorageError("读取 Schema Python 脚本失败") from exc
        return definition.script, body

    def _create(
        self,
        *,
        kind: str,
        payload: dict[str, Any],
        user_id: str,
        filename: str,
        content_type: str | None,
        script_data: bytes,
    ) -> dict[str, Any]:
        user_id = user_id.strip()
        if not user_id or len(user_id) > 128:
            raise SchemaPermissionError("X-User-Id 不能为空且不能超过 128 个字符")
        if self._dao.exists_by_key_or_name(payload["schema_key"], payload["name"]):
            raise SchemaConflictError("schemaKey 或 Schema 名称已存在")

        self._validate_script(filename, script_data)
        schema_id = str(uuid4())
        object_key = f"schemas/{kind}/{schema_id}/{uuid4().hex}-{_safe_filename(filename)}"
        sha256 = hashlib.sha256(script_data).hexdigest()
        stored = None
        try:
            try:
                stored = self._storage.put_bytes(
                    object_key,
                    script_data,
                    content_type or "text/x-python",
                )
            except Exception as exc:
                raise SchemaStorageError("上传 Schema Python 脚本失败") from exc
            self._dao.create(
                schema_id=schema_id,
                kind=kind,
                payload=payload,
                created_by=user_id,
                script={
                    "bucket": stored.bucket,
                    "object_key": stored.object_key,
                    "original_filename": Path(filename).name,
                    "content_type": content_type or "text/x-python",
                    "size_bytes": len(script_data),
                    "etag": stored.etag,
                    "sha256": sha256,
                    "uploaded_by": user_id,
                },
            )
            self._session.commit()
        except IntegrityError as exc:
            self._session.rollback()
            if stored:
                self._delete_uploaded_quietly(stored.bucket, stored.object_key)
            raise SchemaConflictError("schemaKey、Schema 名称或属性名已存在") from exc
        except Exception:
            self._session.rollback()
            if stored:
                self._delete_uploaded_quietly(stored.bucket, stored.object_key)
            raise

        created = self._require_schema(schema_id)
        return self._serialize(created, user_id=user_id, detail=True)

    @staticmethod
    def _validate_script(filename: str, data: bytes) -> None:
        if not filename or Path(filename).suffix.lower() != ".py":
            raise SchemaScriptError("必须上传 .py 格式的 Python 脚本")
        if not data:
            raise SchemaScriptError("Python 脚本不能为空")
        if len(data) > max_script_bytes():
            raise SchemaScriptError(f"Python 脚本不能超过 {max_script_bytes() // (1024 * 1024)} MB")
        try:
            source = data.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise SchemaScriptError("Python 脚本必须使用 UTF-8 编码") from exc
        try:
            ast.parse(source, filename=Path(filename).name)
        except SyntaxError as exc:
            raise SchemaScriptError(
                f"Python 脚本语法错误（第 {exc.lineno or 0} 行）: {exc.msg}"
            ) from exc

    def _require_schema(self, schema_id: str) -> GraphSchemaDefinition:
        definition = self._dao.get(schema_id)
        if definition is None:
            raise SchemaNotFoundError(f"Schema 不存在: {schema_id}")
        return definition

    def _serialize(
        self, definition: GraphSchemaDefinition, *, user_id: str | None, detail: bool
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "id": definition.id,
            "key": definition.schema_key,
            "kind": definition.kind,
            "kindLabel": "实体" if definition.kind == "entity" else "关系",
            "name": definition.name,
            "label": definition.label,
            "description": definition.description,
            "identityKey": definition.identity_key,
            "attributeIdentityKey": definition.attribute_identity_key,
            "attributeSource": definition.attribute_source,
            "instanceCount": definition.instance_count,
            "version": definition.version,
            "isCore": definition.is_core,
            "relationCategory": definition.relation_category,
            "isSystem": definition.is_system,
            "createdBy": definition.created_by,
            "createdAt": _iso(definition.created_at),
            "updatedAt": _iso(definition.updated_at),
            "sourceSchemaId": definition.source_schema_id,
            "sourceSchemaName": definition.source_expression
            or (definition.source_schema.name if definition.source_schema else None),
            "targetSchemaId": definition.target_schema_id,
            "targetSchemaName": definition.target_expression
            or (definition.target_schema.name if definition.target_schema else None),
            "mappings": [item.source_name for item in definition.mappings],
            "canDelete": bool(
                user_id and not definition.is_system and definition.created_by == user_id
            ),
        }
        if detail:
            result["properties"] = [
                {
                    "name": item.name,
                    "dataType": item.data_type,
                    "required": item.required,
                    "rule": item.rule,
                    "category": item.category,
                }
                for item in definition.properties
            ]
            result["script"] = self._serialize_script(definition.script, definition.id)
        else:
            result["propertyCount"] = len(definition.properties)
            result["scriptFilename"] = (
                definition.script.original_filename if definition.script else None
            )
        return result

    @staticmethod
    def _serialize_script(
        script: GraphSchemaScript | None, schema_id: str
    ) -> dict[str, Any] | None:
        if script is None:
            return None
        return {
            "filename": script.original_filename,
            "contentType": script.content_type,
            "sizeBytes": script.size_bytes,
            "etag": script.etag,
            "sha256": script.sha256,
            "uploadedBy": script.uploaded_by,
            "uploadedAt": _iso(script.uploaded_at),
            "downloadUrl": f"/api/v1/schema-management/schemas/{schema_id}/script",
        }

    @staticmethod
    def _script_snapshot(script: GraphSchemaScript | None) -> dict[str, str] | None:
        if script is None:
            return None
        return {"bucket": script.bucket, "object_key": script.object_key}

    def _delete_uploaded_quietly(self, bucket: str, object_key: str) -> None:
        try:
            self._storage.delete_object(bucket, object_key)
        except Exception:
            logger.exception("回滚 S3 脚本失败: %s/%s", bucket, object_key)
