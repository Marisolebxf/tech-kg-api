"""Report 实体抽取步：gkx_kg_sm.sm_report → gkx_kg_sm 图空间（自包含单文件）。

kg.schema.extract 平台喂数管道直传可用：payload["rows"] → {"entities": [...]}。
vid = report_{pk}（与 kg_edge 端点约定一致）；props = 表全列（extra_json 除外）+ 平台身份列 id/name。
"""

from __future__ import annotations

import json

from kg_sdk import step

SOURCES = [dict(table="sm_report", pk="report_id", time="")]

_COLS = [('report_id', 'string'), ('title_cn', 'string'), ('abstract_cn', 'string'), ('keywords_cn', 'string'), ('report_type', 'string'), ('report_category', 'string'), ('approval_year', 'int64'), ('preparation_time', 'string'), ('project_annual_number', 'int64'), ('contact_phone', 'string'), ('source_org', 'string'), ('related_institutions', 'string'), ('related_paper_id', 'string'), ('related_project_id', 'string'), ('related_projects', 'string'), ('visibility_scope', 'string'), ('title_en', 'string'), ('abstract_en', 'string'), ('keywords_en', 'string'), ('category', 'string'), ('document_type', 'string'), ('report_number', 'string'), ('contract_number', 'string'), ('corporate_author', 'string'), ('author_id', 'string'), ('country', 'string'), ('pub_year', 'int64'), ('publication_date', 'string'), ('source_agency', 'string'), ('related_literature_id', 'string'), ('authors', 'string'), ('organization', 'string'), ('content', 'string'), ('page_count', 'int64'), ('related_author_id', 'string'), ('related_authors', 'string'), ('related_literature', 'string'), ('related_org_id', 'string'), ('file_path', 'string'), ('file_type', 'string'), ('source_url', 'string'), ('dwd_id', 'int64'), ('table_data_source', 'string'), ('is_deleted', 'int64'), ('insert_remark', 'int64'), ('operator_remarks', 'string'), ('creater', 'string'), ('updater', 'string'), ('created_time', 'string'), ('updated_time', 'string')]
_NAME_COL = 'title_cn'
_VID_PREFIX = "report_"


def _vid(row):
    v = row.get("report_id")
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
        rid = str(row.get("report_id") or "row")
        try:
            vid = _vid(row)
            if not vid:
                raise ValueError("report_id 为空，跳过")
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
                for cand_col in ('title_cn', 'title_en'):
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
