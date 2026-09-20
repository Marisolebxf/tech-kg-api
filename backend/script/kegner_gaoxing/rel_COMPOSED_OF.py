"""组成包含关系抽取：kegner.relations 中 relation_type=组成/包含 的行。"""
from typing import Any, Mapping

from kg_sdk import step

RELATION_TYPE = "组成/包含"


@step
def emit_edges(payload: Mapping[str, Any]) -> dict[str, Any]:
    rows = payload.get("rows") or []
    edges, failures = [], []
    for row in rows:
        if str(row.get("relation_type") or "") != RELATION_TYPE:
            # 其他类型关系由各自 Schema 的脚本处理，这里静默放行
            continue
        src, dst = row.get("subject_entity_id"), row.get("object_entity_id")
        if not src or not dst:
            # 源表残缺端点行（无 subject/object 实体 id）静默跳过，不产生审核 case
            continue
        try:
            edges.append(
                {
                    "fromId": str(src),
                    "toId": str(dst),
                    "props": {
                        "relation_label": RELATION_TYPE,
                        "raw_predicate": str(row.get("raw_predicate") or ""),
                        "trigger_word": str(row.get("trigger_word") or ""),
                        "evidence_sentence": str(row.get("evidence_sentence") or ""),
                        "confidence": float(row.get("confidence") or 0.0),
                        "document_id": int(row.get("document_id") or 0),
                    },
                }
            )
        except (TypeError, ValueError) as exc:
            failures.append({"recordId": str(row.get("id") or "?"), "error": f"{type(exc).__name__}: {exc}"})
    return {"edges": edges, "failures": failures}
