"""间接关系标注 业务逻辑：标注只存业务库，不写图数据库。"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from dao.indirect_relation_annotation import EdgeKey, IndirectRelationAnnotationDAO


class IndirectRelationAnnotationService:
    def __init__(self, session: Session) -> None:
        self._dao = IndirectRelationAnnotationDAO(session)

    @staticmethod
    def normalize_key(source_vid: str, target_vid: str) -> EdgeKey:
        """方向归一：同一对 VID 无论边方向如何都映射到同一行。"""
        if source_vid <= target_vid:
            return (source_vid, target_vid)
        return (target_vid, source_vid)

    def list_annotations(self, keys: Iterable[EdgeKey]) -> list[dict[str, Any]]:
        """按边主键批量查询；查不到数据的关系即视为无标注（不返回该行）。"""
        rows = self._dao.list_by_edges(list(keys))
        return [
            _to_item(row.source_vid, row.target_vid, row.annotation, row.update_time)
            for row in rows
        ]

    def upsert_annotation(
        self, source_vid: str, target_vid: str, annotation: str
    ) -> dict[str, Any]:
        key = self.normalize_key(source_vid, target_vid)
        row = self._dao.upsert(key, annotation)
        return _to_item(row.source_vid, row.target_vid, row.annotation, row.update_time)


def _to_item(
    source_vid: str, target_vid: str, annotation: str, update_time: datetime | None
) -> dict[str, Any]:
    return {
        "sourceVid": source_vid,
        "targetVid": target_vid,
        "annotation": annotation,
        "updateTime": update_time.isoformat() if update_time is not None else None,
    }
