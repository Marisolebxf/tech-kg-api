import re
from pathlib import Path

from script import load_patent_relations as loader


class FakeResult:
    def __init__(self, records):
        self.records = records


class FakeGraph:
    def __init__(self):
        self.writes = []
        self.fields = {
            "INVENTED_BY": {"confidence"},
            "APPLIED_BY": {"confidence"},
            "OWNED_BY": {"confidence"},
            "CITES": {"reference_identifier"},
            "OUTPUT_OF": {"source_table", "source_record_id", "ingest_batch", "ingest_time"},
        }

    def execute_write(self, statement):
        self.writes.append(statement)
        matched = re.match(r"ALTER EDGE (\w+) ADD \((.*)\);", statement)
        if matched:
            self.fields[matched.group(1)].update(
                item.strip().split()[0] for item in matched.group(2).split(",")
            )

    def execute_read(self, statement):
        for edge, fields in self.fields.items():
            if edge in statement:
                return FakeResult([{"Field": field} for field in fields])
        raise AssertionError(statement)


def test_normalizers_are_deterministic():
    assert loader.normalize_name("  清华大学（深圳） ") == "清华大学深圳"
    assert loader.normalize_identifier("CN 123-456 A") == "cn123456a"


def test_application_number_key_aligns_supplier_and_project_formats():
    assert loader.application_number_key("CN-201811400598-A") == "cn201811400598"
    assert loader.application_number_key("CN201811400598.8") == "cn201811400598"
    assert loader.application_number_key("ZL201811400598.8") == "cn201811400598"
    assert loader.application_number_key("2018114005988") == "cn201811400598"


def test_patent_candidates_try_generic_and_application_number_keys():
    index = {
        "cn103332525a": ["patent_publication"],
        "cn201811400598": ["patent_application"],
    }
    assert loader.patent_candidates(index, "CN-103332525-A") == ["patent_publication"]
    assert loader.patent_candidates(index, "ZL201811400598.8") == ["patent_application"]


def test_name_index_includes_foreign_aliases_and_domain_vid():
    rows = [{"vid": "org_1", "name_en": "ACME Inc.", "name_alias": "ACME;艾克米"}]
    index = loader.make_index(rows, ("name_en", "name_alias"))
    assert index["acmeinc"][0]["vid"] == "org_1"
    assert index["艾克米"][0]["vid"] == "org_1"


def test_canonical_organization_is_decided_only_by_source_table():
    formal = {
        "vid": "org_formal",
        "source_table": "dwd_org_heis_info",
        "source_record_id": "not-an-org-id",
        "org_id": "another-value",
    }
    temporary = {
        "vid": "org_temporary",
        "source_table": "dwd_scholar",
        "org_id": "even-if-present",
    }
    assert loader.is_canonical_organization(formal)
    assert not loader.is_canonical_organization(temporary)
    assert not loader.is_canonical_organization({"source_table": "dwd_org_bankruptcy_public_cases"})
    assert not loader.is_canonical_organization({"source_table": "dwd_org_merger_acquisition_info"})


def test_scholar_graph_person_is_not_filtered_when_source_record_id_does_not_match(
    monkeypatch,
):
    def fake_catalog(_graph, tag, _fields):
        if tag == "Person":
            return [
                {
                    "vid": "person_existing",
                    "name_zh": "张三",
                    "name_en": "Zhang San",
                    "scholar_org": "北京大学",
                    "source_table": "dwd_scholar",
                    "source_record_id": "not-scholar-id",
                }
            ]
        return []

    monkeypatch.setattr(loader, "graph_catalog", fake_catalog)
    monkeypatch.setattr(
        loader,
        "fetch_all",
        lambda _connection, _sql: [
            {
                "scholar_id": "different-id",
                "name_zh": "其他人",
                "name_en": None,
                "scholar_org_name_zh": None,
                "scholar_org_name_en": None,
                "work_experience_institution_zh": None,
                "work_experience_institution_en": None,
            }
        ],
    )
    people, organizations = loader.canonical_entities(object(), object())
    assert organizations == []
    assert people[0]["vid"] == "person_existing"
    assert people[0]["name_zh"] == "张三"
    assert "北京大学" in loader.person_org_names(people[0])


def test_person_organization_evidence_uses_current_and_work_history():
    person = {
        "scholar_org_name_zh": "清华大学",
        "scholar_org_name_en": "Tsinghua University",
        "work_experience_institution_zh": '["北京大学"]',
        "work_experience_institution_en": None,
    }
    names = loader.person_org_names(person)
    assert "清华大学" in names
    assert "tsinghuauniversity" in names
    assert "北京大学" in names


def test_edge_statement_preserves_patent_outgoing_direction():
    edge = loader.EdgeRecord(
        edge_type="INVENTED_BY",
        source_vid="patent_1",
        target_vid="person_1",
        rank=2,
        properties=(("sequence", 2), ("confidence", 0.80)),
    )
    statement = loader.edge_statement("INVENTED_BY", [edge])
    assert '"patent_1"->"person_1"@2' in statement
    assert "INVENTED_BY(sequence,confidence)" in statement


