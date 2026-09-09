"""清除项目域历史桩节点（project_stub）及其关联边。

现行 load_project_graph 已不再建桩；本脚本清理 space=dev 上残留的
``source`` / ``org_kind`` / ``person_kind`` 含 ``project_stub`` 的点，
以及其上项目域边。

用法::

    cd backend
    TRS_GRAPH_SPACE=dev uv run python -m script.cleanup_project_stubs --dry-run
"""

from __future__ import annotations

import argparse
import logging
import os
from typing import Any

from infra.graph_db import TRSGraphClient, close_trs_graph_client, get_trs_graph_client

logger = logging.getLogger("script.cleanup_project_stubs")

GRAPH_SPACE = os.getenv("TRS_GRAPH_SPACE", "dev")
STUB_MARKER = "project_stub"
PEER_LABELS = ("Person", "Organization", "Paper", "Patent", "Report", "Keyword")
PROJECT_EDGE_TYPES = (
    "FUNDED_BY",
    "LEADS",
    "HAS_PARTICIPANT",
    "HAS_KEYWORD",
    "HAS_OUTPUT",
    "PARTICIPATES_IN",
    "OUTPUT_OF",
    "SOURCED_FROM",
)


def get_dev_graph_client() -> TRSGraphClient:
    space = os.getenv("TRS_GRAPH_SPACE")
    if space != GRAPH_SPACE:
        raise RuntimeError(f"Project cleanup requires TRS_GRAPH_SPACE=dev, got {space!r}")
    return get_trs_graph_client()


def _node_props(node: Any) -> dict[str, Any]:
    if node is None:
        return {}
    props = getattr(node, "properties", None)
    if isinstance(props, dict):
        return props
    if isinstance(node, dict):
        return dict(node.get("properties") or node)
    return {}


def _node_id(node: Any) -> str:
    for key in ("id", "vid", "element_id"):
        value = getattr(node, key, None) if not isinstance(node, dict) else node.get(key)
        if value is not None and str(value).strip():
            return str(value)
    return ""


def is_project_stub(props: dict[str, Any], *, vid: str = "") -> bool:
    """判定是否为项目域历史桩。"""
    markers = (
        str(props.get("source") or ""),
        str(props.get("org_kind") or ""),
        str(props.get("person_kind") or ""),
        str(props.get("source_table") or ""),
    )
    if any(STUB_MARKER in marker for marker in markers):
        return True
    # 历史 VID 习惯：*_stub_* 或显式 stub 前缀
    text = str(vid or "")
    return "project_stub" in text or text.startswith("stub_")


def _scan_stub_vids(graph: TRSGraphClient, label: str, *, page_size: int = 500) -> list[str]:
    """分页扫描标签，返回桩 VID 列表。"""
    stubs: list[str] = []
    offset = 0
    while True:
        page = graph.get_nodes_by_label(label, limit=page_size, offset=offset)
        items = list(getattr(page, "items", None) or [])
        if not items:
            break
        for node in items:
            vid = _node_id(node)
            if is_project_stub(_node_props(node), vid=vid):
                stubs.append(vid)
        if len(items) < page_size:
            break
        offset += len(items)
    return stubs


def _delete_project_edges(graph: TRSGraphClient, vid: str, *, dry_run: bool) -> int:
    """删除桩节点上的项目域边；优先用 get_node_edges，失败则 nGQL DETACH 前手动计数。"""
    deleted = 0
    try:
        edges = graph.get_node_edges(vid, direction="both", limit=500)
        items = list(getattr(edges, "items", None) or edges or [])
    except Exception as exc:  # noqa: BLE001
        logger.warning("get_node_edges failed vid=%s: %s", vid, exc)
        items = []
    for edge in items:
        edge_type = (
            getattr(edge, "type", None)
            or getattr(edge, "edge_type", None)
            or (edge.get("type") if isinstance(edge, dict) else None)
            or ""
        )
        edge_id = getattr(edge, "id", None) or (edge.get("id") if isinstance(edge, dict) else None)
        if str(edge_type) not in PROJECT_EDGE_TYPES:
            continue
        deleted += 1
        if dry_run or edge_id is None:
            continue
        try:
            graph.delete_edge(edge_id, edge_type=str(edge_type))
        except Exception as exc:  # noqa: BLE001
            logger.warning("delete_edge failed edge=%s: %s", edge_id, exc)
    return deleted


def cleanup_project_stubs(
    *,
    dry_run: bool = True,
    labels: tuple[str, ...] = PEER_LABELS,
    graph: TRSGraphClient | None = None,
) -> dict[str, Any]:
    """扫描并清除 project_stub 桩节点。返回 JSON 可序列化报告。"""
    owns_graph = graph is None
    graph = graph or get_dev_graph_client()
    report: dict[str, Any] = {
        "dry_run": dry_run,
        "space": GRAPH_SPACE,
        "stubs_found": 0,
        "edges_deleted": 0,
        "nodes_deleted": 0,
        "by_label": {},
        "stub_vids": [],
    }
    try:
        for label in labels:
            vids = _scan_stub_vids(graph, label)
            report["by_label"][label] = len(vids)
            report["stubs_found"] += len(vids)
            for vid in vids:
                report["stub_vids"].append({"label": label, "vid": vid})
                report["edges_deleted"] += _delete_project_edges(graph, vid, dry_run=dry_run)
                if dry_run:
                    report["nodes_deleted"] += 1
                    continue
                try:
                    if graph.delete_node(vid, detach=True):
                        report["nodes_deleted"] += 1
                except Exception as exc:  # noqa: BLE001
                    logger.warning("delete_node failed vid=%s: %s", vid, exc)
        logger.info("cleanup summary: %s", {k: v for k, v in report.items() if k != "stub_vids"})
        return report
    finally:
        if owns_graph:
            close_trs_graph_client()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="默认 dry-run；传 --no-dry-run 才真正删除",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    print(cleanup_project_stubs(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
