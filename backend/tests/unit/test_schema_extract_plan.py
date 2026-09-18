"""平台喂数抽取计划构建单测：definition id / build_extract_definition / load_schema_extract_plan / 水位。"""

from __future__ import annotations

import hashlib
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
    _rematerialize_run_script,
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
        self.uploads: list[tuple[str, bytes]] = []

    @property
    def bucket(self) -> str:
        return "b"

    def get_object(self, bucket: str, key: str) -> FakeBody:
        # 先查已上传对象（run 副本重物化场景），否则回退到 schema 当前脚本内容
        for uploaded_key, data in reversed(self.uploads):
            if uploaded_key == key:
                return FakeBody(data)
        return FakeBody(self.content)

    def put_bytes(self, key: str, data: bytes, content_type: str) -> SimpleNamespace:
        self.uploads.append((key, data))
        return SimpleNamespace(bucket=self.bucket, object_key=key, etag=None)

    def delete_object(self, bucket: str, key: str) -> None:
        self.uploads = [(k, d) for k, d in self.uploads if k != key]


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
            GraphSchemaProperty(
                name="legacy",
                data_type="string",
                required=False,
                category="core",
                position=3,
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
            workflow_function_name="normalize",
        )
        session.add(definition)
        session.commit()
        session.close()

    monkeypatch.setattr("infra.workflow_mysql.get_workflow_engine", lambda: engine)
    monkeypatch.setattr(
        "infra.s3.get_schema_s3_storage",
        lambda: FakeS3(
            b"from kg_sdk import step\n\n\n@step\ndef normalize(payload):\n    return {}\n"
        ),
    )
    yield engine
    engine.dispose()


@pytest.mark.asyncio
async def test_load_schema_extract_plan_rejects_legacy_single_entry(
    plan_env, monkeypatch: pytest.MonkeyPatch
) -> None:
    """旧单步 transform/workflow 脚本在 plan 组装即拒绝（唯一形态是 @step）。"""
    monkeypatch.setattr(
        "infra.s3.get_schema_s3_storage",
        lambda: FakeS3(b"def transform(payload):\n    return {}\n"),
    )
    with pytest.raises(ValueError, match="已下线"):
        await load_schema_extract_plan("schema-1")


@pytest.mark.asyncio
async def test_load_schema_extract_plan_rejects_steps_literal(
    plan_env, monkeypatch: pytest.MonkeyPatch
) -> None:
    """STEPS 清单声明已删除：plan 组装报下线错误。"""
    monkeypatch.setattr(
        "infra.s3.get_schema_s3_storage",
        lambda: FakeS3(b'STEPS = [{"id": "a", "fn": "fa"}]\n\ndef fa(payload):\n    return {}\n'),
    )
    with pytest.raises(ValueError, match="STEPS 清单声明已下线"):
        await load_schema_extract_plan("schema-1")


DECORATED_SCRIPT = (
    b"from kg_sdk import step\n"
    b"\n"
    b"\n"
    b"@step\n"
    b"def normalize(payload):\n"
    b'    return {"cleaned": payload.get("rows", [])}\n'
    b"\n"
    b"\n"
    b'@step("emit-rows")\n'
    b"def do_emit(payload):\n"
    b'    return {"entities": []}\n'
)


@pytest.mark.asyncio
async def test_load_schema_extract_plan_parses_step_decorators(
    plan_env, monkeypatch: pytest.MonkeyPatch
) -> None:
    """@step 装饰器脚本：步顺序 = 源码顺序，显式 id 可含 -，plan 只带 id/fn 键。"""
    monkeypatch.setattr("infra.s3.get_schema_s3_storage", lambda: FakeS3(DECORATED_SCRIPT))
    plan = await load_schema_extract_plan("schema-1")
    assert plan["steps"] == [
        {"id": "normalize", "fn": "normalize"},
        {"id": "emit-rows", "fn": "do_emit"},
    ]


