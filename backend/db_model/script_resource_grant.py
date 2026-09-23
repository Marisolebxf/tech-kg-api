"""Trusted semantic record grants shared by steps of one Temporal run."""

from datetime import datetime

from sqlalchemy import DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from db_model.base import Base


class ScriptResourceGrant(Base):
    __tablename__ = "kg_script_resource_grant"
    __table_args__ = (Index("ix_script_resource_grant_expiry", "expires_at"),)

    run_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    record_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    graph_space: Mapped[str] = mapped_column(String(64), nullable=False)
    client_id: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
