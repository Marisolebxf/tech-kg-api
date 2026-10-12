import asyncio
import io
from contextlib import nullcontext
from types import SimpleNamespace

import pytest
from fastapi import HTTPException


def test_rule_relation_extraction_does_not_resolve_any_model(monkeypatch):
    from application import common_capability

    monkeypatch.setattr(
        common_capability,
        "get_llm_client",
        lambda: pytest.fail("Rule extraction must not resolve a model"),
    )
    application = common_capability.CommonCapabilityApplication()
    application.extract_relations("马云创立了阿里巴巴集团", method="rule")
    application.batch_extract_relations(["马云创立了阿里巴巴集团"], method="rule")


def test_clients_do_not_leak_between_concurrent_businesses_or_default_switch(monkeypatch):
    from infra import llm
    from service.llm_context import selected_llm_business

    defaults = {"a": "model-a", "b": "model-b", None: "public"}
    monkeypatch.setattr(
        "service.llm_config.resolve_llm_settings",
        lambda business_id=None: ("key", "http://models", defaults[business_id]),
    )
    monkeypatch.setattr(llm, "LLMClient", lambda **kw: SimpleNamespace(**kw))

    async def request(business):
        token = selected_llm_business.set(business)
        try:
            await asyncio.sleep(0)
            return llm.get_llm_client()
        finally:
            selected_llm_business.reset(token)

    async def both():
        return await asyncio.gather(request("a"), request("b"))

    a, b = asyncio.run(both())
    assert (a.model, b.model) == ("model-a", "model-b")
    defaults["a"] = "new-a"
    assert asyncio.run(request("a")).model == "new-a"
    assert a.model == "model-a"
    assert selected_llm_business.get() is None
    assert llm.get_llm_client().model == "public"


def test_invalid_selected_model_is_not_silently_degraded(monkeypatch):
    from infra.llm import get_llm_client

    def fail(**kwargs):
        raise HTTPException(409, "selected model disabled")

    monkeypatch.setattr("service.llm_config.resolve_llm_settings", fail)
    with pytest.raises(HTTPException) as error:
        get_llm_client()
    assert error.value.status_code == 409


def test_one_request_keeps_model_while_later_request_uses_new_default(monkeypatch):
    from service.llm_context import request_llm_settings, resolve_request_llm_settings

    current = ["old"]
    monkeypatch.setattr(
        "service.llm_config.resolve_llm_settings", lambda **kw: ("key", "http://models", current[0])
    )
    token = request_llm_settings.set({})
    try:
        assert resolve_request_llm_settings()[2] == "old"
        current[0] = "new"
        assert resolve_request_llm_settings()[2] == "old"
    finally:
        request_llm_settings.reset(token)
    assert resolve_request_llm_settings()[2] == "new"


def test_entity_extraction_respects_business_endpoint_and_switch(monkeypatch):
    from service.common import entity_extraction
    from service.llm_context import selected_llm_business

    monkeypatch.setattr(
        "service.llm_config.resolve_llm_settings",
        lambda business_id=None: ("key", f"http://{business_id}", business_id),
    )
    monkeypatch.setattr(entity_extraction, "OpenAI", lambda **kwargs: kwargs)
    for business in ("a", "b", "a"):
        token = selected_llm_business.set(business)
        try:
            client, model = entity_extraction.get_client()
            assert client["base_url"] == f"http://{business}"
            assert model == business
        finally:
            selected_llm_business.reset(token)


def test_execution_pins_model_for_all_batches_and_next_run_picks_change(monkeypatch):
    from service import temporal_workflows as workflows

    defaults = {"a": "first"}
    monkeypatch.setattr("service.business_access_control.rbac_enabled", lambda: True)
    monkeypatch.setattr(
        "service.workflow_jobs.authorize_background_execution", lambda req: object()
    )
    monkeypatch.setattr("service.workflow_jobs._job_business", lambda actor, req: "a")
    monkeypatch.setattr("infra.mysql.session_scope", lambda: nullcontext(object()))
    monkeypatch.setattr(
        "service.llm_defaults.resolve_default_config",
        lambda session, business_id=None, config_id=None: SimpleNamespace(
            id=config_id or defaults[business_id]
        ),
    )
    monkeypatch.setattr(
        "service.llm_config.get_llm_settings_by_id",
        lambda config_id, business_id=None: {
            "api_key": "secret",
            "base_url": "http://model",
            "model": config_id,
        },
    )
    monkeypatch.setattr("service.script_watermark.read_watermark", lambda *args: None)
    pinned = asyncio.run(workflows.resolve_execution_llm({"clientId": "a"}))
    assert "secret" not in str(pinned)
    defaults["a"] = "second"
    for _ in range(3):
        assert workflows._resolve_resources(pinned, None, "step")["llm"]["model"] == "first"
    assert (
        asyncio.run(workflows.resolve_execution_llm({"clientId": "a"}))["llm_config_id"] == "second"
    )
    assert (
        asyncio.run(
            workflows.resolve_execution_llm({"clientId": "a", "llm_config_id": "explicit"})
        )["llm_config_id"]
        == "explicit"
    )
    with pytest.raises(Exception, match="任务业务与目标图空间不一致"):
        asyncio.run(workflows.resolve_execution_llm({"clientId": "b"}))


