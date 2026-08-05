"""Schema 管理业务逻辑。"""

from __future__ import annotations

import ast
import hashlib
import json
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
from db_model.schema_management import (
    GraphSchemaDefinition,
    GraphSchemaScript,
    GraphSchemaScriptValidation,
)
from infra.s3 import S3Storage, get_schema_s3_storage
from service.schema_script_security import (
    ScriptSafetyError,
    ScriptSafetyReview,
    review_script_with_llm,
    static_security_issues,
)

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

    @property
    def storage(self) -> S3Storage:
        return self._storage

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
        self._prepare_relation_payload(payload)
        return self._create(
            kind="relation",
            payload=payload,
            user_id=user_id,
            filename=filename,
            content_type=content_type,
            script_data=script_data,
        )

    def _prepare_relation_payload(self, payload: dict[str, Any]) -> None:
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

    def replace_script(
        self,
        *,
        schema_id: str,
        user_id: str,
        filename: str,
        content_type: str | None,
        script_data: bytes,
        safety_review: ScriptSafetyReview | None = None,
        safety_validation_id: str | None = None,
    ) -> dict[str, Any]:
        user_id = user_id.strip()
        if not user_id or len(user_id) > 128:
            raise SchemaPermissionError("X-User-Id 不能为空且不能超过 128 个字符")
        definition = self._require_schema(schema_id)
        if definition.is_system and user_id not in _schema_admin_user_ids():
            raise SchemaPermissionError("只有 Schema 管理员可以更换系统 Schema 脚本")
        if not definition.is_system and definition.created_by != user_id:
            raise SchemaPermissionError("只能更换自己创建的 Schema 脚本")

        safety_review = safety_review or self._review_script(filename, script_data)
        if not safety_review.safe:
            raise SchemaScriptError(self._review_failure_message(safety_review))
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
                    **self._safety_script_fields(safety_review, safety_validation_id),
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

    def start_script_validation(
        self,
        *,
        operation: str,
        schema_id: str | None,
        metadata: dict[str, Any] | None,
        user_id: str,
        filename: str,
        content_type: str | None,
        script_data: bytes,
    ) -> dict[str, Any]:
        """把脚本放入隔离区并创建可由 SSE 观察的安全校验任务。"""
        user_id = self._validate_user_id(user_id)
        self._validate_upload_envelope(filename, script_data)
        if operation == "replace":
            if not schema_id:
                raise SchemaScriptError("更换脚本时必须提供 schemaId")
            self._authorize_script_replace(schema_id, user_id)
            metadata = None
        elif operation in {"create_entity", "create_relation"}:
            if metadata is None:
                raise SchemaScriptError("新增 Schema 时必须提供 metadata")
            if self._dao.exists_by_key_or_name(metadata["schema_key"], metadata["name"]):
                raise SchemaConflictError("schemaKey 或 Schema 名称已存在")
            if operation == "create_relation":
                self._prepare_relation_payload(metadata)
            schema_id = None
        else:
            raise SchemaScriptError("不支持的脚本校验操作")

        validation_id = str(uuid4())
        object_key = f"schema-validations/{validation_id}/{uuid4().hex}-{_safe_filename(filename)}"
        stored = None
        try:
            try:
                stored = self._storage.put_bytes(
                    object_key,
                    script_data,
                    content_type or "text/x-python",
                )
            except Exception as exc:
                raise SchemaStorageError("上传待校验脚本失败") from exc
            validation = self._dao.create_script_validation(
                id=validation_id,
                operation=operation,
                schema_id=schema_id,
                metadata_json=(
                    json.dumps(metadata, ensure_ascii=False, separators=(",", ":"))
                    if metadata is not None
                    else None
                ),
                bucket=stored.bucket,
                object_key=stored.object_key,
                original_filename=Path(filename).name,
                content_type=content_type or "text/x-python",
                size_bytes=len(script_data),
                etag=stored.etag,
                sha256=hashlib.sha256(script_data).hexdigest(),
                uploaded_by=user_id,
                status="queued",
                stage="queued",
                progress=5,
                message="脚本已上传到隔离区，等待安全校验",
                summary="",
                issues_json="[]",
            )
            self._session.commit()
        except Exception:
            self._session.rollback()
            if stored:
                self._delete_uploaded_quietly(stored.bucket, stored.object_key)
            raise
        return self._serialize_validation(validation)

    def get_script_validation(self, validation_id: str, user_id: str) -> dict[str, Any]:
        validation = self._require_validation(validation_id)
        if validation.uploaded_by != user_id.strip():
            raise SchemaPermissionError("只能查看自己发起的脚本安全校验")
        return self._serialize_validation(validation)

    def run_script_validation(self, validation_id: str) -> dict[str, Any]:
        """在响应返回后执行静态检查、LLM 审查和最终持久化。"""
        validation = self._require_validation(validation_id)
        if validation.status in {"succeeded", "failed"}:
            return self._serialize_validation(validation)

        self._update_validation(
            validation,
            status="running",
            stage="static_analysis",
            progress=20,
            message="正在检查文件格式、Python 语法和受限能力",
            started_at=validation.started_at or datetime.now(),
        )

        try:
            script_data = self._read_validation_object(validation)
            self._validate_script(validation.original_filename, script_data)
            source = script_data.decode("utf-8-sig")
            static_issues = static_security_issues(source, validation.original_filename)
            if static_issues:
                return self._fail_validation(
                    validation,
                    message="静态安全检查未通过，脚本未保存",
                    summary="脚本使用了 Schema 数据转换不允许的高风险能力",
                    issues=static_issues,
                    error_code="STATIC_SECURITY_REJECTED",
                )

            self._update_validation(
                validation,
                stage="llm_review",
                progress=55,
                message="静态检查已通过，LLM 正在审查业务逻辑和隐藏风险",
            )
            review = review_script_with_llm(source, validation.original_filename)
            if not review.safe:
                return self._fail_validation(
                    validation,
                    message="LLM 安全审查未通过，脚本未保存",
                    summary=review.summary,
                    issues=review.issues,
                    error_code="LLM_SECURITY_REJECTED",
                )

            self._update_validation(
                validation,
                stage="persisting",
                progress=85,
                message="安全审查已通过，正在保存 Schema 与脚本",
                summary=review.summary,
                issues_json=json.dumps(review.issues, ensure_ascii=False),
            )
            result = self._persist_validated_script(validation, script_data, review)
            self._dao.update_script_validation(
                validation,
                status="succeeded",
                stage="completed",
                progress=100,
                message="脚本安全校验通过并已保存",
                summary=review.summary,
                issues_json=json.dumps(review.issues, ensure_ascii=False),
                result_json=json.dumps(result, ensure_ascii=False, default=str),
                result_schema_id=result["id"],
                error_code=None,
                completed_at=datetime.now(),
            )
            self._session.commit()
            return self._serialize_validation(validation)
        except ScriptSafetyError as exc:
            return self._fail_validation(
                validation,
                message="LLM 安全校验无法完成，脚本未保存",
                summary=str(exc),
                issues=exc.issues,
                error_code="LLM_REVIEW_ERROR",
            )
        except SchemaManagementError as exc:
            return self._fail_validation(
                validation,
                message="脚本校验或保存失败",
                summary=str(exc),
                issues=[self._validation_issue(str(exc))],
                error_code=type(exc).__name__,
            )
        except Exception:
            logger.exception("Schema 脚本安全校验任务异常: %s", validation_id)
            return self._fail_validation(
                validation,
                message="安全校验服务发生异常，脚本未保存",
                summary="服务未能完成本次安全校验，请稍后重试",
                issues=[self._validation_issue("服务未能完成本次安全校验，请稍后重试")],
                error_code="INTERNAL_ERROR",
            )
        finally:
            self._delete_uploaded_quietly(validation.bucket, validation.object_key)

    def _persist_validated_script(
        self,
        validation: GraphSchemaScriptValidation,
        script_data: bytes,
        review: ScriptSafetyReview,
    ) -> dict[str, Any]:
        if validation.operation == "replace":
            if validation.schema_id is None:
                raise SchemaScriptError("脚本校验任务缺少 schemaId")
            return self.replace_script(
                schema_id=validation.schema_id,
                user_id=validation.uploaded_by,
                filename=validation.original_filename,
                content_type=validation.content_type,
                script_data=script_data,
                safety_review=review,
                safety_validation_id=validation.id,
            )

        metadata = json.loads(validation.metadata_json or "{}")
        kind = "entity" if validation.operation == "create_entity" else "relation"
        if kind == "relation":
            self._prepare_relation_payload(metadata)
        return self._create(
            kind=kind,
            payload=metadata,
            user_id=validation.uploaded_by,
            filename=validation.original_filename,
            content_type=validation.content_type,
            script_data=script_data,
            safety_review=review,
            safety_validation_id=validation.id,
        )

    def _read_validation_object(self, validation: GraphSchemaScriptValidation) -> bytes:
        try:
            body = self._storage.get_object(validation.bucket, validation.object_key)
            try:
                return body.read()
            finally:
                body.close()
        except Exception as exc:
            raise SchemaStorageError("读取待校验脚本失败") from exc

    def _fail_validation(
        self,
        validation: GraphSchemaScriptValidation,
        *,
        message: str,
        summary: str,
        issues: list[dict[str, Any]],
        error_code: str,
    ) -> dict[str, Any]:
        self._session.rollback()
        validation = self._require_validation(validation.id)
        self._dao.update_script_validation(
            validation,
            status="failed",
            progress=max(validation.progress, 20),
            message=message,
            summary=summary,
            issues_json=json.dumps(issues, ensure_ascii=False),
            error_code=error_code,
            completed_at=datetime.now(),
        )
        self._session.commit()
        return self._serialize_validation(validation)

    def _update_validation(self, validation: GraphSchemaScriptValidation, **values: Any) -> None:
        self._dao.update_script_validation(validation, **values)
        self._session.commit()

    def _require_validation(self, validation_id: str) -> GraphSchemaScriptValidation:
        validation = self._dao.get_script_validation(validation_id)
        if validation is None:
            raise SchemaNotFoundError(f"脚本安全校验任务不存在: {validation_id}")
        return validation

    @staticmethod
    def _validation_issue(message: str) -> dict[str, Any]:
        return {
            "severity": "high",
            "category": "validation",
            "line": None,
            "message": message,
            "suggestion": "修复问题后重新上传脚本。",
        }

    def execution_context(self, schema_id: str, user_id: str) -> dict[str, Any]:
        """Return an authorized, immutable script reference for workflow execution."""
        user_id = user_id.strip()
        if not user_id:
            raise SchemaPermissionError("X-User-Id 不能为空")
        definition = self._require_schema(schema_id)
        if (
            not definition.is_system
            and definition.created_by != user_id
            and user_id not in _schema_admin_user_ids()
        ):
            raise SchemaPermissionError("只能执行自己创建的 Schema 脚本")
        if definition.script is None:
            raise SchemaNotFoundError("该 Schema 没有关联的 Python 脚本")
        return {
            "schema": self._serialize(definition, user_id=user_id, detail=True),
            "script": {
                "bucket": definition.script.bucket,
                "objectKey": definition.script.object_key,
                "sha256": definition.script.sha256,
            },
        }

    def _create(
        self,
        *,
        kind: str,
        payload: dict[str, Any],
        user_id: str,
        filename: str,
        content_type: str | None,
        script_data: bytes,
        safety_review: ScriptSafetyReview | None = None,
        safety_validation_id: str | None = None,
    ) -> dict[str, Any]:
        user_id = user_id.strip()
        if not user_id or len(user_id) > 128:
            raise SchemaPermissionError("X-User-Id 不能为空且不能超过 128 个字符")
        if self._dao.exists_by_key_or_name(payload["schema_key"], payload["name"]):
            raise SchemaConflictError("schemaKey 或 Schema 名称已存在")

        safety_review = safety_review or self._review_script(filename, script_data)
        if not safety_review.safe:
            raise SchemaScriptError(self._review_failure_message(safety_review))
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
                    **self._safety_script_fields(safety_review, safety_validation_id),
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

    @staticmethod
    def _validate_upload_envelope(filename: str, data: bytes) -> None:
        if not filename or Path(filename).suffix.lower() != ".py":
            raise SchemaScriptError("必须上传 .py 格式的 Python 脚本")
        if not data:
            raise SchemaScriptError("Python 脚本不能为空")
        if len(data) > max_script_bytes():
            raise SchemaScriptError(f"Python 脚本不能超过 {max_script_bytes() // (1024 * 1024)} MB")

    @staticmethod
    def _validate_user_id(user_id: str) -> str:
        normalized = user_id.strip()
        if not normalized or len(normalized) > 128:
            raise SchemaPermissionError("X-User-Id 不能为空且不能超过 128 个字符")
        return normalized

    def _authorize_script_replace(self, schema_id: str, user_id: str) -> None:
        definition = self._require_schema(schema_id)
        if definition.is_system and user_id not in _schema_admin_user_ids():
            raise SchemaPermissionError("只有 Schema 管理员可以更换系统 Schema 脚本")
        if not definition.is_system and definition.created_by != user_id:
            raise SchemaPermissionError("只能更换自己创建的 Schema 脚本")

    def _review_script(self, filename: str, data: bytes) -> ScriptSafetyReview:
        self._validate_script(filename, data)
        source = data.decode("utf-8-sig")
        issues = static_security_issues(source, filename)
        if issues:
            return ScriptSafetyReview(
                safe=False,
                summary="静态安全检查发现脚本使用了受限能力",
                issues=issues,
                model="static",
            )
        try:
            return review_script_with_llm(source, filename)
        except ScriptSafetyError as exc:
            raise SchemaScriptError(str(exc)) from exc

    @staticmethod
    def _review_failure_message(review: ScriptSafetyReview) -> str:
        details = []
        for issue in review.issues[:3]:
            line = f"第 {issue['line']} 行" if issue.get("line") else "脚本"
            details.append(f"{line}：{issue.get('message', '存在安全风险')}")
        suffix = "；".join(details)
        return f"脚本安全校验未通过：{suffix or review.summary}"

    @staticmethod
    def _safety_script_fields(
        review: ScriptSafetyReview, validation_id: str | None
    ) -> dict[str, Any]:
        return {
            "safety_validation_id": validation_id,
            "safety_status": "approved",
            "safety_summary": review.summary,
            "safety_issues": json.dumps(review.issues, ensure_ascii=False),
            "safety_model": review.model,
            "safety_validated_at": datetime.now(),
        }

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
        try:
            safety_issues = json.loads(script.safety_issues or "[]")
        except json.JSONDecodeError:
            safety_issues = []
        return {
            "filename": script.original_filename,
            "contentType": script.content_type,
            "sizeBytes": script.size_bytes,
            "etag": script.etag,
            "sha256": script.sha256,
            "uploadedBy": script.uploaded_by,
            "uploadedAt": _iso(script.uploaded_at),
            "safetyValidationId": script.safety_validation_id,
            "safetyStatus": script.safety_status,
            "safetySummary": script.safety_summary or "",
            "safetyIssues": safety_issues,
            "safetyModel": script.safety_model,
            "safetyValidatedAt": _iso(script.safety_validated_at),
            "downloadUrl": f"/api/v1/schema-management/schemas/{schema_id}/script",
        }

    @staticmethod
    def _serialize_validation(validation: GraphSchemaScriptValidation) -> dict[str, Any]:
        try:
            issues = json.loads(validation.issues_json or "[]")
        except json.JSONDecodeError:
            issues = []
        try:
            result = json.loads(validation.result_json) if validation.result_json else None
        except json.JSONDecodeError:
            result = None
        return {
            "id": validation.id,
            "operation": validation.operation,
            "schemaId": validation.schema_id,
            "filename": validation.original_filename,
            "sizeBytes": validation.size_bytes,
            "sha256": validation.sha256,
            "status": validation.status,
            "stage": validation.stage,
            "progress": validation.progress,
            "message": validation.message,
            "summary": validation.summary,
            "issues": issues,
            "result": result,
            "resultSchemaId": validation.result_schema_id,
            "errorCode": validation.error_code,
            "createdAt": _iso(validation.created_at),
            "startedAt": _iso(validation.started_at),
            "completedAt": _iso(validation.completed_at),
            "eventsUrl": (f"/api/v1/schema-management/script-validations/{validation.id}/events"),
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
