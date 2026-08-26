"""图空间列表 API。空间在 NebulaGraph 管理，此处只读列出供触发选择。"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from biz.schemas.common import ApiResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/graph-spaces", tags=["graph-space"])


@router.get("", response_model=ApiResponse)
def list_graph_spaces() -> ApiResponse:
    try:
        from infra.graph_db import get_trs_graph_client

        client = get_trs_graph_client()
        spaces = client.list_spaces()
    except Exception as exc:  # noqa: BLE001
        logger.warning("列出图空间失败，回退空列表: %s", exc)
        spaces = []
    return ApiResponse(data={"items": spaces})
