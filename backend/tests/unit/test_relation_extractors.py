"""关系抽取脚本的旧口径等价性单元测试。

覆盖确定性 rank 公式、nGQL 边渲染、端点解析（keyword/paper 桩/机构精确名）、
机构域 spec 引擎的候选生成与字段映射、以及各结构边脚本的端点/属性语义。
"""

from __future__ import annotations

import hashlib
import unicodedata

import pytest

from script.relation_extractors_one_relation import common, org_edges, resolvers
from script.relation_extractors_one_relation.affiliated_with_relation import affiliated_with
from script.relation_extractors_one_relation.authored_by_fallback_relation import (
    authored_by_fallback,
)
from script.relation_extractors_one_relation.authored_by_relation import authored_by
from script.relation_extractors_one_relation.catalog import RELATION_EDGE_SPECS, SPECS_BY_KEY
from script.relation_extractors_one_relation.child_of_relation import child_of
from script.relation_extractors_one_relation.coauthor_with_relation import coauthor_with
from script.relation_extractors_one_relation.covers_chain_relation import covers_chain
from script.relation_extractors_one_relation.downstream_of_relation import downstream_of
from script.relation_extractors_one_relation.has_node_relation import has_node
from script.relation_extractors_one_relation.member_of_family_relation import member_of_family
from script.relation_extractors_one_relation.paper_cites_relation import paper_cites
from script.relation_extractors_one_relation.paper_has_keyword_relation import paper_has_keyword
from script.relation_extractors_one_relation.patent_has_keyword_relation import patent_has_keyword
from script.relation_extractors_one_relation.published_in_relation import published_in
from script.relation_extractors_one_relation.referenced_by_relation import referenced_by


def _md5(value: str) -> str:
    return hashlib.md5(value.encode("utf-8")).hexdigest()


class TestRankAndRendering:
    def test_edge_rank_legacy_formula(self):
        # 旧公式：sha256 前 8 字节大端 & (2^63-1)
        key = "INVOLVED_IN|org_A|event_t_1|rid"
        expected = int.from_bytes(hashlib.sha256(key.encode("utf-8")).digest()[:8], "big") & (
            (1 << 63) - 1
        )
        assert common.edge_rank("INVOLVED_IN", "org_A", "event_t_1", "rid") == expected

    def test_render_edge_insert_rank_mode(self):
        record = common.EdgeRecord(
            "HAS_NODE",
            "chain_C1",
            "node_N1",
            {"confidence": 1.0, "source_table": "t"},
            rank=7,
        )
        statement = common.render_edge_insert([record])
        assert statement.startswith("INSERT EDGE `HAS_NODE` (`confidence`,`source_table`) VALUES")
        # 旧 ngql_literal 数值口径：整数浮点渲染为整数
        assert '"chain_C1"->"node_N1"@7:(1,"t");' in statement

    def test_render_requires_uniform_signature(self):
        a = common.EdgeRecord("E", "s", "t", {"a": 1}, rank=0)
        b = common.EdgeRecord("E", "s2", "t2", {"b": 1}, rank=0)
        with pytest.raises(ValueError):
            common.render_edge_insert([a, b])

    def test_apply_since(self):
        sql = "SELECT * FROM t ORDER BY id"
        assert common.apply_since(sql, "2026-01-01") == (
            "SELECT * FROM t WHERE updated_time > :since ORDER BY id"
        )
        assert common.apply_since("SELECT * FROM t WHERE x = 1", "s") == (
            "SELECT * FROM t WHERE x = 1 AND updated_time > :since"
        )


