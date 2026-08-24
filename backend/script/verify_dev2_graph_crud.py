"""穷举式验证 trs-graph REST API 在 dev2 图空间上的 CRUD 行为。

按 CLAUDE.md 的口径：Node CRUD 应当 broken，Edge CRUD 应当 work，DDL 走 nGQL 应当 work。
本脚本逐个调用 TRSGraphClient 的方法，报告每个操作实际返回什么。

用法：
    docker exec tech-kg-api-dev2 .venv/bin/python -m script.verify_dev2_graph_crud
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime

from infra.graph_db import get_trs_graph_client
from infra.graph_db.exceptions import GraphRepoError

logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _status(ok: bool, detail: str = "") -> str:
    return f"{'OK ' if ok else 'FAIL'} {detail}".strip()


def main() -> int:
    client = get_trs_graph_client()
    # 显式 connect 触发日志确认 space
    _ = client.get_node("__crudtest_probe__")  # noop，仅触发连接日志
    print(f"=== space={client._settings.space} ===")  # type: ignore[attr-defined]
    print()

    results: list[tuple[str, str]] = []

    # ===== DDL (nGQL) =====
    print("--- DDL via execute_write ---")
    try:
        client.execute_write(
            "CREATE TAG IF NOT EXISTS CrudTest(vid string, name string, ts string);"
        )
        results.append(("DDL CREATE TAG CrudTest", _status(True)))
    except Exception as exc:
        results.append(("DDL CREATE TAG CrudTest", _status(False, str(exc)[:200])))
    try:
        client.execute_write("CREATE EDGE IF NOT EXISTS CRUD_TEST_EDGE(reason string, ts string);")
        results.append(("DDL CREATE EDGE CRUD_TEST_EDGE", _status(True)))
    except Exception as exc:
        results.append(("DDL CREATE EDGE CRUD_TEST_EDGE", _status(False, str(exc)[:200])))

    # ===== Node CRUD =====
    print("--- Node CRUD ---")
    ts = datetime.now().strftime("%H%M%S")
    vid1 = f"crudtest_node_{ts}"
    vid2 = f"crudtest_merge_{ts}"

    # create_node
    try:
        node = client.create_node(["CrudTest"], {"vid": vid1, "name": "alice", "ts": ts})
        results.append(("create_node", _status(True, f"id={node.id} labels={node.labels}")))
    except Exception as exc:
        results.append(("create_node", _status(False, repr(exc)[:200])))

    # merge_node（旧 ETL 用的就是这个）
    try:
        node = client.merge_node(
            ["CrudTest"],
            {"vid": vid2},
            {"name": "bob", "ts": ts},
        )
        results.append(("merge_node (identityProps=vid)", _status(True, f"id={node.id}")))
    except Exception as exc:
        results.append(("merge_node (identityProps=vid)", _status(False, repr(exc)[:200])))

    # merge_node with empty identity props (常见 ETL 失败模式)
    try:
        node = client.merge_node(
            ["CrudTest"], {}, {"vid": f"crudtest_merge2_{ts}", "name": "carol"}
        )
        results.append(("merge_node (empty identityProps)", _status(True, f"id={node.id}")))
    except Exception as exc:
        results.append(("merge_node (empty identityProps)", _status(False, repr(exc)[:200])))

    # get_node
    try:
        node = client.get_node(vid1)
        results.append(("get_node", _status(node is not None, f"got={node.id if node else None}")))
    except Exception as exc:
        results.append(("get_node", _status(False, repr(exc)[:200])))

    # get_nodes_by_label
    try:
        page = client.get_nodes_by_label("CrudTest", limit=10)
        results.append(
            ("get_nodes_by_label", _status(True, f"total={page.total} items={len(page.items)}"))
        )
    except Exception as exc:
        results.append(("get_nodes_by_label", _status(False, repr(exc)[:200])))

    # find_nodes
    try:
        page = client.find_nodes(["CrudTest"], {"name": "alice"}, limit=10)
        results.append(
            (
                "find_nodes by name=alice",
                _status(True, f"total={page.total} items={len(page.items)}"),
            )
        )
    except Exception as exc:
        results.append(("find_nodes by name=alice", _status(False, repr(exc)[:200])))

    # update_node
    try:
        node = client.update_node(vid1, {"name": "alice_updated"})
        results.append(("update_node", _status(True, f"name={node.properties.get('name')}")))
    except Exception as exc:
        results.append(("update_node", _status(False, repr(exc)[:200])))

    # delete_node
    try:
        ok = client.delete_node(vid1, detach=True)
        results.append(("delete_node", _status(ok)))
    except Exception as exc:
        results.append(("delete_node", _status(False, repr(exc)[:200])))

    # ===== Edge CRUD =====
    print("--- Edge CRUD ---")
    # 先确保两个端点存在
    src = f"crudtest_edge_src_{ts}"
    tgt = f"crudtest_edge_tgt_{ts}"
    try:
        client.create_node(["CrudTest"], {"vid": src, "name": "src", "ts": ts})
        client.create_node(["CrudTest"], {"vid": tgt, "name": "tgt", "ts": ts})
    except Exception:
        pass  # 上面 create_node 已经报告过状态

    # create_edge
    try:
        edge = client.create_edge(src, tgt, "CRUD_TEST_EDGE", {"reason": "smoke", "ts": ts})
        results.append(("create_edge", _status(True, f"id={edge.id} type={edge.type}")))
    except Exception as exc:
        results.append(("create_edge", _status(False, repr(exc)[:200])))

    # merge_edge
    try:
        edge = client.merge_edge(
            src, tgt, "CRUD_TEST_EDGE", {"reason": "smoke"}, {"reason": "smoke_merge", "ts": ts}
        )
        results.append(("merge_edge", _status(True, f"id={edge.id}")))
    except Exception as exc:
        results.append(("merge_edge", _status(False, repr(exc)[:200])))

    # get_node_edges
    try:
        edges = client.get_node_edges(src, direction="outgoing", limit=10)
        results.append(("get_node_edges", _status(True, f"count={len(edges)}")))
    except Exception as exc:
        results.append(("get_node_edges", _status(False, repr(exc)[:200])))

    # get_edges_by_type
    try:
        page = client.get_edges_by_type("CRUD_TEST_EDGE", limit=10)
        results.append(
            ("get_edges_by_type", _status(True, f"total={page.total} items={len(page.items)}"))
        )
    except Exception as exc:
        results.append(("get_edges_by_type", _status(False, repr(exc)[:200])))

    # find_edges
    try:
        page = client.find_edges("CRUD_TEST_EDGE", {"reason": "smoke"}, limit=10)
        results.append(
            (
                "find_edges by reason=smoke",
                _status(True, f"total={page.total} items={len(page.items)}"),
            )
        )
    except Exception as exc:
        results.append(("find_edges by reason=smoke", _status(False, repr(exc)[:200])))

    # get_edge (by edge_id "src->tgt:0")
    edge_id = f"{src}->{tgt}:0"
    try:
        edge = client.get_edge(edge_id, edge_type="CRUD_TEST_EDGE")
        results.append(("get_edge", _status(edge is not None, f"got={edge.id if edge else None}")))
    except Exception as exc:
        results.append(("get_edge", _status(False, repr(exc)[:200])))

    # update_edge
    try:
        edge = client.update_edge(edge_id, {"reason": "smoke_updated"}, edge_type="CRUD_TEST_EDGE")
        results.append(("update_edge", _status(True, f"reason={edge.properties.get('reason')}")))
    except Exception as exc:
        results.append(("update_edge", _status(False, repr(exc)[:200])))

    # delete_edge
    try:
        ok = client.delete_edge(edge_id, edge_type="CRUD_TEST_EDGE")
        results.append(("delete_edge", _status(ok)))
    except Exception as exc:
        results.append(("delete_edge", _status(False, repr(exc)[:200])))

    # ===== 输出 =====
    print()
    print("=== Summary ===")
    for name, status in results:
        print(f"  {name:40s} -> {status}")

    # 清理
    print()
    print("--- Cleanup ---")
    try:
        client.execute_write("DROP TAG IF EXISTS CrudTest;")
        print("  DROP TAG CrudTest: OK")
    except Exception as exc:
        print(f"  DROP TAG CrudTest: FAIL {exc}")
    try:
        client.execute_write("DROP EDGE IF EXISTS CRUD_TEST_EDGE;")
        print("  DROP EDGE CRUD_TEST_EDGE: OK")
    except Exception as exc:
        print(f"  DROP EDGE CRUD_TEST_EDGE: FAIL {exc}")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except GraphRepoError as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
