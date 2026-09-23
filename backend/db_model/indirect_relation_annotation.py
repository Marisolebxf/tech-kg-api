"""单节点间接关系人工标注模型。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from db_model.base import Base


class IndirectRelationAnnotation(Base):
    """间接关系人工标注：存业务库，不写图数据库。

    主键为边的主键（两端图节点 VID，写入前按字典序归一方向）；
    同一对 VID 无论查询时边方向如何都命中同一行。
    """

    __tablename__ = "kg_indirect_relation_annotation"

    source_vid: Mapped[str] = mapped_column(String(256), primary_key=True)
    target_vid: Mapped[str] = mapped_column(String(256), primary_key=True)
    annotation: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    create_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    update_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )
