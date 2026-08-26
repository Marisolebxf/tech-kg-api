"""平台 MySQL 数据源配置持久化模型。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from db_model.base import Base


class MysqlDatasource(Base):
    """平台 MySQL 数据源记录。`is_default=True` 全局唯一，由 service 层保证。"""

    __tablename__ = "platform_mysql_datasource"
    __table_args__ = (Index("ix_mysql_datasource_default_status", "is_default", "status"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    host: Mapped[str] = mapped_column(String(256), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False, default=3306)
    default_database: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    username: Mapped[str] = mapped_column(String(128), nullable=False)
    password: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    owner: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="正常")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
