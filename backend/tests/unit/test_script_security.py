"""service.script_security 单元测试（CI 跑，无真实 LLM）。"""

from __future__ import annotations

from service.script_security import ScriptSecurityVerdict, review_script_security


class _FakeLLM:
    def __init__(self, response: str | None) -> None:
        self._response = response
        self.calls: list[tuple[str, int]] = []

    def synthesize(self, prompt: str, max_tokens: int = 2048) -> str | None:
        self.calls.append((prompt, max_tokens))
        return self._response


def test_review_safe() -> None:
    client = _FakeLLM('{"safe": true, "issues": [], "summary": "安全"}')
    verdict = review_script_security(client, "transform.py", "def transform(row):\n    return row\n")
    assert isinstance(verdict, ScriptSecurityVerdict)
    assert verdict.safe is True
    assert verdict.issues == []
    assert verdict.summary == "安全"
    assert client.calls and client.calls[0][1] == 1024


def test_review_unsafe() -> None:
    client = _FakeLLM(
        '{"safe": false, "issues": ["使用 os.system", "读取 os.environ"], "summary": "危险脚本"}'
    )
    verdict = review_script_security(client, "evil.py", "import os\nos.system('rm -rf /')\n")
    assert verdict.safe is False
    assert verdict.issues == ["使用 os.system", "读取 os.environ"]
    assert verdict.summary == "危险脚本"


def test_review_llm_none() -> None:
    client = _FakeLLM(None)
    verdict = review_script_security(client, "transform.py", "def transform(row):\n    return row\n")
    assert verdict.safe is False
    assert any("LLM 调用失败" in i for i in verdict.issues)
    assert verdict.summary == "LLM 调用失败"


def test_review_malformed_non_json() -> None:
    client = _FakeLLM("这不是 JSON")
    verdict = review_script_security(client, "transform.py", "x = 1\n")
    assert verdict.safe is False
    assert any("格式异常" in i for i in verdict.issues)


def test_review_malformed_missing_safe_field() -> None:
    client = _FakeLLM('{"issues": [], "summary": "ok"}')
    verdict = review_script_security(client, "transform.py", "x = 1\n")
    assert verdict.safe is False
    assert any("格式异常" in i for i in verdict.issues)


def test_review_strips_code_fence() -> None:
    client = _FakeLLM('```json\n{"safe": true, "issues": [], "summary": "ok"}\n```')
    verdict = review_script_security(client, "transform.py", "x = 1\n")
    assert verdict.safe is True
    assert verdict.summary == "ok"


def test_review_normalizes_bad_issues_field() -> None:
    client = _FakeLLM('{"safe": true, "issues": "not a list", "summary": 123}')
    verdict = review_script_security(client, "transform.py", "x = 1\n")
    assert verdict.safe is True
    assert verdict.issues == []
    assert verdict.summary == ""
