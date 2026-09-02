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
from db_model.schema_management import (
    GraphSchemaDefinition,
    GraphSchemaProperty,
    GraphSchemaScript,
    GraphSchemaSource,
)
from infra.llm import LLMClient, get_llm_client
from infra.s3 import S3Storage, get_schema_s3_storage
from service.schema_ddl import (
    default_graph_space,
    describe_schema_columns,
    run_alter_add_ddl,
    run_alter_drop_ddl,
    run_schema_ddl,
)
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


def _allow_system_delete() -> bool:
    """测试/开发模式下允许删除系统 Schema（生产应保持 false）。

    默认 false——保护系统 catalog 不被误删。dev2 compose 会显式设
    SCHEMA_ALLOW_SYSTEM_DELETE=true。
    """
    return os.getenv("SCHEMA_ALLOW_SYSTEM_DELETE", "false").lower() in {"1", "true", "yes", "on"}


# 新 ETL 脚本（entity_extractors_one_entity / relation_extractors_one_relation）
# 统一写的溯源属性。前端/API 创建 schema 时自动附加，避免 merge_node 写图时
# `Unknown column X in schema`。用户已显式声明的同名属性保留用户口径。
_ENTITY_PROVENANCE_PROPERTIES: list[dict[str, str]] = [
    {"name": "vid", "data_type": "string", "category": "provenance"},
    {"name": "source_system", "data_type": "string", "category": "provenance"},
    {"name": "source_table", "data_type": "string", "category": "provenance"},
    {"name": "source_record_id", "data_type": "string", "category": "provenance"},
    {"name": "source_url", "data_type": "string", "category": "provenance"},
    {"name": "ingest_batch", "data_type": "string", "category": "provenance"},
    {"name": "ingest_time", "data_type": "string", "category": "provenance"},
    {"name": "source_update_time", "data_type": "string", "category": "provenance"},
    {"name": "confidence", "data_type": "string", "category": "provenance"},
    {"name": "match_method", "data_type": "string", "category": "provenance"},
    {"name": "match_evidence", "data_type": "string", "category": "provenance"},
]
_RELATION_PROVENANCE_PROPERTIES: list[dict[str, str]] = [
    {"name": "source_table", "data_type": "string", "category": "provenance"},
    {"name": "source_record_id", "data_type": "string", "category": "provenance"},
    {"name": "ingest_batch", "data_type": "string", "category": "provenance"},
    {"name": "ingest_time", "data_type": "string", "category": "provenance"},
    {"name": "confidence", "data_type": "string", "category": "provenance"},
    {"name": "match_method", "data_type": "string", "category": "provenance"},
    {"name": "match_evidence", "data_type": "string", "category": "provenance"},
]


def _inject_provenance_properties(kind: str, payload: dict[str, Any]) -> None:
    """把溯源属性注入 payload['properties']（已声明的保留）。"""
    if os.getenv("SCHEMA_AUTO_PROVENANCE", "true").lower() not in {"1", "true", "yes", "on"}:
        return
    provenance = (
        _ENTITY_PROVENANCE_PROPERTIES if kind == "entity" else _RELATION_PROVENANCE_PROPERTIES
    )
    properties = payload.setdefault("properties", [])
    declared = {p["name"] for p in properties if isinstance(p, dict) and "name" in p}
    for prop in provenance:
        if prop["name"] not in declared:
            properties.append({**prop, "required": False, "rule": ""})


# 公共必选属性：平台喂数抽取依赖的标准列。创建时强制注入头部并置 required=True；
# 用户已声明同名属性则强制 required + category=required（保留用户数据类型口径）。
# source_table 与溯源注入共享去重（先注入 required，provenance 不会再重复追加）。
_ENTITY_REQUIRED_PROPERTIES: list[dict[str, str]] = [
    {"name": "id", "data_type": "string", "category": "required"},
    {"name": "name", "data_type": "string", "category": "required"},
    {"name": "create_time", "data_type": "string", "category": "required"},
    {"name": "update_time", "data_type": "string", "category": "required"},
    {"name": "source_table", "data_type": "string", "category": "required"},
]
_RELATION_REQUIRED_PROPERTIES: list[dict[str, str]] = [
    {"name": "create_time", "data_type": "string", "category": "required"},
    {"name": "update_time", "data_type": "string", "category": "required"},
    {"name": "source_table", "data_type": "string", "category": "required"},
]


