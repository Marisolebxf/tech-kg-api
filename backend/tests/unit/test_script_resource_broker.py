from types import SimpleNamespace

import pytest

from service import script_resource_broker as gateway


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM other.items",
        "SELECT * FROM information_schema.tables",
        "SELECT * FROM platform_mysql_datasource",
        "SELECT * FROM kg_business_member",
        "SELECT LOAD_FILE('/etc/passwd')",
        "SELECT SLEEP(20)",
        "SELECT evil_function()",
        "SELECT app.evil_function()",
        "SELECT @@global.general_log_file",
        "SELECT 1 INTO OUTFILE '/tmp/a'",
        "SELECT 1; SELECT 2",
        "SELECT 1 /*! INTO OUTFILE '/tmp/x' */",
        "SELECT * FROM items FOR UPDATE",
        "DELETE FROM items",
        "SET @x=1",
        "SELECT (SELECT password FROM platform_mysql_datasource)",
        "WITH q AS (SELECT * FROM other.items) SELECT * FROM q",
    ],
)
def test_mysql_denies_escape(sql):
    with pytest.raises(gateway.ScriptAccessDenied):
        gateway.validate_source_sql(sql, "app")


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT id,name FROM app.items WHERE id=:id LIMIT 20",
        "SELECT COUNT(*) FROM items",
        "SELECT COALESCE(name, '') FROM items",
        "WITH q AS (SELECT id FROM items) SELECT * FROM q",
        "SELECT id FROM items UNION SELECT id FROM items2",
    ],
)
def test_mysql_allows_bounded_scope(sql):
    assert gateway.validate_source_sql(sql, "app")


@pytest.mark.parametrize(
    "query",
    [
        "USE other; MATCH (n) RETURN n",
        "SHOW SPACES",
        "SHOW USERS",
        "SHOW CONFIGS",
        "DESC SPACE other",
        "EXPLAIN SHOW SPACES",
        "RETURN 1; USE other",
        "CREATE SPACE other",
        "DROP SPACE app",
        "GET CONFIGS",
        "RETURN 1 /*x*/",
        "RETURN 1 | SHOW SPACES",
        "RETURN 1 UNION SHOW USERS",
    ],
)
def test_graph_denies_global_and_multi_query(query):
    with pytest.raises(gateway.ScriptAccessDenied):
        gateway.validate_graph_query(query)


@pytest.mark.parametrize(
    ("query", "kind"),
    [
        ('MATCH (n:Person) WHERE id(n)=="x" RETURN n LIMIT 1', "read"),
        ('INSERT VERTEX Person(name) VALUES "x":("test")', "write"),
        ("SHOW TAGS", "read"),
        ("DESCRIBE TAG Person", "read"),
        ('RETURN "USE other; SHOW SPACES"', None),
    ],
)
def test_graph_local_queries(query, kind):
    if kind is None:  # conservative multi-statement guard also rejects ; inside literals
        with pytest.raises(gateway.ScriptAccessDenied):
            gateway.validate_graph_query(query)
    else:
        assert gateway.validate_graph_query(query) == kind


@pytest.fixture
def broker(monkeypatch):
    actor = SimpleNamespace(user_id="alice", business_id="business-a")
    monkeypatch.setattr(gateway, "validate_script_resources", lambda request: actor)
    monkeypatch.setattr(gateway, "authorize_workflow_resource", lambda *a: None)
    monkeypatch.setattr(gateway, "ensure_space_access", lambda *a: None)
    resolved = {
        "graph": {"api_key": "GLOBAL_SECRET", "space": "bad"},
        "mysql": {"host": "private", "username": "root", "password": "SECRET", "database": "app"},
        "milvus": {"token": "TOKEN", "db_name": "other"},
        "llm": {"api_key": "LLM_SECRET", "model": "model"},
    }
    return gateway.ScriptResourceBroker({"graphSpace": "space-a", "selectors": {}}, resolved)


def test_public_context_never_contains_credentials(broker):
    import json

    value = broker.public_context()
    encoded = json.dumps(value)
    assert value["_sandbox"]
    assert value["graph"]["space"] == "space-a"
    assert value["milvus"]["db_name"] == "space-a"
    assert all(
        word not in encoded
        for word in ("SECRET", "TOKEN", "password", "api_key", "private", "root")
    )


