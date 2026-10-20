"""classify_llm_error 错误分类单测（CI 跑，无真实 LLM）。"""

from __future__ import annotations

import httpx

from infra.llm import classify_llm_error


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
