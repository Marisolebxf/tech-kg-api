"""实体抽取脚本模板：一张来源表 → 一个实体 Schema。

只改「① 字段映射（配置区）」，② 逻辑处理与 ③ 输出契约保持通用即可。
完整规范（输入/输出契约、禁区、常见错误对照）见
backend/docs/抽取脚本编写规范.md。

使用：Schema 管理页 → 行内「上传脚本」；绑定来源表后到「图谱构建」页
新建抽取任务。写图/消歧/推水位由平台完成，脚本只做转换。
"""

from collections.abc import Mapping
from typing import Any

from kg_sdk import step

# ============== ① 字段映射（配置区，按需修改） ==============

# 判别列：一张表喂多个 Schema 时，只处理 row[列] == 值 的行
# （如 entities 表按 type_code 分流到 Course/Document/... 各自的 Schema）。
# 单表单实体设为 None（全表都属于本 Schema）。
DISCRIMINATOR: tuple[str, str] | None = None  # 例：("type_code", "COURSE")

# 字段映射：Schema 属性名 → 源列名，或 (源列名, 转换函数)。
# - 键必须在 Schema 目录属性内：目录外的键写图前会被平台静默丢弃（不报错）；
# - 转换函数做类型纠正（str/int/float/bool）；建议必填列显式给 str；
# - 源列为 NULL 时保持 None 透传（可空列写 NULL，平台按图库列类型兜底）。
FIELD_MAP: dict[str, str | tuple[str, Any]] = {
    "name": ("name", str),
    # "standard_zh": ("standard_zh", str),
    # "confidence": ("confidence", float),
    # "document_id": "document_id",  # 同名直传
}

# vid 前缀：实体唯一标识 = 前缀 + 主键值。多来源主键可能撞车时加前缀
# （如 "person_"）；引用本实体的关系脚本端点必须用同一前缀。空串 = 不加。
VID_PREFIX = ""


# ============== ② 逻辑处理（一般不动） ==============


@step
def emit_entities(payload: Mapping[str, Any]) -> dict[str, Any]:
    rows = payload.get("rows") or []
    pk_column = (payload.get("source") or {}).get("pkColumn") or "id"
    entities: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    for row in rows:
        if DISCRIMINATOR is not None and str(row.get(DISCRIMINATOR[0]) or "") != DISCRIMINATOR[1]:
            continue  # 属于其他 Schema 的行静默放行，由各自的脚本处理
        record_id = row.get(pk_column)
        if record_id is None or not str(record_id).strip():
            # 无主键的行无法生成稳定 vid，按失败上报进人工审核
            failures.append({"recordId": "?", "error": f"缺失主键列: {pk_column}"})
            continue
        try:
            props = _map_fields(row)
            entities.append(
                {
                    "id": f"{VID_PREFIX}{record_id}",
                    "props": {"id": str(record_id), **props},
                }
            )
        except (KeyError, TypeError, ValueError) as exc:
            failures.append({"recordId": str(record_id), "error": f"{type(exc).__name__}: {exc}"})
    return {"entities": entities, "failures": failures}


def _map_fields(row: Mapping[str, Any]) -> dict[str, Any]:
    props: dict[str, Any] = {}
    for prop_name, spec in FIELD_MAP.items():
        column, convert = (spec, None) if isinstance(spec, str) else spec
        value = row.get(column)
        props[prop_name] = convert(value) if convert is not None and value is not None else value
    return props


# ============== ③ 输出契约（不要动） ==============
# {"entities": [{"id": vid, "props": {...}}], "failures": [{"recordId", "error"}]}
# - id 即图库 vid，必须稳定：同一源行每次产出同值，重跑才是幂等覆盖；
# - failures 逐行进 T_EXTRACT_FAIL 人工审核，可按执行重跑；
# - source_table/create_time/update_time 由平台自动补齐，脚本只管业务字段。
