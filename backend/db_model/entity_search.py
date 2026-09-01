"""实体检索（Milvus 混合搜索）ORM 模型——控制库。

存 BM25 编码器状态（词表/文档频率等）与索引统计，按图空间一行。
BM25 状态放 MySQL 而非容器文件系统：容器重建不丢，查询端点无需重新 fit。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column

from service.workflow_models import Base


def _long_text() -> Text:
    """MySQL 用 LONGTEXT（中文 JSON 词表可超 64KB），SQLite（测试）退化为 TEXT。"""
    return Text().with_variant(LONGTEXT(), "mysql")


class EntitySearchState(Base):
    """实体检索索引状态（每个图空间一行，主键 = graph_space）。"""

    __tablename__ = "kg_entity_search_state"
    __table_args__ = {"comment": "实体 Milvus 混合检索索引状态（按图空间，BM25 词表 + 统计）"}

    graph_space: Mapped[str] = mapped_column(String(64), primary_key=True)
    # BM25SparseEncoder 序列化状态（JSON，词表 + 文档频率）
    vocabulary: Mapped[str] = mapped_column(_long_text(), nullable=False, default="")
    document_frequency: Mapped[str] = mapped_column(_long_text(), nullable=False, default="")
    document_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    average_document_length: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    k1: Mapped[float] = mapped_column(Float, nullable=False, default=1.5)
    b: Mapped[float] = mapped_column(Float, nullable=False, default=0.75)
    # 索引统计
    entity_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    type_counts: Mapped[str] = mapped_column(_long_text(), nullable=False, default="{}")
    embedding_model: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )
