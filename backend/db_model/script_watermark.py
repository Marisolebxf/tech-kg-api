"""脚本增量水位持久化模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, PrimaryKeyConstraint, String
from sqlalchemy.orm import Mapped, mapped_column

from db_model.base import Base


class ScriptWatermark(Base):
    """跨运行增量游标：记录某 (definition, step) 上次成功运行的时间/检查点。

    语义类比 Kafka consumer offset / Debezium lsn —— 领域 ETL 游标，
    非 Temporal workflow step 状态缓存（见 memory temporal-native-over-workarounds）。
    step 成功后由 activity 写入；失败不写，reset 后重读上次成功水位。
    """

    __tablename__ = "kg_script_watermark"
    __table_args__ = (PrimaryKeyConstraint("definition_id", "step_id"),)

    definition_id: Mapped[str] = mapped_column(String(64), nullable=False)
    step_id: Mapped[str] = mapped_column(String(64), nullable=False, default="_default")
    watermark: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    checkpoint: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
