"""Person 实体抽取步：gkx_kg_sm.sm_person → gkx_kg_sm 图空间（自包含单文件）。

kg.schema.extract 平台喂数管道直传可用：payload["rows"] → {"entities": [...]}。
vid = person_{pk}（与 kg_edge 端点约定一致）；props = 表全列（extra_json 除外）+ 平台身份列 id/name。
"""

from __future__ import annotations

import json

from kg_sdk import step

SOURCES = [dict(table="sm_person", pk="person_id", time="")]

_COLS = [('person_id', 'string'), ('name_en', 'string'), ('name_zh', 'string'), ('name_cn', 'string'), ('email', 'string'), ('source', 'string'), ('person_kind', 'string'), ('country_code', 'string'), ('country', 'string'), ('birth_date', 'string'), ('gender', 'string'), ('biography', 'string'), ('bio_zh', 'string'), ('avatar', 'string'), ('scholar_org', 'string'), ('paper_nums', 'int64'), ('citation_nums', 'int64'), ('h_index', 'int64'), ('scholar_status', 'int64'), ('is_academician', 'string'), ('research_fields', 'string'), ('work_experience_date', 'string'), ('work_experience_institution_en', 'string'), ('work_experience_department_en', 'string'), ('work_experience_position_en', 'string'), ('work_experience_institution_zh', 'string'), ('work_experience_department_zh', 'string'), ('work_experience_position_zh', 'string'), ('education_background_date', 'string'), ('education_background_institution_en', 'string'), ('education_background_degree_en', 'string'), ('education_background_institution_zh', 'string'), ('education_background_degree_zh', 'string'), ('source_system', 'string'), ('source_table', 'string'), ('source_record_id', 'string'), ('source_url', 'string'), ('ingest_batch', 'string'), ('ingest_time', 'string'), ('source_update_time', 'string'), ('match_method', 'string'), ('match_evidence', 'string'), ('organization_base', 'string'), ('organization_id', 'string'), ('coauthor_ids', 'string'), ('affiliation_org_ids', 'string'), ('scholar_org_name_zh', 'string'), ('scholar_org_name_en', 'string')]
_NAME_COL = 'name_zh'
_VID_PREFIX = "person_"


def _vid(row):
    v = row.get("person_id")
    if v in (None, ""):
        return ""
    return _VID_PREFIX + str(v)


def _plain(v):
    if hasattr(v, "isoformat"):
        return v.isoformat(sep=" ")
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)
    return v


@step
def extract(payload):
    rows = payload.get("rows") or []
    entities, failures = [], []
    for row in rows:
        rid = str(row.get("person_id") or "row")
        try:
            vid = _vid(row)
            if not vid:
                raise ValueError("person_id 为空，跳过")
            props = {"id": vid}
            for col, _t in _COLS:
                if col == "id":
                    continue
                v = row.get(col)
                if v is not None:
                    props[col] = _plain(v)
            name_v = ""
            if _NAME_COL:
                v = row.get(_NAME_COL)
                if v not in (None, ""):
                    name_v = str(_plain(v))
            if not name_v:
                for cand_col in ('name_zh', 'name_en', 'name_cn'):
                    cand = row.get(cand_col)
                    if cand not in (None, ""):
                        name_v = str(_plain(cand))
                        break
            props["name"] = name_v
            entities.append({"id": vid, "props": props})
        except Exception as exc:
            failures.append({"recordId": rid, "error": (type(exc).__name__ + ": " + str(exc))[:500]})
    return {
        "entities": entities,
        "failures": failures,
        "stats": {"rows": len(rows), "entities": len(entities), "failed": len(failures)},
    }
