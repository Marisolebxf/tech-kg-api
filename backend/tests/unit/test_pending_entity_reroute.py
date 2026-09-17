"""挂实体改道写前消歧单测：确定性 vid / pendingReview 实体项形状 /
_enqueue_pending_review 实体项建 T_LINK（强制人裁）/ 关系项废弃丢弃 / 重跑幂等。"""

from __future__ import annotations

import json
import logging

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db_model.base import Base
from db_model.manual_review import ReviewCase
from script.extract_transform_common import pending_entity_items
from script.relation_extractors_one_relation.patent_matching import (
    PendingEntity,
    pending_entity_vid,
)
from service.manual_review_production import ManualReviewService
from service.temporal_workflows import _enqueue_pending_review

# ---------------------------------------------------------------------------
# 确定性 vid：同名字段归并到同一挂起点
# ---------------------------------------------------------------------------


class TestPendingEntityVid:
    def test_same_name_same_vid(self):
        assert pending_entity_vid("person", "张三") == pending_entity_vid("person", "张三")

    def test_normalization_collapses_width_and_case(self):
        # NFKC 全角折叠 + casefold：写法差异不拆 case
        assert pending_entity_vid("org", "ＡＢＣ大学") == pending_entity_vid("org", "abc大学")
        assert pending_entity_vid("person", "John Smith") == pending_entity_vid(
            "person", "john  smith"
        )

    def test_different_names_differ(self):
        assert pending_entity_vid("person", "张三") != pending_entity_vid("person", "李四")

    def test_prefix_separates_person_and_org(self):
        assert pending_entity_vid("person", "甲") != pending_entity_vid("org", "甲")


# ---------------------------------------------------------------------------
# pendingReview 实体项形状（candidate 只放按名字段稳定的内容）
# ---------------------------------------------------------------------------


class TestPendingEntityItems:
    def test_dataclass_item_shape(self):
        vid = pending_entity_vid("person", "张三")
        items = pending_entity_items(
            [
                PendingEntity(
                    name="张三",
                    vid=vid,
                    reason="只有姓名证据",
                    confidence=0.6,
                    evidence=["姓名精确匹配"],
                    node_label="Person",
                    source_record_id="123:inventors:0",
                )
            ],
            source_table="dwd_patent",
            node_label="Person",
        )
        assert items == [
            {
                "kind": "entity",
                "nodeLabel": "Person",
                "objectId": vid,
                "objectName": "张三",
                "candidate": {"name": "张三", "props": {"name": "张三"}},
                "reason": "只有姓名证据",
                "confidence": 0.6,
                "evidence": ["姓名精确匹配"],
                "sourceTable": "dwd_patent",
                "sourceRecordId": "123:inventors:0",
            }
        ]

    def test_candidate_excludes_row_level_ids_for_dedupe_stability(self):
        """dedupe_key 对 candidate_snapshot 求哈希：行级 id 只能放 item 层。"""
        vid = pending_entity_vid("person", "张三")
        items = pending_entity_items(
            [
                PendingEntity(
                    name="张三",
                    vid=vid,
                    reason="r",
                    confidence=None,
                    evidence=[],
                    node_label="Person",
                    source_record_id="1:inventors:0",
                ),
                PendingEntity(
                    name="张三",
                    vid=vid,
                    reason="r",
                    confidence=None,
                    evidence=[],
                    node_label="Person",
                    source_record_id="2:inventors:0",
                ),
            ],
            source_table="dwd_patent",
            node_label="Person",
        )
        # 同一实体（同名同 vid）：candidate 完全一致 → 重跑 dedupe_key 不变；
        # 差异只在 sourceRecordId（item 层，不进快照哈希）
        assert items[0]["candidate"] == items[1]["candidate"]
        assert items[0]["sourceRecordId"] != items[1]["sourceRecordId"]

    def test_dict_items_and_invalid_skipped(self):
        items = pending_entity_items(
            [
                {"name": "甲公司", "vid": "pending-org-x", "node_label": "Organization"},
                {"name": "", "vid": "pending-person-y"},  # 缺名 → 跳过
                {"name": "乙", "vid": ""},
            ],  # 缺 vid → 跳过
            source_table="dwd_patent",
            node_label="Organization",
        )
        assert len(items) == 1
        assert items[0]["nodeLabel"] == "Organization"
        assert items[0]["candidate"]["props"] == {"name": "甲公司"}


# ---------------------------------------------------------------------------
# _enqueue_pending_review：实体项 → T_LINK（强制灰区人裁）
# ---------------------------------------------------------------------------


class _RecallGraph:
    """假图客户端：DESCRIBE 报 name 列；MATCH 返回预置候选（带完整属性供评分）。"""

    def __init__(self, rows):
        self.rows = rows
        self.writes: list[str] = []

    def connect(self):
        pass

    def close(self):
        pass

    def execute_write(self, stmt):
        self.writes.append(stmt)

    def execute_query(self, q):
        assert "DESCRIBE TAG" in q

        class _Result:
            records = [{"Field": "name", "Type": "string", "Null": "YES"}]

        return _Result()

    def execute_read(self, q):
        class _Result:
            records = self.rows

        return _Result()


