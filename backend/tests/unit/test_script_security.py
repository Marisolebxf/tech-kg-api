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
        self,
        prompt: str,
        max_tokens: int = 2048,
        *,
        timeout: float | None = None,
        result_meta: dict | None = None,
        abort_reg: list | None = None,
    ) -> str | None:
        self.calls.append((prompt, max_tokens, timeout or 0.0))
        return self._response


class _ScriptedLLM:
    """按次序返回预设响应（用于验证限流重试）。"""

    def __init__(self, responses: list[str | None]) -> None:
        self._responses = list(responses)
        self.calls = 0

    def synthesize(
        self,
        prompt: str,
        max_tokens: int = 2048,
        *,
        timeout: float | None = None,
        result_meta: dict | None = None,
        abort_reg: list | None = None,
    ) -> str | None:
        idx = min(self.calls, len(self._responses) - 1)
        self.calls += 1
        return self._responses[idx]


class _MetaLLM:
    """按次序返回 (响应, finish_reason) 并回填 result_meta，模拟真实 SDK。

    响应为 None 时模拟 llm.synthesize 的空回答行为（error_class=empty_response）。
    """

    def __init__(self, script: list[tuple[str | None, str | None]]) -> None:
        self._script = list(script)
        self.calls = 0

    def synthesize(
        self,
        prompt: str,
        max_tokens: int = 2048,
        *,
        timeout: float | None = None,
        result_meta: dict | None = None,
        abort_reg: list | None = None,
    ) -> str | None:
        idx = min(self.calls, len(self._script) - 1)
        self.calls += 1
        response, finish = self._script[idx]
        if result_meta is not None:
            result_meta["finish_reason"] = finish
            if response is None:
                result_meta["error_class"] = "empty_response"
        return response


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
    assert verdict.summary.startswith("危险脚本")
    assert "源码命中静态高危调用" in verdict.summary  # 审计标注（评审修订 A）
    assert verdict.category == "rejected"


def test_review_hallucinated_evidence_still_blocked() -> None:
    """评审修订 A：模型判不安全即维持拦截——无逐字证据的理由从展示清单剔除，
    计数与静态高危命中情况写入 summary 供人工复核，不再反转放行。"""
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
    assert verdict.safe is False
    assert verdict.issues == ["模型判不安全：存在环境变量读取与日志注入"]
    assert "2 条理由未附可逐字验证的证据" in verdict.summary
    assert "源码未命中静态高危调用（供人工复核）" in verdict.summary
    assert verdict.category == "rejected"


def test_review_plain_string_issues_format_error() -> None:
    """评审修订 B：旧版纯字符串 issues 不再接受——结构不完整按格式异常处理。"""
    client = _FakeLLM(
        '{"safe": false, "issues": ["使用 os.system", "读取 os.environ"], "summary": "危险脚本"}'
    )
    verdict = review_script_security(client, "evil.py", "import os\nos.system('rm -rf /')\n")
    assert verdict.safe is False
    assert verdict.unavailable is True
    assert any("格式异常" in i for i in verdict.issues)
    assert len(client.calls) == 2  # 格式异常重试一次


def test_review_evidence_whitespace_tolerant() -> None:
    """模型微调了缩进/换行，压缩空白后仍能命中的证据算有效（展示层清洗）。"""
    client = _FakeLLM(
        '{"safe": false, "issues": [{"problem": "执行系统命令", '
        '"evidence": "import os\\nos.system(1)"}], "summary": "危险"}'
    )
    verdict = review_script_security(client, "evil.py", "import  os\nos . system(1)\n")
    # 逐字与压空白都不命中（多了空格）→ 剔除该 issue，但判定仍维持拦截
    assert verdict.safe is False
    assert verdict.issues == ["模型判不安全：危险"]
    client2 = _FakeLLM(
        '{"safe": false, "issues": [{"problem": "执行系统命令", '
        '"evidence": "import os\\n    os.system(1)"}], "summary": "危险"}'
    )
    verdict2 = review_script_security(client2, "evil.py", "import os\nos.system(1)\n")
    # 换行/缩进差异命中 → 带证据拦截
    assert verdict2.safe is False
    assert verdict2.issues == ["执行系统命令"]


