"""Protocol and fail-closed tests for the worker-to-runner boundary."""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from service import script_sandbox_client as sandbox


class Broker:
    def __init__(self):
        self.calls = []
        self.closed = False
        self.error = False

    def call(self, resource, method, args, kwargs):
        self.calls.append((resource, method, args, kwargs))
        if self.error:
            raise RuntimeError("mysql://secret-password@internal-host")
        return {"rows": [{"id": 1}]}

    def close(self):
        self.closed = True


@pytest.fixture
def configured(monkeypatch, tmp_path):
    monkeypatch.setenv("SCRIPT_RUNNER_URL", "http://runner:8099")
    monkeypatch.setenv("SCRIPT_RUNNER_TOKEN", "t" * 48)
    script = tmp_path / "step.py"
    script.write_text("def step(payload): return payload", encoding="utf-8")
    return script


def install_transport(monkeypatch, events, requests):
    real_client = httpx.AsyncClient

    async def handler(request):
        requests.append(request)
        assert request.headers["authorization"] == "Bearer " + "t" * 48
        if request.url.path.endswith("/reply"):
            return httpx.Response(200, json={"ok": True})
        return httpx.Response(200, content="\n".join(json.dumps(item) for item in events) + "\n")

    def client_factory(**kwargs):
        assert kwargs["trust_env"] is False
        assert kwargs["follow_redirects"] is False
        return real_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(sandbox.httpx, "AsyncClient", client_factory)


async def test_round_trip_proxies_resources_without_credentials(monkeypatch, configured):
    requests = []
    install_transport(
        monkeypatch,
        [
            {"type": "ready", "runId": "run-1"},
            {
                "type": "rpc",
                "runId": "run-1",
                "id": 1,
                "resource": "mysql",
                "method": "query",
                "args": ["SELECT id FROM x"],
                "kwargs": {},
            },
            {"type": "result", "value": {"entities": []}},
        ],
        requests,
    )
    broker = Broker()
    result = await sandbox.execute_script(
        configured, "step", b'{"rows": []}', {"stepId": "s"}, 2, broker
    )
    assert result == {"result": {"entities": []}}
    assert broker.calls == [("mysql", "query", ["SELECT id FROM x"], {})]
    assert broker.closed
    assert json.loads(requests[0].content)["context"] == {"stepId": "s"}
    assert json.loads(requests[1].content) == {"id": 1, "result": {"rows": [{"id": 1}]}}


async def test_rpc_error_never_reveals_provider_credentials(monkeypatch, configured):
    requests = []
    install_transport(
        monkeypatch,
        [
            {"type": "ready", "runId": "run-1"},
            {"type": "rpc", "runId": "run-1", "id": "x", "resource": "mysql", "method": "query"},
            {"type": "result", "value": {}},
        ],
        requests,
    )
    broker = Broker()
    broker.error = True
    await sandbox.execute_script(configured, "step", b"{}", {}, 2, broker)
    assert "secret-password" not in requests[1].content.decode()
    assert "error" in json.loads(requests[1].content)


@pytest.mark.parametrize(
    "events",
    [
        [{"type": "result", "value": {}}],
        [{"type": "ready", "runId": "../../escape"}],
        [{"type": "ready", "runId": "run-1"}, {"type": "rpc", "runId": "other", "id": 1}],
        [{"type": "ready", "runId": "run-1"}],
        [{"type": "error", "message": {"invalid": True}}],
    ],
)
async def test_invalid_or_incomplete_protocol_fails_closed(monkeypatch, configured, events):
    install_transport(monkeypatch, events, [])
    broker = Broker()
    with pytest.raises(sandbox.ScriptSandboxError) as error:
        await sandbox.execute_script(configured, "step", b"{}", {}, 2, broker)
    assert "password" not in str(error.value)
    assert broker.closed


async def test_unconfigured_runner_never_executes_locally(monkeypatch, configured):
    monkeypatch.delenv("SCRIPT_RUNNER_URL")
    broker = Broker()
    with pytest.raises(sandbox.ScriptSandboxError, match="禁止回退"):
        await sandbox.execute_script(configured, "step", b"{}", {}, 2, broker)
    assert broker.closed


