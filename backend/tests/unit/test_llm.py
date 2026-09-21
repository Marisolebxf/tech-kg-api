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


class _FakeEmbeddingItem:
    def __init__(self, index: int, embedding: list[float]) -> None:
        self.index = index
        self.embedding = embedding


class _FakeEmbeddingResponse:
    def __init__(self, texts: list[str]) -> None:
        self.data = [_FakeEmbeddingItem(i, [float(len(text))]) for i, text in enumerate(texts)]


class _MaxBatchGuardAPI:
    """模拟 m3e 服务：单次 input 超过上限直接抛错。"""

    def __init__(self, max_batch: int, fail_on_call: int | None = None) -> None:
        self.max_batch = max_batch
        self.fail_on_call = fail_on_call
        self.calls: list[int] = []
        self._call_no = 0

    def embeddings_create(self, *, model: str, input: list[str], **kwargs):  # noqa: A002
        self._call_no += 1
        if self.fail_on_call == self._call_no:
            raise RuntimeError("boom")
        self.calls.append(len(input))
        if not input or len(input) > self.max_batch:
            raise ValueError("input数量必须在1到M3E_MAX_BATCH_SIZE之间")
        return _FakeEmbeddingResponse(input)


def _guard_client(api: _MaxBatchGuardAPI) -> llm_mod.EmbeddingClient:
    client = llm_mod.EmbeddingClient(api_key="local-no-auth", base_url="http://x", model="m3e")
    fake = MagicMock()
    fake.embeddings.create.side_effect = api.embeddings_create
    client._client = fake
    return client


def test_embed_chunks_requests_to_service_limit(monkeypatch):
    monkeypatch.setattr(llm_mod, "EMBEDDING_REQUEST_BATCH_SIZE", 64)
    api = _MaxBatchGuardAPI(max_batch=64)
    client = _guard_client(api)
    vectors = client.embed([f"文本{i}" for i in range(150)])
    assert api.calls == [64, 64, 22]
    assert vectors is not None and len(vectors) == 150
    # 顺序保持：第 i 条文本的向量 = [len(文本 i 的字符串长度)]
    assert vectors[0] == [float(len("文本0"))]
    assert vectors[149] == [float(len("文本149"))]


def test_embed_empty_input_returns_empty_list():
    client = llm_mod.EmbeddingClient(api_key="fake", base_url="http://x", model="m")
    client._client = MagicMock()
    assert client.embed([]) == []
    client._client.embeddings.create.assert_not_called()


def test_embed_returns_none_when_any_chunk_fails(monkeypatch):
    monkeypatch.setattr(llm_mod, "EMBEDDING_REQUEST_BATCH_SIZE", 64)
    api = _MaxBatchGuardAPI(max_batch=64, fail_on_call=2)
    client = _guard_client(api)
    assert client.embed([f"文本{i}" for i in range(100)]) is None
    assert api.calls == [64]  # 第二片失败后不再请求，也不返回半批结果


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
