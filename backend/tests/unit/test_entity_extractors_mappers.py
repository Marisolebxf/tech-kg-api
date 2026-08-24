"""单实体抽取脚本的旧口径等价性单元测试。

用构造行验证关键 mapper 的 VID 公式、字段候选链、过滤规则、置信度打分与
合并保护逻辑与旧脚本（organization_entity_etl / load_patent_graph /
load_project_graph / paper_journal_chain_etl）口径一致。
"""

from __future__ import annotations

import hashlib
import json
import unicodedata

import pytest

from script.entity_extractors_one_entity import common, mappers
from script.entity_extractors_one_entity.datasource_entity import datasource_records


def _md5(value: str) -> str:
    return hashlib.md5(value.encode("utf-8")).hexdigest()


class TestVidHelpers:
    def test_person_vid_matches_legacy_formula(self):
        # 旧公式：person_{md5(kind|org|name|birth|country)}，各分量 NFKC+casefold
        kind = "executive"
        parts = ["ORG-1", "张三", "1980-01-01", "CN"]
        identity = "|".join((kind, *(unicodedata.normalize("NFKC", p).casefold() for p in parts)))
        assert common.person_vid(kind, *parts) == f"person_{_md5(identity)}"

    def test_person_vid_skips_none_components(self):
        identity = "|".join(("shareholder", "org-1", "张三"))
        assert common.person_vid("shareholder", "ORG-1", "张三", None, None) == (
            f"person_{_md5(identity)}"
        )

    def test_product_vid_full_md5(self):
        name = "智能 传感器"
        normalized = unicodedata.normalize("NFKC", name).casefold()
        assert common.product_vid(name) == f"product_{_md5(normalized)}"

    def test_bounded_vid_truncates_over_64_bytes(self):
        long_vid = "event_" + "a" * 100
        result = common.bounded_vid(long_vid)
        assert len(result.encode("utf-8")) <= 64
        assert result.endswith("_" + _md5(long_vid))

    def test_stable_record_id_composite_key_all_present(self):
        row = {"org_id": "O1", "year": "2023", "amount": "1"}
        assert common.stable_record_id("t", row, ("org_id", "year")) == "O1|2023"

    def test_stable_record_id_falls_back_to_full_row_md5(self):
        row = {"org_id": "O1", "year": None}
        canonical = json.dumps(
            {"org_id": "O1", "year": None},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        assert common.stable_record_id("t", row, ("org_id", "year")) == _md5(f"t|{canonical}")


class TestOrgDomainCommon:
    def test_is_virtual_source_row(self):
        assert common.is_virtual_source_row({"data_source": "mock"})
        assert common.is_virtual_source_row({"source_system": "stub_loader"})
        assert not common.is_virtual_source_row({"data_source": "dwd"})
        assert not common.is_virtual_source_row({})

    def test_entity_confidence_scoring(self):
        row = {"org_id": "O1", "name_cn": "某公司", "country": "CN"}
        # dwd 表 0.4 起步 + org_id 0.2 + name_cn 0.2 + country 0.1 = 0.9
        assert common.entity_confidence(row, source_table="dwd_org_base_info") == 0.9
        assert common.entity_confidence(row, source_table="other_table") == 0.8

    def test_to_float_or_none(self):
        assert common.to_float_or_none("1,234.5") == 1234.5
        assert common.to_float_or_none("-") is None
        assert common.to_float_or_none(None) is None

    def test_apply_since_before_order_by(self):
        sql = "SELECT * FROM t ORDER BY id"
        assert common.apply_since(sql, "2026-01-01") == (
            "SELECT * FROM t WHERE updated_time > :since ORDER BY id"
        )
        assert common.apply_since(sql, None) == sql


class TestOrganizationRecord:
    def test_missing_org_id_skips(self):
        assert mappers.organization_record("dwd_org_base_info", {"name_cn": "无ID公司"}, "B") == []

    def test_field_candidates_and_vid(self):
        row = {
            "org_id": "ORG-9",
            "company_name": " fallback 前的中文名缺失 ",
            "person_num": "500",
            "incorporation_year": "2010",
            "registered_capital_value": "1000万",
            "industry": "人工智能",
            "industry_l1_name": "不该优先",
            "lerep": "李四",
        }
        records = mappers.organization_record("dwd_org_base_info", row, "B")
        assert len(records) == 1
        rec = records[0]
        assert rec.vid == "org_ORG-9"
        assert rec.merge_protect is True
        assert rec.properties["name_cn"] == "fallback 前的中文名缺失"
        assert rec.properties["org_size"] == "500"
        assert rec.properties["founded_year"] == 2010
        # 旧 to_float 会剔除非数字字符："1000万" → 1000.0
        assert rec.properties["registered_capital"] == 1000.0
        assert rec.properties["industry_class"] == "人工智能"
        assert rec.properties["legal_rep"] == "李四"
        assert rec.properties["org_kind"] == "domestic_organization"

    def test_org_kind_semantic_enum(self):
        rec = mappers.organization_record(
            "dwd_org_heis_info", {"org_id": "H1", "name_cn": "某大学"}, "B"
        )
        assert rec[0].properties["org_kind"] == "domestic_university"

    def test_enrichment_drops_none_fields(self):
        row = {"org_id": "ORG-1", "main_prod": "产品A"}
        rec = mappers.organization_record("dwd_org_stock_base", row, "B")[0]
        # 稀疏 enrichment 行不应下发 name_cn=None 等空字段
        assert "name_cn" not in rec.properties
        assert rec.properties["main_products"] == "产品A"

    def test_virtual_row_skipped(self):
        row = {"org_id": "ORG-1", "name_cn": "x", "data_source": "mock"}
        assert mappers.organization_record("dwd_org_base_info", row, "B") == []


class TestEventRecord:
    def test_composite_key_and_semantic_kind(self):
        row = {"org_id": "O1", "year": "2023", "amount": "100"}
        rec = mappers.event_record("dwd_org_annual_financial_info", row, "B")[0]
        assert rec.vid == "event_dwd_org_annual_financial_info_O1|2023"
        assert rec.properties["event_type"] == "annual_finance"
        assert rec.properties["amount"] == 100.0
        assert rec.merge_protect is True

    def test_missing_composite_key_falls_back_to_row_md5(self):
        row = {"org_id": "O1"}
        rec = mappers.event_record("dwd_org_annual_financial_info", row, "B")[0]
        canonical = json.dumps(
            {"org_id": "O1"}, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        expected = common.bounded_vid(
            f"event_dwd_org_annual_financial_info_{_md5('dwd_org_annual_financial_info|' + canonical)}"
        )
        assert rec.vid == expected

    def test_title_fallback_to_cn_table_name(self):
        row = {"penalty_id": "P1"}
        rec = mappers.event_record("dwd_org_company_punish", row, "B")[0]
        assert rec.properties["title"] == "行政处罚"
        # content 回退为整行 JSON
        assert rec.properties["content"] is not None

    def test_bid_item_full_composite_key(self):
        row = {
            "u_id": "U1",
            "target_item_name": "标的物",
            "bid_section_number": "S1",
            "org_id": "O1",
        }
        rec = mappers.event_record("dwd_bid_target_item_out", row, "B")[0]
        assert rec.vid == "event_dwd_bid_target_item_out_U1|标的物|S1"


class TestNewsRecords:
    def test_org_news_vid_uses_table_and_row_hash(self):
        row = {"news_id": "N1", "news_title": "标题", "org_id": "O1"}
        rec = mappers.news_org_record("dwd_org_important_news_info", row, "B")[0]
        canonical = json.dumps(
            {"news_id": "N1", "news_title": "标题", "org_id": "O1"},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        rid = _md5(f"dwd_org_important_news_info|{canonical}")
        assert rec.vid == common.bounded_vid(f"news_dwd_org_important_news_info_{rid}")
        assert rec.merge_protect is True

    def test_chain_news_skips_missing_news_id_and_uses_relaese_date(self):
        assert mappers.news_chain_record("dwd_industry_chain_news_info", {"title": "t"}, "B") == []
        row = {
            "news_id": "N9",
            "news_title": "产业链新闻",
            "summary": "摘要",
            "relaese_date": "2026-01-02",
        }
        rec = mappers.news_chain_record("dwd_industry_chain_news_info", row, "B")[0]
        assert rec.vid == "news_N9"
        assert rec.properties["release_date"] == "2026-01-02"
        assert rec.properties["content"] == "摘要"
        assert rec.properties["source_system"] == "dwd_industry_chain_news_info"


class TestProductRecord:
    def test_product_from_organization_row(self):
        row = {"org_id": "O1", "main_prod": "  智能传感器 "}
        rec = mappers.product_record("dwd_org_org_product_info", row, "B")[0]
        normalized = unicodedata.normalize("NFKC", "智能传感器").casefold()
        assert rec.vid == f"product_{_md5(normalized)}"
        assert rec.properties["name"] == "智能传感器"
        assert rec.merge_protect is True

    def test_product_requires_org_id(self):
        assert mappers.product_record("dwd_org_base_info", {"main_prod": "X"}, "B") == []

    def test_product_category_candidates(self):
        row = {"org_id": "O1", "main_prod": "X", "industry_class": "装备制造"}
        rec = mappers.product_record("dwd_org_base_info", row, "B")[0]
        assert rec.properties["category"] == "装备制造"


class TestPersonRecords:
    def test_shareholder_organization_type_filtered(self):
        row = {"org_id": "O1", "owners_name": "某投资公司", "owners_type": "企业"}
        assert mappers.organization_role_person("dwd_org_shareholder_info", row, "B") == []
        row2 = {"org_id": "O1", "owners_name": "张三", "owners_type": "自然人"}
        assert len(mappers.organization_role_person("dwd_org_shareholder_info", row2, "B")) == 1

    def test_shareholder_unknown_type_raises(self):
        row = {"org_id": "O1", "owners_name": "张三", "owners_type": "其它"}
        with pytest.raises(ValueError):
            mappers.organization_role_person("dwd_org_shareholder_info", row, "B")

    def test_executive_person_props(self):
        row = {
            "org_id": "O1",
            "executives_name": "王五",
            "bo_country_code": "US",
            "country_code": "CN",
        }
        rec = mappers.organization_role_person("dwd_org_executive_info", row, "B")[0]
        assert rec.properties["person_kind"] == "executive"
        assert rec.properties["name_en"] is None  # 国内表
        assert rec.properties["country_code"] == "US"
        # country 取到 bo_country_code=US，也参与 VID
        identity = "|".join(("executive", "o1", "王五", "us"))
        assert rec.vid == f"person_{_md5(identity)}"

    def test_foreign_executive_name_en(self):
        row = {"org_id": "F1", "executives_name": "John"}
        rec = mappers.organization_role_person("dwd_forg_executive_info", row, "B")[0]
        assert rec.properties["name_en"] == "John"

    def test_legal_representative_person(self):
        row = {"org_id": "O1", "lerep": "赵六"}
        rec = mappers.legal_representative_person("dwd_org_base_info", row, "B")[0]
        identity = "|".join(("legal_representative", "o1", "赵六"))
        assert rec.vid == f"person_{_md5(identity)}"
        assert rec.properties["person_kind"] == "legal_representative"
        assert rec.properties["source_record_id"].endswith("|legal_representative|赵六")

    def test_legal_representative_requires_org_and_name(self):
        assert (
            mappers.legal_representative_person("dwd_org_base_info", {"lerep": "赵六"}, "B") == []
        )
        assert mappers.legal_representative_person("dwd_org_base_info", {"org_id": "O1"}, "B") == []


class TestPaperJournalReport:
    def test_paper_publication_name_from_publication_id(self):
        row = {
            "id": "P1",
            "doi": "10.1/x",
            "title_zh": "标题",
            "publication_id": "J123",
            "publication_name": "期刊名",
        }
        rec = mappers.paper_record("dwd_zh_paper", row, "B")[0]
        assert rec.properties["publication_name"] == "J123"
        assert rec.properties["source_record_id"] == "paper_P1"

    def test_paper_newlines_replaced(self):
        row = {"id": "P2", "title_zh": "第一行\n第二行"}
        rec = mappers.paper_record("dwd_zh_paper", row, "B")[0]
        assert rec.properties["title_zh"] == "第一行 第二行"

    def test_journal_zero_id_skipped(self):
        assert (
            mappers.journal_record("dwd_zh_journal", {"journal_id": 0, "name_zh": "x"}, "B") == []
        )

    def test_report_abstract_only_cn(self):
        row = {
            "report_id": "R1",
            "title_cn": None,
            "title_en": "EN Title",
            "abstract_cn": "",
            "abstract_en": "EN",
        }
        rec = mappers.report_record("dwd_zh_report", row, "B")[0]
        assert rec.properties["title"] == "EN Title"
        assert rec.properties["abstract"] == ""


class TestPatentRecord:
    def test_patent_json_field_semantics(self):
        row = {
            "patent_id": "PN1",
            "titles": '[{"text": "标题A"}, {"content": "标题B"}]',
            "language": '["zh", "en"]',
            "further_ipcr": '["H01L", "G06F"]',
            "keywords": "not-json",
        }
        rec = mappers.patent_record("dwd_patent", row, "B")[0]
        assert rec.properties["title_original"] == "标题A"
        assert rec.properties["language"] == "zh,en"
        assert rec.properties["further_ipcr"] == '["H01L","G06F"]'
        # 旧 json_snapshot 对非 JSON 字符串会重新序列化加引号
        assert rec.properties["keywords"] == '"not-json"'

    def test_patent_datetime_and_provenance_fields(self):
        row = {"patent_id": "PN2", "create_time": "2026-01-01 10:00:00", "update_time": None}
        rec = mappers.patent_record("dwd_patent", row, "B")[0]
        assert rec.properties["create_time"] == "2026-01-01T10:00:00"
        assert rec.properties["update_time"] is None
        assert rec.properties["organization_base"] == "dwd_patent"
        assert rec.properties["organization_id"] == "PN2"

    def test_patent_missing_id_raises(self):
        with pytest.raises(ValueError):
            mappers.patent_record("dwd_patent", {"patent_id": ""}, "B")

    def test_patent_family(self):
        row = {"simple_family_number": "FAM1"}
        rec = mappers.patent_family_record("dwd_patent", row, "B")[0]
        assert rec.vid == "patent_family_FAM1"
        assert rec.properties["organization_base"] == "dwd_patent_family"
        assert rec.properties["source_table"] == "dwd_patent_family"


class TestProjectRecord:
    def test_project_confidence_scoring(self):
        row = {"id": "PRJ1", "title": "T"}
        rec = mappers.project_record("dwd_zh_project", row, "B")[0]
        # 仅 title 填充：1/6 ≈ 0.1667 → 下限 0.3
        assert rec.properties["confidence"] == 0.3
        full = {
            "id": "PRJ2",
            "title": "T",
            "abstract": "A",
            "funded_amount": 1,
            "discipline": "D",
            "approval_year": "2026",
            "fund_category": "F",
        }
        rec2 = mappers.project_record("dwd_zh_project", full, "B")[0]
        assert rec2.properties["confidence"] == 1.0

    def test_project_funded_amount_invalid_to_zero(self):
        row = {"id": "PRJ3", "title": "T", "funded_amount": "abc"}
        rec = mappers.project_record("dwd_zh_project", row, "B")[0]
        assert rec.properties["funded_amount"] == 0.0

    def test_project_en_final_report_abstract_empty(self):
        row = {"id": "PRJ4", "title": "T", "final_report_abstract": "有值也不写"}
        rec = mappers.project_record("dwd_en_project", row, "B")[0]
        assert rec.properties["final_report_abstract"] == ""


class TestMergeProtection:
    def test_preserves_existing_non_null(self):
        existing = {"name_cn": "已有名", "confidence": 0.9, "extra_json": "{}"}
        incoming = {"name_cn": None, "confidence": 0.5, "extra_json": '{"a":1}'}
        updates = common.merge_existing_properties(existing, incoming)
        assert "name_cn" not in updates
        assert "confidence" not in updates  # 只升不降
        assert "source_records" in json.loads(updates["extra_json"])

    def test_overwrites_when_existing_blank(self):
        existing = {"name_cn": "  ", "confidence": 0.4}
        incoming = {"name_cn": "新名", "confidence": 0.9}
        updates = common.merge_existing_properties(existing, incoming)
        assert updates["name_cn"] == "新名"
        assert updates["confidence"] == 0.9

    def test_extra_json_source_records_envelope(self):
        existing = {"extra_json": json.dumps({"source_records": {"t1:r1": {"x": 1}}})}
        incoming = {"source_table": "t2", "source_record_id": "r2", "extra_json": '{"y":2}'}
        updates = common.merge_existing_properties(existing, incoming)
        payload = json.loads(updates["extra_json"])
        assert payload["source_records"]["t1:r1"] == {"x": 1}
        assert payload["source_records"]["t2:r2"] == {"y": 2}


class TestDatasourceRecords:
    def test_replicates_legacy_catalog(self):
        records = datasource_records()
        assert len(records) == 39
        by_table = {r.properties["source_table"]: r for r in records}
        base = by_table["dwd_org_base_info"]
        assert base.vid == "ds_dwd_org_base_info"
        assert base.properties["table_cn_name"] == "机构基本信息"
        assert base.properties["tier"] == "DWD"
        assert base.properties["library"] == "国内机构要素库"
        assert by_table["dwd_forg_base_info"].properties["library"] == "国外机构要素库"
        # 旧 DataSource 只有 4 个目录属性，无溯源字段
        assert set(base.properties) == {"source_table", "table_cn_name", "tier", "library"}


class TestPatentHelpers:
    def test_original_text_list_of_texts(self):
        assert common.original_text('[{"text": ["a", "b"]}]') == "a\nb"

    def test_json_snapshot_none(self):
        assert common.json_snapshot(None) == ""
        assert common.json_snapshot("plain") == '"plain"'
