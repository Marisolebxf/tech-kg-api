"""Trusted, per-invocation data gateway. No connection objects or secrets cross RPC."""

from __future__ import annotations

import copy
import inspect
import json
import re
import threading
from typing import Any

from fastapi.encoders import jsonable_encoder

from service.business_access_control import ensure_space_access

MAX_RPC_BYTES = 7 * 1024 * 1024  # Leave room for the JSON RPC frame inside the 8 MiB wire limit.
MAX_ROWS = 10000
GRAPH_READ = frozenset(
    "execute_read execute_query get_node get_nodes_by_label paged_nodes_by_label find_nodes get_node_edges get_edge get_edges_by_type find_edges get_neighbours shortest_path labels edge_types node_count edge_count label_count stats_snapshot stats_tag_counts".split()
)
GRAPH_WRITE = frozenset(
    "execute_write create_node merge_node update_node delete_node create_edge merge_edge update_edge delete_edge batch_create_nodes batch_create_edges".split()
)
MILVUS_READ = frozenset(
    "query search get list_collections has_collection describe_collection get_collection_stats".split()
)
MILVUS_WRITE = frozenset("insert upsert delete flush".split())
SEMANTIC_METHODS = frozenset(
    "health catalog general_entities research_entities domain_entities classify_zh classify_en classify_domain keywords_zh keywords_en concept_definitions research_questions moves_zh moves_en fund_moves citation_intent citation_sentiment relation_extract deep_cluster cluster_labels structured_review".split()
)
PROTECTED_TABLE_PREFIXES = (
    "kg_",
    "platform_",
    "workflow_",
    "graph_schema",
    "manual_review",
    "external_api_client",
    "auth_",
)


def authorize_workflow_resource(*args):
    from service.workflow_jobs import authorize_workflow_resource as check

    return check(*args)


class ScriptAccessDenied(ValueError):
    """A safe-to-display policy error, never a driver exception."""


def validate_script_resources(request: dict):
    """Authorize task identity, selectors and the persisted source binding before fetching data."""
    from service.workflow_jobs import authorize_background_execution

    selectors = request.get("selectors") or {}
    actor = authorize_background_execution({**request, **selectors})
    source = request.get("source") or {}
    if not request.get("schemaId") or not source.get("id"):
        raise ScriptAccessDenied("脚本缺少可信的Schema来源绑定")
    from dao.schema_management import SchemaManagementDAO
    from infra.workflow_mysql import workflow_session_scope

    with workflow_session_scope() as session:
        schema = SchemaManagementDAO(session).get(request["schemaId"])
        binding = (
            next((row for row in schema.sources if row.id == source["id"]), None)
            if schema
            else None
        )
        if binding is None or any(
            (str(getattr(binding, field, None) or "") != str(source.get(key) or ""))
            for field, key in (
                ("datasource_id", "datasourceId"),
                ("database_name", "databaseName"),
                ("table_name", "tableName"),
                ("query_sql", "querySql"),
                ("pk_column", "pkColumn"),
                ("time_column", "timeColumn"),
            )
        ):
            raise ScriptAccessDenied("来源绑定已变更，请重新创建抽取任务")
    authorize_workflow_resource(
        actor, {**request, **selectors, "mysqlDatasourceId": source["datasourceId"]}, "write"
    )
    sql = (
        source.get("querySql")
        or f"SELECT * FROM `{source.get('databaseName', '')}`.`{source.get('tableName', '')}`"
    )
    validate_source_sql(sql, str(source.get("databaseName") or ""))
    return actor