@pytest.mark.asyncio
async def test_load_schema_extract_plan_rejects_invalid_steps(
    plan_env, monkeypatch: pytest.MonkeyPatch
) -> None:
    """绕过上传通道的非法 @step 声明在 plan 组装时报清晰错误。"""
    broken = b"from kg_sdk import step\n\n@step(1)\ndef f(p):\n    return {}\n"
    monkeypatch.setattr("infra.s3.get_schema_s3_storage", lambda: FakeS3(broken))
    with pytest.raises(ValueError, match="步声明非法.*只接受一个可选的 step id"):
        await load_schema_extract_plan("schema-1")


@pytest.mark.asyncio
async def test_load_schema_extract_plan_includes_all_properties(plan_env) -> None:
    """软删退役：activeProps 为目录属性全集（用户脚本多出的列写图前再剔除兜底）。"""
    plan = await load_schema_extract_plan("schema-1")
    assert plan["kind"] == "entity"
    assert plan["name"] == "Widget"
    assert plan["activeProps"] == ["id", "name", "rank", "legacy"]
    assert plan["sources"] == [
        {
            "id": plan["sources"][0]["id"],
            "datasourceId": "MYSQL-1",
            "databaseName": "gkx",
            "tableName": "scholar",
            "pkColumn": "id",
            "timeColumn": "update_time",
            "querySql": None,
        }
    ]
    # 入口名不再进 plan：@step 是唯一形态，步清单由 plan["steps"] 给出
    assert plan["maxInflight"] >= 1 and plan["failureCaseCap"] >= 0
    with open(plan["scriptPath"], "rb") as handle:
        assert b"@step" in handle.read()


@pytest.mark.asyncio
async def test_load_schema_extract_plan_requires_script_and_sources(plan_env) -> None:
    with pytest.raises(ValueError, match="Schema 不存在"):
        await load_schema_extract_plan("missing")


@pytest.mark.asyncio
async def test_load_schema_extract_plan_pins_run_copy(
    plan_env, monkeypatch: pytest.MonkeyPatch
) -> None:
    """plan 钉住 run 级脚本副本：S3 写入 runs/{id}/script.py，plan 带 key + sha256。"""
    content = b"from kg_sdk import step\n\n\n@step\ndef normalize(payload):\n    return {}\n"
    fake = FakeS3(content)
    monkeypatch.setattr("infra.s3.get_schema_s3_storage", lambda: fake)
    plan = await load_schema_extract_plan("schema-1")
    assert len(fake.uploads) == 1
    key, data = fake.uploads[0]
    assert key.startswith("runs/") and key.endswith("/script.py")
    assert data == content
    assert plan["scriptRunKey"] == key
    assert plan["scriptSha256"] == hashlib.sha256(content).hexdigest()


@pytest.mark.asyncio
async def test_rematerialize_run_script_roundtrip(monkeypatch: pytest.MonkeyPatch) -> None:
    """tempfile 丢失后按 run 副本重物化：下载字节、校验通过、落成新临时文件。"""
    content = b"def transform(payload):\n    return {}\n"
    fake = FakeS3(content)
    monkeypatch.setattr("infra.s3.get_schema_s3_storage", lambda: fake)
    path = await _rematerialize_run_script(
        {
            "scriptPath": "/tmp/gone.py",
            "scriptRunKey": "runs/w1/script.py",
            "scriptSha256": hashlib.sha256(content).hexdigest(),
        }
    )
    with open(path, "rb") as handle:
        assert handle.read() == content


@pytest.mark.asyncio
async def test_rematerialize_run_script_rejects_sha_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """副本内容与钉住的 sha256 不符：硬失败，绝不执行不确定版本的脚本。"""
    fake = FakeS3(b"tampered")
    monkeypatch.setattr("infra.s3.get_schema_s3_storage", lambda: fake)
    with pytest.raises(RuntimeError, match="sha256 校验失败"):
        await _rematerialize_run_script(
            {
                "scriptPath": "/tmp/gone.py",
                "scriptRunKey": "runs/w1/script.py",
                "scriptSha256": hashlib.sha256(b"expected").hexdigest(),
            }
        )


@pytest.mark.asyncio
async def test_rematerialize_run_script_requires_copy_reference() -> None:
    """升级窗口内在飞旧 plan 无 run 副本字段：保持旧的明确失败语义。"""
    with pytest.raises(ValueError, match="脚本不存在且无 run 副本"):
        await _rematerialize_run_script({"scriptPath": "/tmp/gone.py"})


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
