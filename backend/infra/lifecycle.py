"""Centralized shutdown of process-wide infrastructure clients."""

from infra.gkx import reset_gkx_client
from infra.gkx_element import reset_gkx_element_client
from infra.graph_db import close_graph_clients
from infra.llm import reset_llm_client
from infra.milvus import reset_milvus_client
from infra.mysql import mysql_client
from infra.s3 import reset_schema_s3_storage


def close_infrastructure() -> None:
    """Release every lazy singleton that may own sockets, pools, or threads."""
    close_graph_clients()
    reset_milvus_client()
    reset_schema_s3_storage()
    reset_llm_client()
    reset_gkx_element_client()
    reset_gkx_client()
    mysql_client.dispose()
