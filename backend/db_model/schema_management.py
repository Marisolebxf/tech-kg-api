"""Schema 管理服务 ORM 模型。"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db_model.base import Base


def _uuid() -> str:
    return str(uuid4())


class GraphSchemaDefinition(Base):
    """实体或关系 Schema 的主定义。"""

    __tablename__ = "kg_schema_definition"
    __table_args__ = (
        UniqueConstraint("schema_key", name="uk_kg_schema_definition_key"),
        UniqueConstraint("name", name="uk_kg_schema_definition_name"),
        Index("idx_kg_schema_definition_kind_created", "kind", "created_at"),
        {"comment": "知识图谱实体与关系 Schema 定义"},
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    schema_key: Mapped[str] = mapped_column(String(64), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, comment="entity/relation")
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    label: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    identity_key: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    attribute_identity_key: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    attribute_source: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    instance_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    version: Mapped[str] = mapped_column(String(32), nullable=False, default="v1.0")
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=10000)
    is_core: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    relation_category: Mapped[str | None] = mapped_column(
        String(16), nullable=True, comment="fact/inferred，仅关系 Schema 使用"
    )
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_schema_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("kg_schema_definition.id", ondelete="RESTRICT"), nullable=True
    )
    target_schema_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("kg_schema_definition.id", ondelete="RESTRICT"), nullable=True
    )
    source_expression: Mapped[str | None] = mapped_column(String(512), nullable=True)
    target_expression: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    properties: Mapped[list[GraphSchemaProperty]] = relationship(
        back_populates="schema",
        cascade="all, delete-orphan",
        order_by="GraphSchemaProperty.position",
    )
    mappings: Mapped[list[GraphSchemaMapping]] = relationship(
        back_populates="schema",
        cascade="all, delete-orphan",
        order_by="GraphSchemaMapping.position",
    )
    script: Mapped[GraphSchemaScript | None] = relationship(
        back_populates="schema", cascade="all, delete-orphan", uselist=False
    )
    source_schema: Mapped[GraphSchemaDefinition | None] = relationship(
        foreign_keys=[source_schema_id], remote_side=[id]
    )
    target_schema: Mapped[GraphSchemaDefinition | None] = relationship(
        foreign_keys=[target_schema_id], remote_side=[id]
    )


class GraphSchemaProperty(Base):
    """Schema 属性及约束。"""

    __tablename__ = "kg_schema_property"
    __table_args__ = (
        UniqueConstraint("schema_id", "name", name="uk_kg_schema_property_name"),
        {"comment": "Schema 属性与约束"},
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    schema_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("kg_schema_definition.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    data_type: Mapped[str] = mapped_column(String(128), nullable=False)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    rule: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    category: Mapped[str] = mapped_column(String(16), nullable=False, default="core")
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    schema: Mapped[GraphSchemaDefinition] = relationship(back_populates="properties")


class GraphSchemaMapping(Base):
    """Schema 到科技要素库来源对象的映射。"""

    __tablename__ = "kg_schema_mapping"
    __table_args__ = (
        UniqueConstraint("schema_id", "source_name", name="uk_kg_schema_mapping_source"),
        {"comment": "Schema 来源对象映射"},
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    schema_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("kg_schema_definition.id", ondelete="CASCADE"), nullable=False
    )
    source_name: Mapped[str] = mapped_column(String(255), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    schema: Mapped[GraphSchemaDefinition] = relationship(back_populates="mappings")


class GraphSchemaScript(Base):
    """用户 Schema 与 S3 Python 脚本对象的一对一关系。"""

    __tablename__ = "kg_schema_script"
    __table_args__ = (
        UniqueConstraint("schema_id", name="uk_kg_schema_script_schema"),
        {"comment": "Schema Python 处理脚本 S3 对象元数据"},
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    schema_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("kg_schema_definition.id", ondelete="CASCADE"), nullable=False
    )
    bucket: Mapped[str] = mapped_column(String(128), nullable=False)
    object_key: Mapped[str] = mapped_column(String(512), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False, default="text/x-python")
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    etag: Mapped[str | None] = mapped_column(String(128), nullable=True)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    uploaded_by: Mapped[str] = mapped_column(String(128), nullable=False)
    workflow_definition_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    workflow_function_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    schema: Mapped[GraphSchemaDefinition] = relationship(back_populates="script")
