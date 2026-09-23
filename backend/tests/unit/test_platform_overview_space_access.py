"""平台总览空间访问口径单测：与实体列表（graph_search._ensure_space_access）同源。

背景（2026-09-24 修复）：非 RBAC 模式下总览此前不校验 space，换账号登录后
前端带着上一用户选中的空间请求，总览把无权空间的数据直接返回给普通用户。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import biz.handler.platform_overview as overview_handler
from service.platform_access import PlatformActor

BINDINGS = {("101", "bound_private")}


def _actor(user_id: str, *, is_admin: bool = False) -> PlatformActor:
    return PlatformActor(
        user_id=user_id, username="u", display_name="u", email="", is_admin=is_admin
    )


@pytest.fixture
def console_backend(monkeypatch: pytest.MonkeyPatch):
    """rbac 关闭 + 图服务/绑定关系桩化；get_overview 记录收到的 space。"""

    calls: dict[str, str | None] = {"space": "__unset__"}

    class FakeGraphSpaceService:
        def __init__(self, session):  # noqa: ANN001
            self.session = session

        def is_bound(self, user_id: str, space: str) -> bool:
            return (user_id, space) in BINDINGS

    monkeypatch.setattr(overview_handler, "rbac_enabled", lambda: False)
    monkeypatch.setattr("service.business_access_control.rbac_enabled", lambda: False)
    monkeypatch.setattr("service.graph_space.GraphSpaceService", FakeGraphSpaceService)
    monkeypatch.setattr("service.graph_space.default_graph_space", lambda: "dev")
    monkeypatch.setattr(
        "infra.mysql.create_session", lambda: SimpleNamespace(close=lambda: None)
    )
    monkeypatch.setattr(
        overview_handler,
        "application",
        SimpleNamespace(get_overview=lambda space: calls.update(space=space) or {"ok": True}),
    )
    return calls


async def test_regular_user_other_private_space_forbidden(console_backend) -> None:
    with pytest.raises(HTTPException) as exc:
        await overview_handler._get_overview("other_private", _actor("101"))
    assert exc.value.status_code == 403
    assert console_backend["space"] == "__unset__"  # 未触达数据查询


async def test_regular_user_default_and_bound_space_pass(console_backend) -> None:
    await overview_handler._get_overview("dev", _actor("101"))  # 默认空间（env 未设 → dev）
    assert console_backend["space"] == "dev"
    await overview_handler._get_overview("bound_private", _actor("101"))
    assert console_backend["space"] == "bound_private"


async def test_admin_exempt_and_none_space_falls_back(console_backend) -> None:
    await overview_handler._get_overview("any_space", _actor("240", is_admin=True))
    assert console_backend["space"] == "any_space"
    await overview_handler._get_overview(None, _actor("101"))
    assert console_backend["space"] is None  # 缺省回落 env 默认空间
