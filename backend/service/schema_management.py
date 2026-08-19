"""Schema 管理业务逻辑。"""

from __future__ import annotations

import ast
import hashlib
import logging
import os
import re
from collections.abc import Iterator
from datetime import date, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from dao.schema_management import SchemaManagementDAO
from db_model.schema_management import GraphSchemaDefinition, GraphSchemaScript
from infra.llm import LLMClient, get_llm_client
from infra.s3 import S3Storage, get_schema_s3_storage
from service.schema_ddl import run_schema_ddl
from service.script_security import review_script_security

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


class SchemaDdlError(SchemaManagementError):
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


def _workflow_definition_id(schema_key: str) -> str:
    safe_key = re.sub(r"[^a-z0-9_-]", "-", schema_key.lower()).strip("-")
    fallback = hashlib.sha256(schema_key.encode()).hexdigest()[:12]
    candidate = f"schema-{safe_key or fallback}"
    if len(candidate) <= 64:
        return candidate
    suffix = hashlib.sha256(candidate.encode()).hexdigest()[:8]
    return f"{candidate[:55]}-{suffix}"


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
    ) -> dict[str, Any]:
        return self._create(kind="entity", payload=payload, user_id=user_id)

    def create_relation(
        self,
        *,
        payload: dict[str, Any],
        user_id: str,
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
        return self._create(kind="relation", payload=payload, user_id=user_id)

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
        definition = self.assert_script_modifiable(schema_id, user_id)
        workflow_function = self._validate_script(filename, script_data)
        _, cleanup_succeeded = self._persist_script(
            definition=definition,
            filename=filename,
            content_type=content_type,
            script_data=script_data,
            user_id=user_id,
            workflow_function_name=workflow_function,
        )
        result = self._serialize(self._require_schema(schema_id), user_id=user_id, detail=True)
        result["previousScriptCleanupSucceeded"] = cleanup_succeeded
        return result

    def assert_script_modifiable(self, schema_id: str, user_id: str) -> GraphSchemaDefinition:
        """前置校验：schema 存在 + 用户有权限更换脚本。失败抛领域错误（→ HTTP 4xx）。"""
        user_id = user_id.strip()
        if not user_id or len(user_id) > 128:
            raise SchemaPermissionError("X-User-Id 不能为空且不能超过 128 个字符")
        definition = self._require_schema(schema_id)
        if definition.is_system and user_id not in _schema_admin_user_ids():
            raise SchemaPermissionError("只有 Schema 管理员可以更换系统 Schema 脚本")
        if not definition.is_system and definition.created_by != user_id:
            raise SchemaPermissionError("只能更换自己创建的 Schema 脚本")
        return definition

    def verify_and_save_script(
        self,
        *,
        schema_id: str,
        user_id: str,
        filename: str,
        content_type: str | None,
        script_data: bytes,
        llm_client: LLMClient | None = None,
    ) -> Iterator[dict[str, Any]]:
        """LLM 安全校验 + 保存脚本，按阶段 yield 事件供 SSE 推送。

        为避免跨线程使用请求 Session，本生成器内部基于 ``self._session.bind`` 新建
        独立 Session 供整个校验/保存流程使用；调用方应在单一专用线程中驱动本生成器。

        前置失败（schema 不存在 / 无权限）yield 带 ``code`` 的 error 事件（供 handler
        映射 4xx）；其余阶段失败 yield 普通 error 事件。不抛领域错误。
        """
        own_session = Session(self._session.bind)
        inner = SchemaManagementService(own_session, storage=self._storage)
        user_id = user_id.strip()
        try:
            try:
                definition = inner._require_schema(schema_id)
            except SchemaNotFoundError:
                yield {
                    "type": "error",
                    "code": "not_found",
                    "stage": "pre",
                    "message": f"Schema 不存在: {schema_id}",
                    "issues": [f"Schema 不存在: {schema_id}"],
                }
                return
            if definition.is_system and user_id not in _schema_admin_user_ids():
                yield {
                    "type": "error",
                    "code": "permission",
                    "stage": "pre",
                    "message": "只有 Schema 管理员可以更换系统 Schema 脚本",
                    "issues": ["只有 Schema 管理员可以更换系统 Schema 脚本"],
                }
                return
            if not definition.is_system and definition.created_by != user_id:
                yield {
                    "type": "error",
                    "code": "permission",
                    "stage": "pre",
                    "message": "只能更换自己创建的 Schema 脚本",
                    "issues": ["只能更换自己创建的 Schema 脚本"],
                }
                return

            yield {"type": "progress", "stage": "syntax", "message": "语法检查中..."}

            try:
                workflow_function = inner._validate_script(filename, script_data)
            except SchemaScriptError as exc:
                yield {
                    "type": "error",
                    "stage": "syntax",
                    "message": str(exc),
                    "issues": [str(exc)],
                }
                return

            try:
                source = script_data.decode("utf-8-sig")
            except UnicodeDecodeError:
                source = script_data.decode("utf-8", errors="replace")

            yield {"type": "progress", "stage": "llm", "message": "LLM 安全校验中..."}

            client = llm_client if llm_client is not None else get_llm_client()
            if client is None:
                yield {
                    "type": "error",
                    "stage": "llm",
                    "message": "LLM 安全校验服务不可用，请联系管理员配置 LLM_API_KEY",
                    "issues": ["LLM 安全校验服务不可用"],
                }
                return

            verdict = review_script_security(client, filename, source)
            if not verdict.safe:
                yield {
                    "type": "error",
                    "stage": "llm",
                    "message": verdict.summary or "脚本未通过 LLM 安全校验",
                    "issues": verdict.issues or ["脚本未通过 LLM 安全校验"],
                }
                return

            yield {"type": "progress", "stage": "saving", "message": "保存脚本中..."}

            try:
                refreshed, _ = inner._persist_script(
                    definition=definition,
                    filename=filename,
                    content_type=content_type,
                    script_data=script_data,
                    user_id=user_id,
                    workflow_function_name=workflow_function,
                )
            except SchemaManagementError as exc:
                yield {
                    "type": "error",
                    "stage": "saving",
                    "message": str(exc),
                    "issues": [str(exc)],
                }
                return

            script = refreshed.script
            yield {
                "type": "success",
                "script": {
                    "scriptId": script.id if script else None,
                    "filename": script.original_filename if script else Path(filename).name,
                    "sha256": script.sha256 if script else None,
                    "sizeBytes": script.size_bytes if script else len(script_data),
                    "uploadedAt": _iso(script.uploaded_at) if script else None,
                },
            }
        finally:
            own_session.close()

    def get_script_content(self, schema_id: str) -> dict[str, Any]:
        script, body = self.get_script(schema_id)
        try:
            data = body.read()
        except Exception as exc:
            raise SchemaStorageError("读取 Schema Python 脚本失败") from exc
        finally:
            try:
                body.close()
            except Exception:
                logger.exception("关闭脚本流失败: %s", schema_id)
        try:
            content = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise SchemaScriptError("Python 脚本不是有效的 UTF-8 文本") from exc
        return {
            "filename": script.original_filename,
            "content": content,
            "contentType": script.content_type,
            "sizeBytes": script.size_bytes,
            "sha256": script.sha256,
            "uploadedAt": _iso(script.uploaded_at),
        }

    def _persist_script(
        self,
        *,
        definition: GraphSchemaDefinition,
        filename: str,
        content_type: str | None,
        script_data: bytes,
        user_id: str,
        workflow_function_name: str | None,
    ) -> tuple[GraphSchemaDefinition, bool]:
        """上传 S3 + 注册工作流 + 写 DB + commit；失败回滚并清理 S3。

        返回 (刷新后的 definition, 旧脚本清理是否成功)。
        """
        schema_id = definition.id
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
            workflow_definition = self._register_workflow(
                definition=definition,
                filename=filename,
                script_data=script_data,
                function_name=workflow_function_name,
            )
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
                    "workflow_definition_id": (
                        workflow_definition["id"] if workflow_definition else None
                    ),
                    "workflow_function_name": workflow_function_name,
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
        refreshed = self._require_schema(schema_id)
        return refreshed, cleanup_succeeded

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
    ) -> dict[str, Any]:
        user_id = user_id.strip()
        if not user_id or len(user_id) > 128:
            raise SchemaPermissionError("X-User-Id 不能为空且不能超过 128 个字符")
        if self._dao.exists_by_key_or_name(payload["schema_key"], payload["name"]):
            raise SchemaConflictError("schemaKey 或 Schema 名称已存在")

        schema_id = str(uuid4())
        try:
            self._dao.create(
                schema_id=schema_id,
                kind=kind,
                payload=payload,
                created_by=user_id,
                script=None,
            )
            self._session.commit()
        except IntegrityError as exc:
            self._session.rollback()
            raise SchemaConflictError("schemaKey、Schema 名称或属性名已存在") from exc
        except Exception:
            self._session.rollback()
            raise

        # 落库后执行图 DDL，结果回写。DDL 失败不回滚 catalog 行。
        ddl_result = run_schema_ddl(kind, payload["name"], payload["properties"])
        try:
            definition = self._require_schema(schema_id)
            definition.ddl_statement = ddl_result["statement"]
            definition.ddl_status = ddl_result["status"]
            definition.ddl_error = ddl_result["error"]
            if ddl_result["executed_at"]:
                definition.ddl_executed_at = datetime.fromisoformat(ddl_result["executed_at"])
            self._session.commit()
        except Exception as exc:
            self._session.rollback()
            logger.exception("回写 DDL 结果失败: %s", schema_id)
            raise SchemaDdlError(f"DDL 结果回写失败: {exc}") from exc

        created = self._require_schema(schema_id)
        return self._serialize(created, user_id=user_id, detail=True)

    @staticmethod
    def _validate_script(filename: str, data: bytes) -> str | None:
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
            tree = ast.parse(source, filename=Path(filename).name)
        except SyntaxError as exc:
            raise SchemaScriptError(
                f"Python 脚本语法错误（第 {exc.lineno or 0} 行）: {exc.msg}"
            ) from exc
        return next(
            (
                node.name
                for node in tree.body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == "workflow"
            ),
            None,
        )

    @staticmethod
    def _register_workflow(
        *,
        definition: GraphSchemaDefinition,
        filename: str,
        script_data: bytes,
        function_name: str | None,
    ) -> dict[str, Any] | None:
        if function_name is None:
            return None
        from service.workflow_operations import workflow_operations_service

        try:
            return workflow_operations_service.create_python_definition(
                filename,
                script_data,
                function_name,
                _workflow_definition_id(definition.schema_key),
                f"{definition.label} Schema 抽取",
                timeout_seconds=int(os.getenv("SCHEMA_WORKFLOW_TIMEOUT_SECONDS", "3600")),
            )
        except (UnicodeDecodeError, SyntaxError, ValueError, OSError) as exc:
            raise SchemaScriptError(f"Schema 脚本工作流注册失败: {exc}") from exc

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
            "ddlStatement": definition.ddl_statement,
            "ddlStatus": definition.ddl_status,
            "ddlError": definition.ddl_error,
            "ddlExecutedAt": _iso(definition.ddl_executed_at),
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
            "workflowDefinitionId": script.workflow_definition_id,
            "workflowFunctionName": script.workflow_function_name,
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
