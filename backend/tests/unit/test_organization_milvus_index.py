from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from infra.graph_db import GraphNode, GraphPagedResult
from script.organization_milvus_index import (
    DOMAIN_ENTITY_TYPES,
    _utf8_truncate,
    collect_documents,
    node_to_document,
    run_index,
)


class FakeGraph:
    def __init__(self, nodes: dict[str, list[GraphNode]]) -> None:
        self.nodes = nodes

    def get_nodes_by_label(
        self,
        label: str,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> GraphPagedResult:
        items = self.nodes.get(label, [])
        return GraphPagedResult(
            items=items[offset : offset + limit],
            total=len(items),
            limit=limit,
            offset=offset,
        )


class DryRunStore:
    def __init__(self) -> None:
        self.write_calls = 0

    def collection_name(self, entity_type: str) -> str:
        return f"org_domain_{entity_type.casefold()}"

    def create_collection(self, *args: Any, **kwargs: Any) -> None:
        self.write_calls += 1

    def upsert(self, *args: Any, **kwargs: Any) -> int:
        self.write_calls += 1
        return 0

    def flush(self, *args: Any, **kwargs: Any) -> None:
        self.write_calls += 1

    def load(self, *args: Any, **kwargs: Any) -> None:
        self.write_calls += 1


def organization_node(
    vid: str,
    source_table: str,
    *,
    name: str = "示例机构",
    extra: dict[str, Any] | None = None,
) -> GraphNode:
    return GraphNode(
        id=vid,
        labels=["Organization"],
        properties={
            "name_cn": name,
            "source_table": source_table,
            "source_record_id": "source-1",
            "extra_json": json.dumps(extra or {}, ensure_ascii=False),
        },
    )


def test_every_39_table_entity_type_has_an_index_target() -> None:
    assert DOMAIN_ENTITY_TYPES == (
        "Organization",
        "Person",
        "News",
        "Event",
        "Product",
        "DataSource",
    )


def test_document_merges_long_tail_fields_from_extra_json() -> None:
    node = organization_node(
        "org_a",
        "dwd_org_base_info",
        extra={
            "external_id": "91310000",
            "province": "北京市",
            "business_scope": "科研与技术开发",
        },
    )
    document = node_to_document("Organization", node)
    assert document.external_id == "91310000"
    assert document.province == "北京市"
    assert "科研与技术开发" in document.search_text


def test_milvus_varchar_limits_are_measured_in_utf8_bytes() -> None:
    value = "中" * 20
    truncated = _utf8_truncate(value, 10)
    assert truncated == "中" * 3
    assert len(truncated.encode()) <= 10


def test_collection_filters_nodes_outside_39_table_domain() -> None:
    graph = FakeGraph(
        {
            "Organization": [
                organization_node("org_domain", "dwd_org_base_info"),
                organization_node("org_other", "another_team_table"),
            ]
        }
    )
    documents, stats = collect_documents(
        graph,  # type: ignore[arg-type]
        "Organization",
        page_size=100,
        max_records=None,
    )
    assert [document.vid for document in documents] == ["org_domain"]
    assert stats.domain_owned == 1
    assert stats.skipped_out_of_scope == 1


def test_dry_run_never_mutates_milvus(tmp_path: Path) -> None:
    graph = FakeGraph({"Organization": [organization_node("org_domain", "dwd_org_base_info")]})
    store = DryRunStore()
    result = run_index(
        entity="Organization",
        write=False,
        graph=graph,  # type: ignore[arg-type]
        store=store,  # type: ignore[arg-type]
        state_dir=str(tmp_path),
    )
    assert result["stats"][0]["indexed"] == 1
    assert store.write_calls == 0
    assert list(tmp_path.iterdir()) == []
