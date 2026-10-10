"""Literal entity index, independent of embeddings and BM25 tokenization."""

from sqlalchemy import (
    BigInteger,
    Column,
    Index,
    Integer,
    LargeBinary,
    MetaData,
    String,
    Table,
    Text,
)
from sqlalchemy.dialects.mysql import BINARY, LONGTEXT, VARCHAR

metadata = MetaData()
key_type = BigInteger().with_variant(Integer(), "sqlite")
hash_type = LargeBinary(32).with_variant(BINARY(32), "mysql")
large_text = Text().with_variant(LONGTEXT(collation="utf8mb4_bin"), "mysql")

states = Table(
    "kg_entity_literal_state",
    metadata,
    Column(
        "space",
        String(64).with_variant(VARCHAR(64, collation="utf8mb4_bin"), "mysql"),
        primary_key=True,
    ),
    Column("generation", String(32), nullable=False),
    Column("revision", String(32), nullable=False),
    Column("type_counts", large_text, nullable=False),
    Column("ready", Integer, nullable=False, default=1),
)
documents = Table(
    "kg_entity_literal_document",
    metadata,
    Column("id", key_type, primary_key=True, autoincrement=True),
    Column("generation", String(32), nullable=False),
    Column(
        "entity_type",
        String(64).with_variant(VARCHAR(64, collation="utf8mb4_bin"), "mysql"),
        nullable=False,
    ),
    Column(
        "vid",
        String(256).with_variant(VARCHAR(256, collation="utf8mb4_bin"), "mysql"),
        nullable=False,
    ),
    Column("payload", large_text, nullable=False),
    Index("ix_literal_document_page", "generation", "entity_type", "vid", unique=True),
)
fields = Table(
    "kg_entity_literal_field",
    metadata,
    Column("id", key_type, primary_key=True, autoincrement=True),
    Column("document_id", key_type, nullable=False),
    Column("field_name", String(128), nullable=False),
    Column("generation", String(32), nullable=False),
    Column("exact_hash", hash_type),
    Column("value", large_text, nullable=False),
    Index("ix_literal_field_exact", "generation", "exact_hash", "field_name", "document_id"),
    Index("ix_literal_field_document", "document_id"),
)
grams = Table(
    "kg_entity_literal_gram",
    metadata,
    Column("generation", String(32), primary_key=True),
    Column("token", hash_type, primary_key=True),
    Column("field_id", key_type, primary_key=True),
    Index("ix_literal_gram_field", "field_id"),
)
