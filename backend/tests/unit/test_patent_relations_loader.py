from pathlib import Path

from script import load_patent_relations as loader


class FakeResult:
    def __init__(self, records):
        self.records = records


class FakeGraph:
    def __init__(self):
        self.writes = []

    def execute_write(self, statement):
        self.writes.append(statement)

    def execute_read(self, statement):
        if any(edge in statement for edge in ("INVENTED_BY", "APPLIED_BY", "OWNED_BY")):
            return FakeResult([{"Field": "confidence"}])
        if "CITES" in statement:
            return FakeResult([{"Field": "reference_identifier"}])
        if "OUTPUT_OF" in statement:
            return FakeResult(
                [
                    {"Field": "source_table"},
                    {"Field": "source_record_id"},
                    {"Field": "ingest_batch"},
                    {"Field": "ingest_time"},
                ]
            )
        raise AssertionError(statement)


def test_normalizers_are_deterministic():
    assert loader.normalize_name("  清华大学（深圳） ") == "清华大学深圳"
    assert loader.normalize_identifier("CN 123-456 A") == "cn123456a"


def test_application_number_key_aligns_supplier_and_project_formats():
    assert loader.application_number_key("CN-201811400598-A") == "cn201811400598"
    assert loader.application_number_key("CN201811400598.8") == "cn201811400598"
    assert loader.application_number_key("ZL201811400598.8") == "cn201811400598"
    assert loader.application_number_key("2018114005988") == "cn201811400598"


def test_name_index_includes_foreign_aliases_and_domain_vid():
    rows = [{"vid": "org_1", "name_en": "ACME Inc.", "name_alias": "ACME;艾克米"}]
    index = loader.make_index(rows, ("name_en", "name_alias"))
    assert index["acmeinc"][0]["vid"] == "org_1"
    assert index["艾克米"][0]["vid"] == "org_1"


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
    assert len(alters) == 2
    assert all("DROP" not in item for item in graph.writes)


class FakeLLM:
    def synthesize(self, _prompt, max_tokens):
        assert max_tokens > 0
        return """{"results":[{"source_name":"SINOPEC","subject_type":"Organization","aliases":["中国石化"],"candidate_vids":["org_1","org_hallucinated"],"reason":"英文简称可能对应中国石化"}]}"""


def test_llm_enrichment_judges_type_alias_and_only_keeps_existing_candidates(monkeypatch):
    reviews = [
        loader.ReviewRecord(
            patent_id="CN1",
            relation_type="APPLIED_BY",
            source_name="SINOPEC",
            reason="名称未精确命中",
            confidence=None,
            candidates=[],
            evidence=[],
        )
    ]
    organizations = [
        {
            "vid": "org_1",
            "name_cn": "中国石油化工股份有限公司",
            "name_en": "China Petroleum & Chemical Corporation",
            "name_alias": "Sinopec Corp",
        }
    ]
    monkeypatch.setattr(loader, "get_llm_client", lambda: FakeLLM())
    monkeypatch.setattr(
        loader, "canonical_entities", lambda _graph, _connection: ([], organizations)
    )
    processed = loader.enrich_reviews_with_llm(reviews, object(), object(), batch_size=1)
    assert processed == 1
    assert reviews[0].llm_subject_type == "Organization"
    assert reviews[0].llm_aliases == ["中国石化"]
    assert [item["vid"] for item in reviews[0].llm_candidate_entities] == ["org_1"]
    assert "org_hallucinated" not in str(reviews[0].llm_candidate_entities)