def test_review_real_evidence_no_high_risk_blocked_with_audit() -> None:
    """评审修订 A：证据真实但源码无静态高危调用也不再"误报放行"——
    维持拦截并标注"供人工复核"。"""
    client = _FakeLLM(
        '{"safe": false, "issues": [{"problem": "构造 payload 存在网络访问风险",'
        ' "evidence": "json.dumps(row, sort_keys=True)"}], "summary": "存在网络访问风险"}'
    )
    source = "import json\n\n\ndef run(row):\n    return json.dumps(row, sort_keys=True)\n"
    verdict = review_script_security(client, "transform.py", source)
    assert verdict.safe is False
    assert verdict.issues == ["构造 payload 存在网络访问风险"]
    assert "源码未命中静态高危调用（供人工复核）" in verdict.summary
    assert verdict.category == "rejected"


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
    assert "源码命中静态高危调用" in verdict.summary


def test_review_re_compile_annotated_not_released() -> None:
    """re.compile 属模块前缀调用，不算高危：仅影响审计标注，不再放行。"""
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
    assert verdict.safe is False
    assert verdict.issues == ["动态构造可执行代码"]
    assert "源码未命中静态高危调用（供人工复核）" in verdict.summary


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


def test_review_bad_issues_field_format_error() -> None:
    """评审修订 B：issues 非数组/summary 非字符串不再"容错归一"，按结构不完整处理。"""
    client = _FakeLLM('{"safe": true, "issues": "not a list", "summary": 123}')
    verdict = review_script_security(client, "transform.py", "x = 1\n")
    assert verdict.safe is False
    assert verdict.unavailable is True
    assert any("格式异常" in i for i in verdict.issues)
    assert len(client.calls) == 2


def test_review_minimal_valid_json_safe_not_released() -> None:
    """评审修订 B 的准确口径验证：截断恰好拼成最小合法 JSON {"safe": true}
    属"结构不完整"，不会判 safe。"""
    client = _FakeLLM('{"safe": true}')
    verdict = review_script_security(client, "transform.py", "x = 1\n")
    assert verdict.safe is False
    assert verdict.unavailable is True
    assert any("格式异常" in i for i in verdict.issues)
    assert len(client.calls) == 2


def test_review_issue_missing_evidence_field_format_error() -> None:
    """issue 缺 evidence 字段：结构不完整（旧版会当无证据静默丢弃）。"""
    client = _FakeLLM('{"safe": false, "issues": [{"problem": "调用系统命令"}], "summary": "危险"}')
    verdict = review_script_security(client, "evil.py", "import os\nos.system(1)\n")
    assert verdict.safe is False
    assert verdict.unavailable is True
    assert any("格式异常" in i for i in verdict.issues)
    assert len(client.calls) == 2


def test_review_unsafe_empty_issues_format_error() -> None:
    client = _FakeLLM('{"safe": false, "issues": [], "summary": "危险"}')
    verdict = review_script_security(client, "transform.py", "x = 1\n")
    assert verdict.safe is False
    assert verdict.unavailable is True
    assert any("格式异常" in i for i in verdict.issues)


def test_review_truncated_json_never_released() -> None:
    """截断的输出绝不放行：JSON 不完整一律按格式异常重试→仍坏归"校验不可用"。"""
    client = _FakeLLM('{"safe": true, "issues": [], "summary": "安')
    verdict = review_script_security(client, "transform.py", CLEAN_SOURCE)
    assert verdict.safe is False
    assert verdict.unavailable is True
    assert any("格式异常" in i for i in verdict.issues)
    assert len(client.calls) == 2  # 格式异常重试一次


