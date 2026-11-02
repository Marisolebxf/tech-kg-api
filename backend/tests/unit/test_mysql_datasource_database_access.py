"""Reviewed credentials do not grant access to other databases on the same server."""

from contextlib import contextmanager, nullcontext
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db_model.base import Base
from db_model.business_access import BusinessClient, BusinessGraphSpace, BusinessSpacePolicy
from db_model.config_ownership import ConfigOwnership
from db_model.mysql_datasource import MysqlDatasource
from service.mysql_datasource_access import ensure_mysql_database_access
from service.platform_access import PlatformActor


def _actor(admin=False):
    return PlatformActor(
        user_id="dev",
        username="dev",
        display_name="Dev",
        email="",
        is_admin=admin,
        business_id="mine",
        business_role="developer",
    )


@pytest.fixture
def database_scope(monkeypatch):
    monkeypatch.setenv("BUSINESS_RBAC_ENABLED", "true")
    engine = create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(
        engine,
        tables=[
            BusinessClient.__table__,
            BusinessGraphSpace.__table__,
            BusinessSpacePolicy.__table__,
            MysqlDatasource.__table__,
            ConfigOwnership.__table__,
        ],
    )
    factory = sessionmaker(engine, expire_on_commit=False)

    @contextmanager
    def scope():
        with factory.begin() as session:
            yield session

    monkeypatch.setattr("infra.mysql.create_session", factory)
    monkeypatch.setattr("infra.mysql.session_scope", scope)
    monkeypatch.setattr("service.business_access_control.session_scope", scope)
    with scope() as session:
        session.add_all(
            [
                BusinessClient(client_id="mine", name="Mine"),
                BusinessGraphSpace(space_name="mine-space", client_id="mine"),
            ]
        )
        for config_id, default in [("public", "allowed"), ("empty", "")]:
            session.add(
                MysqlDatasource(
                    id=config_id,
                    name=config_id,
                    host="example.invalid",
                    username="reader",
                    default_database=default,
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )
            )
            session.add(ConfigOwnership(config_kind="mysql", config_id=config_id, business_id=None))
    yield engine, factory, scope
    engine.dispose()


@pytest.mark.parametrize(
    "config_id,requested,permitted",
    [
        ("public", None, True),
        ("public", "", True),
        ("public", "allowed", True),
        ("public", "other_tenant", False),
        ("public", "Allowed", False),
        ("empty", None, False),
        ("empty", "", False),
        ("empty", "other_tenant", False),
    ],
)
def test_database_scope_is_exact_and_legacy_empty_defaults_fail_closed(
    database_scope, config_id, requested, permitted
):
    _, factory, _ = database_scope
    with factory() as session:
        if permitted:
            assert (
                ensure_mysql_database_access(session, _actor(), config_id, requested) == "allowed"
            )
        else:
            with pytest.raises(HTTPException) as caught:
                ensure_mysql_database_access(session, _actor(), config_id, requested)
            assert caught.value.status_code == 403


def test_admin_can_select_other_database(database_scope):
    _, factory, _ = database_scope
    with factory() as session:
        assert (
            ensure_mysql_database_access(session, _actor(True), "empty", "other_tenant")
            == "other_tenant"
        )


@pytest.mark.parametrize("id_key", ["mysql_datasource_id", "mysqlDatasourceId"])
@pytest.mark.parametrize("db_key", ["mysql_database", "mysqlDatabase"])
def test_workflow_selector_checks_both_aliases(database_scope, id_key, db_key):
    from biz.handler.workflow_system import _validate_resource_selectors

    _validate_resource_selectors(_actor(), {id_key: "public", db_key: "allowed"})
    with pytest.raises(HTTPException):
        _validate_resource_selectors(_actor(), {id_key: "public", db_key: "other_tenant"})


def test_saved_workflow_checks_database_override_in_another_payload_layer(
    database_scope, monkeypatch
):
    from service import workflow_jobs

    monkeypatch.setattr(workflow_jobs, "ensure_space_access", lambda *a: None)
    resource = {
        "graphSpace": "mine-space",
        "clientId": "mine",
        "mysqlDatasourceId": "public",
        "payload": {"mysql_database": "other_tenant"},
    }
    with pytest.raises(HTTPException):
        workflow_jobs.authorize_workflow_resource(_actor(), resource, "write")
    resource["payload"]["mysql_database"] = "allowed"
    workflow_jobs.authorize_workflow_resource(_actor(), resource, "write")