class TestResolvers:
    def test_keyword_vid_unified_formula(self):
        keyword = "智能 传感器"
        normalized = " ".join(unicodedata.normalize("NFKC", keyword).strip().split())
        assert resolvers.keyword_vid(keyword) == f"keyword_{_md5(normalized.casefold())}"

    def test_paper_source_id_strips_suffix(self):
        assert resolvers.paper_source_id("P123__2") == "P123"
        assert resolvers.paper_source_id("P123") == "P123"
        assert resolvers.paper_source_id(None) == ""

    def test_paper_stub_vid_16_char_md5(self):
        assert resolvers.paper_stub_vid("paper_ref", "10.1/x") == f"paper_ref_{_md5('10.1/x')[:16]}"

    def test_exact_organization_resolver_unique_only(self):
        resolver = resolvers.ExactOrganizationResolver({"唯一名": {"O1"}, "多命中": {"O1", "O2"}})
        assert resolver.resolve_exact("唯一名") == "O1"
        assert resolver.resolve_exact("多命中") is None
        assert resolver.resolve_exact("不存在") is None

    def test_person_vid_for_row_entity_formula(self):
        row = {"org_id": "O1", "external_id": None, "executives_name": "张三"}
        vid = resolvers.person_vid_for_row(row, "executive", "executives_name")
        identity = "|".join(("executive", "o1", "张三"))
        assert vid == f"person_{_md5(identity)}"

    def test_person_vid_for_row_external_id_fallback(self):
        # 分叉修复：缺 org_id 时 external_id 参与哈希（实体侧公式）。
        row = {"external_id": "E9", "executives_name": "李四"}
        vid = resolvers.person_vid_for_row(row, "executive", "executives_name")
        identity = "|".join(("executive", "e9", "李四"))
        assert vid == f"person_{_md5(identity)}"


class TestCatalog:
    def test_32_active_specs_11_keys(self):
        assert len(RELATION_EDGE_SPECS) == 32
        assert len(SPECS_BY_KEY) == 11
        assert set(SPECS_BY_KEY) == {
            "legal_representative",
            "shareholder",
            "executive",
            "beneficial_owner",
            "actual_controller",
            "investment",
            "acquisition",
            "subsidiary",
            "news",
            "event",
            "product",
        }

    def test_dead_specs_not_migrated(self):
        tables = {spec.source_table for spec in RELATION_EDGE_SPECS}
        assert "dwd_zh_project" not in tables
        assert "dwd_org_industry_chain_dtl" not in tables
        assert "dwd_org_industry_chain_prod_dtl" not in tables

    def test_involved_in_17_tables(self):
        assert len(SPECS_BY_KEY["event"]) == 17
        assert "dwd_org_bankruptcy_public_cases" in {s.source_table for s in SPECS_BY_KEY["event"]}
        assert "dwd_org_bankruptcy_public_cases_list" in {
            s.source_table for s in SPECS_BY_KEY["event"]
        }


