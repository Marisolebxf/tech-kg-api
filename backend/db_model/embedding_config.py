"""平台 embedding 模型配置持久化模型。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from db_model.base import Base


class EmbeddingConfig(Base):
    """平台 embedding 模型配置记录（OpenAI 兼容）。`is_default=True` 全局唯一。"""

    __tablename__ = "platform_embedding_config"
    __table_args__ = (Index("ix_embedding_config_default_status", "is_default", "status"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    base_url: Mapped[str] = mapped_column(String(256), nullable=False)
    api_key: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    dimensions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    owner: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="正常")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
