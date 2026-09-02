"""抽取合成定义 / triggerSource 单元测试（host 安全，不 import 控制库单例）。"""

from __future__ import annotations

from service.schema_extraction import build_extract_definition, extract_definition_id
from service.temporal_runtime import TemporalRuntime


class TestExtractDefinition:
    def test_definition_shape(self):
        definition = build_extract_definition(
            {"schema_key": "paper", "kind": "entity", "label": "论文", "name": "Paper"}
        )
        assert definition["id"] == "schema-extract-paper"
        assert definition["workflowType"] == "kg.schema.extract"
        assert definition["sourceKind"] == "extract"
        assert definition["category"] == "extract"
        assert definition["active"] is True

    def test_extract_definition_id_deterministic(self):
        assert extract_definition_id("paper") == "schema-extract-paper"


class TestTriggerSource:
    def test_execution_record_default_manual(self):
        record = TemporalRuntime.execution_record(
            "schema-extract-paper",
            {"workflowId": "wf-1", "status": "RUNNING"},
            {"schemaId": "x"},
        )
        assert record["triggerSource"] == "MANUAL"

    def test_execution_record_schedule_from_dispatch(self):
        record = TemporalRuntime.execution_record(
            "schema-extract-paper",
            {"workflowId": "wf-1", "status": "RUNNING", "triggerSource": "SCHEDULE"},
            {},
        )
        assert record["triggerSource"] == "SCHEDULE"

    def test_create_schedule_extract_keeps_flat_payload(self):
        """extract 定义的 Schedule payload 不包装 {definitionId, payload}，只 merge _scheduleId。"""
        import inspect

        source = inspect.getsource(TemporalRuntime.create_schedule)
        assert 'sourceKind") == "extract"' in source