class TestOrgEdgeEngine:
    def _resolver(self):
        return resolvers.ExactOrganizationResolver({})

    def _spec(self, key):
        return SPECS_BY_KEY[key][0]

    def test_edge_props_order_and_confidence(self):
        spec = self._spec("event")
        row = {"org_id": "O1", "year": "2023"}
        props = org_edges.edge_props(spec, row, "O1|2023", "B", {"role": "subject"})
        # 属性顺序由 spec.edge_properties 决定
        assert tuple(props) == spec.edge_properties
        # relation_confidence：dwd_ 表 0.55 + org_id 0.25（其余项不满足）= 0.80
        assert props["confidence"] == 0.80
        assert props["source_record_id"] == "O1|2023"
        assert props["role"] == "subject"
        assert "extra_json" in props

    def test_legal_rep_edge(self):
        spec = [
            s for s in SPECS_BY_KEY["legal_representative"] if s.source_table == "dwd_org_base_info"
        ][0]
        row = {"org_id": "O1", "lerep": "赵六"}
        records = org_edges.extract_edge(spec, row, "O1|赵六", "B", self._resolver())
        assert len(records) == 1
        rec = records[0]
        identity = "|".join(("legal_representative", "o1", "赵六"))
        assert rec.source_vid == f"person_{_md5(identity)}"
        assert rec.target_vid == "org_O1"
        assert rec.source_tag == "Person"
        assert rec.target_tag == "Organization"
        assert rec.rank == common.edge_rank(
            "LEGAL_REP_OF", rec.source_vid, rec.target_vid, "O1|赵六"
        )

    def test_shareholder_person_branch_entity_formula(self):
        spec = [
            s for s in SPECS_BY_KEY["shareholder"] if s.source_table == "dwd_org_shareholder_info"
        ][0]
        row = {"org_id": "O1", "owners_name": "张三", "owners_type": "自然人"}
        records = org_edges.extract_edge(spec, row, "O1|张三|自然人", "B", self._resolver())
        identity = "|".join(("shareholder", "o1", "张三"))
        assert records[0].source_vid == f"person_{_md5(identity)}"

    def test_shareholder_org_branch(self):
        spec = [
            s for s in SPECS_BY_KEY["shareholder"] if s.source_table == "dwd_org_shareholder_info"
        ][0]
        row = {"org_id": "O1", "inv_org_id": "O2", "owners_name": "某公司"}
        records = org_edges.extract_edge(spec, row, "rid", "B", self._resolver())
        assert records[0].source_vid == "org_O2"
        assert records[0].source_tag == "Organization"

    def test_shareholder_unknown_type_invalid(self):
        spec = [
            s for s in SPECS_BY_KEY["shareholder"] if s.source_table == "dwd_org_shareholder_info"
        ][0]
        row = {"org_id": "O1", "owners_name": "X", "owners_type": "其它"}
        with pytest.raises(ValueError):
            org_edges.extract_edge(spec, row, "rid", "B", self._resolver())

    def test_foreign_shareholder_requires_exact_org(self):
        spec = [
            s for s in SPECS_BY_KEY["shareholder"] if s.source_table == "dwd_forg_shareholder_info"
        ][0]
        with pytest.raises(ValueError):
            org_edges.extract_edge(
                spec, {"org_id": "O1", "owners_name": "Unknown"}, "rid", "B", self._resolver()
            )

    def test_actual_controller_self_loop_guard(self):
        spec = SPECS_BY_KEY["actual_controller"][0]
        row = {"org_id": "O1", "entity_type": "person", "entity_name": "张三"}
        records = org_edges.extract_edge(spec, row, "rid", "B", self._resolver())
        assert records[0].source_tag == "Person"
        # 机构分支自环：entity_eid == org_id → 抛错
        row2 = {"org_id": "O1", "entity_type": "company", "entity_eid": "O1", "entity_name": "自环"}
        with pytest.raises(ValueError):
            org_edges.extract_edge(spec, row2, "rid", "B", self._resolver())

    def test_bankruptcy_party_targets_bankruptcy_event(self):
        spec = [
            s
            for s in SPECS_BY_KEY["event"]
            if s.source_table == "dwd_org_bankruptcy_public_cases_list"
        ][0]
        row = {"org_id": "O1", "case_no": "CASE1", "bankruptcy_party_id": "P1"}
        records = org_edges.extract_edge(spec, row, "P1", "B", self._resolver())
        assert records[0].target_vid == "event_dwd_org_bankruptcy_public_cases_CASE1"
        assert records[0].properties["role"] == "bankruptcy_party"

    def test_bid_party_role_by_table(self):
        spec = [s for s in SPECS_BY_KEY["event"] if s.source_table == "dwd_bid_win_candidate_out"][
            0
        ]
        row = {"org_id": "O1", "u_id": "U1"}
        records = org_edges.extract_edge(spec, row, "U1|O1", "B", self._resolver())
        assert records[0].target_vid == "event_dwd_bid_base_out_U1"
        assert records[0].properties["role"] == "winner_candidate"

    def test_make_mapper_filters_virtual_rows(self):
        spec = SPECS_BY_KEY["news"][0]
        mapper = org_edges.make_mapper(spec, self._resolver())
        assert mapper(spec.source_table, {"org_id": "O1", "data_source": "mock"}, "B") == []

    def test_news_target_matches_entity_vid(self):
        # 实体侧 News VID = news_{表}_{stable_record_id(整行)}，关系侧必须同公式。
        spec = SPECS_BY_KEY["news"][0]
        row = {"org_id": "O1", "news_title": "标题", "news_date": "2026-01-01"}
        from script.entity_extractors_one_entity.common import bounded_vid, stable_record_id

        record_id = stable_record_id(spec.source_table, row)
        records = org_edges.extract_edge(spec, row, record_id, "B", self._resolver())
        assert records[0].target_vid == bounded_vid(f"news_{spec.source_table}_{record_id}")


