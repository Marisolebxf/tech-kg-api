"""内置算子。

所有算子都遵循 ``list[dict] -> operator(data, ctx) -> list[dict]`` 接口。
入库算子当前只做规则匹配并返回计划，不直接写数据库，便于后续替换为真实 DAO。
"""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

JsonObject = dict[str, Any]


def _normalize_value(value: Any) -> Any:
    if isinstance(value, str):
        return " ".join(value.strip().split())
    if isinstance(value, list):
        return [_normalize_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _normalize_value(item) for key, item in value.items()}
    return value


def data_normalize(data: list[JsonObject], ctx: JsonObject) -> list[JsonObject]:
    """清理字符串、映射字段名并可选过滤空值。"""
    field_mapping = ctx.get("field_mapping", {})
    drop_empty = bool(ctx.get("drop_empty", False))
    result: list[JsonObject] = []
    for source in data:
        item = {
            str(field_mapping.get(key, key)): _normalize_value(value)
            for key, value in source.items()
        }
        if drop_empty:
            item = {key: value for key, value in item.items() if value not in (None, "", [], {})}
        result.append(item)
    return result


def entity_extract(data: list[JsonObject], ctx: JsonObject) -> list[JsonObject]:
    """按用户提供的正则规则从记录文本中抽取实体。"""
    text_field = str(ctx.get("text_field", "text"))
    rules = ctx.get("rules", [])
    entities: list[JsonObject] = []
    for row_index, item in enumerate(data):
        text = str(item.get(text_field, ""))
        for rule in rules:
            pattern = str(rule.get("pattern", ""))
            if not pattern:
                continue
            entity_type = str(rule.get("entity_type", "Entity"))
            for match in re.finditer(pattern, text):
                value = match.groupdict().get("value") or match.group(0)
                entities.append(
                    {
                        "id": f"E{len(entities) + 1}",
                        "name": value,
                        "type": entity_type,
                        "source_index": row_index,
                        "start": match.start(),
                        "end": match.end(),
                    }
                )
    return entities


def relation_extract(data: list[JsonObject], ctx: JsonObject) -> list[JsonObject]:
    """按字段映射或正则命名分组抽取关系。"""
    source_field = str(ctx.get("source_field", "source"))
    target_field = str(ctx.get("target_field", "target"))
    type_field = str(ctx.get("type_field", "type"))
    default_type = str(ctx.get("default_type", "RELATED_TO"))
    text_field = str(ctx.get("text_field", "text"))
    pattern = ctx.get("pattern")
    relations: list[JsonObject] = []

    for row_index, item in enumerate(data):
        source = item.get(source_field)
        target = item.get(target_field)
        relation_type = item.get(type_field, default_type)
        if source is not None and target is not None:
            relations.append(
                {
                    "source": source,
                    "target": target,
                    "type": relation_type,
                    "source_index": row_index,
                }
            )
            continue

        if pattern:
            for match in re.finditer(str(pattern), str(item.get(text_field, ""))):
                groups = match.groupdict()
                if groups.get("source") is not None and groups.get("target") is not None:
                    relations.append(
                        {
                            "source": groups["source"],
                            "target": groups["target"],
                            "type": groups.get("type") or default_type,
                            "source_index": row_index,
                        }
                    )
    return relations


def _find_match(
    item: JsonObject,
    existing: list[JsonObject],
    primary_keys: list[str],
    name_key: str,
) -> tuple[JsonObject | None, str | None]:
    if primary_keys and all(item.get(key) is not None for key in primary_keys):
        for candidate in existing:
            if all(candidate.get(key) == item.get(key) for key in primary_keys):
                return candidate, "primary_key"
    name = item.get(name_key)
    if name is not None:
        normalized_name = str(name).strip().casefold()
        for candidate in existing:
            if str(candidate.get(name_key, "")).strip().casefold() == normalized_name:
                return candidate, "name"
    return None, None


def entity_load(data: list[JsonObject], ctx: JsonObject) -> list[JsonObject]:
    """实体对齐/消歧的规则占位实现，返回 insert 或 merge 计划。"""
    existing = list(ctx.get("existing_entities", []))
    primary_keys = [str(key) for key in ctx.get("primary_keys", ["id"])]
    name_key = str(ctx.get("name_key", "name"))
    result: list[JsonObject] = []
    for item in data:
        matched, matched_by = _find_match(item, existing, primary_keys, name_key)
        if matched is None:
            output = deepcopy(item)
            output["_ingest"] = {"action": "insert", "matched_by": None}
            existing.append(deepcopy(item))
        else:
            output = {**deepcopy(matched), **deepcopy(item)}
            output["_ingest"] = {
                "action": "merge",
                "matched_by": matched_by,
                "matched_id": matched.get("id"),
            }
        result.append(output)
    return result


def relation_load(data: list[JsonObject], ctx: JsonObject) -> list[JsonObject]:
    """按 source/target/type 组合键生成关系入库计划。"""
    existing = list(ctx.get("existing_relations", []))
    key_fields = [str(key) for key in ctx.get("key_fields", ["source", "target", "type"])]
    result: list[JsonObject] = []
    for item in data:
        matched = next(
            (
                candidate
                for candidate in existing
                if all(candidate.get(key) == item.get(key) for key in key_fields)
            ),
            None,
        )
        if matched is None:
            output = deepcopy(item)
            output["_ingest"] = {"action": "insert", "matched_by": None}
            existing.append(deepcopy(item))
        else:
            output = {**deepcopy(matched), **deepcopy(item)}
            output["_ingest"] = {"action": "merge", "matched_by": key_fields}
        result.append(output)
    return result
