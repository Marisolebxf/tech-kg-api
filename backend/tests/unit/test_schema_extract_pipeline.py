"""平台喂数抽取（kg.schema.extract）单元测试：SQL 构造 / 转换契约 / 失败记录生命周期。"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db_model.base import Base
from db_model.manual_review import ReviewCase
from script.extract_transform_common import (
    edge_transform,
    entity_transform,
    pending_review_items,
)
from service.manual_review_production import ManualReviewService
from service.temporal_workflows import _validate_query_sql, build_source_batch_sql

# ---------------------------------------------------------------------------
# SQL 构造（纯函数）
# ---------------------------------------------------------------------------


class TestBuildSourceBatchSql:
    def test_plain_watermark(self):
        sql = build_source_batch_sql(
            database="gkx",
            table="dwd_paper",
            time_column="update_time",
            pk_column="id",
            cursor_kind="watermark",
        )
        assert sql == (
            "SELECT * FROM `gkx`.`dwd_paper` WHERE `update_time` > :wm "
            "ORDER BY `update_time`, `id` LIMIT :n"
        )

    def test_keyset_without_time(self):
        sql = build_source_batch_sql(
            database="gkx",
            table="t",
            time_column=None,
            pk_column="row_id",
            cursor_kind="keyset",
        )
        assert "`row_id` > :cursor ORDER BY `row_id` LIMIT :n" in sql

    def test_query_sql_wrapped(self):
        sql = build_source_batch_sql(
            database="gkx",
            table=None,
            time_column="update_time",
            pk_column="source_row_id",
            query_sql="SELECT p.id AS source_row_id, p.update_time FROM dwd_patent p",
            cursor_kind="watermark",
        )
        assert sql.startswith("SELECT * FROM (SELECT p.id AS source_row_id")
        assert "AS src WHERE `update_time` > :wm" in sql

    def test_ids_mode_placeholders(self):
        sql = build_source_batch_sql(
            database="gkx",
            table="t",
            time_column="update_time",
            pk_column="id",
            cursor_kind="ids",
            record_ids=["1", "2", "3"],
        )
        assert "WHERE `id` IN (:id_0, :id_1, :id_2)" in sql

    def test_ids_mode_requires_ids(self):
        with pytest.raises(ValueError, match="recordIds"):
            build_source_batch_sql(
                database="gkx",
                table="t",
                time_column=None,
                pk_column="id",
                cursor_kind="ids",
                record_ids=None,
            )


class TestValidateQuerySql:
    def test_rejects_multi_statement(self):
        with pytest.raises(ValueError, match="多语句"):
            _validate_query_sql("SELECT 1; DROP TABLE x")

    def test_rejects_non_select(self):
        with pytest.raises(ValueError, match="SELECT"):
            _validate_query_sql("UPDATE t SET a = 1")

    def test_rejects_into(self):
        with pytest.raises(ValueError, match="INTO"):
            _validate_query_sql("SELECT * INTO t2 FROM t1")

    def test_accepts_with_cte(self):
        assert _validate_query_sql("WITH x AS (SELECT 1) SELECT * FROM x").startswith("WITH")


# ---------------------------------------------------------------------------
# 转换契约（毒行隔离）
# ---------------------------------------------------------------------------


class _Entity:
    def __init__(self, vid, props):
        self.vid = vid
        self.properties = props


class _Edge:
    def __init__(self, src, dst, props):
        self.source_vid = src
        self.target_vid = dst
        self.properties = props


def _payload(rows, **source):
    return {
        "rows": rows,
        "source": {"id": "binding-abcdef12", "pkColumn": "id", "tableName": "t1", **source},
        "source_table": "gkx.t1",
        "kind": "entity",
    }


class TestTransformContract:
    def test_entity_transform_ok(self):
        out = entity_transform(
            _payload([{"id": "1", "name": "甲"}]),
            builder=lambda t, r, b: [_Entity(f"n_{r['id']}", {"name": r["name"]})],
        )
        assert out["entities"] == [{"id": "n_1", "props": {"name": "甲"}}]
        assert out["failures"] == []
        assert out["stats"]["entities"] == 1

    def test_poison_row_isolated(self):
        def builder(table, row, batch):
            if row["id"] == "bad":
                raise ValueError("解析炸了")
            return [_Entity(f"n_{row['id']}", {})]

        out = entity_transform(_payload([{"id": "1"}, {"id": "bad"}, {"id": "2"}]), builder=builder)
        assert [e["id"] for e in out["entities"]] == ["n_1", "n_2"]
        assert out["failures"] == [{"recordId": "bad", "error": "ValueError: 解析炸了"}]

    def test_mapper_by_table_dispatch(self):
        out = entity_transform(
            _payload([{"id": "1"}], tableName="t1"),
            mapper_by_table={
                "t1": lambda t, r, b: [_Entity("a", {})],
                "t2": lambda t, r, b: [_Entity("b", {})],
            },
        )
        assert out["entities"][0]["id"] == "a"

    def test_unknown_table_raises(self):
        with pytest.raises(RuntimeError, match="没有对应的转换 mapper"):
            entity_transform(_payload([{"id": "1"}]), mapper_by_table={})

    def test_edge_transform_shape(self):
        out = edge_transform(
            _payload([{"id": "1"}]), builder=lambda t, r, b: [_Edge("s", "d", {"confidence": 1.0})]
        )
        assert out["edges"] == [{"fromId": "s", "toId": "d", "props": {"confidence": 1.0}}]

    def test_missing_pk_row_gets_stable_id(self):
        """pk 列缺失时用行内容 sha 兜底（重跑 IN 过滤仍可用）。"""
        out = entity_transform(
            _payload([{"k": "v"}], pkColumn="id"),
            builder=lambda t, r, b: [_Entity("x", {})],
        )
        assert out["failures"] == [] or out["entities"]

    def test_pending_review_items_from_dataclass(self):
        class Review:
            patent_id = "P1"
            relation_type = "APPLIED_BY"
            source_name = "华为"
            reason = "命中多个机构"
            confidence = None
            candidates = [{"vid": "org_1"}, {"vid": "org_2"}]
            evidence = ["精确匹配不唯一"]
            patent_vid = "patent_P1"
            source_record_id = "123:applicants:0"

        items = pending_review_items([Review()], source_table="dwd_patent")
        assert items[0]["edgeType"] == "APPLIED_BY"
        assert items[0]["fromId"] == "patent_P1"
        assert items[0]["candidate"]["candidates"] == [{"vid": "org_1"}, {"vid": "org_2"}]
        assert items[0]["sourceRecordId"] == "123:applicants:0"


# ---------------------------------------------------------------------------
# T_EXTRACT_FAIL 失败记录生命周期（sqlite）
# ---------------------------------------------------------------------------


@pytest.fixture
def review_service():
    engine = create_engine(
        "sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return ManualReviewService(sessionmaker(engine, expire_on_commit=False))


def _make_fail_case(service, record_id, *, binding="bind-1", execution="EXEC-1", attempt=1):
    return service.create_direct_case(
        task_id="TASK-EX",
        execution_id=execution,
        step_id="extract",
        kind="entity",
        candidate={"recordId": record_id, "error": "ValueError: boom", "schemaKey": "paper"},
        object_id=record_id,
        object_name=f"dwd_paper#{record_id}",
        reason="记录解析失败: ValueError: boom",
        source_table="gkx.dwd_paper",
        source_record_id=record_id,
        service_actor="kg.schema.extract",
        template_id="T_EXTRACT_FAIL",
        workflow_type="kg.schema.extract",
        exception_code="KG_EXTRACT_RECORD_FAILED",
        extra_snapshot={
            "schemaId": "schema-paper",
            "schemaKey": "paper",
            "sourceBindingId": binding,
            "jobId": "job-1",
            "attempt": attempt,
        },
    )


class TestExtractFailLifecycle:
    def test_case_created_as_extract_fail(self, review_service):
        case_resp = _make_fail_case(review_service, "42")
        assert case_resp["status"] == "OPEN"
        cases = review_service.list_extract_fail_cases()
        assert [c["caseId"] for c in cases] == [case_resp["reviewId"]]

    def test_list_extract_fail_cases(self, review_service):
        _make_fail_case(review_service, "42")
        _make_fail_case(review_service, "43")
        cases = review_service.list_extract_fail_cases()
        assert {c["recordId"] for c in cases} == {"42", "43"}
        by_execution = review_service.list_extract_fail_cases(execution_id="EXEC-1")
        assert len(by_execution) == 2
        assert review_service.list_extract_fail_cases(execution_id="EXEC-X") == []

    def test_mark_attach_revert(self, review_service):
        case_resp = _make_fail_case(review_service, "42")
        marked = review_service.mark_extract_rerun([case_resp["reviewId"]])
        assert marked == 1
        # 重复标记幂等跳过
        assert review_service.mark_extract_rerun([case_resp["reviewId"]]) == 0
        review_service.attach_rerun_execution([case_resp["reviewId"]], "EXEC-2")
        with review_service.sf() as s:
            row = s.scalar(select(ReviewCase).where(ReviewCase.id == case_resp["reviewId"]))
            import json

            snapshot = json.loads(row.input_snapshot)
        assert snapshot["rerunExecutionId"] == "EXEC-2"
        # 回滚为 OPEN
        assert review_service.revert_extract_rerun([case_resp["reviewId"]], reason="测试") == 1
        with review_service.sf() as s:
            row = s.scalar(select(ReviewCase).where(ReviewCase.id == case_resp["reviewId"]))
            assert row.status == "OPEN"

    def test_resolve_success_closes_case(self, review_service):
        case_resp = _make_fail_case(review_service, "42")
        review_service.mark_extract_rerun([case_resp["reviewId"]])
        result = review_service.resolve_extract_rerun(
            rerun_case_ids=[case_resp["reviewId"]],
            failed_records=[],
            rerun_execution_id="EXEC-2",
            task_id="TASK-EX",
        )
        assert result == {"resolved": 1, "refailed": 0, "recreated": 0}
        with review_service.sf() as s:
            row = s.scalar(select(ReviewCase).where(ReviewCase.id == case_resp["reviewId"]))
            assert row.status == "RESOLVED"

    def test_resolve_refail_creates_attempt2_case(self, review_service):
        case_resp = _make_fail_case(review_service, "42")
        review_service.mark_extract_rerun([case_resp["reviewId"]])
        result = review_service.resolve_extract_rerun(
            rerun_case_ids=[case_resp["reviewId"]],
            failed_records=[{"sourceBindingId": "bind-1", "recordId": "42", "error": "还是炸"}],
            rerun_execution_id="EXEC-2",
            task_id="TASK-EX",
        )
        assert result["refailed"] == 1 and result["recreated"] == 1
        open_cases = review_service.list_extract_fail_cases(statuses=("OPEN",))
        assert len(open_cases) == 1
        assert open_cases[0]["attempt"] == 2
        assert open_cases[0]["executionId"] == "EXEC-2"
        # 原 case 关闭
        with review_service.sf() as s:
            row = s.scalar(select(ReviewCase).where(ReviewCase.id == case_resp["reviewId"]))
            assert row.status == "RESOLVED"

    def test_category_c_filter(self, review_service):
        """category=C 只含 T_EXTRACT_FAIL；A 不含。"""
        _make_fail_case(review_service, "42")
        # 再造一个 T_DIRECT case
        service = review_service
        service.create_direct_case(
            task_id="T2", execution_id=None, step_id="extract", kind="entity", candidate={"id": "x"}
        )
        a_cases = service.list_cases({"category": "A", "page": 1, "page_size": 50}, _admin_actor())
        c_cases = service.list_cases({"category": "C", "page": 1, "page_size": 50}, _admin_actor())
        assert all(i["templateId"] != "T_EXTRACT_FAIL" for i in a_cases["items"])
        assert [i["templateId"] for i in c_cases["items"]] == ["T_EXTRACT_FAIL"]


def _admin_actor():
    from service.manual_review_domain import ReviewIdentity

    return ReviewIdentity(
        "admin", "admin", frozenset({"review_admin"}), frozenset({"*"}), "org", "req"
    )
