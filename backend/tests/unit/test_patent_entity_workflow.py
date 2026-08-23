from __future__ import annotations

import json
from typing import Any

import pytest

from script.patent_entity_workflow import workflow


def _fake_load_patents(monkeypatch, result=(3, 5, 5)) -> list[tuple[int]]:
    """替换 load_patents，记录调用参数并返回固定结果。"""
    calls: list[tuple[int]] = []

    def _fake(batch_size: int) -> tuple[int, int, int]:
        calls.append((batch_size,))
        return result

    monkeypatch.setattr("script.load_patent_graph.load_patents", _fake)
    return calls


def test_workflow_returns_stats_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _fake_load_patents(monkeypatch, result=(12, 7, 7))

    result = workflow({"batch_size": 25})

    assert calls == [(25,)]
    assert result["ok"] is True
    assert result["stats"] == {
        "patents": 12,
        "keywordRefs": 7,
        "hasKeywordEdges": 7,
    }


def test_workflow_uses_default_batch_size(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _fake_load_patents(monkeypatch)

    workflow({})

    assert calls == [(50,)]


def test_workflow_result_is_json_serializable(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_load_patents(monkeypatch, result=(3, 5, 5))

    result = workflow({})

    json.dumps(result)


def test_workflow_re_raises_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(batch_size: int) -> Any:
        raise RuntimeError("db down")

    monkeypatch.setattr("script.load_patent_graph.load_patents", _boom)

    with pytest.raises(RuntimeError, match="db down"):
        workflow({"batch_size": 10})


def test_workflow_rejects_non_dict_payload() -> None:
    with pytest.raises(ValueError, match="payload 必须是 dict"):
        workflow("not a dict")  # type: ignore[arg-type]
