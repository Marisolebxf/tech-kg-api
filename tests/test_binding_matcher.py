"""Tests for the rule-based binding matcher."""
import pytest
from app.services.binding_matcher import BindingMatcher, jaccard_similarity, edit_distance_similarity


class TestJaccardSimilarity:
    def test_identical_sets(self):
        assert jaccard_similarity("清华大学", "清华大学") == 1.0

    def test_partial_overlap(self):
        sim = jaccard_similarity("清华大学", "清华")
        assert 0.0 < sim < 1.0

    def test_no_overlap(self):
        # "清华大学" and "北京大学" share characters "大学", so not zero overlap
        assert jaccard_similarity("清华大学", "北京大学") > 0.0
        # Truly disjoint character sets
        assert jaccard_similarity("ABC", "XYZ") == 0.0

    def test_empty_strings(self):
        assert jaccard_similarity("", "") == 0.0


class TestEditDistanceSimilarity:
    def test_identical(self):
        assert edit_distance_similarity("浙江大学", "浙江大学") == 1.0

    def test_similar(self):
        sim = edit_distance_similarity("浙江大学", "浙大")
        assert sim >= 0.5

    def test_completely_different(self):
        sim = edit_distance_similarity("清华大学", "复旦大学")
        assert sim <= 0.5


class TestBindingMatcherTalentPaper:
    def setup_method(self):
        self.matcher = BindingMatcher()

    def test_name_exact_match(self):
        talent = {"name_zh": "张伟", "name_en": "Wei Zhang", "scholar_org_name_zh": "清华大学", "fields": "知识图谱"}
        paper = {"authors": "张伟", "institution": "清华大学", "keywords": "知识图谱;实体对齐"}
        pairs = self.matcher.match_talent_paper([talent], [paper])
        assert len(pairs) == 1
        assert pairs[0]["rule_score"] >= 0.5

    def test_name_no_match(self):
        talent = {"name_zh": "张伟", "name_en": "Wei Zhang", "scholar_org_name_zh": "清华大学", "fields": "知识图谱"}
        paper = {"authors": "赵磊", "institution": "中科院", "keywords": "推荐系统"}
        pairs = self.matcher.match_talent_paper([talent], [paper])
        assert len(pairs) == 0

    def test_name_match_org_abbreviation(self):
        talent = {"name_zh": "王芳", "name_en": "Fang Wang", "scholar_org_name_zh": "浙江大学", "fields": "计算机视觉"}
        paper = {"authors": "王芳", "institution": "浙大", "keywords": "计算机视觉;深度学习"}
        pairs = self.matcher.match_talent_paper([talent], [paper])
        assert len(pairs) == 1

    def test_below_threshold_not_returned(self):
        talent = {"name_zh": "张伟", "scholar_org_name_zh": "清华大学", "fields": "知识图谱"}
        paper = {"authors": "不同的人", "institution": "不同的大学", "keywords": "完全不同"}
        pairs = self.matcher.match_talent_paper([talent], [paper])
        assert len(pairs) == 0


class TestBindingMatcherTalentPatent:
    def setup_method(self):
        self.matcher = BindingMatcher()

    def test_inventor_match(self):
        talent = {"name_zh": "张伟", "scholar_org_name_zh": "清华大学", "fields": "知识图谱"}
        patent = {"first_inventor_name": "张伟", "first_applicant_name": "清华大学", "title_zh": "知识图谱构建方法"}
        pairs = self.matcher.match_talent_patent([talent], [patent])
        assert len(pairs) == 1

    def test_inventor_no_match(self):
        talent = {"name_zh": "张伟", "scholar_org_name_zh": "清华大学", "fields": "知识图谱"}
        patent = {"first_inventor_name": "赵磊", "first_applicant_name": "中科院", "title_zh": "智能推荐"}
        pairs = self.matcher.match_talent_patent([talent], [patent])
        assert len(pairs) == 0


class TestBindingMatcherOrgOrg:
    def setup_method(self):
        self.matcher = BindingMatcher()

    def test_same_org_name(self):
        org_a = {"name_cn": "清华大学", "province": "北京市", "city": "北京", "org_type": "高等院校"}
        org_b = {"name_cn": "清华大学", "province": "北京市", "city": "北京", "org_type": "高等院校"}
        pairs = self.matcher.match_org_org([org_a], [org_b])
        assert len(pairs) == 1
        assert pairs[0]["rule_score"] >= 0.6

    def test_sub_org_match(self):
        org_a = {"name_cn": "清华大学", "province": "北京市", "city": "北京", "org_type": "高等院校"}
        org_b = {"name_cn": "清华大学计算机系", "province": "北京市", "city": "北京", "org_type": "院系"}
        pairs = self.matcher.match_org_org([org_a], [org_b])
        assert len(pairs) == 1

    def test_no_match(self):
        org_a = {"name_cn": "清华大学", "province": "北京市", "city": "北京", "org_type": "高等院校"}
        org_b = {"name_cn": "浙江大学", "province": "浙江省", "city": "杭州", "org_type": "高等院校"}
        pairs = self.matcher.match_org_org([org_a], [org_b])
        assert len(pairs) == 0