class TestChainEdges:
    def test_has_node(self):
        assert has_node("t", {"chain_code": "C1", "node_id": "N1"}, "B")[0].target_vid == "node_N1"
        assert has_node("t", {"node_id": "N1"}, "B") == []

    def test_child_of(self):
        rec = child_of("t", {"node_id": "N1", "parent_id": "P1"}, "B")[0]
        assert rec.source_vid == "node_N1" and rec.target_vid == "node_P1"
        assert rec.rank == 0 and rec.properties == {}

    def test_downstream_of(self):
        rec = downstream_of("t", {"node_id": "N1", "downstream_link_code": "D1"}, "B")[0]
        assert rec.target_vid == "node_D1"

    def test_belongs_to_node_score_fallback(self):
        from script.relation_extractors_one_relation.belongs_to_node_relation import (
            belongs_to_node,
        )

        rec = belongs_to_node("t", {"antitypic": "A1", "node_id": "N1", "chain_score": "x"}, "B")[0]
        assert rec.properties["chain_score"] == 0.0
        assert rec.source_tag == "Organization"
        assert rec.target_tag == "IndustryNode"

    def test_covers_chain(self):
        rec = covers_chain("t", {"news_id": "N1", "chain_code": "C1"}, "B")[0]
        assert rec.source_vid == "news_N1" and rec.target_vid == "chain_C1"


class TestPaperEdges:
    def test_authored_by_strips_suffix(self):
        rec = authored_by(
            "t",
            {"paper_id": "P1__2", "author_id": "A1", "author_sequence": 1, "correspond": 0},
            "B",
        )[0]
        assert rec.source_vid == "paper_P1"
        assert rec.properties["author_order"] == "1"
        assert rec.properties["confidence"] == 1.0

    def test_published_in(self):
        rec = published_in("t", {"id": "P1__3", "publication_id": "J9"}, "B")[0]
        assert rec.source_vid == "paper_P1" and rec.target_vid == "journal_J9"

    def test_paper_has_keyword_en_json(self):
        recs = paper_has_keyword(
            "dwd_en_paper_classification", {"id": "P1", "keywords": '["AI", "ML"]'}, "B"
        )
        assert [r.target_vid for r in recs] == [
            resolvers.keyword_vid("AI"),
            resolvers.keyword_vid("ML"),
        ]

    def test_paper_cites_doi_stub(self):
        rec = paper_cites("dwd_zh_paper_reference", {"id": "P1", "doi": "10.1/x"}, "B")[0]
        assert rec.edge_type == "CITES"
        assert rec.target_vid == resolvers.paper_stub_vid("paper_ref", "10.1/x")
        assert rec.properties == {"confidence": 0.5, "reference_identifier": "10.1/x"}
        assert rec.validate_endpoints is False

    def test_related_to_confidence(self):
        rec = paper_cites("dwd_zh_paper_related", {"id": "P1", "doi": "10.1/y"}, "B")[0]
        assert rec.edge_type == "RELATED_TO" and rec.properties["confidence"] == 0.7

    def test_referenced_by_expands_report_ids(self):
        recs = referenced_by("t", {"paper_id": "P1", "report_id": '["R1", "R2"]'}, "B")
        assert [r.target_vid for r in recs] == ["report_R1", "report_R2"]
        assert recs[0].source_vid == "paper_rp_P1"


class TestPatentEdges:
    def test_patent_has_keyword(self):
        recs = patent_has_keyword("dwd_patent", {"patent_id": "PN1", "keywords": '["AI"]'}, "B")
        assert recs[0].source_vid == "patent_PN1"
        assert recs[0].target_vid == resolvers.keyword_vid("AI")
        assert recs[0].properties["source_record_id"] == "PN1"

    def test_member_of_family(self):
        rec = member_of_family(
            "dwd_patent", {"patent_id": "PN1", "simple_family_number": "F1"}, "B"
        )[0]
        assert rec.target_vid == "patent_family_F1"
        assert rec.properties["match_method"] == "source_family_number"