def validate_source_sql(sql: str, database: str) -> str:
    """Parse read-only SQL and reject cross-database/system access and function escapes."""
    import sqlglot
    from sqlglot import exp

    if not isinstance(sql, str) or not sql.strip() or len(sql) > 65536:
        raise ScriptAccessDenied("查询为空或超过长度限制")
    # MySQL executable comments and session variables are never data queries.
    if any(part in sql for part in ("/*", "--", "#", "@", "\\")):
        raise ScriptAccessDenied("查询不支持注释、会话变量或反斜杠转义")
    try:
        statements = sqlglot.parse(sql, read="mysql")
    except Exception:
        raise ScriptAccessDenied("无法解析查询") from None
    if len(statements) != 1 or not isinstance(statements[0], (exp.Select, exp.Union)):
        raise ScriptAccessDenied("数据源只允许单条 SELECT 查询")
    root = statements[0]
    forbidden = {
        "into",
        "lock",
        "command",
        "insert",
        "update",
        "delete",
        "create",
        "drop",
        "alter",
        "grant",
        "transaction",
        "set",
        "use",
        "parameter",
        "sessionparameter",
        "propertyeq",
    }
    safe_functions = set(
        "ABS AVG CAST CEIL CEILING COALESCE CONCAT CONCAT_WS COUNT DATE DATE_ADD DATE_SUB DATEDIFF DATE_DIFF DATE_FORMAT DAY DAYOFMONTH DAYOFWEEK EXTRACT FLOOR GREATEST IF IFNULL JSON_EXTRACT JSON_UNQUOTE LEAST LEFT LENGTH CHAR_LENGTH LOWER LTRIM MAX MIN MONTH NULLIF REPLACE RIGHT ROUND RTRIM SUBSTRING SUM TRIM UPPER YEAR STR_TO_DATE TIME_TO_STR TS_OR_DS_TO_DATE TS_OR_DS_TO_TIMESTAMP STR_TO_TIME CURRENT_DATE CURRENT_TIMESTAMP ROW_NUMBER RANK DENSE_RANK GROUP_CONCAT CONCAT_WS NULLIF".split()
    )
    for node in root.walk():
        if node.key in forbidden:
            raise ScriptAccessDenied("查询包含不允许的数据库操作")
        if isinstance(node, exp.Table):
            if not isinstance(node.this, exp.Identifier) or node.catalog:
                raise ScriptAccessDenied("不允许表函数或跨目录访问")
            if node.db and node.db.lower() != database.lower():
                raise ScriptAccessDenied("不允许访问所选数据源库以外的数据库")
            if node.name.lower().startswith(PROTECTED_TABLE_PREFIXES) or node.name.lower() in {
                "batches",
                "tasks",
                "source_updates",
                "settings",
            }:
                raise ScriptAccessDenied("脚本不能读取平台权限、凭据或工作流内部表")
        if isinstance(node, exp.Dot) and isinstance(node.expression, exp.Func):
            raise ScriptAccessDenied("不允许调用数据库存储函数")
        if isinstance(node, exp.Func):
            name = node.name.upper() if isinstance(node, exp.Anonymous) else node.sql_name().upper()
            # Logical expressions use Func internally; their syntax cannot invoke stored routines.
            if isinstance(node, (exp.And, exp.Or, exp.Case)):
                continue
            if name not in safe_functions:
                raise ScriptAccessDenied("查询使用了未开放的函数")
    if (
        database.lower() in {"mysql", "sys", "information_schema", "performance_schema"}
        or not database
    ):
        raise ScriptAccessDenied("未选择业务数据源数据库")
    # Execute the parsed/canonical form, not input discarded or reinterpreted by the parser.
    return root.sql(dialect="mysql")