async def test_oversized_ndjson_is_rejected(monkeypatch, configured):
    monkeypatch.setattr(sandbox, "_MAX_LINE", 10)
    install_transport(monkeypatch, [{"type": "ready", "runId": "run-1"}], [])
    with pytest.raises(sandbox.ScriptSandboxError, match="大小"):
        await sandbox.execute_script(configured, "step", b"{}", {}, 2, Broker())


async def test_timeout_covers_waiting_resource_call(monkeypatch, configured):
    install_transport(
        monkeypatch,
        [
            {"type": "ready", "runId": "run-1"},
            {"type": "rpc", "runId": "run-1", "id": 1, "resource": "mysql", "method": "query"},
        ],
        [],
    )
    broker = Broker()

    async def blocked(*args):
        await asyncio.sleep(30)

    broker.call = blocked
    with pytest.raises(sandbox.ScriptSandboxError, match="超时"):
        await sandbox.execute_script(configured, "step", b"{}", {}, 0.03, broker)
    assert broker.closed


async def test_cancellation_closes_broker(monkeypatch, configured):
    install_transport(
        monkeypatch,
        [
            {"type": "ready", "runId": "run-1"},
            {"type": "rpc", "runId": "run-1", "id": 1, "resource": "mysql", "method": "query"},
        ],
        [],
    )
    broker = Broker()
    entered = asyncio.Event()

    async def blocked(*args):
        entered.set()
        await asyncio.sleep(30)

    broker.call = blocked
    task = asyncio.create_task(sandbox.execute_script(configured, "step", b"{}", {}, 2, broker))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert broker.closed


async def test_existing_script_is_rehashed_before_running(monkeypatch, tmp_path):
    from service import business_access_control, temporal_workflows

    monkeypatch.setattr(business_access_control, "rbac_enabled", lambda: False)
    script = tmp_path / "changed.py"
    script.write_text("changed", encoding="utf-8")
    with pytest.raises(RuntimeError, match="sha256"):
        await temporal_workflows.execute_transform(
            {"scriptPath": str(script), "scriptSha256": "0" * 64, "functionName": "step"}
        )


async def test_rbac_spawn_never_falls_back_to_worker_process(monkeypatch, configured):
    from service import business_access_control, script_resource_broker, temporal_workflows

    monkeypatch.setattr(business_access_control, "rbac_enabled", lambda: True)
    monkeypatch.delenv("SCRIPT_RUNNER_URL")
    broker = Broker()
    broker.public_context = lambda: {"stepId": "s"}
    monkeypatch.setattr(script_resource_broker, "ScriptResourceBroker", lambda request, ctx: broker)

    async def forbidden_spawn(*args, **kwargs):
        pytest.fail("RBAC must never launch a local subprocess")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", forbidden_spawn)
    with pytest.raises(sandbox.ScriptSandboxError, match="禁止回退"):
        await temporal_workflows._spawn_script(
            configured,
            "step",
            b"{}",
            {},
            1,
            "legacy-runner",
            "script",
            request={"actorUserId": "alice"},
        )
    assert broker.closed


async def test_transform_checks_identity_before_fetching_payload(monkeypatch, configured):
    from fastapi import HTTPException

    from service import business_access_control, temporal_workflows, workflow_jobs

    monkeypatch.setattr(business_access_control, "rbac_enabled", lambda: True)

    def deny(request):
        raise HTTPException(403, "revoked")

    monkeypatch.setattr(workflow_jobs, "authorize_background_execution", deny)
    with pytest.raises(HTTPException):
        await temporal_workflows.execute_transform(
            {"scriptPath": str(configured), "rowsKey": "private/source", "functionName": "step"}
        )


