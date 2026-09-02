"""属性硬删除配套单测：写图自愈 / unknown column 解析 / 水位清理 / 脚本健康回写。"""

from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from dao.script_watermark import ScriptWatermarkDAO
from db_model.base import Base as BusinessBase
from db_model.schema_management import GraphSchemaScript
from db_model.script_watermark import ScriptWatermark
from infra.graph_db.exceptions import GraphRequestError
from service.schema_extraction import extract_watermark_definition_ids
from service.script_watermark import ScriptWatermarkService, clear_watermarks
from service.temporal_workflows import (
    _unknown_column_name,
    record_schema_script_run,
    write_records,
)

# ---------------------------------------------------------------------------
# unknown column 报错解析
# ---------------------------------------------------------------------------


class TestUnknownColumnName:
    def test_nebula_semantic_error(self):
        exc = GraphRequestError(
            "TRS Graph query failed on /api/v1/query: SemanticError: `rank' not "
            "found in schema, or SemanticError: Unknown column `rank' in schema",
            status_code=200,
        )
        assert _unknown_column_name(exc) == "rank"

    def test_single_quoted(self):
        exc = GraphRequestError(
            "400 Bad Request: Unknown column 'confidence' in schema", status_code=400
        )
        assert _unknown_column_name(exc) == "confidence"

    def test_case_insensitive(self):
        exc = GraphRequestError('unknown column "ingest_time" in schema', status_code=400)
        assert _unknown_column_name(exc) == "ingest_time"

    def test_no_match_returns_none(self):
        assert _unknown_column_name(GraphRequestError("timeout", status_code=504)) is None


# ---------------------------------------------------------------------------
# write_records 写图自愈
# ---------------------------------------------------------------------------


class FakeGraphClient:
    """首写按配置炸 unknown column，重试（列已剔除）成功。"""

    def __init__(self, *, entity_bad: str | None = None, edge_bad: str | None = None) -> None:
        self.entity_bad = entity_bad
        self.edge_bad = edge_bad
        self.writes: list[str] = []
        self.merged_props: list[dict] = []

    def connect(self) -> None:
        return None

    def close(self) -> None:
        return None

    def execute_write(self, statement: str):
        self.writes.append(statement)
        if self.entity_bad and f"`{self.entity_bad}`" in statement:
            raise GraphRequestError(
                f"TRS Graph query failed: Unknown column `{self.entity_bad}` in schema",
                status_code=200,
            )

    def merge_edge(self, from_id, to_id, name, base, props):
        self.merged_props.append(dict(props))
        if self.edge_bad and self.edge_bad in props:
            raise GraphRequestError(
                f"TRS Graph query failed: Unknown column '{self.edge_bad}' in schema",
                status_code=400,
            )


def _bind_fake_client(monkeypatch: pytest.MonkeyPatch, client: FakeGraphClient) -> None:
    monkeypatch.setattr("infra.graph_db.client.TRSGraphClient", lambda settings: client)


@pytest.mark.asyncio
async def test_write_records_entity_self_heals_unknown_column(monkeypatch):
    client = FakeGraphClient(entity_bad="rank")
    _bind_fake_client(monkeypatch, client)
    result = await write_records(
        {
            "kind": "entity",
            "name": "Widget",
            "activeProps": [],
            "graph": {"space": "test"},
            "sourceTable": "gkx.t",
            "records": [
                {"id": "n1", "props": {"name": "甲", "rank": "A", "ext": "x"}},
            ],
        }
    )
    assert result == {"written": 1}
    assert len(client.writes) == 2
    assert "`rank`" not in client.writes[1]  # 重试语句已剔除坏列
    assert "`name`" in client.writes[1] and "`ext`" in client.writes[1]


@pytest.mark.asyncio
async def test_write_records_edge_self_heals_unknown_column(monkeypatch):
    client = FakeGraphClient(edge_bad="confidence")
    _bind_fake_client(monkeypatch, client)
    result = await write_records(
        {
            "kind": "relation",
            "name": "EMPLOYED_BY",
            "activeProps": [],
            "graph": {"space": "test"},
            "sourceTable": "gkx.t",
            "records": [
                {"fromId": "s", "toId": "d", "props": {"role": "engineer", "confidence": "0.9"}},
            ],
        }
    )
    assert result == {"written": 1}
    assert len(client.merged_props) == 2
    assert "confidence" not in client.merged_props[1]
    assert client.merged_props[1]["role"] == "engineer"


@pytest.mark.asyncio
async def test_write_records_gives_up_when_only_column_unknown(monkeypatch):
    client = FakeGraphClient(entity_bad="name")
    _bind_fake_client(monkeypatch, client)
    with pytest.raises(GraphRequestError):
        await write_records(
            {
                "kind": "entity",
                "name": "Widget",
                # 限定只写 name 一列：剔除后无列可写，必须抛而不是静默丢
                "activeProps": ["name"],
                "graph": {"space": "test"},
                "sourceTable": "gkx.t",
                "records": [{"id": "n1", "props": {"name": "甲"}}],
            }
        )
    assert len(client.writes) == 1  # 只剩一列不可剔除，直接抛


