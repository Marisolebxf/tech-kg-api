"""平台 LLM 配置持久化模型。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from db_model.base import Base


class LlmConfig(Base):
    """平台 LLM 配置记录。`is_default=True` 全局唯一，由 service 层保证。"""

    __tablename__ = "platform_llm_config"
    __table_args__ = (Index("ix_llm_config_default_status", "is_default", "status"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    base_url: Mapped[str] = mapped_column(String(256), nullable=False)
    api_key: Mapped[str] = mapped_column(String(256), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    owner: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="正常")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