def _inject_required_properties(kind: str, payload: dict[str, Any]) -> None:
    """把公共必选属性注入 payload['properties'] 头部（已声明的强制 required + category=required）。"""
    required = _ENTITY_REQUIRED_PROPERTIES if kind == "entity" else _RELATION_REQUIRED_PROPERTIES
    properties = payload.setdefault("properties", [])
    missing: list[dict[str, Any]] = []
    for prop in required:
        declared = next(
            (p for p in properties if isinstance(p, dict) and p.get("name") == prop["name"]),
            None,
        )
        if declared is None:
            missing.append({**prop, "required": True, "rule": ""})
        else:
            declared["required"] = True
            declared["category"] = "required"
    if missing:
        properties[0:0] = missing


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


def _validate_datasource_exists(datasource_id: str) -> None:
    """校验平台数据源存在（业务库 dao，独立短连接）。失败抛 SchemaConflictError。"""
    from service.mysql_datasource import get_mysql_settings_by_id

    if get_mysql_settings_by_id(datasource_id) is None:
        raise SchemaConflictError(f"来源数据源不存在: {datasource_id}")


def _resolve_graph_space(payload: dict[str, Any]) -> str:
    """解析并校验目标图空间：payload 显式指定 > TRS_GRAPH_SPACE 默认。

    空间必须真实存在于图服务（SHOW SPACES），不存在抛 SchemaConflictError。
    """
    space = (payload.get("graph_space") or "").strip() or default_graph_space()
    try:
        from service.schema_ddl import list_graph_spaces

        spaces = list_graph_spaces()
    except Exception as exc:  # noqa: BLE001
        raise SchemaConflictError(f"图服务不可用，无法校验图空间: {exc}") from exc
    if space not in spaces:
        raise SchemaConflictError(f"图空间 {space} 不存在，请先在配置管理页创建或绑定该图空间")
    return space


def find_running_extraction(definition: GraphSchemaDefinition) -> dict[str, Any] | None:
    """查该 Schema 是否有运行中的 kg.schema.extract 执行记录（删除属性前拦截用）。

    返回 ``{executionId, name}``（name 为任务中心展示名）或 ``None``。
    """
    from service.schema_extraction import extract_definition_id
    from service.workflow_repository import repository

    executions = repository.list_executions(
        definition_id=extract_definition_id(definition.schema_key), limit=100
    )
    for execution in executions:
        if execution.get("status") != "RUNNING":
            continue
        if (execution.get("payload") or {}).get("schemaId") != definition.id:
            continue
        task_name = None
        task_id = execution.get("taskId")
        if task_id:
            task = repository.get_task(task_id) or {}
            task_name = task.get("objectName")
        return {
            "executionId": execution["id"],
            "name": task_name or f"{definition.label} 平台喂数抽取",
        }
    return None


def _stale_behind(property_revision: int | None, captured_revision: int | None) -> int:
    """脚本落后版本数：未上传脚本（captured 为 None）或未落后返回 0。"""
    if property_revision is None or captured_revision is None:
        return 0
    return max(int(property_revision) - int(captured_revision), 0)


