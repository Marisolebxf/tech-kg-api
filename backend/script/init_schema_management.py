"""创建 Schema 管理表并初始化 Schema 管理页面的系统目录。

用法：
    cd backend
    uv run python script/init_schema_management.py
"""

from __future__ import annotations

import re
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import Engine, inspect, or_, select, text
from sqlalchemy.orm import Session, selectinload

from db_model.base import Base
from db_model.schema_management import (
    GraphSchemaDefinition,
    GraphSchemaMapping,
    GraphSchemaProperty,
    GraphSchemaScript,
)
from infra.mysql import get_engine
from service.schema_catalog_seed import (
    ATTRIBUTE_SPECS,
    ENTITY_SPECS,
    FACT_RELATION_SPECS,
    INFERRED_RELATION_SPECS,
)

MANAGED_TABLES = [
    GraphSchemaDefinition.__table__,
    GraphSchemaProperty.__table__,
    GraphSchemaMapping.__table__,
    GraphSchemaScript.__table__,
]

INCREMENTAL_COLUMNS = {
    "kg_schema_definition": {
        "identity_key": "VARCHAR(512) NOT NULL DEFAULT ''",
        "attribute_identity_key": "VARCHAR(512) NOT NULL DEFAULT ''",
        "attribute_source": "VARCHAR(1024) NOT NULL DEFAULT ''",
        "display_order": "INT NOT NULL DEFAULT 10000",
        "source_expression": "VARCHAR(512) NULL",
        "target_expression": "VARCHAR(512) NULL",
        "llm_config_id": "VARCHAR(64) NULL",
        "ddl_statement": "VARCHAR(2048) NULL",
        "ddl_status": "VARCHAR(16) NOT NULL DEFAULT 'pending'",
        "ddl_error": "VARCHAR(1024) NULL",
        "ddl_executed_at": "DATETIME NULL",
    },
    "kg_schema_property": {
        "category": "VARCHAR(16) NOT NULL DEFAULT 'core'",
    },
    "kg_schema_script": {
        "workflow_definition_id": "VARCHAR(64) NULL",
        "workflow_function_name": "VARCHAR(128) NULL",
        "uploaded_by": "VARCHAR(128) NOT NULL DEFAULT ''",
    },
}


def _schema_key(name: str) -> str:
    if "_" in name:
        return name.lower().replace("_", "-")
    return re.sub(r"(?<!^)(?=[A-Z])", "-", name).lower()


def _system_id(kind: str, name: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"tech-kg-schema:{kind}:{name}"))


def _split_sources(value: str) -> list[str]:
    return [item.strip() for item in value.split(" / ") if item.strip()]


