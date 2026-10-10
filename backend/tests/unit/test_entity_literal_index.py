import json
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event, select, update
from sqlalchemy.orm import Session

from db_model.entity_literal_index import documents, states
from service.entity_literal_index import EntityLiteralIndex, LiteralIndexError


@pytest.fixture
def index():
    engine = create_engine("sqlite://")
    with Session(engine) as session:
        yield EntityLiteralIndex(session)
    engine.dispose()


def item(vid, props, label="Paper"):
    return {"vid": vid, "props": props, "entity_type": label}


def test_exact_title_and_business_id_do_not_read_gram_index_or_graph(index):
    index.build(
        "dev2",
        [
            item("p1", {"name": "内部名称", "title_zh": "生命科学研究", "id": "P/001"}),
            item("p2", {"title_zh": "生命科学研究进展"}),
        ],
        ["Paper"],
    )
    statements = []
    event.listen(
        index.session.get_bind(),
        "before_cursor_execute",
        lambda conn, cur, stmt, params, ctx, many: statements.append(stmt),
    )
    for keyword in ("生命科学研究", "P/001", "p1"):
        result = index.page(space="dev2", keyword=keyword)
        assert result["matchMode"] == "exact"
        assert result["total"] == 1
        assert result["items"][0]["vid"] == "p1"
        assert result["items"][0]["name"] == "生命科学研究"
    assert not any("kg_entity_literal_gram" in stmt for stmt in statements)
    assert any("exact_hash" in stmt for stmt in statements)


@pytest.mark.parametrize(
    "keyword", ["科", "生命", "生命科学", "10.12/ABC", "%_", "'", "末尾匹配", "2026"]
)
def test_contains_is_literal_handles_short_chinese_punctuation_and_untruncated_fields(
    index, keyword
):
    index.build(
        "dev2",
        [
            item(
                "p1",
                {
                    "title_zh": "目标论文",
                    "abstract": "a" * 1000 + "末尾匹配",
                    "topic": "生命科学",
                    "doi": "10.12/abc",
                    "code": "%_'",
                    "year": 2026,
                },
            ),
            item("p2", {"title_zh": "相似但不匹配的论文", "topic": "地缘经济格局"}),
        ],
        ["Paper"],
    )
    result = index.page(space="dev2", keyword=keyword)
    assert [row["vid"] for row in result["items"]] == ["p1"]
    assert result["total"] == 1
    assert result["matchMode"] == "contains"


def test_candidates_are_verified_in_one_field_and_documents_deduplicated(index):
    index.build(
        "dev2",
        [
            item("good", {"a": "abcabc", "b": "abcabc"}),
            item("bad", {"a": "abc", "b": "bca", "c": "cab"}),
            item("order", {"a": "abcXbcaXcab"}),
        ],
        ["Paper"],
    )
    result = index.page(space="dev2", keyword="abcabc")
    assert result["total"] == 1
    assert [row["vid"] for row in result["items"]] == ["good"]
    assert index.count(space="dev2", keyword="abcabc")["total"] == 1


def test_spaces_types_and_sql_input_are_isolated(index):
    index.build(
        "dev2",
        [item("p1", {"note": "x' OR 1=1 --"}), item("p1", {"name": "专家"}, "Person")],
        ["Paper", "Person"],
    )
    index.build("other", [item("p1", {"note": "私有数据"})], ["Paper"])
    assert index.page(space="dev2", keyword="私有")["total"] == 0
    assert index.page(space="dev2", keyword="x' OR 1=1 --")["total"] == 1
    assert index.page(space="dev2", keyword="p1", entity_type="Person")["total"] == 1
    with pytest.raises(LiteralIndexError, match="不存在实体类型"):
        index.page(space="dev2", keyword="p1", entity_type="Unknown")


def test_page_never_counts_and_deep_pages_cover_full_range(index):
    index.build(
        "dev2", (item(f"p{i:04}", {"title_zh": "同名论文"}) for i in range(1015)), ["Paper"]
    )
    statements = []
    event.listen(
        index.session.get_bind(),
        "before_cursor_execute",
        lambda conn, cur, stmt, params, ctx, many: statements.append(stmt),
    )
    first = index.page(space="dev2", keyword="同名论文")
    last = index.page(space="dev2", keyword="同名论文", offset=1010)
    assert first["total"] is None and first["hasMore"] is True
    assert last["hasMore"] is False and len(last["items"]) == 5
    assert not any("count(" in stmt.lower() for stmt in statements)
    assert (
        index.count(
            space="dev2", keyword="同名论文", generation=first["generation"], match_mode="exact"
        )["total"]
        == 1015
    )


def test_failed_build_keeps_previous_ready_generation_and_removes_partial_rows(index):
    original = index.build("dev2", [item("old", {"title_zh": "旧数据"})], ["Paper"])

    def broken():
        yield item("new", {"title_zh": "新数据"})
        index.session.commit()
        raise LiteralIndexError("某标签失败")

    with pytest.raises(LiteralIndexError):
        index.build("dev2", broken(), ["Paper"])
    assert index.page(space="dev2", keyword="旧数据")["generation"] == original["generation"]
    assert index.session.scalar(select(documents.c.id).where(documents.c.vid == "new")) is None


