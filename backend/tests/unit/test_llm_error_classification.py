"""infra.llm 错误分类与 synthesize 元数据/中止句柄单测（CI 跑，无真实 LLM）。"""

from __future__ import annotations

import types

import httpx

from infra.llm import LLMAbortHandle, LLMClient, classify_llm_error


class _FakeHTTPStatusError(Exception):
    def __init__(self, status_code: int, message: str = "") -> None:
        super().__init__(message or f"HTTP {status_code}")
        self.status_code = status_code


def test_timeout_exception_classified() -> None:
    assert classify_llm_error(httpx.TimeoutException("read timed out")) == "timeout"
    assert classify_llm_error(httpx.ReadTimeout("connection timed out")) == "timeout"


def test_insufficient_balance_by_text() -> None:
    # 智谱 1113（余额不足）经响应体文本识别——不是独立的异常类型。
    assert (
        classify_llm_error(Exception("Error code: 1113, 当前账户余额不足"))
        == "insufficient_balance"
    )
    assert classify_llm_error(RuntimeError("余额不足，请充值")) == "insufficient_balance"


def test_http_status_code_classified() -> None:
    assert classify_llm_error(_FakeHTTPStatusError(500)) == "http_500"
    assert classify_llm_error(_FakeHTTPStatusError(503, "service unavailable")) == "http_503"


def test_other_for_plain_exceptions() -> None:
    assert classify_llm_error(RuntimeError("boom")) == "other"
    assert classify_llm_error(ValueError("bad arg")) == "other"


# ---- synthesize 元数据与中止句柄（2026-10-21 复核 SEC-META / SEC-LIFETIME）----


class _StubCompletions:
    def __init__(self, resp: object) -> None:
        self._resp = resp
        self.calls = 0

    def create(self, **kwargs):  # noqa: ANN003
        self.calls += 1
        if isinstance(self._resp, Exception):
            raise self._resp
        return self._resp


def _resp(content: str | None, finish_reason: str, reasoning_tokens: int | None = 12) -> object:
    message = types.SimpleNamespace(content=content)
    choice = types.SimpleNamespace(message=message, finish_reason=finish_reason)
    usage = types.SimpleNamespace(
        completion_tokens_details=types.SimpleNamespace(reasoning_tokens=reasoning_tokens)
    )
    return types.SimpleNamespace(choices=[choice], usage=usage)


def _client_with(resp: object) -> tuple[LLMClient, _StubCompletions]:
    client = LLMClient(api_key="test-key")
    stub = _StubCompletions(resp)
    client._client = types.SimpleNamespace(  # noqa: SLF001 - 测试桩注入
        chat=types.SimpleNamespace(completions=stub)
    )
    return client, stub


def test_synthesize_meta_success_fields() -> None:
    client, stub = _client_with(_resp("hello", "stop"))
    meta: dict = {}
    out = client.synthesize("p", result_meta=meta)
    assert out == "hello"
    assert stub.calls == 1
    assert meta["finish_reason"] == "stop"
    assert meta["reasoning_tokens"] == 12
    assert "error_class" not in meta


def test_synthesize_empty_and_blank_content_classified() -> None:
    for content in (None, "", "   "):
        client, _ = _client_with(_resp(content, "length"))
        meta: dict = {}
        out = client.synthesize("p", result_meta=meta)
        assert out is None
        assert meta["error_class"] == "empty_response"
        assert meta["finish_reason"] == "length"


def test_synthesize_exception_classified_in_meta() -> None:
    client, _ = _client_with(_FakeHTTPStatusError(500))
    meta: dict = {}
    out = client.synthesize("p", result_meta=meta)
    assert out is None
    assert meta["error_class"] == "http_500"


def test_abort_handle_register_cancel_mutex() -> None:
    handle = LLMAbortHandle()
    first = httpx.Client()
    assert handle.register(first) is True
    handle.cancel()
    assert handle.cancelled is True
    assert handle.closed_count == 1
    # 取消后的迟登记被拒：登记方须自行关闭且不得再发请求。
    late = httpx.Client()
    assert handle.register(late) is False
    # 幂等：重复 cancel 不再计数、不再动新传输。
    handle.cancel()
    assert handle.closed_count == 1


def test_abort_handle_mark_cancelled_sync_flag_close_async() -> None:
    """复核 942b442e：置标志与关传输分离——标志同步生效（关没关都拒迟登记）。"""
    handle = LLMAbortHandle()
    first = httpx.Client()
    assert handle.register(first) is True
    pending = handle.mark_cancelled()
    # 标志已同步置位：即使 close_transports 尚未执行（守护线程未获调度），
    # 迟到的 register 也必被拒。
    assert handle.cancelled is True
    assert len(pending) == 1
    late = httpx.Client()
    assert handle.register(late) is False
    # 关闭是独立一步（生产路径放守护线程），之后幂等：再 mark 无新增。
    handle.close_transports(pending)
    assert handle.closed_count == 1
    assert handle.mark_cancelled() == []
    assert handle.closed_count == 1


def test_synthesize_aborted_before_request_never_calls_sdk() -> None:
    """迟登记竞态修复验证：handle 已取消（仅同步置标志，关闭未执行）时
    synthesize 直接放弃，不构造 OpenAI 客户端、不发起任何请求。"""
    client, stub = _client_with(_resp("hello", "stop"))
    handle = LLMAbortHandle()
    assert handle.mark_cancelled() == []  # 同步置标志；close_transports 不执行
    meta: dict = {}
    out = client.synthesize("p", timeout=5.0, result_meta=meta, abort_reg=handle)
    assert out is None
    assert meta["error_class"] == "aborted"
    assert stub.calls == 0