async def test_source_reader_rejects_internal_table_before_credentials(monkeypatch):
    from service import (
        business_access_control,
        mysql_datasource,
        script_resource_broker,
        temporal_workflows,
    )
    from service.script_resource_broker import ScriptAccessDenied

    monkeypatch.setattr(business_access_control, "rbac_enabled", lambda: True)

    def credentials(*args):
        pytest.fail("Forbidden source must be rejected before resolving credentials")

    monkeypatch.setattr(mysql_datasource, "get_mysql_settings_by_id", credentials)
    monkeypatch.setattr(script_resource_broker, "validate_script_resources", lambda request: None)
    with pytest.raises(ScriptAccessDenied):
        await temporal_workflows.read_source_batch(
            {
                "datasourceId": "source",
                "database": "business",
                "table": "platform_mysql_datasource",
                "pkColumn": "id",
                "source": {
                    "datasourceId": "source",
                    "databaseName": "business",
                    "tableName": "platform_mysql_datasource",
                    "pkColumn": "id",
                },
            }
        )


async def test_access_report_is_preserved(monkeypatch, configured):
    install_transport(
        monkeypatch, [{"type": "ready", "runId": "run-1"}, {"type": "result", "value": {}}], []
    )
    broker = Broker()
    broker.access_report = lambda: {"resources": [{"resource": "mysql", "method": "query"}]}
    result = await sandbox.execute_script(configured, "step", b"{}", {}, 2, broker)
    assert result["_access"] == broker.access_report()


async def test_rpc_reply_limit_sends_error_without_desynchronizing(monkeypatch, configured):
    requests = []
    monkeypatch.setattr(sandbox, "_MAX_REPLY", 10)
    install_transport(
        monkeypatch,
        [
            {"type": "ready", "runId": "run-1"},
            {"type": "rpc", "runId": "run-1", "id": 1, "resource": "mysql", "method": "query"},
            {"type": "result", "value": {}},
        ],
        requests,
    )
    await sandbox.execute_script(configured, "step", b"{}", {}, 2, Broker())
    reply = json.loads(requests[1].content)
    assert reply["id"] == 1 and "error" in reply and "result" not in reply


async def test_safe_access_denial_is_visible(monkeypatch, configured):
    from service.script_resource_broker import ScriptAccessDenied

    requests = []
    install_transport(
        monkeypatch,
        [
            {"type": "ready", "runId": "run-1"},
            {"type": "rpc", "runId": "run-1", "id": 1, "resource": "mysql", "method": "query"},
            {"type": "result", "value": {}},
        ],
        requests,
    )
    broker = Broker()

    def denied(*args):
        raise ScriptAccessDenied("source table is outside the authorized business")

    broker.call = denied
    await sandbox.execute_script(configured, "step", b"{}", {}, 2, broker)
    assert (
        json.loads(requests[1].content)["error"]
        == "source table is outside the authorized business"
    )


async def test_script_error_detail_is_bounded_and_visible(monkeypatch, configured):
    install_transport(
        monkeypatch,
        [
            {"type": "ready", "runId": "run-1"},
            {"type": "error", "message": "ValueError: missing name column " + "x" * 5000},
        ],
        [],
    )
    with pytest.raises(
        sandbox.ScriptSandboxError, match="ValueError: missing name column"
    ) as error:
        await sandbox.execute_script(configured, "step", b"{}", {}, 2, Broker())
    assert len(str(error.value)) < 4200


async def test_source_reader_rechecks_revoked_identity_before_credentials(monkeypatch):
    from fastapi import HTTPException

    from service import (
        business_access_control,
        mysql_datasource,
        script_resource_broker,
        temporal_workflows,
    )

    monkeypatch.setattr(business_access_control, "rbac_enabled", lambda: True)

    def deny(request):
        assert request["actorUserId"] == "revoked"
        raise HTTPException(403, "revoked")

    monkeypatch.setattr(script_resource_broker, "validate_script_resources", deny)
    monkeypatch.setattr(
        mysql_datasource,
        "get_mysql_settings_by_id",
        lambda *args: pytest.fail("must authorize before resolving credentials"),
    )
    with pytest.raises(HTTPException, match="revoked"):
        await temporal_workflows.read_source_batch(
            {"datasourceId": "source", "pkColumn": "id", "actorUserId": "revoked"}
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("datasourceId", "other"),
        ("database", "other"),
        ("table", "other"),
        ("querySql", "SELECT 1"),
        ("pkColumn", "other"),
        ("timeColumn", "other"),
    ],
)
async def test_source_reader_rejects_changed_read_scope(monkeypatch, field, value):
    from service import (
        business_access_control,
        mysql_datasource,
        script_resource_broker,
        temporal_workflows,
    )

    monkeypatch.setattr(business_access_control, "rbac_enabled", lambda: True)
    monkeypatch.setattr(script_resource_broker, "validate_script_resources", lambda request: None)
    monkeypatch.setattr(
        mysql_datasource,
        "get_mysql_settings_by_id",
        lambda *args: pytest.fail("must reject inconsistent source before credentials"),
    )
    request = {
        "datasourceId": "source",
        "database": "business",
        "table": "papers",
        "pkColumn": "id",
        "source": {
            "datasourceId": "source",
            "databaseName": "business",
            "tableName": "papers",
            "pkColumn": "id",
        },
    }
    request[field] = value
    with pytest.raises(script_resource_broker.ScriptAccessDenied, match="读取参数"):
        await temporal_workflows.read_source_batch(request)


