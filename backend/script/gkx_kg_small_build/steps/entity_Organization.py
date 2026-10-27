"""Organization 实体抽取步：gkx_kg_sm.sm_organization → gkx_kg_sm 图空间（自包含单文件）。

kg.schema.extract 平台喂数管道直传可用：payload["rows"] → {"entities": [...]}。
vid = org_{pk}（与 kg_edge 端点约定一致）；props = 表全列（extra_json 除外）+ 平台身份列 id/name。
"""

from __future__ import annotations

import json

from kg_sdk import step

SOURCES = [dict(table="sm_organization", pk="org_id", time="")]

_COLS = [('org_id', 'string'), ('name_cn', 'string'), ('name_en', 'string'), ('source', 'string'), ('external_id', 'string'), ('province', 'string'), ('city', 'string'), ('area', 'string'), ('country_code', 'string'), ('country', 'string'), ('address', 'string'), ('postal_code', 'string'), ('phone', 'string'), ('email', 'string'), ('legal_rep', 'string'), ('org_type', 'string'), ('org_size', 'string'), ('founded_year', 'int64'), ('listing_status', 'string'), ('listed_date', 'string'), ('registered_capital', 'double'), ('capital_currency', 'string'), ('industry_class', 'string'), ('stock_code', 'string'), ('stock_noun', 'string'), ('stock_type', 'string'), ('org_kind', 'string'), ('description', 'string'), ('main_products', 'string'), ('organization_base', 'string'), ('organization_id', 'string'), ('manual_disabled', 'int64'), ('correction_id', 'string'), ('corrected_at', 'string'), ('source_system', 'string'), ('source_table', 'string'), ('source_record_id', 'string'), ('source_url', 'string'), ('ingest_batch', 'string'), ('ingest_time', 'string'), ('source_update_time', 'string'), ('shareholders', 'string'), ('forg_subsidiaries', 'string'), ('sub_orgs', 'string'), ('industry_node_ids', 'string'), ('executives', 'string'), ('invests', 'string'), ('acquires', 'string'), ('actual_controllers', 'string'), ('beneficial_owners', 'string')]
_NAME_COL = 'name_cn'
_VID_PREFIX = "org_"


def _vid(row):
    v = row.get("org_id")
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
        rid = str(row.get("org_id") or "row")
        try:
            vid = _vid(row)
            if not vid:
                raise ValueError("org_id 为空，跳过")
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
                for cand_col in ('name_cn', 'name_en'):
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
