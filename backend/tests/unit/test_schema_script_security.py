from __future__ import annotations

import json

from service.schema_script_security import review_script_with_llm, static_security_issues


class FakeLLM:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def synthesize(self, prompt: str, max_tokens: int = 2048) -> str:
        assert "BEGIN UNTRUSTED CODE" in prompt
        return json.dumps(self.payload, ensure_ascii=False)


def test_static_security_rejects_system_access() -> None:
    issues = static_security_issues(
        "import os\ndef transform(row):\n    os.system('id')\n    return row\n"
    )
    assert {item["category"] for item in issues} == {"dangerous_import", "system_access"}


def test_llm_security_review_parses_structured_result(monkeypatch) -> None:
    monkeypatch.setattr(
        "service.schema_script_security.get_llm_client",
        lambda: FakeLLM(
            {
                "safe": False,
                "summary": "检测到向外部端点发送数据",
                "issues": [
                    {
                        "severity": "high",
                        "category": "data_exfiltration",
                        "line": 3,
                        "message": "可能泄露输入数据",
                        "suggestion": "移除外部发送逻辑",
                    }
                ],
            }
        ),
    )
    result = review_script_with_llm("def transform(row):\n    return row\n", "safe.py")
    assert result.safe is False
    assert result.issues[0]["line"] == 3
    assert result.issues[0]["category"] == "data_exfiltration"