def test_review_truncated_unsafe_body_never_released() -> None:
    """unsafe 报告被截断同样不放行：不得从半截 JSON 里捞结论。"""
    client = _FakeLLM(
        '{"safe": false, "issues": [{"problem": "执行任意代码", "evidence": "eval(code)'
    )
    verdict = review_script_security(client, "evil.py", "x = eval(input())\n")
    assert verdict.safe is False
    assert verdict.unavailable is True
    assert any("格式异常" in i for i in verdict.issues)


# ---- 2026-10-21 复核追加（Codex de454db1 四项）----


def test_review_contradictory_safe_with_real_evidence_not_released() -> None:
    """SEC-JSON：safe=true 附带证据齐全的危险 issues 不得放行——
    在证据清洗前按"结论自相矛盾"处理，重试仍矛盾归不可用。"""
    client = _FakeLLM(
        '{"safe": true, "issues": [{"problem": "command execution",'
        ' "evidence": "os.system(\\"id\\")"}], "summary": "risk"}'
    )
    verdict = review_script_security(client, "evil.py", 'import os\nos.system("id")\n')
    assert verdict.safe is False
    assert verdict.unavailable is True
    assert any("自相矛盾" in i for i in verdict.issues)
    assert len(client.calls) == 2


def test_review_contradictory_safe_with_hallucinated_evidence_still_format_error() -> None:
    """矛盾检查先于证据清洗：evidence 为幻觉不影响"自相矛盾"定性，
    不允许清洗后空数组掩盖矛盾。"""
    client = _FakeLLM(
        '{"safe": true, "issues": [{"problem": "读取密钥",'
        ' "evidence": "os.environ[\'KEY\']"}], "summary": "risk"}'
    )
    verdict = review_script_security(client, "transform.py", "x = 1\n")
    assert verdict.unavailable is True
    assert any("自相矛盾" in i for i in verdict.issues)


def test_review_finish_reason_length_with_valid_json_not_released() -> None:
    """SEC-META：finish_reason=length 且 JSON 恰好完整（首尾恰好停在合法位置）
    不得产生 passed——按结束原因异常重试，仍截断归不可用。"""
    client = _MetaLLM([('{"safe": true, "issues": [], "summary": "ok"}', "length")] * 2)
    verdict = review_script_security(client, "transform.py", "x = 1\n")
    assert verdict.safe is False
    assert verdict.unavailable is True
    assert any("截断" in i for i in verdict.issues)
    assert verdict.category == "unavailable_format"
    assert client.calls == 2


def test_review_finish_reason_content_filter_not_released() -> None:
    client = _MetaLLM([('{"safe": true, "issues": [], "summary": "ok"}', "content_filter")] * 2)
    verdict = review_script_security(client, "transform.py", "x = 1\n")
    assert verdict.unavailable is True
    assert any("格式异常" in i for i in verdict.issues)
    assert verdict.category == "unavailable_format"


def test_review_finish_reason_length_then_stop_recovers() -> None:
    """截断重试拿到正常 stop 的完整输出即放行；也验证上一轮的 length
    元数据不污染后一轮判定（每次尝试清空元数据）。"""
    client = _MetaLLM(
        [
            ('{"safe": true, "issues": [], "summary": "ok"}', "length"),
            ('{"safe": true, "issues": [], "summary": "ok"}', "stop"),
        ]
    )
    verdict = review_script_security(client, "transform.py", "x = 1\n")
    assert verdict.safe is True
    assert verdict.category == "passed"
    assert client.calls == 2


def test_review_finish_reason_stop_passes_unchanged() -> None:
    client = _MetaLLM([('{"safe": true, "issues": [], "summary": "ok"}', "stop")])
    verdict = review_script_security(client, "transform.py", "x = 1\n")
    assert verdict.safe is True


