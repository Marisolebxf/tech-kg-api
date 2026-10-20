"""service.script_security 单元测试（CI 跑，无真实 LLM）。"""

from __future__ import annotations

import json

from service.script_security import (
    REVIEW_MAX_TOKENS,
    REVIEW_STAGE_SECONDS,
    ScriptSecurityVerdict,
    review_script_security,
)


class _FakeLLM:
    def __init__(self, response: str | None) -> None:
        self._response = response
        self.calls: list[tuple[str, int, float]] = []

    def synthesize(
        self, prompt: str, max_tokens: int = 2048, *, timeout: float | None = None
    ) -> str | None:
        self.calls.append((prompt, max_tokens, timeout or 0.0))
        return self._response


class _ScriptedLLM:
    """按次序返回预设响应（用于验证限流重试）。"""

    def __init__(self, responses: list[str | None]) -> None:
        self._responses = list(responses)
        self.calls = 0

    def synthesize(
        self, prompt: str, max_tokens: int = 2048, *, timeout: float | None = None
    ) -> str | None:
        idx = min(self.calls, len(self._responses) - 1)
        self.calls += 1
        return self._responses[idx]


CLEAN_SOURCE = "from kg_sdk import step\n\n\n@step\ndef clean_row(payload):\n    return payload\n"


def test_review_safe() -> None:
    client = _FakeLLM('{"safe": true, "issues": [], "summary": "安全"}')
    verdict = review_script_security(client, "transform.py", CLEAN_SOURCE)
    assert isinstance(verdict, ScriptSecurityVerdict)
    assert verdict.safe is True
    assert verdict.issues == []
    assert verdict.summary == "安全"
    assert client.calls
    # 思考型模型预算（2026-10-20）：max_tokens 必须覆盖 reasoning，超时封顶低于
    # web nginx 60s（SSE 静默期上限）。首调用拿的是"剩余墙钟时间"=50−ε。
    assert client.calls[0][1] == REVIEW_MAX_TOKENS
    assert REVIEW_STAGE_SECONDS - 1 <= client.calls[0][2] <= REVIEW_STAGE_SECONDS


def test_review_unsafe_with_evidence_kept() -> None:
    client = _FakeLLM(
        '{"safe": false, "issues": [{"problem": "调用 os.system 执行系统命令",'
        ' "evidence": "os.system(\'rm -rf /\')"}], "summary": "危险脚本"}'
    )
    verdict = review_script_security(client, "evil.py", "import os\nos.system('rm -rf /')\n")
    assert verdict.safe is False
    assert verdict.issues == ["调用 os.system 执行系统命令"]
    assert verdict.summary == "危险脚本"


def test_review_hallucinated_evidence_released() -> None:
    """模型判不安全，但证据在源码中找不到 → 视为幻觉，放行并留审计说明。"""
    client = _FakeLLM(
        '{"safe": false, "issues": ['
        '{"problem": "读取敏感环境变量", "evidence": "os.environ[\'LLM_API_KEY\']"},'
        '{"problem": "异常块日志注入", "evidence": "repr(exc)"}],'
        ' "summary": "存在环境变量读取与日志注入"}'
    )
    verdict = review_script_security(
        client,
        "organization_entity_step.py",
        "import hashlib\nimport json\n\n\ndef run(row):\n    return row\n",
    )
    assert verdict.safe is True
    assert verdict.issues == []
    assert "无实证放行" in verdict.summary
    assert "日志注入" in verdict.summary  # 保留模型原判供审计


def test_review_plain_string_issues_released() -> None:
    """旧格式（无 evidence 的纯字符串理由）一律视为无实证 → 放行。"""
    client = _FakeLLM(
        '{"safe": false, "issues": ["使用 os.system", "读取 os.environ"], "summary": "危险脚本"}'
    )
    verdict = review_script_security(client, "evil.py", "import os\nos.system('rm -rf /')\n")
    assert verdict.safe is True
    assert verdict.issues == []
    assert "无实证放行" in verdict.summary


def test_review_evidence_whitespace_tolerant() -> None:
    """模型微调了缩进/换行，压缩空白后仍能命中的证据算有效。"""
    client = _FakeLLM(
        '{"safe": false, "issues": [{"problem": "执行系统命令", '
        '"evidence": "import os\\nos.system(1)"}], "summary": "危险"}'
    )
    verdict = review_script_security(client, "evil.py", "import  os\nos . system(1)\n")
    # 逐字与压空白都不命中（多了空格）→ 放行
    assert verdict.safe is True
    client2 = _FakeLLM(
        '{"safe": false, "issues": [{"problem": "执行系统命令", '
        '"evidence": "import os\\n    os.system(1)"}], "summary": "危险"}'
    )
    verdict2 = review_script_security(client2, "evil.py", "import os\nos.system(1)\n")
    # 换行/缩进差异命中 → 拦截
    assert verdict2.safe is False


