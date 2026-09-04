from __future__ import annotations

import pytest
from pydantic import ValidationError

from biz.schemas.llm_config import LlmConfigCreate, LlmConfigUpdate


def valid_create_payload() -> dict[str, object]:
    return {
        "name": "主模型",
        "description": "用于知识抽取",
        "baseUrl": "https://llm.example.internal/v1",
        "apiKey": "secret-token_123",
        "model": "glm-test",
        "owner": "平台组",
        "isDefault": True,
        "status": "正常",
    }


def test_llm_config_create_validates_and_normalizes_all_text_fields():
    config = LlmConfigCreate.model_validate(valid_create_payload())

    assert config.name == "主模型"
    assert config.base_url == "https://llm.example.internal/v1"
    assert config.api_key == "secret-token_123"
    assert config.is_default is True


def test_llm_config_update_accepts_explicit_null_optional_fields():
    config = LlmConfigUpdate.model_validate(
        {
            "name": None,
            "description": None,
            "baseUrl": None,
            "apiKey": None,
            "model": None,
            "owner": None,
        }
    )

    assert config.model_dump(exclude_unset=True) == {
        "name": None,
        "description": None,
        "base_url": None,
        "api_key": None,
        "model": None,
        "owner": None,
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("name", "<script>"),
        ("description", "bad\x00text"),
        ("baseUrl", "javascript:alert(1)"),
        ("apiKey", "token with spaces"),
        ("model", "<bad-model>"),
        ("owner", "<admin>"),
    ],
)
def test_llm_config_create_rejects_unsafe_text(field: str, value: str):
    payload = valid_create_payload()
    payload[field] = value

    with pytest.raises(ValidationError):
        LlmConfigCreate.model_validate(payload)


def test_llm_config_update_runs_validators_for_present_values():
    config = LlmConfigUpdate.model_validate(
        {
            "name": "备用模型",
            "description": "容灾配置",
            "baseUrl": "https://backup.example.internal/v1",
            "apiKey": "backup-token_456",
            "model": "glm-backup",
            "owner": "运维组",
        }
    )

    assert config.name == "备用模型"
    assert config.base_url.startswith("https://")
    assert config.api_key == "backup-token_456"