@pytest.mark.parametrize(
    ("resource", "method"),
    [
        ("graph", "_request"),
        ("graph", "list_spaces"),
        ("graph", "connect"),
        ("milvus", "using_database"),
        ("milvus", "create_database"),
        ("mysql", "execute_write"),
        ("llm", "api_key"),
        ("semantic", "_request"),
    ],
)
def test_only_explicit_resource_methods(broker, resource, method):
    with pytest.raises(gateway.ScriptAccessDenied):
        broker.call(resource, method, [], {})


def test_revocation_checked_before_cached_client(broker, monkeypatch):
    broker._clients["graph"] = SimpleNamespace(labels=lambda: ["Person"])
    assert broker.call("graph", "labels", [], {}) == ["Person"]

    def revoked(request):
        raise gateway.ScriptAccessDenied("revoked")

    monkeypatch.setattr(gateway, "validate_script_resources", revoked)
    with pytest.raises(gateway.ScriptAccessDenied, match="revoked"):
        broker.call("graph", "labels", [], {})


def test_production_write_allowed_but_no_review_rpc(broker):
    broker._clients["graph"] = SimpleNamespace(
        create_node=lambda labels, properties: {"id": "x", "labels": labels}
    )
    assert broker.call("graph", "create_node", [["Person"], {"name": "A"}], {})["id"] == "x"
    with pytest.raises(gateway.ScriptAccessDenied):
        broker.call("manual_review", "approve", ["case"], {})


def test_graph_path_traversal_rejected(broker):
    broker._clients["graph"] = SimpleNamespace(
        get_node=lambda node: pytest.fail("must not call transport")
    )
    with pytest.raises(gateway.ScriptAccessDenied):
        broker.call("graph", "get_node", ["../../schema/spaces"], {})


@pytest.mark.parametrize("edge_id", ["..->nodes@0", "x->..@0", ".->x@0"])
def test_graph_edge_components_cannot_traverse_paths(broker, edge_id):
    broker._clients["graph"] = SimpleNamespace(get_edge=lambda *a: pytest.fail("must not call"))
    with pytest.raises(gateway.ScriptAccessDenied):
        broker.call("graph", "get_edge", [edge_id], {})


def test_milvus_database_override_rejected(broker):
    with pytest.raises(gateway.ScriptAccessDenied):
        broker.call("milvus", "query", [], {"collection_name": "x", "db_name": "other"})


def test_semantic_record_from_other_execution_denied(broker):
    with pytest.raises(gateway.ScriptAccessDenied):
        broker.call("semantic", "relation_extract", ["foreign-record"], {})


def test_semantic_broker_remembers_server_results_for_later_steps(broker, monkeypatch):
    from service import script_resource_grants as grants

    remembered = set()
    monkeypatch.setattr(
        grants,
        "remember",
        lambda run, record, actor, space: remembered.add((run, record, actor.user_id, space)),
    )
    monkeypatch.setattr(
        grants,
        "allows",
        lambda run, record, actor, space: (run, record, actor.user_id, space) in remembered,
    )
    broker.request["_sandboxRunKey"] = "a" * 64
    broker._clients["semantic"] = SimpleNamespace(
        general_entities=lambda text: {"data": {"record_id": "record-generated"}},
        relation_extract=lambda record: {"data": {"triples": []}},
    )
    broker.call("semantic", "general_entities", ["text"], {})
    broker._semantic_records.clear()  # A later step/worker has no process-local grant.
    assert broker.call("semantic", "relation_extract", ["record-generated"], {}) == {
        "data": {"triples": []}
    }
    broker.request["_sandboxRunKey"] = "b" * 64
    with pytest.raises(gateway.ScriptAccessDenied):
        broker.call("semantic", "relation_extract", ["record-generated"], {})


def test_access_reports_are_per_invocation(broker):
    broker._clients["graph"] = SimpleNamespace(labels=lambda: ["Person"])
    broker.call("graph", "labels", [], {})
    assert broker.access_report()["graph"]["tag"]["_unspecified"]["count"] == 1


def test_cancel_during_client_construction_closes_late_client(broker, monkeypatch):
    from sdk.kg_sdk import Context

    closed = []
    client = SimpleNamespace(close=lambda: closed.append(True))

    def connect(context):
        broker.close()
        return client

    monkeypatch.setattr(Context, "graph", property(connect))
    with pytest.raises(gateway.ScriptAccessDenied, match="已结束"):
        broker._client("graph")
    assert closed == [True]
    assert broker._clients == {}
    with pytest.raises(gateway.ScriptAccessDenied, match="已结束"):
        broker.call("graph", "labels", [], {})