def validate_graph_query(query: str) -> str:
    """Restrict raw nGQL to the current space; never allow session/global operations."""
    from service.graph_console import classify_statement

    if not isinstance(query, str) or any(x in query for x in ("/*", "--", "//", "#")):
        raise ScriptAccessDenied("图查询不支持注释")
    # A conservative scanner removes only complete quoted literals/identifiers.
    scrubbed = re.sub(r"\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'|`[^`]*`", " value ", query)
    if any(x in scrubbed for x in ('"', "'", "`", "\\")):
        raise ScriptAccessDenied("图查询引号或转义不完整")
    tokens = re.findall(r"[A-Za-z_]+", scrubbed.upper())
    if not tokens:
        raise ScriptAccessDenied("图查询为空")
    global_tokens = {
        "USE",
        "SPACE",
        "SPACES",
        "CREATE",
        "ALTER",
        "DROP",
        "REBUILD",
        "SUBMIT",
        "ADMIN",
        "DOWNLOAD",
        "INGEST",
        "KILL",
        "SIGNOUT",
        "BALANCE",
        "HOSTS",
        "USERS",
        "ROLES",
        "CONFIGS",
        "SESSIONS",
        "CALL",
        "EXPLAIN",
        "PROFILE",
    }
    if set(tokens) & global_tokens:
        raise ScriptAccessDenied("脚本不允许切换图空间或执行集群管理语句")
    if tokens[0] == "SHOW" and tokens not in (
        ["SHOW", "TAGS"],
        ["SHOW", "EDGES"],
        ["SHOW", "STATS"],
        ["SHOW", "TAG", "INDEXES"],
        ["SHOW", "EDGE", "INDEXES"],
    ):
        raise ScriptAccessDenied("只允许查看当前图空间元数据")
    if tokens[0] in {"DESC", "DESCRIBE"} and (len(tokens) < 3 or tokens[1] not in {"TAG", "EDGE"}):
        raise ScriptAccessDenied("只允许查看当前图空间的 TAG/EDGE")
    if tokens[0] == "GET" and (len(tokens) < 2 or tokens[1] != "SUBGRAPH"):
        raise ScriptAccessDenied("不允许读取全局状态")
    try:
        return classify_statement(query)
    except Exception:
        raise ScriptAccessDenied("不支持该图查询，只允许空间内数据读写") from None


