from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from service.relation_detail_annotation import RelationDetailAnnotationService


def _svc(graph):
    svc = RelationDetailAnnotationService()
    svc._graph = graph  # noqa: SLF001
    return svc


def test_annotate_updates_edge_and_returns_role_level():
    graph = MagicMock()
    graph.get_edge = MagicMock(return_value=MagicMock(id="S001->E001@0", type="EMPLOYED_BY"))
    graph.update_edge = MagicMock()

    resp = _svc(graph).annotate(
        {
            "relationId": "S001->E001@0",
            "roleType": "chief_scientist",
            "techField": "人工智能",
            "period": {"start": "2021-01-01", "end": "2024-12-31"},
        }
    )
    assert resp["roleLabel"] == "首席科学家"
    assert resp["roleLevel"] == "L1"
    assert resp["annotated"] is True
    graph.update_edge.assert_called_once()
    args, kwargs = graph.update_edge.call_args
    assert args[0] == "S001->E001@0"
    assert kwargs["edge_type"] == "EMPLOYED_BY"
    assert kwargs["properties"]["role"] == "chief_scientist"
    assert kwargs["properties"]["tech_field"] == "人工智能"
    assert kwargs["properties"]["start_date"] == "2021-01-01"


def test_annotate_missing_edge_raises():
    graph = MagicMock()
    graph.get_edge = MagicMock(return_value=None)
    graph.update_edge = MagicMock()
    with pytest.raises(KeyError):
        _svc(graph).annotate(
            {"relationId": "S001->E001@0", "roleType": "engineer", "techField": "", "period": {}}
        )
    graph.update_edge.assert_not_called()
