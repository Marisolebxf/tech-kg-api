from datetime import datetime

from script.load_patent_relations import (
    edge_statement,
    extract_edges,
    extract_output_edges,
    graph_exact_resolvers,
    item_identifier,
    normalize_identifier,
    trusted_graph_vid,
)
from script.patent_indexing import HashedBM25, normalize_text, tokens


def test_hashed_bm25_roundtrip_and_normalization():
    model = HashedBM25(dimensions=128)
    model.observe("知识图谱 graph database")
    model.observe("图数据库")
    vector = model.encode("知识图谱")
    assert vector and all(0 <= key < 128 for key in vector)
    restored = HashedBM25.from_dict(model.to_dict())
    assert restored.encode("知识图谱") == vector
    assert normalize_text(" ＣＮ-1 A ") == "cn-1 a"
    assert "知识" in tokens("知识图谱")


def test_extract_edges_keeps_directions_and_routes_unresolved():
    row = {
        "patent_id": "CN1",
        "inventors": [{"name": "张三", "sequence": 2}],
        "applicants": [{"name": "某大学"}],
        "assignees": [],
        "patent_citations": [{"publicationNumber": "CN2"}],
        "cited_by": [{"number": "CN3"}],
    }

    def subjects(kind, name, metadata):
        return ("person_1", 0.99, "Person") if kind == "Person" else None

    def patents(raw):
        return (f"patent_{normalize_identifier(raw).upper()}", 1.0)

    statements, review = extract_edges(row, subjects, patents, "B", datetime(2026, 7, 31))
    joined = "\n".join(statements)
    assert '"patent_CN1"->"person_1"' in joined
    assert '"patent_CN1"->"patent_CN2"' in joined
    assert '"patent_CN3"->"patent_CN1"' in joined
    assert review[0]["edge"] == "APPLIED_BY"


def test_patent_collection_declares_exactly_eight_indexes():
    from script.build_patent_milvus_indexes import SCALAR_INDEXES

    assert len(SCALAR_INDEXES) == 6
    assert {field for field, _ in SCALAR_INDEXES} == {
        "publication_number",
        "application_number",
        "granted_number",
        "simple_family_number",
        "country_code",
        "source_table",
    }


def test_resume_rejects_changed_bm25_corpus(tmp_path):
    from script.build_patent_milvus_indexes import persist_bm25_state

    first = HashedBM25(dimensions=128)
    first.observe("专利 图谱")
    path = tmp_path / "patent_bm25.json"
    persist_bm25_state(first, path, resume=False)
    persist_bm25_state(first, path, resume=True)

    changed = HashedBM25(dimensions=128)
    changed.observe("完全不同的语料")
    try:
        persist_bm25_state(changed, path, resume=True)
    except RuntimeError as exc:
        assert "--rebuild" in str(exc)
    else:
        raise AssertionError("语料变化后不应混用旧BM25向量")


def test_only_patent_is_configured_for_indexing():
    from script.build_patent_milvus_indexes import PATENT_SPEC

    assert PATENT_SPEC.tag == "Patent"
    assert "Person" not in repr(PATENT_SPEC)
    assert "Organization" not in repr(PATENT_SPEC)


def test_existing_entity_indexes_are_read_only_and_require_unique_match():
    from script.load_patent_relations import ExistingEntityIndexResolver

    class FakeMilvus:
        def has_collection(self, name):
            return name in {"org_domain_person", "org_domain_organization"}

        def query(self, collection, filter, limit, output_fields):
            assert filter == ""
            assert limit == 16384
            assert output_fields == ["vid", "canonical_name", "aliases", "external_id"]
            if collection == "org_domain_person":
                return [
                    {
                        "vid": "person_1",
                        "canonical_name": "张三",
                        "external_id": "ID-1",
                        "aliases": [],
                    },
                    {"vid": "person_2", "canonical_name": "同名", "external_id": "", "aliases": []},
                    {"vid": "person_3", "canonical_name": "同名", "external_id": "", "aliases": []},
                ]
            return [
                {
                    "vid": "opaque-org-vid",
                    "canonical_name": "某大学",
                    "external_id": "ORG-1",
                    "aliases": ["同名"],
                }
            ]

    resolver = ExistingEntityIndexResolver(FakeMilvus())
    # 跨厂商 person_id 即使碰巧等于索引 external_id，也不能作为直接关联依据。
    assert resolver.resolve("Person", "", {"person_id": "ID-1"}) is None
    assert resolver.resolve("Person", "张三", {"person_id": "ID-1"}) is None
    assert resolver.resolve("Person", "同名", {}) is None
    assert resolver.resolve("Project", "项目", {}) is None
    assert resolver.resolve("Unknown", "某大学", {}) == (
        "opaque-org-vid",
        0.98,
        "Organization",
    )
    # 同一个名称同时存在于Person和Organization域时，不自动判成机构。
    assert resolver.resolve("Unknown", "同名", {}) is None


