"""Project 实体抽取步：gkx_kg_sm.sm_project → gkx_kg_sm 图空间（自包含单文件）。

kg.schema.extract 平台喂数管道直传可用：payload["rows"] → {"entities": [...]}。
vid = project_{pk}（与 kg_edge 端点约定一致）；props = 表全列（extra_json 除外）+ 平台身份列 id/name。
"""

from __future__ import annotations

import json

from kg_sdk import step

SOURCES = [dict(table="sm_project", pk="id", time="")]

_COLS = [('id', 'string'), ('project_number', 'string'), ('title', 'string'), ('project_host', 'string'), ('project_source', 'string'), ('project_level', 'string'), ('funded_amount', 'double'), ('discipline', 'string'), ('discipline_code', 'string'), ('fund_category', 'string'), ('funded_region', 'string'), ('approval_year', 'string'), ('approval_time', 'string'), ('research_period', 'string'), ('abstract', 'string'), ('final_report_abstract', 'string'), ('project_page_url', 'string'), ('source', 'string'), ('total_outputs', 'int64'), ('journal_articles_count', 'int64'), ('conference_papers_count', 'int64'), ('books_count', 'int64'), ('degree_papers_count', 'int64'), ('patents_count', 'int64'), ('clinical_trials_count', 'int64'), ('products_count', 'int64'), ('awards_count', 'int64'), ('reports_count', 'int64'), ('other_outputs_count', 'int64'), ('output_awards', 'string'), ('keywords', 'string'), ('evaluation', 'string'), ('source_system', 'string'), ('source_table', 'string'), ('source_record_id', 'string'), ('source_url', 'string'), ('ingest_batch', 'string'), ('ingest_time', 'string'), ('source_update_time', 'string'), ('match_method', 'string'), ('match_evidence', 'string'), ('leader_person_ids', 'string'), ('participant_person_ids', 'string'), ('funded_org_ids', 'string'), ('participants', 'string'), ('funded_institution', 'string'), ('participating_institution', 'string'), ('output_journal_articles', 'string'), ('output_conference_papers', 'string'), ('output_degree_papers', 'string'), ('output_patents', 'string'), ('output_reports', 'string')]
_NAME_COL = 'title'
_VID_PREFIX = "project_"


def _vid(row):
    v = row.get("id")
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
        rid = str(row.get("id") or "row")
        try:
            vid = _vid(row)
            if not vid:
                raise ValueError("id 为空，跳过")
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
                for cand_col in ('title'):
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