@pytest.mark.parametrize("database,allowed", [("allowed", True), ("other_tenant", False)])
def test_schema_source_binding_checks_selected_database(
    database_scope, monkeypatch, database, allowed
):
    from biz.handler import schema_management
    from biz.schemas.schema_management import SchemaSourcesReplace

    monkeypatch.setattr(
        schema_management, "_schema_access", lambda *a: SimpleNamespace(graph_space="mine-space")
    )
    application = Mock()
    application.replace_sources.return_value = {}
    monkeypatch.setattr(schema_management, "_application", lambda session: application)
    payload = SchemaSourcesReplace(
        sources=[{"datasourceId": "public", "databaseName": database, "tableName": "items"}]
    )
    if allowed:
        schema_management.replace_schema_sources("schema", _actor(), None, payload)
        application.replace_sources.assert_called_once()
    else:
        with pytest.raises(HTTPException):
            schema_management.replace_schema_sources("schema", _actor(), None, payload)
        application.replace_sources.assert_not_called()


@pytest.mark.asyncio
async def test_read_batch_rechecks_database_before_client_construction(database_scope, monkeypatch):
    from service import mysql_datasource, script_resource_broker, temporal_workflows

    monkeypatch.setattr(
        script_resource_broker, "validate_script_resources", lambda request: _actor()
    )
    monkeypatch.setattr(
        mysql_datasource,
        "get_mysql_settings_by_id",
        lambda cid: {
            "host": "10.1.2.3",
            "port": 3306,
            "username": "reader",
            "password": "",
            "database": "allowed",
        },
    )
    monkeypatch.setattr("service.script_watermark.read_watermark", lambda *a: None)
    client = Mock(side_effect=AssertionError("must not open a cross-database connection"))
    monkeypatch.setattr("infra.mysql.MySQLClient", client)
    request = {
        "datasourceId": "public",
        "database": "other_tenant",
        "table": "items",
        "pkColumn": "id",
        "source": {
            "datasourceId": "public",
            "databaseName": "other_tenant",
            "tableName": "items",
            "pkColumn": "id",
        },
    }
    with pytest.raises(HTTPException):
        await temporal_workflows.read_source_batch(request)
    client.assert_not_called()


def test_broker_rechecks_persisted_binding_database(database_scope, monkeypatch):
    from dao.schema_management import SchemaManagementDAO
    from service import script_resource_broker as broker

    monkeypatch.setattr(
        "service.workflow_jobs.authorize_background_execution", lambda request: _actor()
    )
    monkeypatch.setattr(broker, "authorize_workflow_resource", lambda *a: None)
    monkeypatch.setattr("infra.workflow_mysql.workflow_session_scope", lambda: nullcontext(None))
    binding = SimpleNamespace(
        id="binding",
        datasource_id="public",
        database_name="other_tenant",
        table_name="items",
        query_sql=None,
        pk_column="id",
        time_column=None,
    )
    monkeypatch.setattr(
        SchemaManagementDAO, "get", lambda self, key: SimpleNamespace(sources=[binding])
    )
    request = {
        "schemaId": "schema",
        "source": {
            "id": "binding",
            "datasourceId": "public",
            "databaseName": "other_tenant",
            "tableName": "items",
            "pkColumn": "id",
        },
    }
    with pytest.raises(HTTPException):
        broker.validate_script_resources(request)


def test_broker_rechecks_resolved_database_before_engine_construction(database_scope, monkeypatch):
    from service.script_resource_broker import ScriptResourceBroker

    broker = object.__new__(ScriptResourceBroker)
    broker.request = {"source": {"datasourceId": "public"}}
    broker.selectors = {}
    broker.resolved = {"mysql": {"host": "example.invalid", "database": "other_tenant"}}
    engine = Mock(side_effect=AssertionError("must not construct a cross-database engine"))
    monkeypatch.setattr("sqlalchemy.create_engine", engine)
    with pytest.raises(HTTPException):
        broker._mysql(_actor(), ["SELECT * FROM other_tenant.items"], {})
    engine.assert_not_called()


def test_sql_database_qualifier_cannot_escape_by_case():
    from service.script_resource_broker import ScriptAccessDenied, validate_source_sql

    with pytest.raises(ScriptAccessDenied):
        validate_source_sql("SELECT * FROM Allowed.items", "allowed")
