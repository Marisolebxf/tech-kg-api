"""Patent 实体抽取步：gkx_kg_sm.sm_patent → gkx_kg_sm 图空间（自包含单文件）。

kg.schema.extract 平台喂数管道直传可用：payload["rows"] → {"entities": [...]}。
vid = patent_{pk}（与 kg_edge 端点约定一致）；props = 表全列（extra_json 除外）+ 平台身份列 id/name。
"""

from __future__ import annotations

import json

from kg_sdk import step

SOURCES = [dict(table="sm_patent", pk="patent_id", time="")]

_COLS = [('patent_id', 'string'), ('publication_number', 'string'), ('application_number', 'string'), ('application_kind', 'string'), ('country_code', 'string'), ('country', 'string'), ('publication_date', 'string'), ('application_date', 'string'), ('granted_number', 'string'), ('grant_date', 'string'), ('status', 'string'), ('anticipated_expiration', 'string'), ('title_original', 'string'), ('title_en', 'string'), ('title_zh', 'string'), ('abstract_zh', 'string'), ('language', 'string'), ('main_ipcr', 'string'), ('further_ipcr', 'string'), ('main_cpc', 'string'), ('further_cpc', 'string'), ('keywords', 'string'), ('citation_nums', 'int64'), ('cited_by_nums', 'int64'), ('patent_value', 'int64'), ('simple_family_number', 'string'), ('db_source', 'string'), ('create_time', 'string'), ('update_time', 'string'), ('title', 'string'), ('source', 'string'), ('output_awards', 'string'), ('evaluation', 'string'), ('source_system', 'string'), ('source_table', 'string'), ('source_record_id', 'string'), ('source_url', 'string'), ('ingest_batch', 'string'), ('ingest_time', 'string'), ('source_update_time', 'string'), ('match_method', 'string'), ('match_evidence', 'string'), ('organization_base', 'string'), ('organization_id', 'string'), ('inventors', 'string'), ('applicants', 'string'), ('assignees', 'string'), ('source_patent_row_id', 'string')]
_NAME_COL = 'title_zh'
_VID_PREFIX = "patent_"


def _vid(row):
    v = row.get("patent_id")
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
        rid = str(row.get("patent_id") or "row")
        try:
            vid = _vid(row)
            if not vid:
                raise ValueError("patent_id 为空，跳过")
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
                for cand_col in ('title_zh', 'title_en', 'title_original', 'title'):
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
