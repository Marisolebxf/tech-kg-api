from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

from script.patent_relation_workflow import workflow


def _fake_load(monkeypatch, result: Counter[str] | None = None) -> dict[str, Any]:
    """替换 load，记录调用 kwargs 并返回固定结果。"""
    captured: dict[str, Any] = {}

    def _fake(**kwargs: Any) -> Counter[str]:
        captured.update(kwargs)
        return result if result is not None else Counter({"INVENTED_BY:loaded": 2})

    monkeypatch.setattr("script.load_patent_relations.load", _fake)
    return captured


def test_workflow_returns_stats_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_load(monkeypatch, result=Counter({"INVENTED_BY:loaded": 4, "CITES:loaded": 7}))

    result = workflow({"apply": True})

    assert result["ok"] is True
    assert result["stats"] == {"INVENTED_BY:loaded": 4, "CITES:loaded": 7}


def test_workflow_forwards_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _fake_load(monkeypatch)

    workflow({})

    assert captured == {
        "apply": False,
        "replace": False,
        "review_output": None,
        "use_vector": True,
        "vector_threshold": 0.88,
        "vector_margin": 0.08,
        "vector_top_k": 20,
        "vector_state_dir": None,
    }


def test_workflow_forwards_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _fake_load(monkeypatch)

    workflow(
        {
            "apply": True,
            "replace": True,
            "use_vector": True,
            "vector_threshold": 0.91,
            "vector_margin": 0.12,
            "vector_top_k": 12,
            "review_output": "/tmp/reviews.jsonl",
            "vector_state_dir": "/tmp/vector-state",
        }
    )

    assert captured == {
        "apply": True,
        "replace": True,
        "review_output": Path("/tmp/reviews.jsonl"),
        "use_vector": True,
        "vector_threshold": 0.91,
        "vector_margin": 0.12,
        "vector_top_k": 12,
        "vector_state_dir": Path("/tmp/vector-state"),
    }


def test_workflow_result_is_json_serializable(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_load(monkeypatch, result=Counter({"INVENTED_BY:loaded": 2}))

    result = workflow({})

    json.dumps(result)


def test_workflow_re_raises_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(**kwargs: Any) -> Any:
        raise ValueError("graph write failed")

    monkeypatch.setattr("script.load_patent_relations.load", _boom)

    with pytest.raises(ValueError, match="graph write failed"):
        workflow({"apply": True})


def test_workflow_rejects_non_dict_payload() -> None:
    with pytest.raises(ValueError, match="payload 必须是 dict"):
        workflow(["not", "a", "dict"])  # type: ignore[arg-type]


@pytest.mark.parametrize("key", ["apply", "replace", "use_vector"])
def test_workflow_rejects_string_booleans(key: str) -> None:
    with pytest.raises(ValueError, match="JSON boolean"):
        workflow({key: "false"})


def test_workflow_rejects_replace_without_apply() -> None:
    with pytest.raises(ValueError, match="replace=true"):
        workflow({"replace": True})


@pytest.mark.parametrize(
    "payload",
    [{"vector_threshold": 1.1}, {"vector_margin": -0.1}, {"vector_top_k": 1}],
)
def test_workflow_rejects_invalid_vector_policy(payload: dict) -> None:
    with pytest.raises(ValueError):
        workflow(payload)
