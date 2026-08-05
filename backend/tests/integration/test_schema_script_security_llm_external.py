from __future__ import annotations

import os
from pathlib import Path

import pytest

from infra.llm import reset_llm_client
from service.schema_script_security import review_script_with_llm

RUN_REAL_LLM = os.getenv("RUN_REAL_LLM_TESTS", "").lower() == "true"
HAS_LLM_KEY = bool(os.getenv("LLM_API_KEY") or os.getenv("ZHIPUAI_API_KEY"))
UNSAFE_SCRIPT = Path(__file__).parents[1] / "fixtures" / "unsafe_schema_script.py"


@pytest.mark.external
@pytest.mark.skipif(
    os.getenv("CI", "").lower() == "true" or not RUN_REAL_LLM or not HAS_LLM_KEY,
    reason="仅在本地显式启用真实 LLM 安全校验测试",
)
def test_real_llm_distinguishes_safe_and_risky_schema_scripts() -> None:
    reset_llm_client()
    safe = review_script_with_llm(
        "def transform(row):\n    return {'name': str(row.get('name', '')).strip()}\n",
        "safe_transform.py",
    )
    risky = review_script_with_llm(
        UNSAFE_SCRIPT.read_text(encoding="utf-8"),
        UNSAFE_SCRIPT.name,
    )
    assert safe.safe is True, safe.summary
    assert risky.safe is False, risky.summary
    assert risky.issues