class TestScholarEdges:
    def test_affiliated_with_org_id_direct(self):
        rec = affiliated_with(
            "dwd_scholar",
            {"scholar_id": "S1", "scholar_org_id": "O1", "scholar_org_name_zh": "某大学"},
            "B",
        )[0]
        assert rec.target_vid == "org_O1"
        assert rec.properties["confidence"] == 1.0
        assert rec.properties["organization_base"] == "dwd_scholar"
        assert rec.validate_endpoints is False
        assert rec.identity == {"source_record_id": "S1"}

    def test_affiliated_with_placeholder(self):
        rec = affiliated_with(
            "dwd_scholar",
            {"scholar_id": "S1", "scholar_org_name_zh": "某研究所"},
            "B",
        )[0]
        key = "某研究所".strip().lower()
        assert rec.target_vid == f"org_{_md5(key)[:16]}"
        assert rec.properties["confidence"] == 0.6
        assert rec.properties["match_method"] == "org_name_md5_placeholder"

    def test_affiliated_with_no_org_skipped(self):
        assert affiliated_with("dwd_scholar", {"scholar_id": "S1"}, "B") == []

    def test_authored_by_fallback(self):
        rec = authored_by_fallback(
            "dwd_scholar_paper_relation",
            {"paper_id": "P1", "scholar_id": "S1", "citations": 3},
            "B",
        )[0]
        assert rec.source_vid == "paper_P1"  # 原始 paper_id，不去后缀
        assert rec.properties["confidence"] == 0.9
        assert rec.source_tag == "Paper" and rec.target_tag == "Person"
        assert rec.identity == {"source_record_id": "P1_S1"}

    def test_coauthor_with(self):
        rec = coauthor_with(
            "dwd_scholar_coauthor",
            {"scholar_id": "S1", "co_scholar_id": "S2", "co_paper_count": 5},
            "B",
        )[0]
        assert rec.source_vid == "person_S1" and rec.target_vid == "person_S2"
        assert rec.properties["co_paper_count"] == 5
        assert rec.properties["confidence"] == 1.0
        assert rec.identity == {"source_record_id": "S1_S2"}


class TestPatentMatchingPrimitives:
    """专利域匹配原语（移植自旧 load_patent_relations.py，口径对拍已验证）。"""

    def test_normalize_name_and_identifier(self):
        from script.relation_extractors_one_relation.patent_matching import (
            normalize_identifier,
            normalize_name,
        )

        assert normalize_name("  某公司 ") == "某公司"
        assert normalize_identifier(" CN-123456 ") == "cn123456"

    def test_application_number_key(self):
        from script.relation_extractors_one_relation.patent_matching import (
            application_number_key,
        )

        assert application_number_key("CN202310123456.7") == "cn202310123456"

    def test_identifier_index_and_candidates_unique(self):
        from script.relation_extractors_one_relation.patent_matching import (
            identifier_index,
            patent_candidates,
        )

        rows = [
            {
                "vid": "patent_P1",
                "patent_id": "P1",
                "publication_number": "PUB1",
                "granted_number": "G1",
                "application_number": "CN202310123456.7",
            },
        ]
        index = identifier_index(rows)
        assert patent_candidates(index, "P1") == ["patent_P1"]
        assert patent_candidates(index, "PUB1") == ["patent_P1"]
        assert patent_candidates(index, "CN202310123456.7") == ["patent_P1"]

    def test_names_from_json_or_plain(self):
        from script.relation_extractors_one_relation.patent_matching import names_from

        assert names_from('["甲", "乙"]') == {"甲", "乙"}
        assert names_from("甲") == {"甲"}

    def test_edge_property_schemas_cover_four_edges(self):
        from script.relation_extractors_one_relation.patent_matching import (
            EDGE_PROPERTY_SCHEMAS,
        )

        assert set(EDGE_PROPERTY_SCHEMAS) == {"INVENTED_BY", "APPLIED_BY", "OWNED_BY", "CITES"}


class TestProjectRelationModules:
    """项目域 5 个脚本的导入与关键常量冒烟。"""

    def test_modules_importable_and_share_matcher(self):
        from script.relation_extractors_one_relation import (
            funded_by_relation,
            has_output_relation,
            has_participant_relation,
            leads_relation,
            project_has_keyword_relation,
        )

        for module in (
            funded_by_relation,
            leads_relation,
            has_participant_relation,
            has_output_relation,
            project_has_keyword_relation,
        ):
            assert callable(module.main)