class ScriptResourceBroker:
    def __init__(self, request: dict, resolved: dict):
        self.request = copy.deepcopy(request)
        self.resolved = copy.deepcopy(resolved)
        self.selectors = self.request.get("selectors") or {}
        self.space = str(self.request.get("graphSpace") or self.selectors.get("graph_space") or "")
        if not self.space:
            raise ScriptAccessDenied("脚本任务缺少目标图空间")
        self._semantic_records: set[str] = set()
        self._clients: dict[str, Any] = {}
        self._client_lock = threading.Lock()
        self._closed = False
        from sdk.access import _AccessState

        self._access = _AccessState()
        self._authorize()
        # Never inherit default graph/database fallbacks supplied to legacy scripts.
        from infra.graph_db.config import TRSGraphSettings

        settings = TRSGraphSettings.from_env()
        self.resolved["graph"] = {
            "base_url": settings.base_url,
            "space": self.space,
            "api_key": settings.api_key,
            "timeout": min(settings.timeout, 30),
        }
        if self.resolved.get("milvus"):
            selected = self.selectors.get("milvus_database")
            if selected and selected != self.space:
                raise ScriptAccessDenied("脚本向量库必须与任务图空间同名")
            self.resolved["milvus"]["db_name"] = self.space
            self.resolved["milvus"]["timeout"] = 30
        if "semantic" not in self.resolved:
            import os

            url = os.getenv("SEMANTIC_TOOLKIT_BASE_URL")
            if url:
                self.resolved["semantic"] = {
                    "base_url": url,
                    "api_key": os.getenv("SEMANTIC_TOOLKIT_API_KEY", ""),
                    "timeout": 30,
                }

    def _authorize(self):
        actor = validate_script_resources(self.request)
        ensure_space_access(actor, self.space, "write")
        authorize_workflow_resource(actor, {**self.request, **self.selectors}, "write")
        source = self.request.get("source") or {}
        if source.get("datasourceId"):
            authorize_workflow_resource(
                actor, {**self.request, "mysqlDatasourceId": source["datasourceId"]}, "write"
            )
        return actor

    def public_context(self) -> dict:
        public = {
            key: self.resolved[key]
            for key in (
                "watermark",
                "checkpoint",
                "stepId",
                "attempt",
                "prevOutputs",
                "source",
                "executionId",
                "taskId",
                "definitionId",
            )
            if key in self.resolved
        }
        fields = {
            "mysql": ("database",),
            "graph": ("space",),
            "milvus": ("db_name",),
            "llm": ("model",),
            "embedding": ("model", "dimensions"),
            "semantic": (),
        }
        for name, keys in fields.items():
            if self.resolved.get(name):
                public[name] = {
                    "available": True,
                    **{key: self.resolved[name].get(key) for key in keys},
                }
        return {**public, "_sandbox": True}

    def _client(self, resource):
        with self._client_lock:
            if self._closed:
                raise ScriptAccessDenied("脚本执行已结束")
            current = self._clients.get(resource)
        if current is None:
            from sdk.kg_sdk import Context

            client = getattr(Context(self.resolved), resource)
            if client is None:
                raise ScriptAccessDenied("任务未配置该资源")
            if resource in {"llm", "embedding"}:
                # The observer stays worker-side. Bound underlying sockets even after task cancel.
                original = client._observed_client
                original._client.timeout = 30
                original._client.max_retries = 0
            with self._client_lock:
                if not self._closed:
                    self._clients[resource] = client
                    return client
            self._close_client(resource, client)
            raise ScriptAccessDenied("脚本执行已结束")
        return current

    def call(self, resource: str, method: str, args: list, kwargs: dict):
        with self._client_lock:
            if self._closed:
                raise ScriptAccessDenied("脚本执行已结束")
        if (
            not isinstance(args, list)
            or not isinstance(kwargs, dict)
            or len(json.dumps([args, kwargs]).encode()) > MAX_RPC_BYTES
        ):
            raise ScriptAccessDenied("资源请求参数无效或超限")
        actor = self._authorize()  # Includes every cache hit and every call after revocation.
        if resource == "mysql" and method == "query":
            result = self._mysql(args, kwargs)
        elif resource == "graph" and method in GRAPH_READ | GRAPH_WRITE:
            result = self._graph(actor, method, args, kwargs)
        elif resource == "milvus" and method in MILVUS_READ | MILVUS_WRITE:
            common = {"collection_name", "partition_names", "partition_name"}
            allowed = {
                "query": (
                    1,
                    common
                    | {"filter", "output_fields", "ids", "limit", "offset", "consistency_level"},
                ),
                "search": (
                    2,
                    common
                    | {
                        "data",
                        "filter",
                        "output_fields",
                        "limit",
                        "search_params",
                        "anns_field",
                        "consistency_level",
                    },
                ),
                "get": (2, common | {"ids", "output_fields"}),
                "insert": (2, common | {"data"}),
                "upsert": (2, common | {"data"}),
                "delete": (2, common | {"ids", "filter"}),
                "flush": (1, {"collection_name"}),
                "list_collections": (0, set()),
                "has_collection": (1, {"collection_name"}),
                "describe_collection": (1, {"collection_name"}),
                "get_collection_stats": (1, {"collection_name"}),
            }
            count, keys = allowed[method]
            if len(args) > count or set(kwargs) - keys:
                raise ScriptAccessDenied("不能覆盖向量库连接或授权范围")
            ensure_space_access(actor, self.space, "write" if method in MILVUS_WRITE else "read")
            result = getattr(self._client(resource), method)(*args, **kwargs, timeout=30)
        elif resource == "llm" and method in {"synthesize", "synthesize_json"}:
            if "timeout" in kwargs and not 0 < float(kwargs["timeout"]) <= 30:
                raise ScriptAccessDenied("模型调用超时上限为30秒")
            result = getattr(self._client(resource), method)(*args, **kwargs)
        elif resource == "embedding" and method in {"embed", "embed_one"}:
            result = getattr(self._client(resource), method)(*args, **kwargs)
        elif resource == "semantic" and method in SEMANTIC_METHODS:
            if set(kwargs) & {
                "base_url",
                "api_key",
                "url",
                "path",
                "headers",
                "upstream_ner_record_id",
                "recordId",
            }:
                raise ScriptAccessDenied("不能覆盖语义服务连接或引用其他任务记录")
            if method != "relation_extract" and "record_id" in kwargs:
                raise ScriptAccessDenied("只能使用本次脚本生成的语义记录")
            if method == "relation_extract":
                record_id = args[0] if args else kwargs.get("record_id")
                valid = isinstance(record_id, str) and re.fullmatch(
                    r"[A-Za-z0-9_-]{1,128}", record_id
                )
                permitted = record_id in self._semantic_records if valid else False
                if valid and not permitted and self.request.get("_sandboxRunKey"):
                    from service.script_resource_grants import allows

                    permitted = allows(self.request["_sandboxRunKey"], record_id, actor, self.space)
                if not permitted:
                    raise ScriptAccessDenied("只能读取本次脚本生成的语义记录")
            result = getattr(self._client(resource), method)(*args, **kwargs)
            if isinstance(result, dict):
                from sdk.kg_sdk import SemanticToolkitClient

                record = SemanticToolkitClient.record_id_of(result)
                if record and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", record):
                    self._semantic_records.add(record)
                    if self.request.get("_sandboxRunKey"):
                        from service.script_resource_grants import remember

                        remember(self.request["_sandboxRunKey"], record, actor, self.space)
        else:
            raise ScriptAccessDenied("该资源操作未开放给抽取脚本")
        result = jsonable_encoder(result)
        if len(json.dumps(result, ensure_ascii=False).encode()) > MAX_RPC_BYTES:
            raise ScriptAccessDenied("资源返回超限，请缩小查询批次")
        self._record(resource, method, args, kwargs)
        return result

    def access_report(self):
        return self._access.render()

    def _record(self, resource, method, args, kwargs):
        if resource == "mysql":
            import sqlglot
            from sqlglot import exp

            tree = sqlglot.parse_one(args[0], read="mysql")
            ctes = {cte.alias_or_name for cte in tree.find_all(exp.CTE)}
            for name in {table.name for table in tree.find_all(exp.Table)} - ctes:
                self._access.apply(
                    {
                        "t": "mysql",
                        "table": name,
                        "db": self.resolved["mysql"].get("database"),
                        "op": "SELECT",
                    }
                )
        elif resource == "graph":
            if method.startswith("execute_"):
                self._access.apply(
                    {
                        "t": "ngql",
                        "op": method.removeprefix("execute_"),
                        "query": args[0] if args else kwargs.get("query", ""),
                    }
                )
            else:
                from infra.graph_db.client import TRSGraphClient

                values = (
                    inspect.signature(getattr(TRSGraphClient, method))
                    .bind(None, *args, **kwargs)
                    .arguments
                )
                names = values.get("labels") or [
                    values.get("label") or values.get("edge_type") or "_unspecified"
                ]
                for name in names:
                    self._access.apply(
                        {
                            "t": "graph",
                            "kind": "edge" if "edge" in method else "tag",
                            "name": name,
                            "op": "write" if method in GRAPH_WRITE else "read",
                        }
                    )
        elif resource == "milvus":
            self._access.apply(
                {
                    "t": "milvus",
                    "collection": args[0] if args else kwargs.get("collection_name", "_metadata"),
                    "op": "write" if method in MILVUS_WRITE else "read",
                }
            )
        elif resource in {"llm", "embedding"}:
            self._access.apply(
                {
                    "t": resource,
                    "model": self.resolved[resource].get("model", "unknown"),
                    "ok": True,
                }
            )

    def _graph(self, actor, method, args, kwargs):
        client = self._client("graph")
        if method.startswith("execute_"):
            if set(kwargs) - {"query", "params"} or len(args) > 2:
                raise ScriptAccessDenied("图查询参数无效")
            query = args[0] if args else kwargs.get("query")
            kind = validate_graph_query(query)
            if method == "execute_read" and kind != "read":
                raise ScriptAccessDenied("只读查询不能写图")
            ensure_space_access(actor, self.space, "write" if kind == "write" else "read")
        else:
            ensure_space_access(actor, self.space, "write" if method in GRAPH_WRITE else "read")
            # Bind against the real implementation, not the observer's **kwargs wrapper.
            from infra.graph_db.client import TRSGraphClient

            params = (
                inspect.signature(getattr(TRSGraphClient, method))
                .bind(None, *args, **kwargs)
                .arguments
            )
            if "edge_id" in params:
                from infra.graph_db.client import _parse_edge_id

                source, target, _ = _parse_edge_id(str(params["edge_id"]))
                params.update(source_id=source, target_id=target)
            for key in ("node_id", "edge_id", "source_id", "target_id", "label", "edge_type"):
                value = params.get(key)
                if value is not None and (
                    any(c in str(value) for c in ("/", "\\", "?", "#", "%"))
                    or str(value) in {".", ".."}
                ):
                    raise ScriptAccessDenied("资源标识不允许路径控制字符；复杂ID请使用参数化图查询")
            for key in ("label", "edge_type"):
                if params.get(key) is not None and not re.fullmatch(
                    r"[A-Za-z_][A-Za-z0-9_]*", str(params[key])
                ):
                    raise ScriptAccessDenied("图类型标识不合法")
            if "labels" in params and (
                not isinstance(params["labels"], list)
                or any(
                    not isinstance(x, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", x)
                    for x in params["labels"]
                )
            ):
                raise ScriptAccessDenied("图类型标识不合法")
        return getattr(client, method)(*args, **kwargs)

    def _mysql(self, args, kwargs):
        if kwargs or not 1 <= len(args) <= 2 or not self.resolved.get("mysql"):
            raise ScriptAccessDenied("查询需要已授权的数据源及SQL参数")
        settings = self.resolved["mysql"]
        sql = validate_source_sql(args[0], str(settings.get("database") or ""))
        parameters = args[1] if len(args) == 2 else {}
        if parameters is None:
            parameters = {}
        if not isinstance(parameters, dict):
            raise ScriptAccessDenied("查询参数必须是命名参数字典")
        from sqlalchemy import create_engine, text
        from sqlalchemy.engine import URL

        # Short-lived connection, no credentials in logs/result; cap server and socket time.
        engine = create_engine(
            URL.create(
                "mysql+pymysql",
                username=settings["username"],
                password=settings.get("password", ""),
                host=settings["host"],
                port=int(settings.get("port", 3306)),
                database=settings["database"],
            ),
            connect_args={"connect_timeout": 10, "read_timeout": 30, "write_timeout": 10},
        )
        try:
            with engine.connect() as conn:
                conn.exec_driver_sql("SET SESSION MAX_EXECUTION_TIME=30000")
                conn.exec_driver_sql("SET TRANSACTION READ ONLY")
                result = conn.execute(text(sql), parameters)
                columns = list(result.keys())
                rows = result.mappings().fetchmany(MAX_ROWS + 1)
                if len(rows) > MAX_ROWS:
                    raise ScriptAccessDenied("查询超过10000行，请分页读取")
                return {
                    "rows": [dict(row) for row in rows],
                    "columns": columns,
                    "rowcount": len(rows),
                }
        finally:
            engine.dispose()

    @staticmethod
    def _close_client(resource, client):
        try:
            if resource in {"graph", "milvus"}:
                client.close()
            elif resource in {"llm", "embedding"}:
                client._observed_client._client.close()
        except Exception:
            pass  # Cleanup cannot hide the original script error or disclose driver details.

    def close(self):
        with self._client_lock:
            self._closed = True
            clients, self._clients = self._clients, {}
        for resource, client in clients.items():
            self._close_client(resource, client)
