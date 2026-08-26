"""平台 Milvus 配置持久化模型。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from db_model.base import Base


class MilvusConfig(Base):
    """平台 Milvus 配置记录。`uri` 为空时回退 `MILVUS_*` 环境变量。`is_default` 全局唯一。"""

    __tablename__ = "platform_milvus_config"
    __table_args__ = (Index("ix_milvus_config_default_status", "is_default", "status"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    uri: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    token: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    default_db: Mapped[str] = mapped_column(String(128), nullable=False, default="default")
    owner: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="正常")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
