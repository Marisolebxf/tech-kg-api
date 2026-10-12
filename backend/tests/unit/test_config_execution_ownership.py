"""Configuration ownership must hold at selection and persisted execution boundaries."""

from contextlib import contextmanager
from datetime import datetime

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db_model.base import Base
from db_model.business_access import BusinessClient, BusinessGraphSpace, BusinessSpacePolicy
from db_model.config_ownership import ConfigOwnership
from db_model.llm_config import LlmConfig
from db_model.mysql_datasource import MysqlDatasource
from service.platform_access import PlatformActor


@pytest.fixture
def ownership_db(monkeypatch):
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
            ConfigOwnership.__table__,
            LlmConfig.__table__,
            MysqlDatasource.__table__,
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
                BusinessClient(client_id="other", name="Other"),
                BusinessGraphSpace(space_name="mine-space", client_id="mine"),
            ]
        )
        now = datetime.now()
        for suffix, business in (
            ("public", None),
            ("mine", "mine"),
            ("other", "other"),
            ("unknown", "unknown"),
        ):
            session.add(
                LlmConfig(
                    id=f"llm-{suffix}",
                    name=suffix,
                    base_url="http://example.invalid",
                    model="test",
                    api_key="test",
                    owner="legacy-owner",
                    created_at=now,
                    updated_at=now,
                )
            )
            session.add(
                MysqlDatasource(
                    id=f"mysql-{suffix}",
                    name=suffix,
                    host="example.invalid",
                    username="test",
                    password="test",
                    owner="legacy-owner",
                    created_at=now,
                    updated_at=now,
                )
            )
            if business:
                for kind in ("mysql", "llm"):
                    session.add(
                        ConfigOwnership(
                            config_kind=kind,
                            config_id=f"{kind}-{suffix}",
                            business_id=business,
                        )
                    )
    yield engine, factory
    engine.dispose()


def developer():
    return PlatformActor(
        user_id="developer",
        username="developer",
        display_name="Developer",
        email="",
        is_admin=False,
        business_id="mine",
        business_role="developer",
    )


@pytest.mark.parametrize(
    "kind,selector", [("mysql", "mysql_datasource_id"), ("llm", "llm_config_id")]
)
@pytest.mark.parametrize(
    "suffix,allowed", [("public", True), ("mine", True), ("other", False), ("unknown", False)]
)
def test_workflow_selector_enforces_configuration_business(
    ownership_db, kind, selector, suffix, allowed
):
    from biz.handler.workflow_system import _validate_resource_selectors

    selected = {selector: f"{kind}-{suffix}"}
    if allowed:
        _validate_resource_selectors(developer(), selected)
    else:
        with pytest.raises(HTTPException) as error:
            _validate_resource_selectors(developer(), selected)
        assert error.value.status_code == 403


@pytest.mark.parametrize("kind,selector", [("mysql", "mysqlDatasourceId"), ("llm", "llmConfigId")])
@pytest.mark.parametrize(
    "suffix,allowed", [("public", True), ("mine", True), ("other", False), ("unknown", False)]
)
def test_saved_workflow_rechecks_configuration_business(
    ownership_db, monkeypatch, kind, selector, suffix, allowed
):
    from service import workflow_jobs

    monkeypatch.setattr(workflow_jobs, "ensure_space_access", lambda *args: None)
    resource = {
        "graphSpace": "mine-space",
        "clientId": "mine",
        "payload": {selector: f"{kind}-{suffix}"},
    }
    if allowed:
        workflow_jobs.authorize_workflow_resource(developer(), resource, "write")
    else:
        with pytest.raises(HTTPException) as error:
            workflow_jobs.authorize_workflow_resource(developer(), resource, "write")
        assert error.value.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "suffix,allowed", [("public", True), ("mine", True), ("other", False), ("unknown", False)]
)
async def test_schema_plan_rechecks_persisted_source_ownership(
    ownership_db, monkeypatch, suffix, allowed
):
    from db_model.schema_management import GraphSchemaDefinition, GraphSchemaSource
    from script.init_schema_management import MANAGED_TABLES
    from service.temporal_workflows import load_schema_extract_plan
    from service.workflow_models import Base as WorkflowBase

    engine, factory = ownership_db
    WorkflowBase.metadata.create_all(engine, tables=MANAGED_TABLES)
    with factory.begin() as session:
        definition = GraphSchemaDefinition(
            id="schema",
            schema_key="example",
            kind="entity",
            name="Example",
            label="Example",
            graph_space="mine-space",
        )
        definition.sources = [
            GraphSchemaSource(
                datasource_id=f"mysql-{suffix}",
                database_name="example",
                table_name="items",
                pk_column="id",
            )
        ]
        session.add(definition)
    monkeypatch.setattr("infra.workflow_mysql.get_workflow_engine", lambda: engine)
    monkeypatch.setattr(
        "service.workflow_jobs.authorize_background_execution", lambda payload: developer()
    )
    if allowed:
        # Authorization passes before the intentionally absent script is inspected.
        with pytest.raises(ValueError, match="Schema 未上传脚本"):
            await load_schema_extract_plan({"schemaId": "schema"})
    else:
        with pytest.raises(HTTPException) as error:
            await load_schema_extract_plan({"schemaId": "schema"})
        assert error.value.status_code == 403
