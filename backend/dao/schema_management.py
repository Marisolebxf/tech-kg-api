"""Schema 管理数据访问层。"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from db_model.schema_management import (
    GraphSchemaDefinition,
    GraphSchemaMapping,
    GraphSchemaProperty,
    GraphSchemaScript,
)
from service.schema_ddl import default_graph_space


class SchemaManagementDAO:
    def __init__(self, session: Session) -> None:
        self.session = session

    @staticmethod
    def _load_options():
        return (
            selectinload(GraphSchemaDefinition.properties),
            selectinload(GraphSchemaDefinition.mappings),
            selectinload(GraphSchemaDefinition.script),
            selectinload(GraphSchemaDefinition.sources),
            selectinload(GraphSchemaDefinition.source_schema),
            selectinload(GraphSchemaDefinition.target_schema),
        )

    def get(self, schema_id: str) -> GraphSchemaDefinition | None:
        statement = (
            select(GraphSchemaDefinition)
            .where(
                GraphSchemaDefinition.id == schema_id, GraphSchemaDefinition.is_deleted.is_(False)
            )
            .options(*self._load_options())
        )
        return self.session.scalar(statement)

    def get_entity(self, schema_id: str) -> GraphSchemaDefinition | None:
        statement = select(GraphSchemaDefinition).where(
            GraphSchemaDefinition.id == schema_id,
            GraphSchemaDefinition.kind == "entity",
            GraphSchemaDefinition.is_deleted.is_(False),
        )
        return self.session.scalar(statement)

    def exists_by_key_or_name(self, schema_key: str, name: str, graph_space: str) -> bool:
        statement = select(GraphSchemaDefinition.id).where(
            GraphSchemaDefinition.graph_space == graph_space,
            GraphSchemaDefinition.is_deleted.is_(False),
            or_(
                GraphSchemaDefinition.schema_key == schema_key,
                GraphSchemaDefinition.name == name,
            ),
        )
        return self.session.scalar(statement) is not None

    def list(
        self,
        *,
        kind: str | None,
        keyword: str | None,
        page: int,
        page_size: int,
        graph_space: str | None = None,
    ) -> tuple[list[GraphSchemaDefinition], int]:
        filters = [GraphSchemaDefinition.is_deleted.is_(False)]
        if kind:
            filters.append(GraphSchemaDefinition.kind == kind)
        if graph_space:
            filters.append(GraphSchemaDefinition.graph_space == graph_space)
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

    def list_all(self, graph_space: str | None = None) -> list[GraphSchemaDefinition]:
        statement = (
            select(GraphSchemaDefinition)
            .options(*self._load_options())
            .where(GraphSchemaDefinition.is_deleted.is_(False))
        )
        if graph_space:
            statement = statement.where(GraphSchemaDefinition.graph_space == graph_space)
        statement = statement.order_by(
            GraphSchemaDefinition.kind,
            GraphSchemaDefinition.relation_category,
            GraphSchemaDefinition.display_order,
            GraphSchemaDefinition.created_at,
            GraphSchemaDefinition.id,
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
            graph_space=payload.get("graph_space") or default_graph_space(),
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
            GraphSchemaDefinition.is_deleted.is_(False),
            or_(
                GraphSchemaDefinition.source_schema_id == schema_id,
                GraphSchemaDefinition.target_schema_id == schema_id,
            ),
        )
        return list(self.session.scalars(statement).all())

    def referencing_relations(self, schema_id: str) -> list[GraphSchemaDefinition]:
        """引用该实体的关系定义（删除属性时检查 source/target 表达式引用）。"""
        statement = select(GraphSchemaDefinition).where(
            GraphSchemaDefinition.kind == "relation",
            GraphSchemaDefinition.is_deleted.is_(False),
            or_(
                GraphSchemaDefinition.source_schema_id == schema_id,
                GraphSchemaDefinition.target_schema_id == schema_id,
            ),
        )
        return list(self.session.scalars(statement).all())

    def delete(self, definition: GraphSchemaDefinition) -> None:
        """目录假删：置 is_deleted 标记保留物理行（审计/图库存量数据不受影响）。

        同时改写 schema_key/name 释放 (key,graph_space)/(name,graph_space) 唯一键，
        否则删除后无法在同名空间重建同名 schema（假删行仍占用唯一约束）。
        """
        now = datetime.now()
        stamp = now.strftime("%Y%m%d%H%M%S") + uuid4().hex[:4]
        definition.is_deleted = True
        definition.deleted_at = now
        definition.schema_key = f"{definition.schema_key[:48]}#del-{stamp}"
        definition.name = f"{definition.name[:110]}#del-{stamp}"
        self.session.add(definition)

    def stats(self, graph_space: str | None = None) -> dict[str, int]:
        space_filters = [GraphSchemaDefinition.is_deleted.is_(False)]
        if graph_space:
            space_filters.append(GraphSchemaDefinition.graph_space == graph_space)

        def _count(*conditions):
            return (
                self.session.scalar(
                    select(func.count())
                    .select_from(GraphSchemaDefinition)
                    .where(*space_filters, *conditions)
                )
                or 0
            )

        entity_count = _count(GraphSchemaDefinition.kind == "entity")
        relation_count = _count(GraphSchemaDefinition.kind == "relation")
        core_count = _count(
            GraphSchemaDefinition.kind == "entity", GraphSchemaDefinition.is_core.is_(True)
        )
        fact_count = _count(
            GraphSchemaDefinition.kind == "relation",
            GraphSchemaDefinition.relation_category == "fact",
        )
        inferred_count = _count(
            GraphSchemaDefinition.kind == "relation",
            GraphSchemaDefinition.relation_category == "inferred",
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
