"""资料文档实体抽取：kegner.entities 中 type_code=DOCUMENT 的行。"""
from typing import Any, Mapping

from kg_sdk import step

TYPE_CODE = "DOCUMENT"


@step
def emit_entities(payload: Mapping[str, Any]) -> dict[str, Any]:
    rows = payload.get("rows") or []
    entities, failures = [], []
    for row in rows:
        if str(row.get("type_code") or "") != TYPE_CODE:
            # 其他类型实体由各自 Schema 的脚本处理，这里静默放行
            continue
        try:
            entities.append(
                {
                    "id": str(row["id"]),
                    "props": {
                        "id": str(row["id"]),
                        "name": str(row.get("name") or ""),
                        "standard_zh": str(row.get("standard_zh") or ""),
                        "standard_en": str(row.get("standard_en") or ""),
                        "context_text": str(row.get("context_text") or ""),
                        "confidence": float(row.get("confidence") or 0.0),
                        "document_id": int(row.get("document_id") or 0),
                    },
                }
            )
        except (KeyError, TypeError, ValueError) as exc:
            failures.append({"recordId": str(row.get("id") or "?"), "error": f"{type(exc).__name__}: {exc}"})
    return {"entities": entities, "failures": failures}
