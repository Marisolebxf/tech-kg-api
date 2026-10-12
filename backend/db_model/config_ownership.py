"""Configuration visibility without rewriting legacy owner/default metadata."""

from datetime import datetime

from sqlalchemy import DateTime, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from db_model.base import Base


class ConfigOwnership(Base):
    __tablename__ = "platform_config_ownership"
    __table_args__ = (Index("ix_config_ownership_business", "business_id"),)

    config_kind: Mapped[str] = mapped_column(String(16), primary_key=True)
    config_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    # Null is public. Missing legacy records are public too; migration explicitly
    # registers the reviewed historical inventory before the new API is deployed.
    business_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
