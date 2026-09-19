"""面向外部系统的项目关系查询业务服务。"""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

from biz.schemas.project_relation import (
    ProjectData,
    ProjectRelationItem,
    ProjectRelationPage,
    ProjectRelationQueryRequest,
    RelatedEntityData,
    RelationData,
)
from infra.graph_db import TRSGraphClient

ALLOWED_RELATIONS = (
    "FUNDED_BY",
    "LEADS",
    "HAS_PARTICIPANT",
    "HAS_KEYWORD",
    "HAS_OUTPUT",
)
RELATION_NAMES = {
    "FUNDED_BY": "项目资助机构",
    "LEADS": "项目负责人",
    "HAS_PARTICIPANT": "项目参与人",
    "HAS_KEYWORD": "项目关键词",
    "HAS_OUTPUT": "项目产出成果",
}
ENTITY_NAME_KEYS = {
    "Organization": ("name_cn", "name_zh", "name_en", "name"),
    "Person": ("name_zh", "name_cn", "name_en", "name"),
    "Keyword": ("keyword", "name"),
    "Paper": ("title_zh", "title_en", "title"),
    "Patent": ("title_zh", "title_en", "title", "publication_number"),
    "Report": ("title_zh", "title_en", "title"),
}
RELATION_PROPERTY_KEYS = {
    "FUNDED_BY": ("funded_amount", "fund_category", "confidence"),
    "LEADS": ("confidence",),
    "HAS_PARTICIPANT": ("confidence",),
    "HAS_KEYWORD": ("confidence",),
    "HAS_OUTPUT": ("output_type", "output_title", "output_identifier", "confidence"),
}


class InvalidCursorError(ValueError):
    """游标格式错误或不属于当前筛选条件。"""


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip('"')


class ProjectRelationService:
    def __init__(self, client: TRSGraphClient) -> None:
        self._client = client

    def query(self, body: ProjectRelationQueryRequest) -> ProjectRelationPage:
        relation_types = tuple(body.relationTypes) or ALLOWED_RELATIONS
        fingerprint = self._fingerprint(body, relation_types)
        offset = self._decode_cursor(body.cursor, fingerprint)
        query, params = self._build_query(body, relation_types, offset)
        records = self._client.execute_read(query, params=params).records
        has_more = len(records) > body.pageSize
        records = records[: body.pageSize]
        items = [self._record_to_item(record) for record in records]
        next_cursor = self._encode_cursor(offset + body.pageSize, fingerprint) if has_more else ""
        return ProjectRelationPage(
            items=items,
            pageSize=body.pageSize,
            nextCursor=next_cursor,
            hasMore=has_more,
        )

    @staticmethod
    def _fingerprint(
        body: ProjectRelationQueryRequest, relation_types: tuple[str, ...]
    ) -> str:
        filters = {
            "keyword": body.keyword or "",
            "projectNumber": body.projectNumber or "",
            "relationTypes": sorted(relation_types),
        }
        raw = json.dumps(filters, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()[:24]

    @staticmethod
    def _encode_cursor(offset: int, fingerprint: str) -> str:
        raw = json.dumps(
            {"v": 1, "offset": offset, "filter": fingerprint}, separators=(",", ":")
        ).encode()
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    @staticmethod
    def _decode_cursor(cursor: str | None, fingerprint: str) -> int:
        if not cursor:
            return 0
        try:
            raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
            payload = json.loads(raw)
            offset = payload["offset"]
            if payload.get("v") != 1 or payload.get("filter") != fingerprint:
                raise InvalidCursorError("游标与当前筛选条件不一致")
            if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
                raise InvalidCursorError("游标中的分页位置无效")
            return offset
        except InvalidCursorError:
            raise
        except (KeyError, TypeError, ValueError) as exc:
            raise InvalidCursorError("游标格式无效") from exc

    @staticmethod
    def _build_query(
        body: ProjectRelationQueryRequest,
        relation_types: tuple[str, ...],
        offset: int,
    ) -> tuple[str, dict[str, Any]]:
        # 边类型只能来自 Pydantic Literal 白名单，因此可安全编译到查询结构中。
        edge_types = "|".join(f"`{item}`" for item in relation_types)
        conditions: list[str] = []
        params: dict[str, Any] = {}
        if body.projectNumber:
            conditions.append("p.Project.project_number == $project_number")
            params["project_number"] = body.projectNumber
        elif body.keyword:
            conditions.append(
                "(p.Project.title CONTAINS $keyword OR "
                "p.Project.project_number CONTAINS $keyword)"
            )
            params["keyword"] = body.keyword
        where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        query = (
            f"MATCH (p:`Project`)-[r:{edge_types}]->(related)"
            f"{where} "
            "RETURN id(p) AS project_id, properties(p) AS project_properties, "
            "type(r) AS relation_type, properties(r) AS relation_properties, "
            "id(related) AS related_id, labels(related) AS related_labels, "
            "properties(related) AS related_properties "
            "ORDER BY project_id, relation_type, related_id "
            f"SKIP {offset} LIMIT {body.pageSize + 1}"
        )
        return query, params

    @staticmethod
    def _record_to_item(record: dict[str, Any]) -> ProjectRelationItem:
        project = _as_dict(record.get("project_properties"))
        relation = _as_dict(record.get("relation_properties"))
        related = _as_dict(record.get("related_properties"))
        relation_type = _text(record.get("relation_type"))
        raw_labels = record.get("related_labels") or []
        if isinstance(raw_labels, str):
            try:
                raw_labels = json.loads(raw_labels)
            except ValueError:
                raw_labels = [raw_labels]
        labels = [_text(label) for label in raw_labels]
        entity_type = next((label for label in labels if label in ENTITY_NAME_KEYS), "")
        name = next(
            (_text(related.get(key)) for key in ENTITY_NAME_KEYS.get(entity_type, ()) if related.get(key)),
            "",
        )
        allowed_props = RELATION_PROPERTY_KEYS.get(relation_type, ())
        relation_properties = {
            key: relation[key] for key in allowed_props if key in relation and relation[key] is not None
        }
        return ProjectRelationItem(
            project=ProjectData(
                id=_text(record.get("project_id")),
                projectNumber=_text(project.get("project_number")),
                title=_text(project.get("title")),
                projectSource=_text(project.get("project_source")),
                projectLevel=_text(project.get("project_level")),
                approvalYear=_text(project.get("approval_year")),
                researchPeriod=_text(project.get("research_period")),
            ),
            relation=RelationData(
                type=relation_type,
                name=RELATION_NAMES[relation_type],
                properties=relation_properties,
            ),
            relatedEntity=RelatedEntityData(
                id=_text(record.get("related_id")),
                type=entity_type,
                name=name,
                properties={},
            ),
        )
