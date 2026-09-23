"""Business membership and graph-space ownership, independent of OAuth clients."""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from db_model.base import Base


class BusinessClient(Base):
    __tablename__ = "kg_business_client"

    client_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class BusinessMember(Base):
    __tablename__ = "kg_business_member"
    __table_args__ = (Index("ix_business_member_client", "client_id"),)

    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    client_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("kg_business_client.client_id"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="user")


class BusinessGraphSpace(Base):
    __tablename__ = "kg_business_graph_space"
    __table_args__ = (Index("ix_business_space_client", "client_id"),)

    space_name: Mapped[str] = mapped_column(String(64), primary_key=True)
    client_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("kg_business_client.client_id"), nullable=True
    )
    is_shared_production: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    shared_key: Mapped[str | None] = mapped_column(String(16), nullable=True, unique=True)
    provision_request_id: Mapped[str | None] = mapped_column(String(36), nullable=True)


class BusinessSpaceRequest(Base):
    __tablename__ = "kg_business_space_request"
    __table_args__ = (
        Index("ix_business_request_client_status", "client_id", "status"),
        UniqueConstraint("client_id", "active_space_name", name="uq_business_active_request"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    client_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("kg_business_client.client_id"), nullable=False
    )
    space_name: Mapped[str] = mapped_column(String(64), nullable=False)
    active_space_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    requested_by: Mapped[str] = mapped_column(String(128), nullable=False)
    reviewed_by: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    review_note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    last_error: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