def test_cross_domain_generic_id_is_not_treated_as_patent_identifier():
    assert item_identifier({"id": "vendor-row-42"}) == ""
    assert item_identifier({"patent_number": "CN-1-A", "id": "vendor-row-42"}) == "CN-1-A"


def test_subject_type_is_explicit_and_does_not_depend_on_vid_prefix():
    statement = edge_statement(
        "APPLIED_BY",
        "patent_1",
        "opaque-vendor-independent-vid",
        1,
        "dwd_patent",
        "1:applicants:0",
        "B",
        datetime(2026, 7, 31),
        0.98,
        "Organization",
        source_name="某大学",
    )
    assert '"Organization"' in statement
    assert '"某大学"' in statement


def test_citation_keeps_source_business_identifier_not_target_vid():
    statement = edge_statement(
        "CITES",
        "patent-src",
        "opaque-target-vid",
        None,
        "dwd_patent_cited",
        "1:patent_citations:0",
        "B",
        datetime(2026, 7, 31),
        1.0,
        reference_identifier="CN-123-A",
    )
    assert '"CN-123-A"' in statement


def test_output_relation_uses_resolved_project_vid_not_a_constructed_prefix():
    statements, review = extract_output_edges(
        {"id": "vendor-project-1", "output_patents": [{"patent_number": "CN1"}]},
        lambda _: ("patent-real-vid", 1.0),
        lambda source_id: "opaque-project-vid" if source_id == "vendor-project-1" else None,
        "B",
        datetime(2026, 7, 31),
    )
    assert not review
    assert '"patent-real-vid"->"opaque-project-vid"' in statements[0]
    assert "project_vendor-project-1" not in statements[0]


def test_only_explicit_dev_namespace_can_supply_graph_vid():
    assert trusted_graph_vid({"graph_vid": "person_1", "id_namespace": "dev"}) == "person_1"
    assert (
        trusted_graph_vid({"graph_vid": "person_1", "graph_namespace": "trsgraph:dev"})
        == "person_1"
    )
    assert trusted_graph_vid({"graph_vid": "person_1"}) is None
    assert trusted_graph_vid({"person_id": "person_1", "id_namespace": "vendor_a"}) is None


def test_graph_resolver_never_treats_cross_domain_raw_id_as_vid():
    class Graph:
        def __init__(self):
            self.lookups = []

        def get_node(self, vid):
            self.lookups.append(vid)
            return type("Node", (), {"labels": ["Person"]})()

        def execute_read(self, query):
            raise AssertionError("无名称时不应执行名称查询")

    graph = Graph()
    subject, _ = graph_exact_resolvers(graph)
    assert subject("Person", "", {"person_id": "person_1"}) is None
    assert graph.lookups == []
    assert subject(
        "Person", "", {"graph_vid": "person_1", "id_namespace": "dev"}
    ) == ("person_1", 1.0, "Person")
    assert graph.lookups == ["person_1"]


def test_explicit_graph_vid_must_have_the_requested_entity_label():
    class Graph:
        def get_node(self, vid):
            return type("Node", (), {"labels": ["Organization"]})()

        def execute_read(self, query):
            raise AssertionError("类型不一致且无名称时不应继续查询")

    subject, _ = graph_exact_resolvers(Graph())
    assert (
        subject("Person", "", {"graph_vid": "org-real-vid", "id_namespace": "dev"})
        is None
    )


def test_search_text_is_truncated_by_utf8_bytes():
    from script.patent_indexing import truncate_utf8

    result = truncate_utf8("专利" * 100, 101)
    assert len(result.encode("utf-8")) <= 101
    assert result.encode("utf-8").decode("utf-8") == result


def test_hybrid_search_reads_real_collection_fields_instead_of_metadata():
    from script.patent_hybrid_search import hybrid_search

    class Client:
        def hybrid_search(self, collection, requests, ranker, limit, output_fields):
            assert collection == "patent"
            assert "metadata" not in output_fields
            assert {"vid", "patent_id", "publication_number"} <= set(output_fields)
            return [[{"id": "fallback", "distance": 0.9, "entity": {"vid": "patent-real"}}]]

    matches = hybrid_search(Client(), "patent", [0.1, 0.2], {1: 0.5})
    assert matches[0].graph_vid == "patent-real"


def test_edge_write_is_explicitly_idempotent():
    from script.load_patent_relations import write_edge_if_absent

    class Graph:
        def __init__(self, existing):
            self.existing = existing
            self.writes = []

        def get_edge(self, edge_id, edge_type):
            assert edge_id == "patent_1->org_1@0"
            assert edge_type == "APPLIED_BY"
            return object() if self.existing else None

        def execute_write(self, statement):
            self.writes.append(statement)

    statement = 'INSERT EDGE APPLIED_BY(sequence) VALUES "patent_1"->"org_1":(1);'
    existing = Graph(True)
    assert write_edge_if_absent(existing, statement) is False
    assert not existing.writes
    missing = Graph(False)
    assert write_edge_if_absent(missing, statement) is True
    assert missing.writes == [statement]
