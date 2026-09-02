"""One-relation transform for AFFILIATED_WITH（Person → Organization）（平台喂数抽取：只输出边 JSON）.

复刻旧 load_scholar_relations.py 口径：dwd_scholar（status=1），机构端优先
``scholar_org_id`` 直连（confidence=1.0），否则机构名 md5 16 位桩 VID
（confidence=0.6，桩顶点可不存在，后续由 SAME_AS 对齐认领）；
REST merge_edge 按 source_record_id 幂等。

"""

import hashlib
from typing import Any

from script.extract_transform_common import edge_transform
from script.relation_extractors_one_relation.common import (
    EdgeRecord,
    now_utc,
)

# 旧 ensure_schema 补齐的边属性（类型与 dwd_scholar 源一致）。
EDGE_SCHEMA = {
    "affiliation_name": "string",
    "work_experience_date": "string",
    "work_experience_department_zh": "string",
    "work_experience_position_zh": "string",
    "source": "string",
    "source_table": "string",
    "source_record_id": "string",
    "ingest_batch": "string",
    "ingest_time": "string",
    "organization_base": "string",
    "organization_id": "string",
    "confidence": "double",
    "match_method": "string",
    "match_evidence": "string",
}

_PROBE_COLUMNS = (
    "scholar_org_id",
    "work_experience_date",
    "work_experience_department_zh",
    "work_experience_position_zh",
    "scholar_org_name_zh",
    "scholar_org_name_en",
)


def _org_vid(scholar_org_id: str | None, org_name: str | None) -> str | None:
    """旧 org_vid：优先机构 ID，否则机构名小写 md5 前 16 位桩。"""
    if scholar_org_id and scholar_org_id.strip():
        return f"org_{scholar_org_id.strip()}"
    if org_name and org_name.strip():
        key = org_name.strip().lower()
        return f"org_{hashlib.md5(key.encode('utf-8')).hexdigest()[:16]}"
    return None


def affiliated_with(table: str, row: dict, batch: str) -> list[EdgeRecord]:
    sid = str(row.get("scholar_id") or "").strip()
    org_name = str(row.get("scholar_org_name_zh") or row.get("scholar_org_name_en") or "")
    dst = _org_vid(str(row.get("scholar_org_id")) if row.get("scholar_org_id") else None, org_name)
    if not sid or not dst:
        return []
    has_org_id = bool(row.get("scholar_org_id") and str(row.get("scholar_org_id")).strip())
    if has_org_id:
        confidence = 1.0
        method = "source_org_id"
        evidence = "dwd_scholar.scholar_org_id 直接指向机构，无需名称推断"
    else:
        confidence = 0.6
        method = "org_name_md5_placeholder"
        evidence = (
            "源表无 scholar_org_id，机构顶点按机构名 md5 生成桩 VID，待正式 Organization 落地后对齐"
        )
    props = {
        "affiliation_name": org_name,
        "work_experience_date": row.get("work_experience_date") or "",
        "work_experience_department_zh": row.get("work_experience_department_zh") or "",
        "work_experience_position_zh": row.get("work_experience_position_zh") or "",
        "source": "scholar",
        "source_table": "dwd_scholar",
        "source_record_id": sid,
        "ingest_batch": batch,
        "ingest_time": now_utc(),
        "organization_base": "dwd_scholar" if has_org_id else "",
        "organization_id": str(row.get("scholar_org_id") or "").strip(),
        "confidence": confidence,
        "match_method": method,
        "match_evidence": evidence,
    }
    return [
        EdgeRecord(
            "AFFILIATED_WITH",
            f"person_{sid}",
            dst,
            props,
            identity={"source_record_id": sid},
            # 桩端点允许悬空（旧口径不做端点验存）。
            validate_endpoints=False,
        )
    ]


SOURCES = [
    {
        "table": "dwd_scholar",
        "pk": "scholar_id",
        "time": "update_time",
        # 旧 _build_sql 口径：dwd_scholar 无 scholar_org_id（缺列 NULL 兜底），
        # 其余工作经历列真实存在，SELECT * 即可
        "query_sql": "SELECT s.*, NULL AS scholar_org_id FROM dwd_scholar s WHERE status = 1",
    },
]


def transform(payload: dict[str, Any]) -> dict[str, Any]:
    """kg.schema.extract 转换入口：rows → edges JSON。"""
    return edge_transform(payload, builder=affiliated_with)