def test_execute_batched_automatically_splits_rejected_large_batches():
    class LimitedBatchGraph:
        def __init__(self):
            self.accepted_sizes = []

        def execute_write(self, statement):
            size = int(statement)
            if size > 2:
                raise RuntimeError("模拟TRSGraph单批过大")
            self.accepted_sizes.append(size)

    graph = LimitedBatchGraph()
    loader.execute_batched(graph, list(range(5)), lambda batch: str(len(batch)), batch_size=5)
    assert sum(graph.accepted_sizes) == 5
    assert max(graph.accepted_sizes) <= 2


def test_review_record_does_not_create_a_stub_or_edge():
    record = loader.review(
        "CN1",
        "INVENTED_BY",
        "张三",
        "同名候选仍有多个",
        None,
        [{"vid": "person_1"}, {"vid": "person_2"}],
        ["姓名相同"],
    )
    assert record.confidence is None
    assert len(record.candidates) == 2
    assert not hasattr(loader, "person_stub_statement")
    assert not hasattr(loader, "organization_stub_statement")


def test_ensure_schema_executes_relation_ddl_and_only_adds_missing(monkeypatch):
    ddl = """
    CREATE EDGE IF NOT EXISTS INVENTED_BY (confidence double);
    CREATE EDGE IF NOT EXISTS APPLIED_BY (confidence double);
    CREATE EDGE IF NOT EXISTS OWNED_BY (confidence double);
    """
    monkeypatch.setattr(loader, "DDL_FILE", Path("unused"))
    monkeypatch.setattr(Path, "read_text", lambda *_args, **_kwargs: ddl)
    graph = FakeGraph()
    loader.ensure_schema(graph)
    creates = [item for item in graph.writes if item.startswith("CREATE EDGE")]
    alters = [item for item in graph.writes if item.startswith("ALTER EDGE")]
    assert len(creates) == 3
    assert len(alters) == 5
    assert all("DROP" not in item for item in graph.writes)


def test_milvus_unique_match_promotes_organization_edge(monkeypatch, tmp_path):
    state = tmp_path / "org_domain_organization.bm25.json"
    state.write_text("{}", encoding="utf-8")

    class Store:
        def has_collection(self, entity_type):
            return entity_type == "Organization"

        def collection_name(self, entity_type):
            return f"org_domain_{entity_type.lower()}"

    candidate = type(
        "Candidate",
        (),
        {
            "vid": "org_pku",
            "canonical_name": "北京大学",
            "score": 0.93,
            "retrieval_score": 0.9,
            "evidence": ("name_high_similarity",),
        },
    )()
    decision = type(
        "Decision",
        (),
        {
            "status": "matched",
            "selected_vid": "org_pku",
            "score": 0.93,
            "margin": 0.15,
            "reason": "qualified",
            "candidates": (candidate,),
        },
    )()
    matcher = type("Matcher", (), {"align": lambda self, context: decision})()
    monkeypatch.setattr(loader.BM25SparseEncoder, "load", lambda path: object())
    monkeypatch.setattr(loader, "OrganizationHybridMatcher", lambda *args, **kwargs: matcher)
    record = loader.ReviewRecord(
        patent_id="CN2",
        relation_type="APPLIED_BY",
        source_name="北大",
        reason="not exact",
        confidence=None,
        candidates=[],
        evidence=[],
        patent_vid="patent_2",
        sequence=1,
        role="applicant",
        source_record_id="2:applicants:1",
    )
    edges, remaining = loader.promote_vector_organization_matches(
        [record], state_dir=tmp_path, store=Store()
    )
    assert not remaining
    assert edges[0].target_vid == "org_pku"
    assert dict(edges[0].properties)["match_method"] == "milvus_bm25_dense_hybrid"
    assert dict(edges[0].properties)["confidence"] == 0.93


def test_person_review_is_not_promoted_by_organization_vector_index(tmp_path):
    class Store:
        def has_collection(self, entity_type):
            return True

        def collection_name(self, entity_type):
            return f"org_domain_{entity_type.lower()}"

    (tmp_path / "org_domain_organization.bm25.json").write_text("{}", encoding="utf-8")
    record = loader.ReviewRecord(
        patent_id="CN3",
        relation_type="INVENTED_BY",
        source_name="张三",
        reason="same name",
        confidence=None,
        candidates=[],
        evidence=[],
    )
    original_load = loader.BM25SparseEncoder.load
    loader.BM25SparseEncoder.load = lambda path: object()
    try:
        edges, remaining = loader.promote_vector_organization_matches(
            [record], state_dir=tmp_path, store=Store()
        )
    finally:
        loader.BM25SparseEncoder.load = original_load
    assert not edges
    assert remaining == [record]
