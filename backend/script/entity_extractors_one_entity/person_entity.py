"""One-entity extractor for Person.

三个来源分别复刻旧脚本口径：

- ``--source scholar``：旧 ``load_scholar_entities.py``（dwd_scholar，status=1）。
- ``--source paper-author``：旧 ``workflow/paper_journal_chain_etl.py``（论文作者，
  paper_id 去掉 ``__数字`` 后缀后与 author_id 均非空才建点，同 author 首次出现胜出）。
- ``--source organization-role``：旧 ``organization_entity_etl.py``（高管/股东/受益人/
  实控人各表 + 机构表的法定代表人，person_vid 旧公式）。
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from script.entity_extractors_one_entity.common import (
    EntityRecord,
    build_parser,
    configure_logging,
    extra_json,
    paper_text,
    print_json,
    provenance,
    run_entity_extractor,
    text_or_empty,
)
from script.entity_extractors_one_entity.mappers import (
    legal_representative_person,
    organization_role_person,
)
from script.entity_extractors_one_entity.org_catalog import ORGANIZATION_TABLES, PERSON_TABLES

_SUFFIX_RE = re.compile(r"__\d+$")

SCHOLAR_SQL = """
SELECT s.*,
       (SELECT tf.academician FROM dwd_scholar_talent_flag tf
          WHERE tf.scholar_id = s.scholar_id ORDER BY tf.id DESC LIMIT 1) AS academician,
       (SELECT GROUP_CONCAT(rd.fields ORDER BY rd.id SEPARATOR '；')
          FROM dwd_scholar_research_direction rd WHERE rd.scholar_id = s.scholar_id)
         AS research_fields
FROM dwd_scholar s
WHERE s.status = 1
ORDER BY s.scholar_id
"""


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
    # 旧口径：merge identity 除 vid 外还带 source_record_id。
    return [EntityRecord("Person", vid, props, identity={"vid": vid, "source_record_id": sid})]


def paper_author_person(table: str, row: Mapping[str, Any], batch: str) -> list[EntityRecord]:
    aid = row.get("author_id")
    paper_id = row.get("paper_id")
    # 旧口径：paper_id 去掉 __数字 后缀后与 author_id 均非空才建点。
    if not aid or not _SUFFIX_RE.sub("", str(paper_id or "")):
        return []
    vid = f"person_{aid}"
    props = {
        "name_zh": paper_text(row.get("zh_name")),
        "name_en": paper_text(row.get("en_name")),
        "extra_json": extra_json(row),
        **provenance(table=table, record_id=vid, ingest_batch=batch),
    }
    return [EntityRecord("Person", vid, props)]


def main() -> None:
    parser = build_parser(__doc__ or "")
    parser.add_argument(
        "--source",
        choices=("scholar", "paper-author", "organization-role"),
        default="scholar",
    )
    args = parser.parse_args()
    configure_logging(args.log_level)
    dedupe = None
    if args.source == "scholar":
        sources = [("dwd_scholar", SCHOLAR_SQL, scholar_person)]
    elif args.source == "paper-author":
        # 旧口径：同一 author_id 首次出现的姓名胜出。
        dedupe = "first"
        sources = [
            (
                "dwd_zh_author",
                "SELECT * FROM dwd_zh_author ORDER BY author_id",
                paper_author_person,
            ),
            (
                "dwd_en_author",
                "SELECT * FROM dwd_en_author ORDER BY author_id",
                paper_author_person,
            ),
        ]
    else:
        sources = [
            (table, f"SELECT * FROM {table} ORDER BY 1", organization_role_person)
            for table in PERSON_TABLES
        ] + [
            (table, f"SELECT * FROM {table} ORDER BY 1", legal_representative_person)
            for table in ORGANIZATION_TABLES
        ]
    print_json(
        run_entity_extractor(
            database=args.database,
            batch_size=args.batch_size,
            limit=args.limit,
            dry_run=args.dry_run,
            ingest_batch=args.ingest_batch,
            since=args.since,
            dedupe=dedupe,
            sources=sources,
        )
    )


if __name__ == "__main__":
    main()
