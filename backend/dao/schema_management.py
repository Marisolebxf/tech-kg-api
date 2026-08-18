"""Schema 管理数据访问层。"""

from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from db_model.schema_management import (
    GraphSchemaDefinition,
    GraphSchemaMapping,
    GraphSchemaProperty,
    GraphSchemaScript,
)


class SchemaManagementDAO:
    def __init__(self, session: Session) -> None:
        self.session = session

    @staticmethod
    def _load_options():
        return (
            selectinload(GraphSchemaDefinition.properties),
            selectinload(GraphSchemaDefinition.mappings),
            selectinload(GraphSchemaDefinition.script),
            selectinload(GraphSchemaDefinition.source_schema),
            selectinload(GraphSchemaDefinition.target_schema),
        )

    def get(self, schema_id: str) -> GraphSchemaDefinition | None:
        statement = (
            select(GraphSchemaDefinition)
            .where(GraphSchemaDefinition.id == schema_id)
            .options(*self._load_options())
        )
        return self.session.scalar(statement)

    def get_entity(self, schema_id: str) -> GraphSchemaDefinition | None:
        statement = select(GraphSchemaDefinition).where(
            GraphSchemaDefinition.id == schema_id,
            GraphSchemaDefinition.kind == "entity",
        )
        return self.session.scalar(statement)

    def exists_by_key_or_name(self, schema_key: str, name: str) -> bool:
        statement = select(GraphSchemaDefinition.id).where(
            or_(
                GraphSchemaDefinition.schema_key == schema_key,
                GraphSchemaDefinition.name == name,
            )
        )
        return self.session.scalar(statement) is not None

    def list(
        self,
        *,
        kind: str | None,
        keyword: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[GraphSchemaDefinition], int]:
        filters = []
        if kind:
            filters.append(GraphSchemaDefinition.kind == kind)
        if keyword:
            pattern = f"%{keyword}%"
            filters.append(
                or_(
                    GraphSchemaDefinition.name.like(pattern),
                    GraphSchemaDefinition.label.like(pattern),
                    GraphSchemaDefinition.schema_key.like(pattern),
                )
            )

        total = (
            self.session.scalar(select(func.count(GraphSchemaDefinition.id)).where(*filters)) or 0
        )
        statement = (
            select(GraphSchemaDefinition)
            .where(*filters)
            .options(*self._load_options())
            .order_by(
                GraphSchemaDefinition.kind,
                GraphSchemaDefinition.relation_category,
                GraphSchemaDefinition.display_order,
                GraphSchemaDefinition.created_at,
                GraphSchemaDefinition.id,
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(self.session.scalars(statement).all()), int(total)

    def list_all(self) -> list[GraphSchemaDefinition]:
        statement = (
            select(GraphSchemaDefinition)
            .options(*self._load_options())
            .order_by(
                GraphSchemaDefinition.kind,
                GraphSchemaDefinition.relation_category,
                GraphSchemaDefinition.display_order,
                GraphSchemaDefinition.created_at,
                GraphSchemaDefinition.id,
            )
        )
        return list(self.session.scalars(statement).all())

    def create(
        self,
        *,
        schema_id: str,
        kind: str,
        payload: dict,
        created_by: str,
        script: dict | None = None,
    ) -> GraphSchemaDefinition:
        definition = GraphSchemaDefinition(
            id=schema_id,
            schema_key=payload["schema_key"],
            kind=kind,
            name=payload["name"],
            label=payload["label"],
            description=payload["description"],
            identity_key=payload.get("identity_key", ""),
            attribute_identity_key=payload.get("attribute_identity_key")
            or payload.get("identity_key", ""),
            attribute_source=payload.get("attribute_source")
            or " / ".join(payload.get("mappings", [])),
            instance_count=0,
            version=payload["version"],
            display_order=-1,
            is_core=payload["is_core"],
            relation_category=payload.get("relation_category"),
            is_system=False,
            created_by=created_by,
            source_schema_id=payload.get("source_schema_id"),
            target_schema_id=payload.get("target_schema_id"),
            source_expression=payload.get("source_expression"),
            target_expression=payload.get("target_expression"),
            llm_config_id=payload.get("llm_config_id"),
        )
        definition.properties = [
            GraphSchemaProperty(
                name=item["name"],
                data_type=item["data_type"],
                required=item["required"],
                rule=item["rule"],
                category=item.get("category", "core"),
                position=index,
            )
            for index, item in enumerate(payload["properties"])
        ]
        definition.mappings = [
            GraphSchemaMapping(source_name=item, position=index)
            for index, item in enumerate(payload["mappings"])
        ]
        if script is not None:
            definition.script = GraphSchemaScript(**script)
        self.session.add(definition)
        self.session.flush()
        return definition

    def save_script(
        self,
        definition: GraphSchemaDefinition,
        *,
        script: dict,
    ) -> GraphSchemaScript:
        if definition.script is None:
            definition.script = GraphSchemaScript(**script)
        else:
            for key, value in script.items():
                setattr(definition.script, key, value)
        self.session.flush()
        return definition.script

    def referenced_relation_names(self, schema_id: str) -> list[str]:
        statement = select(GraphSchemaDefinition.name).where(
            GraphSchemaDefinition.kind == "relation",
            or_(
                GraphSchemaDefinition.source_schema_id == schema_id,
                GraphSchemaDefinition.target_schema_id == schema_id,
            ),
        )
        return list(self.session.scalars(statement).all())

    def delete(self, definition: GraphSchemaDefinition) -> None:
        self.session.delete(definition)

    def stats(self) -> dict[str, int]:
        entity_count = (
            self.session.scalar(
                select(func.count())
                .select_from(GraphSchemaDefinition)
                .where(GraphSchemaDefinition.kind == "entity")
            )
            or 0
        )
        relation_count = (
            self.session.scalar(
                select(func.count())
                .select_from(GraphSchemaDefinition)
                .where(GraphSchemaDefinition.kind == "relation")
            )
            or 0
        )
        core_count = (
            self.session.scalar(
                select(func.count())
                .select_from(GraphSchemaDefinition)
                .where(
                    GraphSchemaDefinition.kind == "entity", GraphSchemaDefinition.is_core.is_(True)
                )
            )
            or 0
        )
        fact_count = (
            self.session.scalar(
                select(func.count())
                .select_from(GraphSchemaDefinition)
                .where(
                    GraphSchemaDefinition.kind == "relation",
                    GraphSchemaDefinition.relation_category == "fact",
                )
            )
            or 0
        )
        inferred_count = (
            self.session.scalar(
                select(func.count())
                .select_from(GraphSchemaDefinition)
                .where(
                    GraphSchemaDefinition.kind == "relation",
                    GraphSchemaDefinition.relation_category == "inferred",
                )
            )
            or 0
        )
        property_count = (
            self.session.scalar(select(func.count()).select_from(GraphSchemaProperty)) or 0
        )
        required_count = (
            self.session.scalar(
                select(func.count())
                .select_from(GraphSchemaProperty)
                .where(GraphSchemaProperty.required.is_(True))
            )
            or 0
        )
        constraint_count = (
            self.session.scalar(
                select(func.count())
                .select_from(GraphSchemaProperty)
                .where(GraphSchemaProperty.rule != "")
            )
            or 0
        )
        mapping_count = (
            self.session.scalar(select(func.count(func.distinct(GraphSchemaMapping.source_name))))
            or 0
        )
        return {
            "entity_count": int(entity_count),
            "relation_count": int(relation_count),
            "core_count": int(core_count),
            "fact_count": int(fact_count),
            "inferred_count": int(inferred_count),
            "property_count": int(property_count),
            "required_count": int(required_count),
            "constraint_count": int(constraint_count),
            "mapping_count": int(mapping_count),
        }
