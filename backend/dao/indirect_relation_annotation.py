"""间接关系标注 DAO：按边主键批量查询与 upsert。"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select, tuple_
from sqlalchemy.orm import Session

from db_model.indirect_relation_annotation import (
    SpaceIndirectRelationAnnotation as IndirectRelationAnnotation,
)
from service.graph_space_context import get_current_space

# 边主键：两端节点 VID（方向已归一）。
EdgeKey = tuple[str, str]


class IndirectRelationAnnotationDAO:
    """kg_indirect_relation_annotation 表查询与 upsert 封装。"""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._space = get_current_space()

    def list_by_edges(self, keys: Sequence[EdgeKey]) -> list[IndirectRelationAnnotation]:
        if not keys:
            return []
        statement = select(IndirectRelationAnnotation).where(
            IndirectRelationAnnotation.graph_space == self._space,
            tuple_(
                IndirectRelationAnnotation.source_vid,
                IndirectRelationAnnotation.target_vid,
            ).in_(keys)
        )
        return list(self._session.scalars(statement))

    def upsert(self, key: EdgeKey, annotation: str) -> IndirectRelationAnnotation:
        """按复合主键 merge：不存在则插入，存在则只更新 annotation 与 update_time。"""
        source_vid, target_vid = key
        row = self._session.merge(
            IndirectRelationAnnotation(
                graph_space=self._space,
                source_vid=source_vid,
                target_vid=target_vid,
                annotation=annotation,
            )
        )
        # 刷新以取回 create_time/update_time 等库端默认值。
        self._session.flush()
        self._session.refresh(row)
        return row