def test_graph_write_updates_projection_count_and_revision(monkeypatch, index):
    from service.entity_literal_sync import sync_literal_write

    index.build("dev2", [item("p1", {"title_zh": "旧标题"})], ["Paper"])
    old_revision = index.state("dev2")["revision"]
    engine = index.session.get_bind()
    index.session.close()
    monkeypatch.setenv("ENTITY_LITERAL_INDEX_SYNC_ENABLED", "true")
    monkeypatch.setattr("service.entity_literal_sync.get_workflow_engine", lambda: engine)

    class Graph:
        space = "dev2"

        @sync_literal_write
        def update_node(self):
            return SimpleNamespace(id="p1", labels=["Paper"], properties={"title_zh": "新标题"})

        @sync_literal_write
        def delete_node(self, node_id):
            return True

    Graph().update_node()
    assert index.page(space="dev2", keyword="旧标题")["total"] == 0
    assert index.page(space="dev2", keyword="新标题")["total"] == 1
    assert json.loads(index.state("dev2")["type_counts"])["Paper"] == 1
    with pytest.raises(LiteralIndexError, match="已更新"):
        index.count(space="dev2", keyword="新标题", generation=old_revision)
    index.session.close()
    Graph().delete_node("p1")
    assert index.page(space="dev2", keyword="新标题")["total"] == 0


def test_sync_failure_marks_index_unavailable_instead_of_returning_stale_results(
    monkeypatch, index
):
    from service.entity_literal_sync import sync_literal_write

    index.build("dev2", [item("p1", {"title_zh": "旧标题"})], ["Paper"])
    engine = index.session.get_bind()
    index.session.close()
    monkeypatch.setenv("ENTITY_LITERAL_INDEX_SYNC_ENABLED", "true")
    monkeypatch.setattr("service.entity_literal_sync.get_workflow_engine", lambda: engine)
    monkeypatch.setattr(
        EntityLiteralIndex,
        "sync_node",
        lambda *args, **kw: (_ for _ in ()).throw(RuntimeError("DB error")),
    )

    @sync_literal_write
    def update_node(graph):
        return SimpleNamespace(id="p1", labels=["Paper"], properties={"title_zh": "新标题"})

    assert update_node(SimpleNamespace(space="dev2")).properties["title_zh"] == "新标题"
    with pytest.raises(LiteralIndexError, match="失效"):
        index.page(space="dev2", keyword="旧标题")


def test_build_on_pinned_connection_commits_published_generation(index):
    engine = index.session.get_bind()
    with engine.connect() as connection, Session(bind=connection) as session:
        EntityLiteralIndex(session).build("dev2", [item("p1", {"title_zh": "已发布"})], ["Paper"])
    with Session(engine) as session:
        assert EntityLiteralIndex(session).page(space="dev2", keyword="已发布")["total"] == 1


def test_invalid_or_missing_index_is_explicit(index):
    with pytest.raises(LiteralIndexError, match="尚未建立"):
        index.page(space="dev2", keyword="论文")
    index.build("dev2", [], ["Paper"])
    index.session.execute(update(states).values(ready=0))
    index.session.commit()
    with pytest.raises(LiteralIndexError, match="失效"):
        index.page(space="dev2", keyword="论文")


def test_construction_write_reads_complete_node_and_edge_stats_do_not_invalidate(
    monkeypatch, index
):
    from service.entity_literal_sync import sync_literal_write

    index.build("dev2", [], ["Paper"])
    engine = index.session.get_bind()
    index.session.close()
    monkeypatch.setenv("ENTITY_LITERAL_INDEX_SYNC_ENABLED", "true")
    monkeypatch.setattr("service.entity_literal_sync.get_workflow_engine", lambda: engine)

    class Graph:
        space = "dev2"

        def get_node(self, vid):
            return SimpleNamespace(id=vid, labels=["Paper"], properties={"title_zh": "新入图论文"})

        @sync_literal_write
        def execute_entity_write(self, query, *, node_ids):
            return SimpleNamespace(records=[])

        @sync_literal_write
        def execute_write(self, query):
            return SimpleNamespace(records=[])

    Graph().execute_entity_write(
        'INSERT VERTEX Paper(title_zh) VALUES "p1":("新入图论文")', node_ids=["p1"]
    )
    assert index.page(space="dev2", keyword="新入图论文")["total"] == 1
    revision = index.state("dev2")["revision"]
    index.session.close()
    Graph().execute_write("SUBMIT JOB STATS")
    Graph().execute_write('INSERT EDGE coauthor() VALUES "p1"->"p2":()')
    assert index.state("dev2")["revision"] == revision
    index.session.close()
    Graph().execute_write('UPDATE VERTEX ON Paper "p1" SET title_zh="原始修改"')
    with pytest.raises(LiteralIndexError, match="失效"):
        index.page(space="dev2", keyword="新入图论文")
