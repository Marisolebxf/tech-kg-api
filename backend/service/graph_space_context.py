"""Request-local graph selection. Never mutate a shared graph client's settings."""

from contextvars import ContextVar

request_can_write: ContextVar[bool] = ContextVar("request_can_write", default=False)

selected_graph_space: ContextVar[str | None] = ContextVar("selected_graph_space", default=None)

# 九大业务数据面标记：require_business_data 路由内置位，infra.graph_db 据此让
# get_trs_graph_client 优先返回 TRS_GRAPH_BUSINESS_* 独立连接（未配置该环境变量
# 时与平台面共用 TRS_GRAPH_*，行为不变）。平台管理路由与 worker 均不置位。
business_data_plane: ContextVar[bool] = ContextVar("business_data_plane", default=False)


def get_current_space() -> str:
    from infra.graph_db.config import TRSGraphSettings

    return selected_graph_space.get() or TRSGraphSettings.from_env().space


def effective_graph_space() -> str:
    """本次请求实际取数的图空间。

    九大业务（business_data_plane 置位）配置 TRS_GRAPH_BUSINESS_* 时返回业务面
    空间（TRS_GRAPH_BUSINESS_SPACE，未配置时按请求空间名映射），数据连接已被
    业务面接管；其余情况与 get_current_space() 一致。溯源标注（"trs-graph /
    space=..."）与按空间分型的查询参数（techkg 的边型/VID 前缀/方向）应以此
    为准，避免「数据取自 dev、口径按请求空间 test1012」的错位。
    """
    from infra.graph_db.config import business_plane_settings

    if business_data_plane.get():
        settings = business_plane_settings(selected_graph_space.get())
        if settings is not None:
            return settings.space
    return get_current_space()


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