def test_env_snapshot_keeps_endpoint_and_model_without_secret(monkeypatch):
    from service import temporal_workflows as workflows

    monkeypatch.setattr("service.business_access_control.rbac_enabled", lambda: False)
    monkeypatch.setattr("infra.mysql.session_scope", lambda: nullcontext(object()))
    monkeypatch.setattr("service.llm_defaults.resolve_default_config", lambda *args, **kw: None)
    monkeypatch.setattr("service.script_watermark.read_watermark", lambda *args: None)
    monkeypatch.setenv("LLM_API_KEY", "secret")
    monkeypatch.setenv("LLM_MODEL", "old-model")
    monkeypatch.setenv("LLM_BASE_URL", "http://old")
    pinned = asyncio.run(workflows.resolve_execution_llm({"_llm_env": {"model": "injected"}}))
    assert "secret" not in str(pinned)
    monkeypatch.setenv("LLM_MODEL", "new-model")
    monkeypatch.setenv("LLM_BASE_URL", "http://new")
    assert workflows._resolve_resources(pinned, None, "step")["llm"] == {
        "api_key": "secret",
        "model": "old-model",
        "base_url": "http://old",
    }
    monkeypatch.delenv("LLM_API_KEY")
    monkeypatch.delenv("ZHIPUAI_API_KEY", raising=False)
    with pytest.raises(ValueError, match="凭据已失效"):
        workflows._resolve_resources(pinned, None, "step")


def test_new_workflow_resolves_once_before_chain_dispatch(monkeypatch):
    from service import temporal_workflows as workflows

    monkeypatch.setattr(workflows.workflow, "patched", lambda name: True)
    calls = []

    async def activity(fn, request, **kwargs):
        calls.append(fn)
        return {"llm_config_id": "pinned", "_llm_business_id": "a", "_llm_env": None}

    async def chain(request, ids):
        assert request["llm_config_id"] == "pinned"
        return {"ok": True}

    monkeypatch.setattr(workflows, "_execute_activity", activity)
    instance = workflows.SchemaExtractWorkflow()
    monkeypatch.setattr(instance, "_run_chain", chain)
    assert asyncio.run(instance._run_dispatch({"schemaIds": ["s1", "s2"]})) == {"ok": True}
    assert calls == [workflows.resolve_execution_llm]


def test_old_workflow_history_keeps_explicit_selection_without_new_activity(monkeypatch):
    from service import temporal_workflows as workflows

    monkeypatch.setattr(workflows.workflow, "patched", lambda name: False)

    async def single(request, schema_id):
        assert request["llm_config_id"] == "old-explicit"
        return {"ok": True}

    instance = workflows.SchemaExtractWorkflow()
    monkeypatch.setattr(instance, "_run_single", single)
    assert asyncio.run(
        instance._run_dispatch({"schemaId": "s1", "llm_config_id": "old-explicit"})
    ) == {"ok": True}


@pytest.mark.parametrize("business", ["a", "b"])
def test_script_verification_executor_uses_authorized_schema_business(monkeypatch, business):
    from fastapi import UploadFile

    from biz.handler import schema_management as handler
    from infra.llm import get_llm_client
    from service.llm_context import request_llm_settings, selected_llm_business

    monkeypatch.setattr(
        handler, "_schema_access", lambda *args: SimpleNamespace(graph_space="space")
    )

    def business_for_schema(actor, space):
        assert space == "space"
        return business

    monkeypatch.setattr("service.llm_context.request_llm_business", business_for_schema)
    monkeypatch.setattr(
        "service.llm_config.resolve_llm_settings",
        lambda business_id=None: ("key", "http://models", business_id or "public"),
    )
    monkeypatch.setattr("infra.llm.LLMClient", lambda **kwargs: SimpleNamespace(**kwargs))
    observed = []

    def verify(**kwargs):
        observed.append(get_llm_client().model)
        yield {"type": "success"}

    monkeypatch.setattr(
        handler, "_application", lambda session: SimpleNamespace(verify_and_save_script=verify)
    )

    async def execute():
        response = await handler.verify_and_save_script(
            "schema",
            SimpleNamespace(user_id="u", is_admin=True),
            object(),
            UploadFile(filename="x.py", file=io.BytesIO(b"pass")),
        )
        chunks = [chunk async for chunk in response.body_iterator]
        assert b"success" in b"".join(chunks)
        assert await asyncio.get_running_loop().run_in_executor(
            None, lambda: (selected_llm_business.get(), request_llm_settings.get())
        ) == (None, None)

    asyncio.run(execute())
    assert observed == [business]