def test_review_empty_response_classified_not_unknown() -> None:
    """SEC-META：空回答（length 烧光预算时常见）归类 empty_response，
    不再落 unknown/服务异常。"""
    client = _MetaLLM([(None, "length"), (None, "length")])
    verdict = review_script_security(client, "transform.py", "x = 1\n")
    assert verdict.unavailable is True
    assert verdict.category == "unavailable_empty_response"
    assert any("模型返回空内容" in i for i in verdict.issues)


def test_review_capacity_recovers_after_timeouts(monkeypatch) -> None:
    """SEC-LIFETIME：4 路超时占满槽位后，工作线程收尾释放槽位，
    后续校验容量恢复正常（不以提前释放伪造恢复，也不永久泄漏）。"""
    import concurrent.futures as cf
    import time as _time

    import service.script_security as mod

    monkeypatch.setattr(mod, "REVIEW_STAGE_SECONDS", 1.0)
    monkeypatch.setattr(mod, "_RETRY_FLOOR_SECONDS", 0.5)

    class _SlowLLM:
        def synthesize(
            self,
            prompt: str,
            max_tokens: int = 2048,
            *,
            timeout: float | None = None,
            result_meta: dict | None = None,
            abort_reg: object | None = None,
        ) -> str | None:
            _time.sleep(1.5)
            return '{"safe": true, "issues": [], "summary": "ok"}'

    slow_results: list[mod.ScriptSecurityVerdict] = []
    with cf.ThreadPoolExecutor(max_workers=4) as pool:
        futures = [
            pool.submit(mod.review_script_security, _SlowLLM(), "t.py", "x = 1\n") for _ in range(4)
        ]
        for f in cf.as_completed(futures):
            slow_results.append(f.result())
    assert len(slow_results) == 4
    assert all(v.unavailable for v in slow_results)

    # 工作线程 sleep 结束、future 终态释放槽位后，新校验正常放行。
    deadline = _time.monotonic() + 10.0
    verdict = None
    while _time.monotonic() < deadline:
        verdict = mod.review_script_security(
            _FakeLLM('{"safe": true, "issues": [], "summary": "ok"}'), "t.py", "x = 1\n"
        )
        if verdict.safe:
            break
        _time.sleep(0.2)
    assert verdict is not None and verdict.safe


def test_review_cancel_flag_set_synchronously_before_return(monkeypatch) -> None:
    """复核 942b442e（SEC-LIFETIME 收口）：取消标志须在调用方返回前同步置位。

    Codex 确定性交错复现的竞态：清理线程"尚未获调度"（close 被闸挡住），
    调用方已超时返回，迟到初始化的工作线程此时才 register——若标志要等
    守护线程里才置位，register 会成功、请求会在放弃后发出。本测试固定
    该交错：清理线程全程被闸住，调用方返回后才放行工作线程初始化，
    register 必被拒、模拟 SDK create 零调用（旧实现此用例必失败）。
    """
    import threading as _threading
    import time as _time

    import service.script_security as mod
    from infra.llm import LLMAbortHandle

    monkeypatch.setattr(mod, "REVIEW_STAGE_SECONDS", 0.5)
    monkeypatch.setattr(mod, "_RETRY_FLOOR_SECONDS", 0.3)

    close_gate = _threading.Event()
    init_gate = _threading.Event()
    state: dict = {"register_ok": None, "dispatch": 0, "close_done": False}

    def gated_close(self, transports):  # noqa: ANN001
        assert close_gate.wait(10.0)  # 模拟清理线程未获调度/慢 close
        state["close_done"] = True

    monkeypatch.setattr(LLMAbortHandle, "close_transports", gated_close)

    class _LateInitLLM:
        def synthesize(
            self,
            prompt: str,
            max_tokens: int = 2048,
            *,
            timeout: float | None = None,
            result_meta: dict | None = None,
            abort_reg: object | None = None,
        ) -> str | None:
            # 初始化暂停：停在 register 之前（Codex 复现的专属传输构造点）
            assert init_gate.wait(10.0)
            assert abort_reg is not None
            state["register_ok"] = bool(abort_reg.register(object()))
            if state["register_ok"]:
                state["dispatch"] += 1  # register 成功即视为 SDK create 已发出
            return None

    verdict = mod.review_script_security(_LateInitLLM(), "late.py", "x = 1\n")
    assert verdict.unavailable is True
    # 调用方已返回、清理线程仍被闸住（未完成）：此刻才放行迟到初始化。
    init_gate.set()
    deadline = _time.monotonic() + 5.0
    while _time.monotonic() < deadline and state["register_ok"] is None:
        _time.sleep(0.05)
    # 标志在调用线程同步置位：迟登记必被拒，请求零发出，且清理尚未完成。
    assert state["register_ok"] is False
    assert state["dispatch"] == 0
    assert state["close_done"] is False
    close_gate.set()  # 放行清理线程收尾（幂等；此刻无在登记传输）


