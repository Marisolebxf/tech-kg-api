from __future__ import annotations

from unittest.mock import MagicMock

import infra.llm as llm_mod


def test_get_llm_client_returns_none_without_key(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("ZHIPUAI_API_KEY", raising=False)
    monkeypatch.setattr(llm_mod, "_resolve_settings", lambda: None)
    llm_mod.reset_llm_client()
    assert llm_mod.get_llm_client() is None


def test_get_llm_client_caches_singleton(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "fake-key")
    llm_mod.reset_llm_client()
    c1 = llm_mod.get_llm_client()
    c2 = llm_mod.get_llm_client()
    assert c1 is c2
    llm_mod.reset_llm_client()


def test_synthesize_returns_none_on_exception(monkeypatch):
    client = llm_mod.LLMClient(api_key="fake", base_url="http://x", model="m")
    client._client = MagicMock()
    client._client.chat.completions.create.side_effect = RuntimeError("boom")
    assert client.synthesize("hi") is None


def test_synthesize_json_prefers_json_schema(monkeypatch):
    client = llm_mod.LLMClient(api_key="fake", base_url="http://x", model="m")
    mock_api = MagicMock()
    mock_api.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content='{"items":[]}'))]
    )
    client._client = mock_api
    schema = {"type": "object", "properties": {"items": {"type": "array"}}, "required": ["items"]}
    out = client.synthesize_json("hi", schema=schema, schema_name="demo")
    assert out == '{"items":[]}'
    kwargs = mock_api.chat.completions.create.call_args.kwargs
    assert kwargs["response_format"]["type"] == "json_schema"
    assert kwargs["response_format"]["json_schema"]["name"] == "demo"


def test_synthesize_json_falls_back_to_json_object():
    client = llm_mod.LLMClient(api_key="fake", base_url="http://x", model="m")
    mock_api = MagicMock()

    def _create(**kwargs):
        rf = kwargs.get("response_format") or {}
        if rf.get("type") == "json_schema":
            raise RuntimeError("schema unsupported")
        return MagicMock(choices=[MagicMock(message=MagicMock(content='{"ok":true}'))])

    mock_api.chat.completions.create.side_effect = _create
    client._client = mock_api
    out = client.synthesize_json("hi", schema={"type": "object"}, schema_name="demo")
    assert out == '{"ok":true}'
    assert mock_api.chat.completions.create.call_count >= 2


def test_synthesize_json_respects_modes_and_timeout():
    client = llm_mod.LLMClient(api_key="fake", base_url="http://x", model="m")
    mock_api = MagicMock()
    mock_api.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content='{"ok":true}'))]
    )
    client._client = mock_api
    out = client.synthesize_json(
        "hi",
        schema={"type": "object"},
        schema_name="demo",
        modes=("json_object",),
        timeout=12.5,
    )
    assert out == '{"ok":true}'
    assert mock_api.chat.completions.create.call_count == 1
    kwargs = mock_api.chat.completions.create.call_args.kwargs
    assert kwargs["response_format"]["type"] == "json_object"
    assert kwargs["timeout"] == 12.5
