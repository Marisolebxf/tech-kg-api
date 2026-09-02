"""抽取失败重跑分组 / extract 任务类型（需控制库 MySQL，容器内跑）。

与单测的区别：这里覆盖 ``rerun_failed_records`` 与 ``WorkflowJobService.create_job /
trigger_job`` 的完整链路——它们内部 ``from service.workflow_repository import repository``
取真实单例，host 无 MySQL 时 import 即失败。
"""

from __future__ import annotations

from typing import Any

import pytest

import service.schema_extraction as schema_extraction
from service.platform_access import PlatformActor
from service.schema_extraction import rerun_failed_records
from service.workflow_jobs import WorkflowJobError, WorkflowJobService

pytestmark = pytest.mark.external


class _FakeReviewService:
    def __init__(self, cases):
        self._cases = cases
        self.marked: list[list[str]] = []
        self.reverted: list[list[str]] = []
        self.attached: list[tuple[list[str], str]] = []

    def list_extract_fail_cases(self, *, case_ids=None, execution_id=None, statuses=None):
        result = self._cases
        if case_ids:
            result = [c for c in result if c["caseId"] in case_ids]
        if execution_id:
            result = [c for c in result if c["executionId"] == execution_id]
        return result

    def mark_extract_rerun(self, case_ids, rerun_execution_id=None):
        self.marked.append(case_ids)
        return len(case_ids)

    def attach_rerun_execution(self, case_ids, rerun_execution_id):
        self.attached.append((case_ids, rerun_execution_id))
        return len(case_ids)

    def revert_extract_rerun(self, case_ids, *, reason):
        self.reverted.append(case_ids)
        return len(case_ids)


class _FakeOperations:
    def __init__(self):
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.fail_next = False

    async def execute_definition(self, definition, payload, persist_task=False):
        if self.fail_next:
            self.fail_next = False
            raise RuntimeError("Temporal 不可用")
        self.calls.append((definition["id"], payload))
        return {"id": f"EXEC-R{len(self.calls)}", "workflowId": "wf", "status": "RUNNING"}


def _case(case_id, record_id, binding, schema_id="schema-paper", execution="EXEC-1"):
    return {
        "caseId": case_id,
        "recordId": record_id,
        "sourceBindingId": binding,
        "schemaId": schema_id,
        "schemaKey": "paper",
        "executionId": execution,
        "jobId": "job-9",
        "attempt": 1,
        "sourceTable": "gkx.dwd_paper",
        "status": "OPEN",
    }


@pytest.fixture
def rerun_env(monkeypatch):
    fake_review = _FakeReviewService(
        [
            _case("MR-1", "42", "bind-1"),
            _case("MR-2", "43", "bind-1"),
            _case("MR-3", "99", "bind-2", schema_id="schema-patent"),
            {**_case("MR-4", "77", "bind-3"), "schemaId": None},
        ]
    )
    fake_ops = _FakeOperations()
    fake_repo = type(
        "R",
        (),
        {
            "get_execution": staticmethod(
                lambda i: (
                    {"id": "EXEC-1", "jobId": "job-9", "payload": {"graphSpace": "dev2"}}
                    if i == "EXEC-1"
                    else None
                )
            )
        },
    )()
    # 必须打到源模块属性：rerun_failed_records 运行时 from ... import repository
    monkeypatch.setattr("service.workflow_repository.repository", fake_repo)
    monkeypatch.setattr("service.manual_review_production.manual_review_service", fake_review)
    monkeypatch.setattr("service.workflow_operations.workflow_operations_service", fake_ops)
    monkeypatch.setattr(
        schema_extraction,
        "load_extract_schema",
        lambda schema_id: {
            "id": schema_id,
            "schema_key": schema_id.removeprefix("schema-"),
            "kind": "entity",
            "name": "Paper",
            "label": "论文",
        },
    )
    monkeypatch.setattr(schema_extraction, "persist_extract_definition", lambda d: d)
    return fake_review, fake_ops