@pytest.mark.external
def test_real_mysql_readonly_named_parameter_query(broker):
    """Run only against the disposable test database, never application data."""
    import os

    if not os.getenv("SCRIPT_BROKER_TEST_MYSQL"):
        pytest.skip("explicit disposable MySQL required")
    broker.resolved["mysql"] = {
        "host": "temporal-mysql",
        "port": 3306,
        "database": "techkg_control",
        "username": "root",
        "password": "rbac-test-only",
    }
    assert broker.call("mysql", "query", ["SELECT :n AS total", {"n": 42}], {}) == {
        "rows": [{"total": 42}],
        "columns": ["total"],
        "rowcount": 1,
    }


def test_gateway_uses_current_membership_and_persisted_source(monkeypatch):
    from contextlib import contextmanager, nullcontext
    from datetime import datetime

    from fastapi import HTTPException
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from dao.schema_management import SchemaManagementDAO
    from db_model.base import Base
    from db_model.business_access import BusinessClient, BusinessGraphSpace, BusinessMember
    from db_model.mysql_datasource import MysqlDatasource
    from db_model.platform_governance import PlatformUser, PlatformUserRole
    from infra import mysql, workflow_mysql
    from service import business_access_control

    monkeypatch.setenv("BUSINESS_RBAC_ENABLED", "true")
    monkeypatch.setenv("PLATFORM_INITIAL_ADMIN_USER_IDS", "")
    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine,
        tables=[
            row.__table__
            for row in (
                BusinessClient,
                BusinessGraphSpace,
                BusinessMember,
                PlatformUser,
                PlatformUserRole,
                MysqlDatasource,
            )
        ],
    )
    factory = sessionmaker(engine, expire_on_commit=False)

    @contextmanager
    def scope():
        with factory.begin() as session:
            yield session

    monkeypatch.setattr(mysql, "session_scope", scope)
    monkeypatch.setattr(business_access_control, "session_scope", scope)
    monkeypatch.setattr(workflow_mysql, "workflow_session_scope", lambda: nullcontext(None))
    source = SimpleNamespace(
        id="src", datasource_id="mysql-a", database_name="app", table_name="items", query_sql=None
    )
    schemas = {
        "schema-a": SimpleNamespace(graph_space="space-a", sources=[source]),
        "schema-b": SimpleNamespace(graph_space="space-b", sources=[source]),
    }
    monkeypatch.setattr(SchemaManagementDAO, "get", lambda self, key: schemas.get(key))
    with scope() as session:
        session.add_all(
            [
                BusinessClient(client_id="a", name="A"),
                BusinessClient(client_id="b", name="B"),
                PlatformUser(user_id="alice"),
            ]
        )
        session.flush()
        session.add_all(
            [
                BusinessMember(user_id="alice", client_id="a", role="developer"),
                BusinessGraphSpace(space_name="space-a", client_id="a"),
                BusinessGraphSpace(space_name="space-b", client_id="b"),
                MysqlDatasource(
                    id="mysql-a",
                    name="A",
                    host="source",
                    port=3306,
                    default_database="app",
                    username="reader",
                    password="secret",
                    owner="business:a",
                    created_at=datetime.now(),
                    updated_at=datetime.now(),
                ),
            ]
        )
    request = {
        "actorUserId": "alice",
        "clientId": "a",
        "schemaId": "schema-a",
        "graphSpace": "space-a",
        "source": {
            "id": "src",
            "datasourceId": "mysql-a",
            "databaseName": "app",
            "tableName": "items",
        },
    }
    try:
        live = gateway.ScriptResourceBroker(request, {})
        live._clients["graph"] = SimpleNamespace(labels=lambda: ["Person"])
        assert live.call("graph", "labels", [], {}) == ["Person"]
        with pytest.raises(HTTPException):
            gateway.ScriptResourceBroker(
                {**request, "schemaId": "schema-b", "graphSpace": "space-b"}, {}
            )
        with pytest.raises(gateway.ScriptAccessDenied):
            gateway.ScriptResourceBroker(
                {**request, "source": {**request["source"], "tableName": "another_table"}}, {}
            )
        with scope() as session:
            session.get(BusinessMember, "alice").role = "user"
        with pytest.raises(HTTPException):
            live.call("graph", "labels", [], {})
    finally:
        engine.dispose()
