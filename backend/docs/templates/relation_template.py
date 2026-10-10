"""关系抽取脚本模板：一张来源表 → 一个关系 Schema（EDGE）。

只改「① 字段映射（配置区）」，② 逻辑处理与 ③ 输出契约保持通用即可。
完整规范（输入/输出契约、禁区、常见错误对照）见
backend/docs/抽取脚本编写规范.md。

关系脚本与实体脚本的配合要点：fromId/toId 必须与端点实体脚本产出的
vid 完全一致（含前缀），否则边会挂到不存在的点上。
"""

from collections.abc import Mapping
from typing import Any

from kg_sdk import step

# ============== ① 字段映射（配置区，按需修改） ==============

# 判别列：一张关系表喂多个 Schema 时按此分流；单表单关系设为 None。
DISCRIMINATOR: tuple[str, str] | None = None  # 例：("relation_type", "组成/包含")

# 端点列：列里存的是端点实体的主键值（不是 vid 时配合前缀拼出 vid）。
FROM_COLUMN = "subject_entity_id"  # 起点端点列
TO_COLUMN = "object_entity_id"  # 终点端点列

# 端点 vid 前缀：必须与端点实体脚本的 VID_PREFIX 完全一致。空串 = 不加。
ENDPOINT_VID_PREFIX = ""

# 边属性映射（规则同实体模板 FIELD_MAP；键须在关系 Schema 目录属性内）。
# 可以留空——纯连接边不输出 props，平台会自动补 NOT NULL 审计列。
FIELD_MAP: dict[str, str | tuple[str, Any]] = {
    # "relation_label": ("relation_type", str),
    # "confidence": ("confidence", float),
}


# ============== ② 逻辑处理（一般不动） ==============


@step
def emit_edges(payload: Mapping[str, Any]) -> dict[str, Any]:
    rows = payload.get("rows") or []
    edges: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    for row in rows:
        if DISCRIMINATOR is not None and str(row.get(DISCRIMINATOR[0]) or "") != DISCRIMINATOR[1]:
            continue  # 属于其他 Schema 的行静默放行，由各自的脚本处理
        src, dst = row.get(FROM_COLUMN), row.get(TO_COLUMN)
        if not src or not dst:
            # 残缺端点行（起/终点实体 id 缺失）静默跳过，不产生审核 case
            continue
        try:
            edges.append(
                {
                    "fromId": f"{ENDPOINT_VID_PREFIX}{src}",
                    "toId": f"{ENDPOINT_VID_PREFIX}{dst}",
                    "props": _map_fields(row),
                }
            )
        except (KeyError, TypeError, ValueError) as exc:
            record_id = row.get("id") or row.get(FROM_COLUMN) or "?"
            failures.append({"recordId": str(record_id), "error": f"{type(exc).__name__}: {exc}"})
    return {"edges": edges, "failures": failures}


def _map_fields(row: Mapping[str, Any]) -> dict[str, Any]:
    props: dict[str, Any] = {}
    for prop_name, spec in FIELD_MAP.items():
        column, convert = (spec, None) if isinstance(spec, str) else spec
        value = row.get(column)
        props[prop_name] = convert(value) if convert is not None and value is not None else value
    return props


# ============== ③ 输出契约（不要动） ==============
# {"edges": [{"fromId": vid, "toId": vid, "props": {...}}], "failures": [...]}
# - fromId/toId 必须与端点实体脚本产出的 vid 完全一致（含前缀）；
# - 端点实体若走了人裁（pendingReview），边会暂存进审核 case 随裁决落图；
# - 边按 (起点, 终点) 列级 upsert，重跑幂等。
