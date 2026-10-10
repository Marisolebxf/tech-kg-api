"""Character inverted index with literal verification and atomic generations.

Use the existing control database; no vector service or external tokenizer is
required. A gram posting selects candidates, INSTR verifies the original field
so punctuation, SQL wildcards and one-character Chinese queries remain literal.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Iterable
from typing import Any

from sqlalchemy import Connection, delete, func, insert, select, update
from sqlalchemy.orm import Session

from db_model.entity_literal_index import documents, fields, grams, metadata, states


class LiteralIndexError(Exception):
    pass


def normalized(value: str) -> str:
    return value.lower()


def digest(value: str) -> bytes:
    return hashlib.sha256(value.encode("utf-8")).digest()


def tokens(value: str, sizes=(1, 2, 3)) -> set[bytes]:
    return {digest(value[i : i + size]) for size in sizes for i in range(len(value) - size + 1)}


def searchable_values(item: dict[str, Any]) -> list[tuple[str, str, bool]]:
    from service.entity_search import NAME_CANDIDATE_KEYS

    props = item["props"]
    values = [("__vid__", normalized(str(item["vid"])), True)]
    exact_fields = {*NAME_CANDIDATE_KEYS, "id", "entity_id"}
    # Retain the corresponding field name (e.g. Paper.title_zh), rather than
    # promoting every public property to the complete-name/ID exact path.
    for key, value in props.items():
        if value is None:
            continue
        if isinstance(value, (dict, list, tuple)):
            value = json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":"))
            exact = False
        else:
            exact = key in exact_fields
        value = normalized(str(value))
        if exact:
            value = value.strip()
        if value:
            values.append((str(key)[:128], value, exact))
    return values


class EntityLiteralIndex:
    def __init__(self, session: Session):
        self.session = session

    def ensure_schema(self) -> None:
        bind = self.session.get_bind()
        metadata.create_all(bind)
        if isinstance(bind, Connection) and bind.in_transaction():
            bind.commit()

    def state(self, space: str, *, require_ready: bool = True) -> dict[str, Any]:
        # Tables are provisioned by the build command, never DDL on a search.
        from sqlalchemy import inspect

        if not inspect(self.session.connection()).has_table(states.name):
            raise LiteralIndexError(
                "文字索引尚未建立，请运行 build_entity_literal_index --space " + space
            )
        row = self.session.execute(select(states).where(states.c.space == space)).mappings().first()
        if row is None or (require_ready and not row["ready"]):
            raise LiteralIndexError("文字索引未就绪或已失效，请重建当前图空间的文字索引")
        return dict(row)

    def _insert_document(self, generation: str, item: dict[str, Any]) -> None:
        from types import SimpleNamespace

        from service.entity_search import _serialize_browse_item

        payload = _serialize_browse_item(
            SimpleNamespace(id=item["vid"], properties=item["props"]), item["entity_type"]
        )
        doc_id = self.session.execute(
            insert(documents).values(
                generation=generation,
                entity_type=item["entity_type"],
                vid=str(item["vid"]),
                payload=json.dumps(payload, ensure_ascii=False),
            )
        ).inserted_primary_key[0]
        for field_name, value, exact in searchable_values(item):
            field_id = self.session.execute(
                insert(fields).values(
                    document_id=doc_id,
                    field_name=field_name,
                    generation=generation,
                    value=value,
                    exact_hash=digest(value) if exact else None,
                )
            ).inserted_primary_key[0]
            rows = [
                {"generation": generation, "token": token, "field_id": field_id}
                for token in tokens(value)
            ]
            # Bound packet size even for very long abstracts/documents.
            for start in range(0, len(rows), 1000):
                self.session.execute(insert(grams), rows[start : start + 1000])

    def build(self, space: str, items: Iterable[dict[str, Any]], labels: list[str]) -> dict:
        """Publish only after *every* label has been read successfully.

        The CLI holds a database advisory lock across build and graph writes.
        Retain old generations until explicit offline cleanup, so in-flight
        searches can finish against their pinned snapshot.
        """
        self.ensure_schema()
        generation = uuid.uuid4().hex
        counts = dict.fromkeys(labels, 0)
        try:
            for item in items:
                self._insert_document(generation, item)
                label = item["entity_type"]
                counts[label] = counts.get(label, 0) + 1
                if sum(counts.values()) % 200 == 0:
                    self.session.commit()
            self.session.execute(delete(states).where(states.c.space == space))
            self.session.execute(
                insert(states).values(
                    space=space,
                    generation=generation,
                    revision=generation,
                    ready=1,
                    type_counts=json.dumps(counts, ensure_ascii=False),
                )
            )
            self.session.commit()
        except BaseException:
            self.session.rollback()
            self.remove_generation(generation)
            raise
        return {"generation": generation, "typeCounts": counts, "total": sum(counts.values())}

    def remove_generation(self, generation: str) -> None:
        for table in (grams, fields, documents):
            self.session.execute(delete(table).where(table.c.generation == generation))
        self.session.commit()

    def _matches(self, generation: str, keyword: str, entity_type: str | None, match_mode: str):
        needle = normalized(keyword.strip())
        query = select(fields.c.document_id).where(fields.c.generation == generation)
        if match_mode == "exact":
            query = query.where(fields.c.exact_hash == digest(needle), fields.c.value == needle)
        else:
            # Drive from the posting index, rather than scanning every field.
            width = min(3, len(needle))
            query_tokens = sorted(tokens(needle, (width,)))
            # Distributed samples reduce common-prefix candidate sets.
            sampled = (
                query_tokens
                if len(query_tokens) <= 8
                else [query_tokens[i * (len(query_tokens) - 1) // 7] for i in range(8)]
            )
            posting = (
                select(grams.c.field_id)
                .where(grams.c.generation == generation, grams.c.token.in_(sampled))
                .group_by(grams.c.field_id)
                .having(func.count() == len(sampled))
            )
            query = query.where(fields.c.id.in_(posting), func.instr(fields.c.value, needle) > 0)
        return select(documents).where(
            documents.c.generation == generation,
            documents.c.id.in_(query),
            *([documents.c.entity_type == entity_type] if entity_type else []),
        )

    def plan(
        self,
        space: str,
        keyword: str,
        entity_type: str | None,
        generation: str | None = None,
        match_mode: str | None = None,
    ):
        if not keyword.strip():
            raise LiteralIndexError("关键词不能为空")
        state = self.state(space)
        active = state["generation"]
        version = state["revision"]
        if generation is not None and generation != version:
            raise LiteralIndexError("文字索引已更新，请重新查询")
        if entity_type and entity_type not in json.loads(state["type_counts"]):
            raise LiteralIndexError(f"图空间中不存在实体类型: {entity_type}")
        if match_mode is None:
            exact = self._matches(active, keyword, entity_type, "exact")
            match_mode = (
                "exact"
                if self.session.execute(exact.with_only_columns(documents.c.id).limit(1)).first()
                else "contains"
            )
        if match_mode not in {"exact", "contains"}:
            raise LiteralIndexError("非法文字匹配模式")
        return version, match_mode, self._matches(active, keyword, entity_type, match_mode)

    def page(
        self,
        *,
        space: str,
        keyword: str,
        entity_type: str | None = None,
        limit: int = 10,
        offset: int = 0,
    ) -> dict:
        generation, mode, query = self.plan(space, keyword, entity_type)
        rows = (
            self.session.execute(
                query.order_by(documents.c.entity_type, documents.c.vid, documents.c.id)
                .offset(offset)
                .limit(limit + 1)
            )
            .mappings()
            .all()
        )
        has_more = len(rows) > limit
        # A short first page proves the exact count without a COUNT query.
        total = len(rows) if offset == 0 and not has_more else None
        return {
            "items": [json.loads(row["payload"]) for row in rows[:limit]],
            "total": total,
            "totalStatus": "ready" if total is not None else "pending",
            "hasMore": has_more,
            "generation": generation,
            "matchMode": mode,
            "returned": min(len(rows), limit),
            "offset": offset,
            "limit": limit,
            "keyword": keyword.strip(),
            "entityType": entity_type,
            "graphSpace": space,
            "mode": "keyword",
        }

    def count(
        self,
        *,
        space: str,
        keyword: str,
        entity_type: str | None = None,
        generation: str | None = None,
        match_mode: str | None = None,
    ) -> dict:
        generation, mode, query = self.plan(space, keyword, entity_type, generation, match_mode)
        total = self.session.scalar(select(func.count()).select_from(query.subquery()))
        return {"total": total, "totalStatus": "ready", "generation": generation, "matchMode": mode}

    def sync_node(self, space: str, node: Any = None, *, vid: str | None = None) -> None:
        state = self.state(space, require_ready=False)
        generation = state["generation"]
        node_id = str(node.id) if node is not None else str(vid)
        old_labels = list(
            self.session.scalars(
                select(documents.c.entity_type).where(
                    documents.c.generation == generation, documents.c.vid == node_id
                )
            )
        )
        doc_ids = select(documents.c.id).where(
            documents.c.generation == generation, documents.c.vid == node_id
        )
        field_ids = select(fields.c.id).where(fields.c.document_id.in_(doc_ids))
        self.session.execute(delete(grams).where(grams.c.field_id.in_(field_ids)))
        self.session.execute(delete(fields).where(fields.c.document_id.in_(doc_ids)))
        self.session.execute(
            delete(documents).where(
                documents.c.generation == generation, documents.c.vid == node_id
            )
        )
        if node is not None:
            for label in node.labels:
                self._insert_document(
                    generation,
                    {
                        "vid": node_id,
                        "entity_type": label,
                        "props": node.properties or {},
                    },
                )
        counts = json.loads(state["type_counts"])
        for label in old_labels:
            counts[label] = max(0, counts.get(label, 0) - 1)
        for label in node.labels if node is not None else []:
            counts[label] = counts.get(label, 0) + 1
        self.session.execute(
            update(states)
            .where(states.c.space == space)
            .values(type_counts=json.dumps(counts, ensure_ascii=False))
        )
