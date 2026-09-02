"""One-entity transform for Person（平台喂数抽取：脚本只输出实体 JSON）。

四个来源分别复刻旧脚本口径（按来源表名分发 mapper）：

- ``dwd_scholar``（自定义聚合 SQL，status=1）→ scholar_person；
- ``dwd_zh_author`` / ``dwd_en_author`` → paper_author_person；
- PERSON_TABLES（机构任职）→ organization_role_person（mappers）；
- ORGANIZATION_TABLES（法定代表人）→ legal_representative_person（mappers）。
"""

import re
from collections.abc import Mapping
from typing import Any

from script.entity_extractors_one_entity.common import (
    EntityRecord,
    extra_json,
    provenance,
    text_or_empty,
)
from script.entity_extractors_one_entity.mappers import (
    legal_representative_person,
    organization_role_person,
)
from script.entity_extractors_one_entity.org_catalog import ORGANIZATION_TABLES, PERSON_TABLES
from script.extract_transform_common import entity_transform

SCHOLAR_QUERY_SQL = """
SELECT s.*,
       (SELECT tf.academician FROM dwd_scholar_talent_flag tf
          WHERE tf.scholar_id = s.scholar_id ORDER BY tf.update_time DESC LIMIT 1) AS academician,
       (SELECT GROUP_CONCAT(rd.fields ORDER BY rd.create_time SEPARATOR '；')
          FROM dwd_scholar_research_direction rd WHERE rd.scholar_id = s.scholar_id)
         AS research_fields
FROM dwd_scholar s
WHERE s.status = 1
"""

_SUFFIX_RE = re.compile(r"__\d+$")


def scholar_person(table: str, row: Mapping[str, Any], batch: str) -> list[EntityRecord]:
    sid = row.get("scholar_id")
    if not sid:
        return []
    sid = str(sid).strip()
    vid = f"person_{sid}"
    props = {
        "name_en": text_or_empty(row.get("name_en")),
        "name_zh": text_or_empty(row.get("name_zh")),
        "email": "",
        "source": "scholar",
        "avatar": text_or_empty(row.get("avatar")),
        "scholar_org": text_or_empty(
            row.get("scholar_org_name_zh") or row.get("scholar_org_name_en")
        ),
        "bio_zh": text_or_empty(row.get("bio_zh")),
        "biography": text_or_empty(row.get("bio")),
        "paper_nums": int(row.get("paper_nums") or 0),
        "citation_nums": int(row.get("citation_nums") or 0),
        "h_index": int(row.get("h_index") or 0),
        "scholar_status": int(row.get("status") or 0),
        "is_academician": text_or_empty(row.get("academician")),
        "research_fields": text_or_empty(row.get("research_fields")),
        "work_experience_date": text_or_empty(row.get("work_experience_date")),
        "work_experience_institution_en": text_or_empty(row.get("work_experience_institution_en")),
        "work_experience_department_en": text_or_empty(row.get("work_experience_department_en")),
        "work_experience_position_en": text_or_empty(row.get("work_experience_position_en")),
        "work_experience_institution_zh": text_or_empty(row.get("work_experience_institution_zh")),
        "work_experience_department_zh": text_or_empty(row.get("work_experience_department_zh")),
        "work_experience_position_zh": text_or_empty(row.get("work_experience_position_zh")),
        "education_background_date": text_or_empty(row.get("education_background_date")),
        "education_background_institution_en": text_or_empty(
            row.get("education_background_institution_en")
        ),
        "education_background_degree_en": text_or_empty(row.get("education_background_degree_en")),
        "education_background_institution_zh": text_or_empty(
            row.get("education_background_institution_zh")
        ),
        "education_background_degree_zh": text_or_empty(row.get("education_background_degree_zh")),
        "organization_id": text_or_empty(row.get("scholar_org_id")),
        "extra_json": extra_json(row),
        **provenance(
            table=table,
            record_id=sid,
            ingest_batch=batch,
            source_update_time=row.get("update_time"),
        ),
    }
    return [EntityRecord("Person", vid, props)]


def paper_author_person(table: str, row: Mapping[str, Any], batch: str) -> list[EntityRecord]:
    aid = row.get("author_id")
    paper_id = row.get("paper_id")
    # 旧口径：paper_id 去掉 __数字 后缀后与 author_id 均非空才建点。
    if not aid or not _SUFFIX_RE.sub("", str(paper_id or "")):
        return []
    vid = f"person_{aid}"
    props = {
        "name_zh": text_or_empty(row.get("zh_name")),
        "name_en": text_or_empty(row.get("en_name")),
        "extra_json": extra_json(row),
        **provenance(table=table, record_id=vid, ingest_batch=batch),
    }
    return [EntityRecord("Person", vid, props)]


MAPPER_BY_TABLE: dict[str, Any] = {
    "dwd_scholar": scholar_person,
    "dwd_zh_author": paper_author_person,
    "dwd_en_author": paper_author_person,
    **{table: organization_role_person for table in PERSON_TABLES},
    **{table: legal_representative_person for table in ORGANIZATION_TABLES},
}

SOURCES = [
    {
        "table": "dwd_scholar",
        "pk": "scholar_id",
        "time": "update_time",
        "query_sql": SCHOLAR_QUERY_SQL,
    },
    {"table": "dwd_zh_author", "pk": "author_id", "time": "update_time"},
    {"table": "dwd_en_author", "pk": "author_id", "time": "update_time"},
    *[{"table": t, "pk": "id", "time": "update_time"} for t in PERSON_TABLES],
    *[{"table": t, "pk": "id", "time": "update_time"} for t in ORGANIZATION_TABLES],
]


def transform(payload: Mapping[str, Any]) -> dict[str, Any]:
    """kg.schema.extract 转换入口：payload["rows"] → {"entities": [...], "failures": [...]}。"""
    return entity_transform(payload, mapper_by_table=MAPPER_BY_TABLE)