class SchemaManagementService:
    def __init__(self, session: Session, storage: S3Storage | None = None) -> None:
        self._session = session
        self._dao = SchemaManagementDAO(session)
        self._storage = storage or get_schema_s3_storage()

    def overview(self, graph_space: str | None = None) -> dict[str, Any]:
        stats = self._dao.stats(graph_space)
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
        is_platform_admin: bool = False,
        graph_space: str | None = None,
    ) -> dict[str, Any]:
        user_id = user_id.strip() if user_id else None
        items, total = self._dao.list(
            kind=kind, keyword=keyword, page=page, page_size=page_size, graph_space=graph_space
        )
        return {
            "items": [
                self._serialize(
                    item,
                    user_id=user_id,
                    detail=include_details,
                    is_platform_admin=is_platform_admin,
                )
                for item in items
            ],
            "total": total,
            "page": page,
            "pageSize": page_size,
        }

    def get_schema(
        self,
        schema_id: str,
        user_id: str | None,
        *,
        is_platform_admin: bool = False,
    ) -> dict[str, Any]:
        user_id = user_id.strip() if user_id else None
        definition = self._require_schema(schema_id)
        return self._serialize(
            definition,
            user_id=user_id,
            detail=True,
            is_platform_admin=is_platform_admin,
        )

    def topology(
        self,
        user_id: str | None,
        *,
        is_platform_admin: bool = False,
        graph_space: str | None = None,
    ) -> dict[str, Any]:
        user_id = user_id.strip() if user_id else None
        definitions = self._dao.list_all(graph_space)
        nodes = [
            self._serialize(
                item,
                user_id=user_id,
                detail=False,
                is_platform_admin=is_platform_admin,
            )
            for item in definitions
            if item.kind == "entity"
        ]
        edges = [
            {
                **self._serialize(
                    item,
                    user_id=user_id,
                    detail=False,
                    is_platform_admin=is_platform_admin,
                ),
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
        # 关系与其端点实体必须同空间：DDL 与端点解析都按空间语义执行
        space = payload.get("graph_space") or default_graph_space()
        for endpoint, role in ((source, "起点"), (target, "终点")):
            if endpoint.graph_space != space:
                raise SchemaConflictError(
                    f"关系{role}实体 {endpoint.name} 属于图空间 {endpoint.graph_space}，"
                    f"与目标图空间 {space} 不一致，请在同一空间内选择关联实体"
                )
        payload["graph_space"] = space
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
        is_platform_admin: bool = False,
    ) -> dict[str, Any]:
        user_id = user_id.strip()
        if not user_id or len(user_id) > 128:
            raise SchemaPermissionError("登录用户 ID 不能为空且不能超过 128 个字符")
        definition = self.assert_script_modifiable(
            schema_id,
            user_id,
            is_platform_admin=is_platform_admin,
        )
        workflow_function = self._validate_script(filename, script_data)
        _, cleanup_succeeded = self._persist_script(
            definition=definition,
            filename=filename,
            content_type=content_type,
            script_data=script_data,
            user_id=user_id,
            workflow_function_name=workflow_function,
        )
        result = self._serialize(
            self._require_schema(schema_id),
            user_id=user_id,
            detail=True,
            is_platform_admin=is_platform_admin,
        )
        result["previousScriptCleanupSucceeded"] = cleanup_succeeded
        return result

    def assert_script_modifiable(
        self,
        schema_id: str,
        user_id: str,
        *,
        is_platform_admin: bool = False,
    ) -> GraphSchemaDefinition:
        """前置校验：schema 存在 + 用户有权限更换脚本。失败抛领域错误（→ HTTP 4xx）。"""
        return self.assert_mutable(
            schema_id,
            user_id,
            is_platform_admin=is_platform_admin,
            denied_system_message="只有 Schema 管理员可以更换系统 Schema 脚本",
            denied_owner_message="只能更换自己创建的 Schema 脚本",
        )

    def assert_mutable(
        self,
        schema_id: str,
        user_id: str,
        *,
        is_platform_admin: bool = False,
        denied_system_message: str = "只有 Schema 管理员可以修改系统 Schema",
        denied_owner_message: str = "只能修改自己创建的 Schema",
    ) -> GraphSchemaDefinition:
        """前置校验：schema 存在 + 用户可修改（脚本 / 属性 / 来源表共用同一规则）。

        规则：is_system 需平台管理员或在 SCHEMA_ADMIN_USER_IDS 中；非系统需
        owner 或平台管理员。失败抛领域错误（→ HTTP 4xx）。
        """
        user_id = user_id.strip()
        if not user_id or len(user_id) > 128:
            raise SchemaPermissionError("登录用户 ID 不能为空且不能超过 128 个字符")
        definition = self._require_schema(schema_id)
        if (
            definition.is_system
            and not is_platform_admin
            and user_id not in _schema_admin_user_ids()
        ):
            raise SchemaPermissionError(denied_system_message)
        if not definition.is_system and not is_platform_admin and definition.created_by != user_id:
            raise SchemaPermissionError(denied_owner_message)
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
        is_platform_admin: bool = False,
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
            if (
                definition.is_system
                and not is_platform_admin
                and user_id not in _schema_admin_user_ids()
            ):
                yield {
                    "type": "error",
                    "code": "permission",
                    "stage": "pre",
                    "message": "只有 Schema 管理员可以更换系统 Schema 脚本",
                    "issues": ["只有 Schema 管理员可以更换系统 Schema 脚本"],
                }
                return
            if (
                not definition.is_system
                and not is_platform_admin
                and definition.created_by != user_id
            ):
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
                    # 上传时快照属性修订号：脚本是否"落后于 Schema"由此判定
                    "captured_revision": definition.property_revision,
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

    def add_property(
        self,
        *,
        schema_id: str,
        payload: dict[str, Any],
        user_id: str,
        is_platform_admin: bool = False,
    ) -> dict[str, Any]:
        """新增属性：目录插入 position=max+1 + 图 ``ALTER TAG/EDGE ADD``。

        与 ``_create`` 的「DDL 失败保留 catalog 行」语义不同：属性新增必须保证
        目录与图一致（目录列在图里不存在会导致 merge_node 400），DDL 失败即
        回滚目录行并抛 SchemaDdlError。Nebula ALTER ADD 不支持 NOT NULL →
        新增属性在图里一律可空（目录保留 required 口径）。
        """
        from biz.schemas.schema_management import SchemaPropertyInput

        definition = self.assert_mutable(schema_id, user_id, is_platform_admin=is_platform_admin)
        prop = SchemaPropertyInput(**payload)

        if any(p.name == prop.name for p in definition.properties):
            raise SchemaConflictError("属性名已存在")

        max_position = max((p.position for p in definition.properties), default=-1)
        try:
            definition.properties.append(
                GraphSchemaProperty(
                    name=prop.name,
                    data_type=prop.data_type,
                    required=prop.required,
                    rule=prop.rule,
                    category=prop.category,
                    position=max_position + 1,
                )
            )
            self._session.flush()
        except IntegrityError as exc:
            self._session.rollback()
            raise SchemaConflictError("属性名已存在") from exc

        ddl_result = run_alter_add_ddl(
            definition.kind, definition.name, prop.model_dump(), definition.graph_space
        )
        if ddl_result["status"] != "succeeded":
            self._session.rollback()
            raise SchemaDdlError(f"图 ALTER DDL 执行失败: {ddl_result['error']}")

        definition.property_revision += 1
        try:
            self._session.commit()
        except Exception as exc:
            self._session.rollback()
            raise SchemaManagementError(f"属性保存失败: {exc}") from exc

        refreshed = self._require_schema(schema_id)
        row = next(p for p in refreshed.properties if p.name == prop.name)
        return {
            "property": self._serialize_property(row),
            "ddlStatement": ddl_result["statement"],
            "ddlStatus": ddl_result["status"],
            "ddlError": ddl_result["error"],
        }

    def delete_property(
        self,
        *,
        schema_id: str,
        property_name: str,
        user_id: str,
        is_platform_admin: bool = False,
    ) -> dict[str, Any]:
        """硬删除属性：图库 ``ALTER ... DROP`` 物理删列 + 目录删行，不可逆。

        Guard 顺序：required 属性硬拦 → 运行中抽取任务硬拦（先去任务中心停止）→
        业务引用（identity/关系表达式）只收集进 ``warnings`` 返回不拦。
        列不存在（system schema DDL 未跑过 / 已删过）时跳过 DDL 只删目录行，
        让目录与图库回到同一个事实源。成功后 ``property_revision += 1``。
        """
        definition = self.assert_mutable(schema_id, user_id, is_platform_admin=is_platform_admin)
        row = next((p for p in definition.properties if p.name == property_name), None)
        if row is None:
            raise SchemaNotFoundError(f"属性不存在: {property_name}")
        if row.category == "required":
            raise SchemaConflictError("必选属性不可删除")
        running = find_running_extraction(definition)
        if running is not None:
            raise SchemaConflictError(
                f"任务「{running['name']}」正在抽取该 Schema，请先到任务中心停止，任务结束后重试"
            )
        warnings = self._collect_property_warnings(definition, property_name)

        ddl_statement: str | None = None
        ddl_status = "skipped"
        ddl_error: str | None = None
        columns = describe_schema_columns(definition.kind, definition.name, definition.graph_space)
        if columns and property_name in columns:
            ddl_result = run_alter_drop_ddl(
                definition.kind, definition.name, property_name, definition.graph_space
            )
            if ddl_result["status"] != "succeeded":
                # 图库删列失败（如索引依赖）：目录不动，错误如实透出
                raise SchemaDdlError(f"图 ALTER DDL 执行失败: {ddl_result['error']}")
            ddl_statement = ddl_result["statement"]
            ddl_status = ddl_result["status"]
            ddl_error = ddl_result["error"]

        definition.properties.remove(row)
        definition.property_revision += 1
        try:
            self._session.commit()
        except Exception as exc:
            self._session.rollback()
            if ddl_status == "succeeded":
                # 极小概率坏状态：图库列已删但目录行还在，只告警不做自动补偿
                logger.exception(
                    "DROP 已成功但目录提交失败（目录有/图库无）: %s.%s",
                    definition.name,
                    property_name,
                )
            raise SchemaManagementError(f"属性删除失败: {exc}") from exc
        return {
            "deleted": True,
            "propertyName": property_name,
            "warnings": warnings,
            "ddlStatement": ddl_statement,
            "ddlStatus": ddl_status,
            "ddlError": ddl_error,
        }

    def _collect_property_warnings(
        self, definition: GraphSchemaDefinition, property_name: str
    ) -> list[str]:
        """收集属性被删除后可能失效的业务引用（substring 匹配，只警告不拦）。

        - 本 definition 的 identity_key / attribute_identity_key；
        - 引用该实体的关系的 source_expression / target_expression。
        脚本内引用不扫（由脚本版本号机制提示）。
        """
        warnings: list[str] = []
        for field in ("identity_key", "attribute_identity_key"):
            if property_name in (getattr(definition, field) or ""):
                warnings.append(f"本 Schema 的 {field} 引用了该属性，删除后唯一性判定可能失效")
        for relation in self._dao.referencing_relations(definition.id):
            for field, expression in (
                ("source_expression", relation.source_expression),
                ("target_expression", relation.target_expression),
            ):
                if property_name in (expression or ""):
                    warnings.append(
                        f"关系 {relation.name} 的 {field} 引用了该属性，删除后表达式可能失效"
                    )
        return warnings

    def replace_sources(
        self,
        *,
        schema_id: str,
        sources: list[dict[str, Any]],
        user_id: str,
        is_platform_admin: bool = False,
    ) -> dict[str, Any]:
        """全量替换 schema 的来源表绑定（实体/关系都可绑多张表）。

        每次调用覆盖全部绑定；datasource 存在性经业务库校验。绑定独立水位
        （definition_id + ``source:{id}`` step_id），多表可并行抽取。
        """
        definition = self.assert_mutable(schema_id, user_id, is_platform_admin=is_platform_admin)
        for item in sources:
            _validate_datasource_exists(item["datasource_id"])
        try:
            # 先删后插：同一 flush 里「新行 INSERT 早于旧行 DELETE」会撞
            # uk_kg_schema_source_table 唯一键（重跑幂等必需）
            definition.sources.clear()
            self._session.flush()
            definition.sources = [
                GraphSchemaSource(
                    datasource_id=item["datasource_id"],
                    database_name=item["database_name"],
                    table_name=item["table_name"],
                    pk_column=item.get("pk_column") or "id",
                    time_column=item.get("time_column") or "update_time",
                    query_sql=(item.get("query_sql") or None),
                    position=index,
                )
                for index, item in enumerate(sources)
            ]
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise
        refreshed = self._require_schema(schema_id)
        return {"sources": [self._serialize_source(item) for item in refreshed.sources]}

    def delete_schema(
        self,
        schema_id: str,
        user_id: str,
        *,
        is_platform_admin: bool = False,
    ) -> dict[str, Any]:
        user_id = user_id.strip()
        if not user_id:
            raise SchemaPermissionError("登录用户 ID 不能为空")
        definition = self._require_schema(schema_id)
        if definition.is_system and not _allow_system_delete():
            raise SchemaPermissionError(
                "系统原有 Schema 不允许删除（测试模式可设 SCHEMA_ALLOW_SYSTEM_DELETE=true 开启）"
            )
        if not is_platform_admin and definition.created_by != user_id:
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
        # 公共必选属性（id/name/create_time/update_time/source_table）注入头部：
        # 平台喂数抽取按这些标准列写入；先于溯源注入，source_table 共享去重。
        _inject_required_properties(kind, payload)
        # 自动注入溯源属性：新 ETL 脚本（entity_extractors_one_entity / relation_extractors_one_relation）
        # 统一写 source_system/source_table/source_record_id/source_url/ingest_batch/ingest_time/
        # source_update_time/confidence/match_method/match_evidence + vid 等 11 个溯源属性。
        # 若用户创建 schema 时不显式声明这些列，merge_node 写图时会 400 Unknown column。
        # 这里在 DDL 前自动补齐（已声明的属性保留用户口径）。
        _inject_provenance_properties(kind, payload)
        user_id = user_id.strip()
        if not user_id or len(user_id) > 128:
            raise SchemaPermissionError("X-User-Id 不能为空且不能超过 128 个字符")
        # 解析并锁定目标图空间：目录唯一性按空间判定，DDL 定向执行
        graph_space = _resolve_graph_space(payload)
        payload["graph_space"] = graph_space
        if self._dao.exists_by_key_or_name(payload["schema_key"], payload["name"], graph_space):
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
        ddl_result = run_schema_ddl(kind, payload["name"], payload["properties"], graph_space)
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
        functions = {
            node.name
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        # 优先平台喂数抽取入口 transform(payload)；旧全量脚本入口 workflow(payload) 兼容
        if "transform" in functions:
            return "transform"
        return "workflow" if "workflow" in functions else None

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
                category="relation" if definition.kind == "relation" else "entity",
            )
        except (UnicodeDecodeError, SyntaxError, ValueError, OSError) as exc:
            raise SchemaScriptError(f"Schema 脚本工作流注册失败: {exc}") from exc

    def _require_schema(self, schema_id: str) -> GraphSchemaDefinition:
        definition = self._dao.get(schema_id)
        if definition is None:
            raise SchemaNotFoundError(f"Schema 不存在: {schema_id}")
        return definition

    def _serialize(
        self,
        definition: GraphSchemaDefinition,
        *,
        user_id: str | None,
        detail: bool,
        is_platform_admin: bool = False,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "id": definition.id,
            "key": definition.schema_key,
            "kind": definition.kind,
            "kindLabel": "实体" if definition.kind == "entity" else "关系",
            "graphSpace": definition.graph_space,
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
            "llmConfigId": definition.llm_config_id,
            "ddlStatement": definition.ddl_statement,
            "ddlStatus": definition.ddl_status,
            "ddlError": definition.ddl_error,
            "ddlExecutedAt": _iso(definition.ddl_executed_at),
            "canDelete": bool(
                user_id
                and not definition.is_system
                and (is_platform_admin or definition.created_by == user_id)
            ),
            "canManageProperties": bool(
                is_platform_admin
                or (
                    not definition.is_system
                    and user_id is not None
                    and definition.created_by == user_id
                )
            ),
        }
        if detail:
            result["propertyRevision"] = definition.property_revision
            result["properties"] = [
                self._serialize_property(item) for item in definition.properties
            ]
            result["sources"] = [self._serialize_source(item) for item in definition.sources]
            result["script"] = self._serialize_script(definition.script, definition)
        else:
            result["propertyCount"] = len(definition.properties)
            result["scriptFilename"] = (
                definition.script.original_filename if definition.script else None
            )
        return result

    @staticmethod
    def _serialize_property(item: GraphSchemaProperty) -> dict[str, Any]:
        return {
            "name": item.name,
            "dataType": item.data_type,
            "required": item.required,
            "rule": item.rule,
            "category": item.category,
            "locked": item.category == "required",
        }

    @staticmethod
    def _serialize_source(item: GraphSchemaSource) -> dict[str, Any]:
        return {
            "id": item.id,
            "datasourceId": item.datasource_id,
            "databaseName": item.database_name,
            "tableName": item.table_name,
            "pkColumn": item.pk_column,
            "timeColumn": item.time_column,
            "querySql": item.query_sql,
            "position": item.position,
        }

    @staticmethod
    def _serialize_script(
        script: GraphSchemaScript | None, definition: GraphSchemaDefinition
    ) -> dict[str, Any] | None:
        if script is None:
            return None
        stale_behind = _stale_behind(definition.property_revision, script.captured_revision)
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
            "capturedRevision": script.captured_revision,
            "lastRunStatus": script.last_run_status,
            "lastRunError": script.last_run_error,
            "stale": stale_behind > 0,
            "staleBehind": stale_behind,
            "downloadUrl": f"/api/v1/schema-management/schemas/{definition.id}/script",
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
