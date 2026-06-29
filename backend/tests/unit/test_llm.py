from __future__ import annotations

from unittest.mock import MagicMock

import infra.llm as llm_mod


def test_get_llm_client_returns_none_without_key(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("ZHIPUAI_API_KEY", raising=False)
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