def _person_item(name="张三", *, props=None, source_record_id="123:inventors:0"):
    return {
        "kind": "entity",
        "nodeLabel": "Person",
        "objectId": pending_entity_vid("person", name),
        "objectName": name,
        "candidate": {"name": name, "props": props if props is not None else {"name": name}},
        "reason": "只有姓名证据",
        "confidence": 0.6,
        "evidence": ["姓名精确匹配"],
        "sourceTable": "dwd_patent",
        "sourceRecordId": source_record_id,
    }


def _request():
    return {"stepId": "source:1#extract", "selectors": {"graph_space": "dev2"}}


@pytest.fixture
def review_service(monkeypatch):
    engine = create_engine(
        "sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    service = ManualReviewService(sessionmaker(engine, expire_on_commit=False))
    monkeypatch.setattr("service.manual_review_production.manual_review_service", service)
    # execution 查询不桩：_enqueue_pending_review 内部 import 失败自带 try/except
    # 兜底（host 无控制库 → task_id 走 PI-kgstep- 前缀，确定性不影响断言）
    return service


def _open_link_cases(service):
    """T_LINK case 的 candidate dict 落 candidate_snapshot 列（input_snapshot 是外壳）。"""
    with service.sf() as s:
        rows = s.scalars(select(ReviewCase).where(ReviewCase.template_id == "T_LINK")).all()
        return [json.loads(r.candidate_snapshot) for r in rows], list(rows)


class TestEnqueueEntityPending:
    def test_entity_item_creates_forced_gray_t_link(self, review_service, monkeypatch):
        graph = _RecallGraph(
            [{"vid": "person_9", "nm0": "张三", "props": {"name": "张三", "org": "计算所"}}]
        )
        monkeypatch.setattr("service.temporal_workflows._pending_graph_client", lambda space: graph)
        _enqueue_pending_review(
            _request(),
            [_person_item(props={"name": "张三", "org": "计算所"})],
            1,
        )
        snapshots, rows = _open_link_cases(review_service)
        assert len(rows) == 1
        case = rows[0]
        assert case.exception_code == "KG_ENTITY_DISAMBIGUATION_GRAY"
        assert case.object_id == pending_entity_vid("person", "张三")
        # 评分 ≥ MERGE_THRESHOLD（同名+属性全一致 = 1.0）仍建 case 强制人裁，
        # 不走 auto-merge（挂起实体的边端点悬在未决 vid，必须人裁改写）
        assert graph.writes == []
        snap = snapshots[0]
        assert snap["existingCandidates"] == [{"vid": "person_9", "name": "张三", "score": 1.0}]
        assert snap["_incoming"]["vid"] == pending_entity_vid("person", "张三")
        assert snap["_incoming"]["sourceTable"] == "dwd_patent"
        assert snap["_pendingRelations"] == []
        assert snap["_graphSpace"] == "dev2"
        assert snap["_resolution"]["policyVersion"] == "script-pending-gray-v1"
        assert "脚本挂起改道消歧" in case.diagnosis

    def test_no_recall_candidates_still_links_with_empty_candidates(
        self, review_service, monkeypatch
    ):
        graph = _RecallGraph([])  # 图库无同名（“人才表未找到同名人员”类）
        monkeypatch.setattr("service.temporal_workflows._pending_graph_client", lambda space: graph)
        _enqueue_pending_review(_request(), [_person_item()], 1)
        snapshots, rows = _open_link_cases(review_service)
        assert len(rows) == 1
        assert snapshots[0]["existingCandidates"] == []
        assert graph.writes == []

    def test_rerun_is_idempotent_by_dedupe_key(self, review_service, monkeypatch):
        graph = _RecallGraph([{"vid": "person_9", "nm0": "张三", "props": {"name": "张三"}}])
        monkeypatch.setattr("service.temporal_workflows._pending_graph_client", lambda space: graph)
        item = _person_item(source_record_id="123:inventors:0")
        _enqueue_pending_review(_request(), [item], 1)
        _enqueue_pending_review(_request(), [_person_item(source_record_id="456:inventors:2")], 1)
        _, rows = _open_link_cases(review_service)
        assert len(rows) == 1  # 同名同人 → 同 dedupe_key → 幂等跳过

    def test_relation_items_dropped_with_warning(self, review_service, monkeypatch, caplog):
        graph = _RecallGraph([])
        monkeypatch.setattr("service.temporal_workflows._pending_graph_client", lambda space: graph)
        legacy_relation_item = {
            "kind": "relation",
            "objectId": "123:applicants:0",
            "edgeType": "APPLIED_BY",
            "reason": "机构名称命中多个已有机构",
        }
        with caplog.at_level(logging.WARNING, logger="workflow.kg.custom.steps"):
            _enqueue_pending_review(_request(), [legacy_relation_item, _person_item()], 1)
        assert any("已废弃" in r.getMessage() for r in caplog.records)
        _, rows = _open_link_cases(review_service)
        assert len(rows) == 1  # 只剩实体项建的 T_LINK

    def test_enqueue_failure_does_not_raise(self, review_service, monkeypatch, caplog):
        def boom(space):
            raise RuntimeError("graph down")

        monkeypatch.setattr("service.temporal_workflows._pending_graph_client", boom)
        with caplog.at_level(logging.WARNING, logger="workflow.kg.custom.steps"):
            _enqueue_pending_review(_request(), [_person_item()], 1)  # 不抛
        assert any("建 T_LINK 失败" in r.getMessage() for r in caplog.records)
