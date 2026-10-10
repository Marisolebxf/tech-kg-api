"""Request-local graph selection. Never mutate a shared graph client's settings."""

from contextvars import ContextVar

request_can_write: ContextVar[bool] = ContextVar("request_can_write", default=False)

selected_graph_space: ContextVar[str | None] = ContextVar("selected_graph_space", default=None)


def get_current_space() -> str:
    from infra.graph_db.config import TRSGraphSettings

    return selected_graph_space.get() or TRSGraphSettings.from_env().space


def has_graph_entity(
    entity_id: str, labels: tuple[str, ...], prefixes: tuple[str, ...] = ()
) -> bool:
    """Only enrich SQL records whose stable ID is present in the selected graph."""
    from infra.graph_db import GraphNotFoundError, get_trs_graph_client

    graph = get_trs_graph_client()
    for vid in dict.fromkeys((entity_id, *(prefix + entity_id for prefix in prefixes))):
        try:
            node = graph.get_node(vid)
        except GraphNotFoundError:
            continue
        if node is not None and set(node.labels).intersection(labels):
            return True
    return False