def _split_properties(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _ensure_incremental_columns(engine: Engine) -> None:
    schema_inspector = inspect(engine)
    existing_tables = set(schema_inspector.get_table_names())
    with engine.begin() as connection:
        for table_name, columns in INCREMENTAL_COLUMNS.items():
            if table_name not in existing_tables:
                continue
            existing_columns = {item["name"] for item in schema_inspector.get_columns(table_name)}
            for column_name, ddl in columns.items():
                if column_name not in existing_columns:
                    connection.execute(
                        text(f"ALTER TABLE `{table_name}` ADD COLUMN `{column_name}` {ddl}")
                    )


def _find_definition(
    session: Session, *, schema_key: str, name: str
) -> GraphSchemaDefinition | None:
    statement = (
        select(GraphSchemaDefinition)
        .where(
            or_(
                GraphSchemaDefinition.schema_key == schema_key,
                GraphSchemaDefinition.name == name,
            )
        )
        .options(
            selectinload(GraphSchemaDefinition.properties),
            selectinload(GraphSchemaDefinition.mappings),
        )
    )
    return session.scalar(statement)


def _replace_children(
    session: Session,
    definition: GraphSchemaDefinition,
    *,
    properties: list[tuple[str, str]],
    mappings: list[str],
) -> None:
    definition.properties.clear()
    definition.mappings.clear()
    session.flush()
    definition.properties = [
        GraphSchemaProperty(
            name=name,
            data_type="string",
            required=False,
            rule="",
            category=category,
            position=position,
        )
        for position, (name, category) in enumerate(properties)
    ]
    definition.mappings = [
        GraphSchemaMapping(source_name=name, position=position)
        for position, name in enumerate(mappings)
    ]


def _entity_properties(name: str, identity_key: str) -> tuple[list[tuple[str, str]], str, str]:
    attribute = ATTRIBUTE_SPECS.get(name)
    if attribute is None:
        identifier = re.split(r"\s[/+]\s", identity_key, maxsplit=1)[0].strip()
        return ([(identifier, "core")] if identifier else []), identity_key, ""

    attribute_key, core, dynamic, attribute_source = attribute
    properties: list[tuple[str, str]] = []
    for property_name in _split_properties(core):
        properties.append((property_name, "core"))
    for property_name in _split_properties(dynamic):
        if property_name not in {item[0] for item in properties}:
            properties.append((property_name, "dynamic"))
    return properties, attribute_key, attribute_source


def _upsert_entities(session: Session) -> tuple[dict[str, str], int]:
    entity_ids: dict[str, str] = {}
    inserted = 0
    for display_order, (
        name,
        label,
        is_core,
        identity_key,
        source,
        description,
    ) in enumerate(ENTITY_SPECS):
        schema_key = _schema_key(name)
        definition = _find_definition(session, schema_key=schema_key, name=name)
        if definition is None:
            definition = GraphSchemaDefinition(id=_system_id("entity", name))
            session.add(definition)
            inserted += 1
        elif not definition.is_system:
            raise RuntimeError(f"用户 Schema 与系统 Schema 名称冲突: {name}")

        properties, attribute_key, attribute_source = _entity_properties(name, identity_key)
        definition.schema_key = schema_key
        definition.kind = "entity"
        definition.name = name
        definition.label = label
        definition.description = description
        definition.identity_key = identity_key
        definition.attribute_identity_key = attribute_key
        definition.attribute_source = attribute_source or source
        definition.instance_count = definition.instance_count or 0
        definition.version = "v1.8"
        definition.display_order = display_order
        definition.is_core = is_core
        definition.relation_category = None
        definition.is_system = True
        definition.created_by = None
        definition.source_schema_id = None
        definition.target_schema_id = None
        definition.source_expression = None
        definition.target_expression = None
        _replace_children(
            session,
            definition,
            properties=properties,
            mappings=_split_sources(source),
        )
        session.flush()
        entity_ids[name] = definition.id
    return entity_ids, inserted


def _upsert_relations(
    session: Session,
    *,
    entity_ids: dict[str, str],
    specs: list[tuple[str, str, str, str, str]],
    category: str,
) -> int:
    inserted = 0
    for display_order, (name, label, source, target, basis) in enumerate(specs):
        schema_key = _schema_key(name)
        definition = _find_definition(session, schema_key=schema_key, name=name)
        if definition is None:
            definition = GraphSchemaDefinition(id=_system_id("relation", name))
            session.add(definition)
            inserted += 1
        elif not definition.is_system:
            raise RuntimeError(f"用户 Schema 与系统 Schema 名称冲突: {name}")

        definition.schema_key = schema_key
        definition.kind = "relation"
        definition.name = name
        definition.label = label
        definition.description = basis
        definition.identity_key = ""
        definition.attribute_identity_key = ""
        definition.attribute_source = ""
        definition.instance_count = definition.instance_count or 0
        definition.version = "v1.8"
        definition.display_order = display_order
        definition.is_core = False
        definition.relation_category = category
        definition.is_system = True
        definition.created_by = None
        definition.source_schema_id = entity_ids.get(source)
        definition.target_schema_id = entity_ids.get(target)
        definition.source_expression = source
        definition.target_expression = target
        _replace_children(
            session,
            definition,
            properties=[("source", "core"), ("target", "core")],
            mappings=[],
        )
        session.flush()
    return inserted


def initialize_schema_management(engine: Engine | None = None) -> int:
    engine = engine or get_engine()
    Base.metadata.create_all(engine, tables=MANAGED_TABLES)
    _ensure_incremental_columns(engine)

    with Session(engine) as session:
        entity_ids, inserted = _upsert_entities(session)
        inserted += _upsert_relations(
            session,
            entity_ids=entity_ids,
            specs=FACT_RELATION_SPECS,
            category="fact",
        )
        inserted += _upsert_relations(
            session,
            entity_ids=entity_ids,
            specs=INFERRED_RELATION_SPECS,
            category="inferred",
        )
        session.commit()
    return inserted


def main() -> None:
    inserted = initialize_schema_management()
    print(f"Schema 管理表初始化完成，新增系统 Schema: {inserted}")


if __name__ == "__main__":
    main()
