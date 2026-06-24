"""角色与合作详情标注 编排层。"""

from __future__ import annotations

from typing import Any

from service.relation_detail_annotation import RelationDetailAnnotationService


class RelationDetailAnnotationApplication:
    def __init__(self) -> None:
        self._service = RelationDetailAnnotationService()

    def describe(self) -> dict[str, object]:
        return self._service.describe()

    def annotate(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._service.annotate(payload)
