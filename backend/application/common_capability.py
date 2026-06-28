import os
from typing import Any

from service.common.entity_alignment import align_knowledge_graphs
from service.common.entity_disambiguation import disambiguate_entity
from service.common.entity_extraction import FOCUS_TYPES, extract
from service.common.relation_extraction import (
    EXAMPLE_TEXTS,
    batch_extract_relations,
    extract_relations,
)


class CommonCapabilityApplication:
    """Application facade for reusable NLP and KG capabilities."""

    def extract_entities(self, text: str, source_type: str = "general") -> dict[str, Any]:
        entities = extract(text, source_type)
        return {
            "source_type": source_type,
            "entity_count": len(entities),
            "entities": entities,
        }

    def align_entities(
        self,
        kg_a: list[dict[str, Any]] | None = None,
        kg_b: list[dict[str, Any]] | None = None,
        top_k: int = 3,
    ) -> dict[str, Any]:
        return align_knowledge_graphs(kg_a, kg_b, top_k=top_k)

    def disambiguate_entity(
        self,
        text: str,
        mention: str,
        kb: list[dict[str, Any]] | None = None,
        top_k: int = 5,
    ) -> dict[str, Any]:
        return disambiguate_entity(text, mention, kb, top_k=top_k)

    def extract_relations(self, text: str, method: str = "rule") -> dict[str, Any]:
        return extract_relations(
            text=text,
            method=method,
            llm_api_key=os.getenv("LLM_API_KEY") or None,
            llm_base_url=os.getenv("LLM_BASE_URL", "https://open.bigmodel.cn/api/paas/v4"),
            llm_model=os.getenv("LLM_MODEL", "glm-4-flash"),
        )

    def batch_extract_relations(self, texts: list[str], method: str = "rule") -> dict[str, Any]:
        return batch_extract_relations(
            texts=texts,
            method=method,
            llm_api_key=os.getenv("LLM_API_KEY") or None,
            llm_base_url=os.getenv("LLM_BASE_URL", "https://open.bigmodel.cn/api/paas/v4"),
            llm_model=os.getenv("LLM_MODEL", "glm-4-flash"),
        )

    def relation_examples(self) -> list[dict[str, str]]:
        return EXAMPLE_TEXTS

    def focus_types(self) -> dict[str, list[str]]:
        return FOCUS_TYPES
