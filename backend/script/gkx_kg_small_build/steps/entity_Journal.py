"""Journal 实体抽取步：gkx_kg_sm.sm_journal → gkx_kg_sm 图空间（自包含单文件）。

kg.schema.extract 平台喂数管道直传可用：payload["rows"] → {"entities": [...]}。
vid = journal_{pk}（与 kg_edge 端点约定一致）；props = 表全列（extra_json 除外）+ 平台身份列 id/name。
"""

from __future__ import annotations

import json

from kg_sdk import step

SOURCES = [dict(table="sm_journal", pk="publication_id", time="")]

_COLS = [('publication_id', 'int64'), ('name_zh', 'string'), ('name_en', 'string'), ('name_abbr', 'string'), ('issn', 'string'), ('eissn', 'string'), ('country', 'string'), ('founding_time', 'int64'), ('impact_factor', 'double'), ('is_sci', 'int64'), ('jcr_zone', 'string'), ('scope_zone', 'string'), ('sub_quartile', 'int64'), ('top', 'int64'), ('zh_core', 'string'), ('cite_nums', 'int64'), ('annual_publication', 'int64'), ('publication_cycle', 'string'), ('source', 'string'), ('source_system', 'string'), ('source_table', 'string'), ('source_record_id', 'string'), ('ingest_batch', 'string'), ('ingest_time', 'string'), ('source_update_time', 'string')]
_NAME_COL = 'name_zh'
_VID_PREFIX = "journal_"


def _vid(row):
    v = row.get("publication_id")
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
        rid = str(row.get("publication_id") or "row")
        try:
            vid = _vid(row)
            if not vid:
                raise ValueError("publication_id 为空，跳过")
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
                for cand_col in ('name_zh', 'name_en', 'name_abbr'):
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