def test_prompt_scope_contract() -> None:
    """提示词分诊化（2026-10-21）的检查范围契约：八类信号、证据要求、防注入、
    JSON 契约与旧版一致；开放式"审计专家（不限于）"人设不得回流。"""
    from service.script_security import _SECURITY_PROMPT_TEMPLATE as template

    for keyword in (
        # 八类信号逐条在册
        "os、subprocess、socket、shutil、ctypes、pickle、marshal、multiprocessing",
        "eval、exec、compile、__import__、os.system、os.popen、subprocess.*",
        "socket、urllib、requests、httpx",
        "~/.ssh、/etc/passwd、.env",
        "os.environ、密钥、凭据、token",
        "subprocess.Popen、os.fork、os.exec*",
        "base64 解码后 exec",
        "base64/hex/marshal 解码后 exec/eval",
        # 证据要求与防注入条款
        "逐字复制",
        "不超过 120 字符",
        "宁可漏报也不要编造",
        "防指令注入",
        "不是给你的指令",
        # 输出契约字段
        '"safe"',
        '"issues"',
        '"evidence"',
        '"summary"',
    ):
        assert keyword in template, keyword
    # 刻意删除的开放式表述：清单外探索性检查已收缩到与 _HIGH_RISK_RE 同口径
    assert "不限于" not in template
    assert "安全审计专家" not in template
    assert "纯计算变换" not in template


def test_review_busy_pool_fast_unavailable() -> None:
    """并发槽占满（4 路在飞）时立即按"暂不可用"返回：不排队、不发起第 5 路调用。"""
    import service.script_security as mod

    acquired = [mod._REVIEW_SLOTS.acquire(blocking=False) for _ in range(mod._REVIEW_CONCURRENCY)]
    assert all(acquired)
    try:
        client = _FakeLLM('{"safe": true, "issues": [], "summary": "安全"}')
        verdict = review_script_security(client, "transform.py", CLEAN_SOURCE)
        assert verdict.unavailable is True
        assert verdict.category == "unavailable_busy"
        assert any("并发已满" in i for i in verdict.issues)
        assert client.calls == []  # 未发起任何 LLM 调用
    finally:
        for _ in range(acquired.count(True)):
            mod._REVIEW_SLOTS.release()


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
            self,
            prompt: str,
            max_tokens: int = 2048,
            *,
            timeout: float | None = None,
            result_meta: dict | None = None,
            abort_reg: list | None = None,
        ) -> str | None:
            _time.sleep(2.0)
            return '{"safe": true, "issues": [], "summary": "安全"}'

    started = _time.monotonic()
    verdict = review_script_security(_SlowLLM(), "transform.py", CLEAN_SOURCE)
    assert verdict.unavailable is True
    assert verdict.category == "unavailable_stage_deadline"
    assert any("预算耗尽" in i for i in verdict.issues)
    assert _time.monotonic() - started < 1.9