def test_review_real_evidence_but_no_high_risk_released() -> None:
    """证据真实、但源码无任何静态高危调用 → 结论错误，按误报放行。"""
    client = _FakeLLM(
        '{"safe": false, "issues": [{"problem": "构造 payload 存在网络访问风险",'
        ' "evidence": "json.dumps(row, sort_keys=True)"}], "summary": "存在网络访问风险"}'
    )
    source = "import json\n\n\ndef run(row):\n    return json.dumps(row, sort_keys=True)\n"
    verdict = review_script_security(client, "transform.py", source)
    assert verdict.safe is True
    assert verdict.issues == []
    assert "误报放行" in verdict.summary
    assert "网络访问风险" in verdict.summary  # 保留模型原判供审计


def test_review_real_high_risk_still_blocked() -> None:
    """源码真有 subprocess 调用：带证据的不安全判定维持拦截。"""
    client = _FakeLLM(
        '{"safe": false, "issues": [{"problem": "派生子进程",'
        ' "evidence": "subprocess.run("}], "summary": "危险脚本"}'
    )
    source = "import subprocess\nsubprocess.run(['ls', '/'])\n"
    verdict = review_script_security(client, "evil.py", source)
    assert verdict.safe is False
    assert verdict.issues == ["派生子进程"]


def test_review_re_compile_not_high_risk() -> None:
    """re.compile 属模块前缀调用，不算高危：误报应放行。"""
    response = json.dumps(
        {
            "safe": False,
            "issues": [{"problem": "动态构造可执行代码", "evidence": 're.compile("ab+")'}],
            "summary": "代码注入风险",
        },
        ensure_ascii=False,
    )
    client = _FakeLLM(response)
    source = 'import re\n\n_SUFFIX_RE = re.compile("ab+")\n\n\ndef run(row):\n    return row\n'
    verdict = review_script_security(client, "transform.py", source)
    assert verdict.safe is True
    assert "误报放行" in verdict.summary


def test_review_duplicate_issues_deduped() -> None:
    """同一问题换措辞重复报：按 problem 原文去重（高危源码仍拦截）。"""
    client = _FakeLLM(
        '{"safe": false, "issues": ['
        '{"problem": "调用系统命令", "evidence": "os.system(1)"},'
        '{"problem": "调用系统命令", "evidence": "import os"}],'
        ' "summary": "危险"}'
    )
    verdict = review_script_security(client, "evil.py", "import os\nos.system(1)\n")
    assert verdict.safe is False
    assert verdict.issues == ["调用系统命令"]


def test_review_llm_none_marks_unavailable_after_retry() -> None:
    client = _FakeLLM(None)
    verdict = review_script_security(client, "transform.py", CLEAN_SOURCE)
    assert verdict.safe is False
    assert verdict.unavailable is True
    assert any("暂不可用" in i for i in verdict.issues)
    assert "不安全" not in (verdict.summary or "")
    assert client.calls
    assert len(client.calls) == 2  # 限流重试一次


def test_review_llm_none_then_success() -> None:
    client = _ScriptedLLM([None, '{"safe": true, "issues": [], "summary": "安全"}'])
    verdict = review_script_security(client, "transform.py", CLEAN_SOURCE)
    assert verdict.safe is True
    assert verdict.unavailable is False
    assert client.calls == 2


def test_review_format_error_retries_then_succeeds() -> None:
    """模型输出非约定 JSON：重试一次拿到合法结论，不判死（46 脚本实测 4 例）。"""
    client = _ScriptedLLM(["抱歉，我无法", '{"safe": true, "issues": [], "summary": "安全"}'])
    verdict = review_script_security(client, "transform.py", CLEAN_SOURCE)
    assert verdict.safe is True
    assert verdict.unavailable is False
    assert client.calls == 2


def test_review_format_error_twice_marks_unavailable() -> None:
    """连续两次输出损坏：按校验不可用处理（稍后重传），不当脚本不安全。"""
    client = _FakeLLM("!!!不是JSON!!!")
    verdict = review_script_security(client, "transform.py", CLEAN_SOURCE)
    assert verdict.safe is False
    assert verdict.unavailable is True
    assert any("格式异常" in i for i in verdict.issues)
    assert "不安全" not in (verdict.summary or "")
    assert len(client.calls) == 2  # 格式异常重试一次


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


def test_review_stage_wall_clock_bound(monkeypatch) -> None:
    """LLM 调用超过阶段墙钟预算时按"暂不可用"快速返回，不无限等待。

    httpx 的 read 超时按字节到达间隔计，思考型模型慢生成拦不住总时长，
    阶段封顶靠 future.result(timeout=) 硬顶（2026-10-20）。
    """
    import time as _time

    import service.script_security as mod

    monkeypatch.setattr(mod, "REVIEW_STAGE_SECONDS", 1.0)
    monkeypatch.setattr(mod, "_RETRY_FLOOR_SECONDS", 0.5)

    class _SlowLLM:
        def synthesize(
            self, prompt: str, max_tokens: int = 2048, *, timeout: float | None = None
        ) -> str | None:
            _time.sleep(2.0)
            return '{"safe": true, "issues": [], "summary": "安全"}'

    started = _time.monotonic()
    verdict = review_script_security(_SlowLLM(), "transform.py", CLEAN_SOURCE)
    assert verdict.unavailable is True
    assert _time.monotonic() - started < 1.9