@pytest.mark.parametrize("sandbox_patch", [True, False])
async def test_schema_space_propagates_to_script_selectors_without_override(
    monkeypatch, sandbox_patch
):
    from service import temporal_workflows as tw

    class ReaderReached(RuntimeError):
        pass

    captured = {}
    monkeypatch.setattr(
        tw.workflow,
        "patched",
        lambda name: sandbox_patch if name == "business-script-sandbox-v1" else True,
    )

    async def execute(fn, request, **kwargs):
        if fn is tw.load_schema_extract_plan:
            return {
                "schemaKey": "papers",
                "graphSpace": "private-business",
                "steps": [{"id": "normalize", "fn": "normalize"}],
                "sources": [
                    {
                        "id": "src",
                        "datasourceId": "ds",
                        "databaseName": "business",
                        "tableName": "papers",
                        "pkColumn": "id",
                    }
                ],
            }
        if fn is tw.read_source_batch:
            captured.update(request)
            raise ReaderReached()
        pytest.fail(f"Unexpected activity {fn}")

    monkeypatch.setattr(tw.workflow, "execute_activity", execute)
    instance = tw.SchemaExtractWorkflow()
    with pytest.raises(ReaderReached):
        await instance._extract_schema({"actorUserId": "alice", "clientId": "project"}, "schema-id")
    assert captured["graphSpace"] == "private-business"
    assert captured["selectors"].get("graph_space") == (
        "private-business" if sandbox_patch else None
    )


async def test_source_reader_rejects_time_column_sql_injection(monkeypatch):
    from service import mysql_datasource, temporal_workflows

    monkeypatch.setattr(
        mysql_datasource,
        "get_mysql_settings_by_id",
        lambda *args: pytest.fail("invalid identifier must fail before credentials"),
    )
    with pytest.raises(ValueError):
        await temporal_workflows.read_source_batch(
            {"datasourceId": "ds", "pkColumn": "id", "timeColumn": "updated` OR 1=1 --"}
        )


async def test_sandbox_run_scope_is_derived_from_temporal_not_request(monkeypatch, configured):
    import hashlib
    from types import SimpleNamespace

    from service import business_access_control, script_resource_broker, temporal_workflows

    monkeypatch.setattr(business_access_control, "rbac_enabled", lambda: True)
    monkeypatch.setattr(
        temporal_workflows.activity,
        "info",
        lambda: SimpleNamespace(workflow_id="workflow", workflow_run_id="run"),
    )
    captured = {}

    def make_broker(request, context):
        captured.update(request)
        broker = Broker()
        broker.public_context = lambda: {}
        return broker

    monkeypatch.setattr(script_resource_broker, "ScriptResourceBroker", make_broker)

    async def execute(*args):
        return {"result": {}}

    monkeypatch.setattr(sandbox, "execute_script", execute)
    await temporal_workflows._spawn_script(
        configured, "step", b"{}", {}, 2, "unused", "test", request={"_sandboxRunKey": "forged"}
    )
    assert (
        captured["_sandboxRunKey"]
        == hashlib.sha256(json.dumps(["workflow", "run"]).encode()).hexdigest()
    )
