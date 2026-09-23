"""科技两点合作成果请求 schema 中文类型容错单测。"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from biz.schemas.expert_cooperation_achievement import CooperationAchievementQueryRequest


def _req(**overrides):
    payload = {"sourceExpertId": "person_9F9A0001", "targetExpertId": "person_9F9A0004"}
    payload.update(overrides)
    return CooperationAchievementQueryRequest(**payload)


class TestAchievementTypesChineseTolerance:
    def test_quanbu_maps_to_none(self):
        """「全部」= 不筛选，与不传 achievementTypes 等价。"""
        assert _req(achievementTypes=["全部"]).achievementTypes is None

    def test_chinese_labels_map_to_codes(self):
        assert _req(achievementTypes=["论文", "专利"]).achievementTypes == ["paper", "patent"]

    def test_single_chinese_label(self):
        assert _req(achievementTypes=["项目"]).achievementTypes == ["project"]

    def test_quanbu_dominates_mixed(self):
        """「全部」与其他项混填时以「全部」为准。"""
        assert _req(achievementTypes=["全部", "论文"]).achievementTypes is None

    def test_english_codes_passthrough(self):
        assert _req(achievementTypes=["paper"]).achievementTypes == ["paper"]

    def test_empty_list_unchanged(self):
        """空列表原样保留（字段语义：空 = 全部类型）。"""
        assert _req(achievementTypes=[]).achievementTypes == []

    def test_unknown_label_still_rejected(self):
        """表外中文值仍 422，不静默吞掉拼写错误。"""
        with pytest.raises(ValidationError):
            _req(achievementTypes=["专著"])

    def test_whitespace_tolerated(self):
        assert _req(achievementTypes=[" 论文 "]).achievementTypes == ["paper"]

    def test_non_list_passthrough_rejected(self):
        with pytest.raises(ValidationError):
            _req(achievementTypes="论文")
