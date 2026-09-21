"""科研文本语义实体抽取脚本。

输入 ``payload["rows"]`` 中每行至少包含：

- ``id``（可选，缺失时按内容生成来源 ID）
- ``title`` 或 ``document_title``
- ``text``、``abstract`` 或 ``content``

脚本通过 ``kg_sdk.SemanticToolkitClient`` 依次调用健康检查、科研实体识别、
概念定义识别和研究问题识别，然后输出平台可写图的 ``entities``。
语义服务可由 ``KG_SCRIPT_CTX.semantic`` 注入，也可使用环境变量：
``SEMANTIC_TOOLKIT_BASE_URL``、``SEMANTIC_TOOLKIT_API_KEY``、
``SEMANTIC_TOOLKIT_TIMEOUT``。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from kg_sdk import SemanticToolkitClient, current_context, get_semantic_client, step


def _clean(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _record_id(row: Mapping[str, Any]) -> str:
    explicit = row.get("id") or row.get("document_id")
    if explicit is not None and _clean(explicit):
        return _clean(explicit)
    digest = hashlib.sha256(
        json.dumps(dict(row), ensure_ascii=False, default=str, sort_keys=True).encode()
    ).hexdigest()
    return f"document:{digest[:16]}"


def _entity_id(entity_type: str, name: str) -> str:
    key = f"{entity_type.casefold()}|{name.casefold()}"
    digest = hashlib.md5(key.encode("utf-8"), usedforsecurity=False).hexdigest()
    return f"semantic_entity_{digest}"


def _client() -> SemanticToolkitClient:
    context = current_context()
    client = context.semantic if context is not None else None
    client = client or get_semantic_client()
    if client is None:
        raise RuntimeError(
            "未配置语义计算服务：请设置 KG_SCRIPT_CTX.semantic 或 "
            "SEMANTIC_TOOLKIT_BASE_URL"
        )
    return client


def _definition_map(items: list[dict[str, Any]]) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in items:
        concept = _clean(
            item.get("concept")
            or item.get("term")
            or item.get("concept_name")
            or item.get("name")
        )
        definition = _clean(
            item.get("definition") or item.get("definition_text") or item.get("text")
        )
        if concept and definition:
            result[concept.casefold()] = definition
    return result


@step("semantic-research-entity-extract")
def extract_research_entities(payload: Mapping[str, Any]) -> dict[str, Any]:
    """调用三个语义工具抽取并补充科研实体，输出图实体 JSON。"""
    client = _client()
    health = client.health()
    if str(health.get("status", "ok")).casefold() not in {"ok", "healthy", "success"}:
        raise RuntimeError(f"语义计算服务健康检查失败：{health}")

    rows = payload.get("rows") or []
    entities: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    seen: set[str] = set()
    api_calls = 1

    for row in rows:
        record_id = _record_id(row)
        title = _clean(row.get("document_title") or row.get("title"))
        text = _clean(row.get("text") or row.get("abstract") or row.get("content"))
        if not title or not text:
            failures.append(
                {
                    "recordId": record_id,
                    "error": "缺少 title/document_title 或 text/abstract/content",
                }
            )
            continue
        try:
            entity_response = client.research_entities(title, text)
            definition_response = client.concept_definitions(text)
            question_response = client.research_questions(title, text)
            api_calls += 3

            extracted = client.entities_of(entity_response)
            definitions = _definition_map(client.definitions_of(definition_response))
            questions = client.questions_of(question_response)
            questions_json = json.dumps(questions, ensure_ascii=False, default=str)

            for item in extracted:
                raw_name = _clean(item.get("text") or item.get("name"))
                standard_names = item.get("standard_names") or {}
                standard_zh = _clean(item.get("std_zh") or standard_names.get("zh"))
                standard_en = _clean(item.get("std_en") or standard_names.get("en"))
                name = standard_zh or raw_name
                entity_type = _clean(item.get("type") or "TOPIC").upper()
                if not name:
                    continue
                vid = _entity_id(entity_type, name)
                if vid in seen:
                    continue
                seen.add(vid)
                props: dict[str, Any] = {
                    "id": vid,
                    "name": name,
                    "original_text": raw_name,
                    "entity_type": entity_type,
                    "source_document_id": record_id,
                    "source_document_title": title,
                    "research_questions": questions_json,
                }
                if standard_zh:
                    props["standard_name_zh"] = standard_zh
                if standard_en:
                    props["standard_name_en"] = standard_en
                if item.get("confidence") is not None:
                    props["confidence"] = float(item["confidence"])
                definition = definitions.get(name.casefold()) or definitions.get(
                    raw_name.casefold()
                )
                if definition:
                    props["definition"] = definition
                entities.append({"id": vid, "props": props})
        except Exception as exc:  # noqa: BLE001 - 单行隔离，交平台审核重跑
            failures.append(
                {
                    "recordId": record_id,
                    "error": f"{type(exc).__name__}: {exc}"[:1000],
                }
            )

    return {
        "entities": entities,
        "failures": failures,
        "stats": {
            "rows": len(rows),
            "entities": len(entities),
            "failed": len(failures),
            "semanticApiCalls": api_calls,
        },
    }