class TestRerunFailedRecords:
    async def test_groups_by_schema(self, rerun_env):
        fake_review, fake_ops = rerun_env
        result = await rerun_failed_records(case_ids=["MR-1", "MR-2", "MR-3", "MR-4"])
        assert len(fake_ops.calls) == 2
        assert result["cases"] == 3
        by_definition = dict(fake_ops.calls)
        paper_payload = by_definition["schema-extract-paper"]
        assert paper_payload["recordIdsBySource"] == {"bind-1": ["42", "43"]}
        for _, payload in fake_ops.calls:
            assert payload["triggerSource"] == "RERUN"
            assert payload["rerunOfExecutionId"] == "EXEC-1"
            assert payload["jobId"] == "job-9"
            assert payload["graphSpace"] == "dev2"
            assert payload["buildIndex"] is False
        assert fake_review.marked and fake_review.attached

    async def test_trigger_failure_reverts_cases(self, rerun_env):
        fake_review, fake_ops = rerun_env
        fake_ops.fail_next = True
        with pytest.raises(RuntimeError):
            await rerun_failed_records(case_ids=["MR-1"])
        assert fake_review.reverted
        assert fake_review.attached == []


class _FakeRepo:
    def __init__(self):
        self.jobs: dict[str, dict[str, Any]] = {}
        self.definitions: dict[str, dict[str, Any]] = {}

    def get_definition(self, definition_id):
        return self.definitions.get(definition_id)

    def save_definition(self, definition):
        self.definitions[definition["id"]] = definition

    def get_job(self, job_id):
        return self.jobs.get(job_id)

    def save_job(self, job):
        self.jobs[job["id"]] = job


class TestExtractJob:
    async def test_create_extract_job_persists_definition(self, monkeypatch):
        repo = _FakeRepo()
        service = WorkflowJobService(repo=repo)
        monkeypatch.setattr(
            schema_extraction,
            "load_extract_schema",
            lambda schema_id: {
                "id": schema_id,
                "schema_key": "paper",
                "kind": "entity",
                "name": "Paper",
                "label": "论文",
            },
        )
        monkeypatch.setattr(
            schema_extraction, "persist_extract_definition", lambda d: repo.save_definition(d) or d
        )
        job = await service.create_job(
            PlatformActor(
                user_id="u1", username="u1", display_name="u1", email="u@x.io", is_admin=True
            ),
            {
                "name": "论文抽取",
                "taskType": "extract",
                "schemaId": "schema-paper",
                "schedule": {"kind": "once"},
                "graphSpace": "dev2",
                "batchSize": 300,
            },
        )
        assert job["taskType"] == "extract"
        assert job["schemaId"] == "schema-paper"
        assert job["definitionId"] == "schema-extract-paper"
        assert repo.definitions["schema-extract-paper"]["sourceKind"] == "extract"

    async def test_create_requires_schema(self):
        service = WorkflowJobService(repo=_FakeRepo())
        with pytest.raises(WorkflowJobError, match="Schema"):
            await service.create_job(
                PlatformActor(
                    user_id="u1", username="u1", display_name="u1", email="u@x.io", is_admin=True
                ),
                {"name": "x", "taskType": "extract", "schedule": {"kind": "once"}},
            )

    async def test_trigger_payload_carries_schema_and_manual_source(self, monkeypatch):
        repo = _FakeRepo()
        service = WorkflowJobService(repo=repo)
        monkeypatch.setattr(
            schema_extraction,
            "load_extract_schema",
            lambda schema_id: {
                "id": schema_id,
                "schema_key": "paper",
                "kind": "entity",
                "name": "Paper",
                "label": "论文",
            },
        )
        monkeypatch.setattr(
            schema_extraction, "persist_extract_definition", lambda d: repo.save_definition(d) or d
        )
        await service.create_job(
            PlatformActor(
                user_id="u1", username="u1", display_name="u1", email="u@x.io", is_admin=True
            ),
            {
                "name": "论文抽取",
                "taskType": "extract",
                "schemaId": "schema-paper",
                "schedule": {"kind": "once"},
                "graphSpace": "dev2",
            },
        )
        captured: dict[str, Any] = {}

        class _Ops:
            @staticmethod
            async def execute_definition(definition, payload, persist_task=False):
                captured.update(definition=definition, payload=payload)
                return {"id": "EXEC-J1", "workflowId": "wf", "status": "RUNNING", "startedAt": "t"}

        monkeypatch.setattr("service.workflow_operations.workflow_operations_service", _Ops)
        job_id = next(iter(repo.jobs))
        execution = await service.trigger_job(
            PlatformActor(
                user_id="u1", username="u1", display_name="u1", email="u@x.io", is_admin=True
            ),
            job_id,
        )
        assert execution["id"] == "EXEC-J1"
        assert captured["payload"]["schemaId"] == "schema-paper"
        assert captured["payload"]["triggerSource"] == "MANUAL"
        assert captured["payload"]["graph_space"] == "dev2"
        assert captured["payload"]["jobId"] == job_id
