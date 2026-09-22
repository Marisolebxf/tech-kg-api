"""科研文本 18 类语义能力实体抽取脚本。

脚本接入语义工具库除“结构化自动综述”外的全部能力：中英文/基金语步、
中英文/专业分类、中英文关键词、研究问题、引用情感、引用意图、概念定义、
通用/科研/专业实体、实体关系、深度聚类和聚类标签。

输入 ``payload["rows"]`` 中每行至少包含题名与正文；可选字段包括 ``language``、
``document_type``、``domain``、``reference_entries``、``publication_date``。不同文种、
文档类型和批量能力会按适用条件路由，单项失败不会阻断同一行的其他抽取结果。
可通过 ``payload["capabilities"]`` 传能力名子集；默认启用全部 18 类能力。
"""

# 回调均在当前循环迭代中同步执行，不会逃逸；B023 的闭包告警不适用于此处。
# ruff: noqa: B023

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping
from typing import Any

from kg_sdk import SemanticToolkitClient, current_context, get_semantic_client, step

CAPABILITIES = (
    "zh_abstract_move",
    "en_abstract_move",
    "fund_move",
    "zh_classify",
    "en_classify",
    "domain_classify",
    "zh_keyword",
    "en_keyword",
    "research_question",
    "citation_sentiment",
    "citation_intent",
    "concept_definition",
    "general_ner",
    "research_ner",
    "domain_ner",
    "relation_extract",
    "deep_cluster",
    "cluster_label",
)
_CAPABILITY_SET = frozenset(CAPABILITIES)
_FUND_TYPES = {"fund", "grant", "project", "基金", "基金项目", "项目"}


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


def _edge_id(source: str, edge_type: str, target: str) -> str:
    key = f"{source}|{edge_type.casefold()}|{target}"
    digest = hashlib.md5(key.encode("utf-8"), usedforsecurity=False).hexdigest()
    return f"semantic_relation_{digest}"


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


def _selected_capabilities(payload: Mapping[str, Any]) -> set[str]:
    requested = payload.get("capabilities")
    if not requested:
        return set(CAPABILITIES)
    if isinstance(requested, str):
        requested = [requested]
    normalized = {_clean(item).casefold().replace("-", "_") for item in requested}
    unknown = normalized - _CAPABILITY_SET
    if unknown:
        raise ValueError(f"未知语义能力：{', '.join(sorted(unknown))}")
    return normalized


