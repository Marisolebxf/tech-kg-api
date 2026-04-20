"""graph_db Service 层 CRUD 集成测试。

运行前确保：
  1. Neo4j 服务已启动（bolt://localhost:7687）
  2. 项目根目录下有 .env 文件配置了 GRAPH_DB_PASSWORD

运行方式：
  cd /home/hyt/KEG/tech-kg-api
  python tests/test_graph_db_services.py
  # 或
  uv run pytest tests/test_graph_db_services.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

# 确保项目根目录在 sys.path
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv

load_dotenv(_ROOT / ".env")

from graph_db import connect, GraphDBConfig
from graph_db.models import IndexSpec, ConstraintSpec
from graph_db.services import (
    EdgeService,
    NodeService,
    QueryService,
    SchemaService,
    TraversalService,
)

# ---------------------------------------------------------------------------
# 全局 db 实例，测试开始前连接、结束后关闭
# ---------------------------------------------------------------------------
db = connect(GraphDBConfig.from_env())

nodes = NodeService(db)
edges = EdgeService(db)
traversal = TraversalService(db)
query = QueryService(db)
schema = SchemaService(db)

_passed = 0
_failed = 0


def _run(name: str, fn):
    global _passed, _failed
    try:
        fn()
        _passed += 1
        print(f"  PASS  {name}")
    except Exception as e:
        _failed += 1
        print(f"  FAIL  {name}: {e}")


# ---------------------------------------------------------------------------
# 测试前清空数据库
# ---------------------------------------------------------------------------
def _clear_db():
    db.execute_write("MATCH (n) DETACH DELETE n")
    # 先删约束（unique constraint 拥有 unique index）
    for c in schema.list_constraints():
        try:
            schema.drop_constraint(c.name)
        except Exception:
            pass
    for idx in schema.list_indexes():
        try:
            schema.drop_index(idx.label, idx.properties)
        except Exception:
            pass


# ===================================================================
# NodeService
# ===================================================================

def test_node_create():
    n = nodes.create(["Person"], {"name": "Alice", "age": 30})
    assert n.id is not None
    assert "Person" in n.labels
    assert n.properties["name"] == "Alice"
    assert n.properties["age"] == 30


def test_node_merge_create():
    n = nodes.merge(["Person"], {"name": "Bob"}, {"age": 25})
    assert n.id is not None
    assert n.properties["name"] == "Bob"


def test_node_merge_update():
    n1 = nodes.merge(["City"], {"name": "北京"}, {"population": 2100})
    n2 = nodes.merge(["City"], {"name": "北京"}, {"population": 2200, "area": 16410})
    assert n2.id == n1.id
    assert n2.properties["population"] == 2200
    assert n2.properties["area"] == 16410


def test_node_get():
    n = nodes.create(["Person"], {"name": "Charlie"})
    got = nodes.get(n.id)
    assert got is not None
    assert got.properties["name"] == "Charlie"


def test_node_get_not_found():
    assert nodes.get("nonexistent_id") is None


def test_node_list_by_label():
    nodes.create(["Animal"], {"name": "Cat"})
    nodes.create(["Animal"], {"name": "Dog"})
    result = nodes.list_by_label("Animal", limit=10)
    assert result.page.total >= 2
    assert len(result.items) >= 2


def test_node_find():
    nodes.create(["Person"], {"name": "Diana", "city": "上海"})
    result = nodes.find(["Person"], {"name": "Diana"})
    assert len(result.items) >= 1
    assert result.items[0].properties["city"] == "上海"


def test_node_update():
    n = nodes.create(["Person"], {"name": "Eve", "age": 20})
    updated = nodes.update(n.id, {"age": 21, "city": "深圳"})
    assert updated.properties["age"] == 21
    assert updated.properties["city"] == "深圳"
    assert updated.properties["name"] == "Eve"


def test_node_delete():
    n = nodes.create(["Person"], {"name": "Frank"})
    assert nodes.delete(n.id) is True
    assert nodes.get(n.id) is None


def test_node_delete_with_edges():
    a = nodes.create(["Person"], {"name": "G1"})
    b = nodes.create(["Person"], {"name": "G2"})
    edges.create(a.id, b.id, "KNOWS")
    # 不带 detach 删除应失败（有边）
    try:
        nodes.delete(a.id, detach=False)
    except Exception:
        pass  # 预期可能报错
    # 带 detach 删除
    assert nodes.delete(a.id, detach=True) is True
    assert nodes.get(a.id) is None


def test_node_batch_create():
    items = [{"name": f"Batch_{i}", "value": i} for i in range(5)]
    created = nodes.batch_create(items, labels=["BatchTest"])
    assert len(created) == 5
    for i, n in enumerate(created):
        assert n.properties["name"] == f"Batch_{i}"


# ===================================================================
# EdgeService
# ===================================================================

def test_edge_create():
    a = nodes.create(["Person"], {"name": "HA"})
    b = nodes.create(["Person"], {"name": "HB"})
    e = edges.create(a.id, b.id, "KNOWS", {"since": 2020})
    assert e.id is not None
    assert e.type == "KNOWS"
    assert e.source_id == a.id
    assert e.target_id == b.id
    assert e.properties["since"] == 2020


def test_edge_merge_create():
    a = nodes.create(["Person"], {"name": "HC"})
    b = nodes.create(["Person"], {"name": "HD"})
    e = edges.merge(a.id, b.id, "FRIEND", {"since": 2021}, {"level": "close"})
    assert e.type == "FRIEND"
    assert e.properties["level"] == "close"


def test_edge_merge_update():
    a = nodes.create(["Person"], {"name": "HE"})
    b = nodes.create(["Person"], {"name": "HF"})
    e1 = edges.merge(a.id, b.id, "COLLEAGUE", {"since": 2022}, {"level": "normal"})
    e2 = edges.merge(a.id, b.id, "COLLEAGUE", {"since": 2022}, {"level": "best"})
    assert e2.id == e1.id
    assert e2.properties["level"] == "best"


def test_edge_get():
    a = nodes.create(["Person"], {"name": "HG"})
    b = nodes.create(["Person"], {"name": "HH"})
    e = edges.create(a.id, b.id, "LINKS")
    got = edges.get(e.id)
    assert got is not None
    assert got.type == "LINKS"


def test_edge_get_not_found():
    assert edges.get("nonexistent_id") is None


def test_edge_list_by_type():
    a = nodes.create(["Person"], {"name": "HI"})
    b = nodes.create(["Person"], {"name": "HJ"})
    edges.create(a.id, b.id, "TEST_LIST", {"seq": 1})
    edges.create(a.id, b.id, "TEST_LIST", {"seq": 2})
    result = edges.list_by_type("TEST_LIST", limit=10)
    assert result.page.total >= 2


def test_edge_find():
    a = nodes.create(["Person"], {"name": "HK"})
    b = nodes.create(["Person"], {"name": "HL"})
    edges.create(a.id, b.id, "FIND_REL", {"key": "val1"})
    result = edges.find("FIND_REL", {"key": "val1"})
    assert len(result.items) >= 1


def test_edge_update():
    a = nodes.create(["Person"], {"name": "HM"})
    b = nodes.create(["Person"], {"name": "HN"})
    e = edges.create(a.id, b.id, "UPD_REL", {"score": 5})
    updated = edges.update(e.id, {"score": 10, "note": "great"})
    assert updated.properties["score"] == 10
    assert updated.properties["note"] == "great"


def test_edge_delete():
    a = nodes.create(["Person"], {"name": "HO"})
    b = nodes.create(["Person"], {"name": "HP"})
    e = edges.create(a.id, b.id, "DEL_REL")
    assert edges.delete(e.id) is True
    assert edges.get(e.id) is None


def test_edge_batch_create():
    a = nodes.create(["Person"], {"name": "HQ"})
    b = nodes.create(["Person"], {"name": "HR"})
    items = [{"source_id": a.id, "target_id": b.id, "weight": i} for i in range(3)]
    created = edges.batch_create(items, edge_type="BATCH_REL")
    assert len(created) == 3


# ===================================================================
# TraversalService
# ===================================================================

def test_traversal_neighbours():
    a = nodes.create(["Person"], {"name": "IA"})
    b = nodes.create(["Person"], {"name": "IB"})
    c = nodes.create(["Person"], {"name": "IC"})
    edges.create(a.id, b.id, "KNOWS_TRAV")
    edges.create(a.id, c.id, "KNOWS_TRAV")
    nbrs = traversal.neighbours(a.id, direction="out", edge_type="KNOWS_TRAV")
    nbr_ids = {n.id for n in nbrs}
    assert b.id in nbr_ids
    assert c.id in nbr_ids


def test_traversal_neighbours_direction():
    a = nodes.create(["Person"], {"name": "JA"})
    b = nodes.create(["Person"], {"name": "JB"})
    edges.create(a.id, b.id, "DIR_REL")
    # out: a -> b
    out_nbrs = traversal.neighbours(a.id, direction="out", edge_type="DIR_REL")
    assert len(out_nbrs) >= 1
    # in: b 收到 a 的边
    in_nbrs = traversal.neighbours(b.id, direction="in", edge_type="DIR_REL")
    assert len(in_nbrs) >= 1


def test_traversal_node_edges():
    a = nodes.create(["Person"], {"name": "KA"})
    b = nodes.create(["Person"], {"name": "KB"})
    edges.create(a.id, b.id, "EDGE_REL", {"seq": 1})
    node_edges_list = traversal.node_edges(a.id, direction="out", edge_type="EDGE_REL")
    assert len(node_edges_list) >= 1


def test_traversal_shortest_path():
    a = nodes.create(["Person"], {"name": "LA"})
    b = nodes.create(["Person"], {"name": "LB"})
    c = nodes.create(["Person"], {"name": "LC"})
    edges.create(a.id, b.id, "PATH_REL")
    edges.create(b.id, c.id, "PATH_REL")
    path = traversal.shortest_path(a.id, c.id, edge_type="PATH_REL", max_depth=5)
    assert path is not None
    assert len(path.nodes) == 3
    assert len(path.edges) == 2


def test_traversal_shortest_path_not_found():
    a = nodes.create(["Person"], {"name": "MA"})
    b = nodes.create(["Person"], {"name": "MB"})
    path = traversal.shortest_path(a.id, b.id, edge_type="NO_SUCH_REL")
    assert path is None


# ===================================================================
# QueryService
# ===================================================================

def test_query_execute():
    nodes.create(["QueryTest"], {"name": "Q1"})
    result = query.execute("MATCH (n:QueryTest) WHERE n.name = $name RETURN n.name AS name", params={"name": "Q1"})
    assert len(result.records) >= 1
    assert result.records[0]["name"] == "Q1"


def test_query_read():
    result = query.read("MATCH (n) RETURN count(n) AS total")
    assert len(result.records) == 1
    assert result.records[0]["total"] >= 0


def test_query_write():
    result = query.write("CREATE (n:QueryWriteTest {ts: timestamp()}) RETURN n.ts AS ts")
    assert len(result.records) == 1
    assert result.records[0]["ts"] is not None


# ===================================================================
# SchemaService
# ===================================================================

def test_schema_index_lifecycle():
    schema.create_index(IndexSpec(label="SchemaTestNode", properties=["name"], unique=False))
    indexes = schema.list_indexes(label="SchemaTestNode")
    assert any(i.properties == ["name"] for i in indexes)
    schema.drop_index("SchemaTestNode", ["name"])


def test_schema_unique_index():
    schema.create_index(IndexSpec(label="UniqueTestNode", properties=["code"], unique=True))
    indexes = schema.list_indexes(label="UniqueTestNode")
    assert any(i.properties == ["code"] and i.unique for i in indexes)
    # Neo4j 5 中 unique index 由 unique constraint 拥有，需通过 drop_constraint 清理
    constraints = schema.list_constraints()
    for c in constraints:
        if c.label == "UniqueTestNode" and c.property == "code":
            schema.drop_constraint(c.name)
            break


def test_schema_constraint_lifecycle():
    schema.create_constraint(ConstraintSpec(
        name="schema_test_unique", label="SchemaTestNode", property="email", kind="unique",
    ))
    constraints = schema.list_constraints()
    assert any(c.name == "schema_test_unique" for c in constraints)
    schema.drop_constraint("schema_test_unique")


def test_schema_node_count():
    count = schema.node_count()
    assert count >= 0


def test_schema_node_count_by_label():
    nodes.create(["CountLabel"], {"name": "cnt1"})
    count = schema.node_count(label="CountLabel")
    assert count >= 1


def test_schema_edge_count():
    count = schema.edge_count()
    assert count >= 0


def test_schema_labels():
    labels = schema.labels()
    assert isinstance(labels, list)


def test_schema_edge_types():
    types = schema.edge_types()
    assert isinstance(types, list)


# ===================================================================
# 运行
# ===================================================================

def main():
    global _passed, _failed

    print("\n清空数据库...")
    _clear_db()

    print("\n=== NodeService ===")
    _run("create", test_node_create)
    _run("merge_create", test_node_merge_create)
    _run("merge_update", test_node_merge_update)
    _run("get", test_node_get)
    _run("get_not_found", test_node_get_not_found)
    _run("list_by_label", test_node_list_by_label)
    _run("find", test_node_find)
    _run("update", test_node_update)
    _run("delete", test_node_delete)
    _run("delete_with_edges", test_node_delete_with_edges)
    _run("batch_create", test_node_batch_create)

    print("\n=== EdgeService ===")
    _run("create", test_edge_create)
    _run("merge_create", test_edge_merge_create)
    _run("merge_update", test_edge_merge_update)
    _run("get", test_edge_get)
    _run("get_not_found", test_edge_get_not_found)
    _run("list_by_type", test_edge_list_by_type)
    _run("find", test_edge_find)
    _run("update", test_edge_update)
    _run("delete", test_edge_delete)
    _run("batch_create", test_edge_batch_create)

    print("\n=== TraversalService ===")
    _run("neighbours", test_traversal_neighbours)
    _run("neighbours_direction", test_traversal_neighbours_direction)
    _run("node_edges", test_traversal_node_edges)
    _run("shortest_path", test_traversal_shortest_path)
    _run("shortest_path_not_found", test_traversal_shortest_path_not_found)

    print("\n=== QueryService ===")
    _run("execute", test_query_execute)
    _run("read", test_query_read)
    _run("write", test_query_write)

    print("\n=== SchemaService ===")
    _run("index_lifecycle", test_schema_index_lifecycle)
    _run("unique_index", test_schema_unique_index)
    _run("constraint_lifecycle", test_schema_constraint_lifecycle)
    _run("node_count", test_schema_node_count)
    _run("node_count_by_label", test_schema_node_count_by_label)
    _run("edge_count", test_schema_edge_count)
    _run("labels", test_schema_labels)
    _run("edge_types", test_schema_edge_types)

    db.close()

    print(f"\n{'='*40}")
    print(f"总计: {_passed + _failed}  通过: {_passed}  失败: {_failed}")
    if _failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
