"""Paper 实体抽取步：gkx_kg_sm.sm_paper → gkx_kg_sm 图空间（自包含单文件）。

kg.schema.extract 平台喂数管道直传可用：payload["rows"] → {"entities": [...]}。
vid = paper_{pk}（与 kg_edge 端点约定一致）；props = 表全列（extra_json 除外）+ 平台身份列 id/name。
"""

from __future__ import annotations

import json

from kg_sdk import step

SOURCES = [dict(table="sm_paper", pk="id", time="")]

_COLS = [('id', 'string'), ('title_zh', 'string'), ('title_en', 'string'), ('doi', 'string'), ('publication_year', 'string'), ('publication_date', 'string'), ('language', 'string'), ('document_type', 'string'), ('publication_type', 'string'), ('publication_id', 'int64'), ('volume', 'string'), ('issue', 'string'), ('start_page', 'string'), ('end_page', 'string'), ('is_oa', 'string'), ('source_url', 'string'), ('source', 'string'), ('created_time', 'string'), ('updated_time', 'string'), ('output_awards', 'string'), ('source_system', 'string'), ('source_table', 'string'), ('source_record_id', 'string'), ('ingest_batch', 'string'), ('ingest_time', 'string'), ('source_update_time', 'string'), ('match_method', 'string'), ('match_evidence', 'string'), ('organization_base', 'string'), ('organization_id', 'string'), ('related_dois', 'string'), ('author_ids', 'string'), ('keyword_ids', 'string')]
_NAME_COL = 'title_zh'
_VID_PREFIX = "paper_"


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
                for cand_col in ('title_zh', 'title_en'):
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
