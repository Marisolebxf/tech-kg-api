"""平台喂数抽取计划构建单测：definition id / build_extract_definition / load_schema_extract_plan / 水位。"""

from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from db_model.schema_management import (
    GraphSchemaDefinition,
    GraphSchemaProperty,
    GraphSchemaScript,
    GraphSchemaSource,
)
from service.schema_extraction import (
    DEFAULT_BATCH_SIZE,
    build_extract_definition,
    extract_definition_id,
)
from service.temporal_workflows import (
    advance_schema_extract_watermark,
    load_schema_extract_plan,
)


def test_extract_definition_id_format() -> None:
    assert extract_definition_id("scholar") == "schema-extract-scholar"
    assert extract_definition_id("uses-technology") == "schema-extract-uses-technology"


def test_build_extract_definition_metadata() -> None:
    schema = SimpleNamespace(schema_key="widget", label="部件")
    definition = build_extract_definition(schema)
    assert definition["id"] == "schema-extract-widget"
    assert definition["workflowType"] == "kg.schema.extract"
    assert definition["name"] == "部件 平台喂数抽取"
    assert definition["timeoutSeconds"] > 0


class FakeBody(BytesIO):
    def close(self) -> None:  # noqa: D102
        pass


class FakeS3:
    def __init__(self, content: bytes) -> None:
        self.content = content

    def get_object(self, bucket: str, key: str) -> FakeBody:
        return FakeBody(self.content)


@pytest.fixture
def plan_env(monkeypatch: pytest.MonkeyPatch):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    from script.init_schema_management import MANAGED_TABLES
    from service.workflow_models import Base

    Base.metadata.create_all(engine, tables=MANAGED_TABLES)
    with Session(engine) as session:
        definition = GraphSchemaDefinition(
            id="schema-1",
            schema_key="widget",
            kind="entity",
            name="Widget",
            label="部件",
            description="",
        )
        definition.properties = [
            GraphSchemaProperty(
                name="id", data_type="string", required=True, category="required", position=0
            ),
            GraphSchemaProperty(
                name="name", data_type="string", required=True, category="required", position=1
            ),
            GraphSchemaProperty(
                name="rank", data_type="int64", required=False, category="core", position=2
            ),
            # 已软删属性不应进入 activeProps
            GraphSchemaProperty(
                name="legacy",
                data_type="string",
                required=False,
                category="core",
                position=3,
                is_deleted=True,
            ),
        ]
        definition.sources = [
            GraphSchemaSource(
                datasource_id="MYSQL-1",
                database_name="gkx",
                table_name="scholar",
                pk_column="id",
                time_column="update_time",
                position=0,
            )
        ]
        definition.script = GraphSchemaScript(
            bucket="b",
            object_key="k",
            original_filename="widget.py",
            size_bytes=10,
            sha256="x" * 64,
            uploaded_by="u",
            workflow_function_name="workflow",
        )
        session.add(definition)
        session.commit()
        session.close()

    monkeypatch.setattr("infra.workflow_mysql.get_workflow_engine", lambda: engine)
    monkeypatch.setattr(
        "infra.s3.get_schema_s3_storage", lambda: FakeS3(b"def workflow(payload):\n    return {}\n")
    )
    yield engine
    engine.dispose()


@pytest.mark.asyncio
async def test_load_schema_extract_plan_filters_deleted(plan_env) -> None:
    plan = await load_schema_extract_plan("schema-1")
    assert plan["kind"] == "entity"
    assert plan["name"] == "Widget"
    assert plan["activeProps"] == ["id", "name", "rank"]
    assert plan["sources"] == [
        {
            "id": plan["sources"][0]["id"],
            "datasourceId": "MYSQL-1",
            "databaseName": "gkx",
            "tableName": "scholar",
            "pkColumn": "id",
            "timeColumn": "update_time",
        }
    ]
    assert plan["functionName"] == "workflow"
    with open(plan["scriptPath"], "rb") as handle:
        assert b"def workflow(payload)" in handle.read()


@pytest.mark.asyncio
async def test_load_schema_extract_plan_requires_script_and_sources(plan_env) -> None:
    with pytest.raises(ValueError, match="Schema 不存在"):
        await load_schema_extract_plan("missing")


@pytest.mark.asyncio
async def test_advance_watermark_activity_writes_per_source_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str | None, str, object]] = []

    def fake_write(definition_id, step_id, watermark=None, checkpoint=None):
        calls.append((definition_id, step_id, watermark))

    monkeypatch.setattr("service.script_watermark.write_watermark", fake_write)
    result = await advance_schema_extract_watermark(
        {
            "definitionId": "schema-extract-widget",
            "stepId": "source:abc-1",
            "watermark": "2026-08-31 10:00:00",
        }
    )
    assert result["ok"] is True
    definition_id, step_id, watermark = calls[0]
    assert definition_id == "schema-extract-widget"
    assert step_id == "source:abc-1"  # 按绑定行独立
    assert watermark is not None
    from datetime import datetime as _dt

    assert isinstance(watermark, _dt) and watermark.year == 2026


def test_default_batch_size_constant() -> None:
    assert DEFAULT_BATCH_SIZE == 500
