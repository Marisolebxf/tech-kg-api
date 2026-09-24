"""organization_base 溯源 mixin 抽取步（@step，yunfei_test 空间还原专用）。

复刻 ``script/paper_journal_relation/attach_provenance.py`` 的「真实实体」通道：
八张论文域源表 → 同名 vid 挂 organization_base mixin（confidence=1.0 + 溯源列，
organization_id 留空——论文表无 org_id 外键）：

  - dwd_zh_paper / dwd_en_paper               → ``paper_{id}``
  - dwd_zh_author / dwd_en_author             → ``person_{author_id}``
  - dwd_zh_journal / dwd_en_journal           → ``journal_{publication_id}``
  - dwd_zh_report / dwd_en_report             → ``report_{report_id}``
  - Keyword 域六源（与老一对一 keyword_entity 同源同 vid 公式 ``keyword_{md5}``，
    source_record_id 用 vid 本身，同 attach_provenance）

未复刻部分（见还原报告）：attach_provenance 的桩 vid（paper_ref_/cit_/rel_/rp_，
confidence=0.3，按图内前缀 MATCH）依赖 backfill_stub_journals 等脚本维护的桩点，
新空间无桩点可挂。mixin 无 name 键 → 平台同名消歧天然跳过，同一 vid 重复行由
INSERT VERTEX 幂等覆盖。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from kg_sdk import step

_VID_RULES: dict[str, tuple[str, str]] = {
    "dwd_zh_paper": ("paper_{}", "id"),
    "dwd_en_paper": ("paper_{}", "id"),
    "dwd_zh_author": ("person_{}", "author_id"),
    "dwd_en_author": ("person_{}", "author_id"),
    "dwd_zh_journal": ("journal_{}", "publication_id"),
    "dwd_en_journal": ("journal_{}", "publication_id"),
    "dwd_zh_report": ("report_{}", "report_id"),
    "dwd_en_report": ("report_{}", "report_id"),
}
_KEYWORD_TABLES = (
    "dwd_scholar_research_direction",
    "dwd_zh_paper_classification",
    "dwd_en_paper_classification",
    "dwd_zh_project",
    "dwd_en_project",
    "dwd_patent",  # query_sql 绑定（tableName 仍为 dwd_patent）
)
_INGEST_BATCH = "yunfei_restore_org_base"


def _mixin_props(source_table: str, source_record_id: str) -> dict[str, Any]:
    return {
        "organization_id": "",
        "confidence": 1.0,
        "source_system": "gkx_element",
        "source_table": source_table,
        "source_record_id": source_record_id,
        "source_url": "",
        "ingest_batch": _INGEST_BATCH,
        "ingest_time": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_update_time": "",
        "extra_json": "",
    }


@step
def emit(payload: Mapping[str, Any]) -> dict[str, Any]:
    source = payload.get("source") or {}
    table = str(payload.get("source_table") or source.get("tableName") or "")
    table = table.rsplit(".", 1)[-1]
    entities: list[dict[str, Any]] = []
    if table in _KEYWORD_TABLES:
        from script.entity_extractors_one_entity.mappers import keyword_records

        for row in payload.get("rows") or []:
            for record in keyword_records(table, row, _INGEST_BATCH):
                entities.append({"id": record.vid, "props": _mixin_props(table, record.vid)})
        return {"entities": entities}
    rule = _VID_RULES.get(table)
    if rule is None:
        raise RuntimeError(f"来源表 {table} 没有对应的 organization_base mixin 规则")
    template, id_column = rule
    for row in payload.get("rows") or []:
        raw_id = row.get(id_column)
        if raw_id is None or not str(raw_id).strip():
            continue
        record_id = str(raw_id).strip()
        entities.append(
            {"id": template.format(record_id), "props": _mixin_props(table, record_id)}
        )
    return {"entities": entities}