@pytest.mark.asyncio
async def test_write_records_non_unknown_column_error_propagates(monkeypatch):
    class BoomClient(FakeGraphClient):
        def execute_write(self, statement):
            raise GraphRequestError("TRS Graph query failed: storage timeout", status_code=500)

    client = BoomClient()
    _bind_fake_client(monkeypatch, client)
    with pytest.raises(GraphRequestError, match="timeout"):
        await write_records(
            {
                "kind": "entity",
                "name": "Widget",
                "activeProps": [],
                "graph": {"space": "test"},
                "sourceTable": "gkx.t",
                "records": [{"id": "n1", "props": {"name": "甲", "ext": "x"}}],
            }
        )


# ---------------------------------------------------------------------------
# 水位清理（回填）
# ---------------------------------------------------------------------------


@pytest.fixture
def watermark_engine():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    BusinessBase.metadata.create_all(engine, tables=[ScriptWatermark.__table__])
    yield engine
    engine.dispose()


def _seed_watermark(session: Session, definition_id: str, step_id: str) -> None:
    session.add(
        ScriptWatermark(
            definition_id=definition_id,
            step_id=step_id,
            watermark=datetime(2026, 9, 1, 12, 0, 0),
            updated_at=datetime.utcnow(),
        )
    )
    session.commit()


def test_dao_delete_source_watermarks(watermark_engine):
    with Session(watermark_engine) as session:
        dao = ScriptWatermarkDAO(session)
        _seed_watermark(session, "schema-extract-widget", "source:bind-1")
        _seed_watermark(session, "schema-extract-widget", "source:bind-2")
        _seed_watermark(session, "schema-extract-widget", "_default")
        _seed_watermark(session, "schema-extract-other", "source:bind-1")

        cleared = dao.delete_source_watermarks("schema-extract-widget")
        assert cleared == 2
        remaining = {(r.definition_id, r.step_id) for r in session.query(ScriptWatermark)}
        assert remaining == {
            ("schema-extract-widget", "_default"),
            ("schema-extract-other", "source:bind-1"),
        }


def test_clear_watermarks_across_definition_ids(watermark_engine, monkeypatch):
    with Session(watermark_engine) as session:
        # raw 变体（工作流实际推水位用的 key）与 sanitized 变体各留一行
        _seed_watermark(session, "schema-extract-Widget", "source:bind-9")
        _seed_watermark(session, "schema-extract-widget", "source:bind-1")
        _seed_watermark(session, "schema-extract-widget", "_default")

        def make_service():
            service = ScriptWatermarkService.__new__(ScriptWatermarkService)
            service._dao = ScriptWatermarkDAO(session)
            return service

        monkeypatch.setattr("service.script_watermark.ScriptWatermarkService", make_service)
        cleared = clear_watermarks(extract_watermark_definition_ids("Widget"))
        assert cleared == 2
        remaining = {
            (row.definition_id, row.step_id)
            for row in session.query(ScriptWatermark).filter(
                ScriptWatermark.step_id.like("source:%")
            )
        }
        assert remaining == set()  # 两个变体的 source 水位全清，_default 不动


def test_extract_watermark_definition_ids_variants():
    # schema_key 已是小写规范形式 → raw 与 sanitized 相同，去重后一个
    assert extract_watermark_definition_ids("widget") == ["schema-extract-widget"]
    # 含大写字符 → 两个候选都覆盖（下划线本就是合法字符，保持不变）
    assert extract_watermark_definition_ids("Widget_x") == [
        "schema-extract-Widget_x",
        "schema-extract-widget_x",
    ]


# ---------------------------------------------------------------------------
# 脚本健康信号回写（record_schema_script_run activity）
# ---------------------------------------------------------------------------


@pytest.fixture
def script_engine(monkeypatch):
    from script.init_schema_management import MANAGED_TABLES
    from service.workflow_models import Base

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine, tables=MANAGED_TABLES)
    monkeypatch.setattr("infra.workflow_mysql.get_workflow_engine", lambda: engine)
    with Session(engine) as session:
        session.add(
            GraphSchemaScript(
                schema_id="schema-1",
                bucket="b",
                object_key="k",
                original_filename="w.py",
                size_bytes=1,
                sha256="x" * 64,
                uploaded_by="u",
            )
        )
        session.commit()
    yield engine
    engine.dispose()


def _get_script_by_schema_id(session: Session, schema_id: str) -> GraphSchemaScript:
    from sqlalchemy import select

    return session.scalar(select(GraphSchemaScript).where(GraphSchemaScript.schema_id == schema_id))


@pytest.mark.asyncio
async def test_record_script_run_ok_clears_error(script_engine):
    with Session(script_engine) as session:
        row = _get_script_by_schema_id(session, "schema-1")
        row.last_run_status = "failed"
        row.last_run_error = "boom"
        session.commit()

    result = await record_schema_script_run({"schemaId": "schema-1", "status": "ok"})
    assert result == {"ok": True, "status": "ok"}
    with Session(script_engine) as session:
        row = _get_script_by_schema_id(session, "schema-1")
        assert row.last_run_status == "ok"
        assert row.last_run_error is None


@pytest.mark.asyncio
async def test_record_script_run_failed_truncates_error(script_engine):
    result = await record_schema_script_run(
        {"schemaId": "schema-1", "status": "failed", "error": "x" * 3000}
    )
    assert result["ok"] is True
    with Session(script_engine) as session:
        row = _get_script_by_schema_id(session, "schema-1")
        assert row.last_run_status == "failed"
        assert len(row.last_run_error) == 1024


@pytest.mark.asyncio
async def test_record_script_run_missing_script(script_engine):
    result = await record_schema_script_run({"schemaId": "missing", "status": "ok"})
    assert result == {"ok": False, "reason": "script-missing"}
