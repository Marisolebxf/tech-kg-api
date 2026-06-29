"""测试参数下拉选项 路由。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from service.kg_options import get_options

router = APIRouter(prefix="/kg-construction/options")


@router.get("")
async def options() -> dict[str, Any]:
    return get_options()