def _language(row: Mapping[str, Any], title: str, text: str) -> str:
    configured = _clean(row.get("language") or row.get("lang")).casefold()
    if configured.startswith("zh") or configured in {"cn", "中文", "chinese"}:
        return "zh"
    if configured.startswith("en") or configured in {"英文", "english"}:
        return "en"
    sample = f"{title}{text}"
    cjk_count = len(re.findall(r"[\u4e00-\u9fff]", sample))
    return "zh" if cjk_count >= max(1, len(sample) // 20) else "en"


def _document_type(row: Mapping[str, Any]) -> str:
    return _clean(row.get("document_type") or row.get("doc_type") or row.get("type")).casefold()


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


def _item_name(item: Mapping[str, Any]) -> tuple[str, str, str]:
    standard_names = item.get("standard_names") or {}
    if not isinstance(standard_names, Mapping):
        standard_names = {}
    raw_name = _clean(
        item.get("text")
        or item.get("keyword")
        or item.get("term")
        or item.get("concept")
        or item.get("name")
        or item.get("label")
        or item.get("topic_name")
        or item.get("category_name")
        or item.get("clc_name")
    )
    standard_zh = _clean(item.get("std_zh") or standard_names.get("zh"))
    standard_en = _clean(item.get("std_en") or standard_names.get("en"))
    normalized = _clean(item.get("normalized_term"))
    return standard_zh or normalized or raw_name or standard_en, standard_zh, standard_en


def _entity_type(item: Mapping[str, Any], default_type: str) -> str:
    raw = _clean(item.get("type") or item.get("entity_type") or default_type).upper()
    return re.sub(r"[^A-Z0-9_]+", "_", raw).strip("_") or default_type


def _upsert_entity(
    entities: dict[str, dict[str, Any]],
    item: Mapping[str, Any],
    *,
    default_type: str,
    capability: str,
    record_id: str,
    title: str,
) -> str:
    name, standard_zh, standard_en = _item_name(item)
    if not name:
        return ""
    entity_type = _entity_type(item, default_type)
    vid = _entity_id(entity_type, name)
    existing = entities.get(vid)
    if existing is not None:
        props = existing["props"]
        sources = props.setdefault("source_document_ids", [props["source_document_id"]])
        if record_id not in sources:
            sources.append(record_id)
        capabilities = props.setdefault("extraction_capabilities", [])
        if capability not in capabilities:
            capabilities.append(capability)
        return vid

    raw_name = _clean(item.get("text") or item.get("keyword") or item.get("name") or name)
    props: dict[str, Any] = {
        "id": vid,
        "name": name,
        "original_text": raw_name,
        "entity_type": entity_type,
        "source_document_id": record_id,
        "source_document_title": title,
        "source_document_ids": [record_id],
        "extraction_capabilities": [capability],
        "semantic_attributes": dict(item),
    }
    if standard_zh:
        props["standard_name_zh"] = standard_zh
    if standard_en:
        props["standard_name_en"] = standard_en
    if item.get("confidence") is not None:
        props["confidence"] = item["confidence"]
    entities[vid] = {"id": vid, "props": props}
    return vid


def _triple_value(value: Any) -> str:
    if isinstance(value, Mapping):
        return _clean(
            value.get("text") or value.get("name") or value.get("label") or value.get("id")
        )
    return _clean(value)


def _append_relations(
    triples: list[dict[str, Any]],
    *,
    entities: dict[str, dict[str, Any]],
    relations: dict[str, dict[str, Any]],
    record_id: str,
    title: str,
) -> None:
    def resolve_endpoint(name: str) -> str:
        for entity_id, entity in entities.items():
            if _clean(entity["props"].get("name")).casefold() == name.casefold():
                return entity_id
        return _upsert_entity(
            entities,
            {"name": name},
            default_type="SEMANTIC_ENTITY",
            capability="relation_extract",
            record_id=record_id,
            title=title,
        )

    for triple in triples:
        subject = _triple_value(triple.get("subject") or triple.get("source"))
        target = _triple_value(triple.get("object") or triple.get("target"))
        relation_name = _clean(
            triple.get("relation") or triple.get("predicate") or triple.get("type")
        )
        if not subject or not target or not relation_name:
            continue
        source_id = resolve_endpoint(subject)
        target_id = resolve_endpoint(target)
        edge_type = (
            re.sub(r"[^A-Z0-9_]+", "_", relation_name.upper()).strip("_")
            or "RELATED_TO"
        )
        edge_id = _edge_id(source_id, edge_type, target_id)
        relations[edge_id] = {
            "id": edge_id,
            "source": source_id,
            "target": target_id,
            "type": edge_type,
            "props": {
                "source_document_id": record_id,
                "original_relation": relation_name,
                "semantic_attributes": dict(triple),
            },
        }


def _cluster_phrase_sets(clusters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    phrase_sets: list[dict[str, Any]] = []
    for index, cluster in enumerate(clusters, start=1):
        cluster_id = _clean(cluster.get("cluster_id") or cluster.get("id") or index)
        phrases = cluster.get("representative_terms") or cluster.get("keywords") or []
        if isinstance(phrases, str):
            phrases = [phrases]
        clean_phrases = [_triple_value(phrase) for phrase in phrases]
        topic = _clean(cluster.get("topic_name") or cluster.get("label") or cluster.get("name"))
        if topic:
            clean_phrases.insert(0, topic)
        clean_phrases = [phrase for phrase in dict.fromkeys(clean_phrases) if phrase]
        if clean_phrases:
            phrase_sets.append({"cluster_id": cluster_id, "phrases": clean_phrases})
    return phrase_sets


@step("semantic-research-entity-extract")
def extract_research_entities(payload: Mapping[str, Any]) -> dict[str, Any]:
    """调用 18 类语义能力，输出实体、关系、语义结果与逐项调用统计。"""
    client = _client()
    health = client.health()
    if str(health.get("status", "ok")).casefold() not in {"ok", "healthy", "success"}:
        raise RuntimeError(f"语义计算服务健康检查失败：{health}")

    selected = _selected_capabilities(payload)
    rows = payload.get("rows") or []
    entities: dict[str, dict[str, Any]] = {}
    relations: dict[str, dict[str, Any]] = {}
    failures: list[dict[str, Any]] = []
    semantic_results: list[dict[str, Any]] = []
    batch_results: dict[str, Any] = {}
    capability_stats = {
        capability: {"attempted": 0, "succeeded": 0, "failed": 0, "skipped": 0}
        for capability in CAPABILITIES
        if capability in selected
    }
    api_calls = 1

    def invoke(
        capability: str,
        record_id: str,
        callback: Callable[[], dict[str, Any]],
    ) -> dict[str, Any] | None:
        nonlocal api_calls
        capability_stats[capability]["attempted"] += 1
        api_calls += 1
        try:
            response = callback()
        except Exception as exc:  # noqa: BLE001 - 单能力隔离，交平台审核重跑
            capability_stats[capability]["failed"] += 1
            failures.append(
                {
                    "recordId": record_id,
                    "capability": capability,
                    "error": f"{type(exc).__name__}: {exc}"[:1000],
                }
            )
            return None
        capability_stats[capability]["succeeded"] += 1
        return response

    def skip(capability: str) -> None:
        if capability in selected:
            capability_stats[capability]["skipped"] += 1

    valid_documents: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            failures.append({"recordId": "", "capability": "input", "error": "row 必须是对象"})
            continue
        record_id = _record_id(row)
        title = _clean(row.get("document_title") or row.get("title") or row.get("project_name"))
        text = _clean(row.get("text") or row.get("abstract") or row.get("content"))
        if not title or not text:
            failures.append(
                {
                    "recordId": record_id,
                    "capability": "input",
                    "error": "缺少 title/document_title/project_name 或 text/abstract/content",
                }
            )
            continue

        language = _language(row, title, text)
        document_type = _document_type(row)
        domain = _clean(row.get("professional_domain") or row.get("domain"))
        reference_entries = _clean(row.get("reference_entries"))
        row_result: dict[str, Any] = {
            "recordId": record_id,
            "title": title,
            "language": language,
            "documentType": document_type,
            "capabilities": {},
        }
        valid_documents.append(
            {
                "document_id": record_id,
                "title": title,
                "text": text,
                "publication_date": _clean(row.get("publication_date") or row.get("year")),
            }
        )

        responses: dict[str, dict[str, Any]] = {}

        def run(capability: str, callback: Callable[[], dict[str, Any]]) -> None:
            response = invoke(capability, record_id, callback)
            if response is not None:
                responses[capability] = response
                row_result["capabilities"][capability] = client.data_of(response)

        if "general_ner" in selected:
            run("general_ner", lambda: client.general_entities(title, text))
        if "research_ner" in selected:
            run("research_ner", lambda: client.research_entities(title, text))
        if "domain_ner" in selected:
            run("domain_ner", lambda: client.domain_entities(title, text, domain=domain))
        if "concept_definition" in selected:
            run("concept_definition", lambda: client.concept_definitions(text))
        if "research_question" in selected:
            run("research_question", lambda: client.research_questions(title, text))
        if "citation_sentiment" in selected:
            run(
                "citation_sentiment",
                lambda: client.citation_sentiment(
                    title, text, reference_entries=reference_entries
                ),
            )
        if "citation_intent" in selected:
            run(
                "citation_intent",
                lambda: client.citation_intent(title, text, reference_entries=reference_entries),
            )

        if language == "zh":
            if "zh_abstract_move" in selected:
                run("zh_abstract_move", lambda: client.moves_zh(title, text))
            if "zh_classify" in selected:
                run("zh_classify", lambda: client.classify_zh(title, text))
            if "zh_keyword" in selected:
                run("zh_keyword", lambda: client.keywords_zh(title, text))
            skip("en_abstract_move")
            skip("en_classify")
            skip("en_keyword")
        else:
            if "en_abstract_move" in selected:
                run("en_abstract_move", lambda: client.moves_en(title, text))
            if "en_classify" in selected:
                run("en_classify", lambda: client.classify_en(title, text))
            if "en_keyword" in selected:
                run("en_keyword", lambda: client.keywords_en(title, text))
            skip("zh_abstract_move")
            skip("zh_classify")
            skip("zh_keyword")

        if "domain_classify" in selected:
            if domain:
                run(
                    "domain_classify",
                    lambda: client.classify_domain(title, text, domain=domain),
                )
            else:
                skip("domain_classify")
        if "fund_move" in selected:
            if document_type in _FUND_TYPES:
                run("fund_move", lambda: client.fund_moves(title, text))
            else:
                skip("fund_move")

        for capability in ("general_ner", "research_ner", "domain_ner"):
            response = responses.get(capability)
            if response is None:
                continue
            for item in client.entities_of(response):
                _upsert_entity(
                    entities,
                    item,
                    default_type="SEMANTIC_ENTITY",
                    capability=capability,
                    record_id=record_id,
                    title=title,
                )

        definition_items = client.definitions_of(responses.get("concept_definition") or {})
        definitions = _definition_map(definition_items)
        for item in definition_items:
            concept, _, _ = _item_name(item)
            definition = definitions.get(concept.casefold())
            if not concept or not definition:
                continue
            vid = _upsert_entity(
                entities,
                item,
                default_type="CONCEPT",
                capability="concept_definition",
                record_id=record_id,
                title=title,
            )
            entities[vid]["props"]["definition"] = definition

        for capability in ("zh_keyword", "en_keyword"):
            for item in client.keywords_of(responses.get(capability) or {}):
                _upsert_entity(
                    entities,
                    item,
                    default_type="KEYWORD",
                    capability=capability,
                    record_id=record_id,
                    title=title,
                )

        for capability in ("zh_classify", "en_classify", "domain_classify"):
            for item in client.classifications_of(responses.get(capability) or {}):
                _upsert_entity(
                    entities,
                    item,
                    default_type="RESEARCH_FIELD",
                    capability=capability,
                    record_id=record_id,
                    title=title,
                )

        questions = client.questions_of(responses.get("research_question") or {})
        questions_json = json.dumps(questions, ensure_ascii=False, default=str)
        for entity in entities.values():
            props = entity["props"]
            if record_id in props.get("source_document_ids", []):
                props["research_questions"] = questions_json
                definition = definitions.get(_clean(props.get("name")).casefold())
                if definition:
                    props["definition"] = definition

        if "relation_extract" in selected:
            ner_response = next(
                (
                    responses[name]
                    for name in ("research_ner", "domain_ner", "general_ner")
                    if name in responses and client.record_id_of(responses[name])
                ),
                None,
            )
            if ner_response is None:
                skip("relation_extract")
            else:
                upstream_id = client.record_id_of(ner_response)
                relation_response = invoke(
                    "relation_extract",
                    record_id,
                    lambda: client.relation_extract(upstream_id),
                )
                if relation_response is not None:
                    row_result["capabilities"]["relation_extract"] = client.data_of(
                        relation_response
                    )
                    _append_relations(
                        client.triples_of(relation_response),
                        entities=entities,
                        relations=relations,
                        record_id=record_id,
                        title=title,
                    )

        semantic_results.append(row_result)

    clusters: list[dict[str, Any]] = []
    if "deep_cluster" in selected:
        if len(valid_documents) >= 4:
            cluster_response = invoke(
                "deep_cluster",
                "__batch__",
                lambda: client.deep_cluster(
                    valid_documents,
                    dimension=_clean(payload.get("cluster_dimension")) or "technology",
                ),
            )
            if cluster_response is not None:
                batch_results["deep_cluster"] = client.data_of(cluster_response)
                clusters = client.clusters_of(cluster_response)
                for cluster in clusters:
                    _upsert_entity(
                        entities,
                        cluster,
                        default_type="CLUSTER_TOPIC",
                        capability="deep_cluster",
                        record_id="__batch__",
                        title="批量深度聚类",
                    )
        else:
            skip("deep_cluster")

    if "cluster_label" in selected:
        phrase_sets = _cluster_phrase_sets(clusters)
        if phrase_sets:
            label_response = invoke(
                "cluster_label",
                "__batch__",
                lambda: client.cluster_labels(phrase_sets),
            )
            if label_response is not None:
                batch_results["cluster_label"] = client.data_of(label_response)
                for label in client.cluster_labels_of(label_response):
                    _upsert_entity(
                        entities,
                        label,
                        default_type="CLUSTER_TOPIC",
                        capability="cluster_label",
                        record_id="__batch__",
                        title="聚类标签生成",
                    )
        else:
            skip("cluster_label")

    return {
        "entities": list(entities.values()),
        "relations": list(relations.values()),
        "semanticResults": semantic_results,
        "batchResults": batch_results,
        "failures": failures,
        "stats": {
            "rows": len(rows),
            "validRows": len(valid_documents),
            "entities": len(entities),
            "relations": len(relations),
            "failed": len(failures),
            "semanticApiCalls": api_calls,
            "capabilities": capability_stats,
        },
    }
