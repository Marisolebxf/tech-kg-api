"""AFFILIATED_WITH 关系抽取步：gkx_kg_sm.sm_edge → gkx_kg_sm 图空间（自包含单文件）。

kg.schema.extract 平台喂数管道直传可用：payload["rows"] → {"edges": [...]}。
端点 vid 直接沿用 kg_edge 的 src_id/dst_id；props 取行内 props JSON 展开。
"""

from __future__ import annotations

import json

from kg_sdk import step

SOURCES = [dict(table="sm_edge", pk="_pk", time="", query_sql="""SELECT CONCAT_WS('|', src_id, dst_id, edge_rank) AS _pk, edge_type, src_id, dst_id, edge_rank, CAST(props AS CHAR) AS props_json FROM sm_edge WHERE edge_type = 'AFFILIATED_WITH'""")]

_PROP_TYPES = {'source': 'str', 'confidence': 'float', 'create_time': 'str', 'ingest_time': 'str', 'update_time': 'str', 'ingest_batch': 'str', 'match_method': 'str', 'source_table': 'str', 'match_evidence': 'str', 'organization_id': 'str', 'affiliation_name': 'str', 'source_record_id': 'str', 'organization_base': 'str', 'work_experience_date': 'str', 'work_experience_position_zh': 'str', 'work_experience_department_zh': 'str'}


@step
def extract(payload):
    rows = payload.get("rows") or []
    edges, failures = [], []
    for row in rows:
        rid = str(row.get("_pk") or "row")
        try:
            src, dst = row.get("src_id"), row.get("dst_id")
            if not src or not dst:
                raise ValueError("端点为空，跳过")
            props = {}
            pj = row.get("props_json")
            if pj:
                try:
                    parsed = json.loads(pj) if isinstance(pj, str) else pj
                    if isinstance(parsed, dict):
                        for k, v in parsed.items():
                            if v is None or k in ("rank",):
                                continue
                            props[str(k)] = v
                except Exception:
                    pass
            edges.append({"fromId": str(src), "toId": str(dst), "props": props})
        except Exception as exc:
            failures.append({"recordId": rid, "error": (type(exc).__name__ + ": " + str(exc))[:500]})
    return {
        "edges": edges,
        "failures": failures,
        "stats": {"rows": len(rows), "edges": len(edges), "failed": len(failures)},
    }
