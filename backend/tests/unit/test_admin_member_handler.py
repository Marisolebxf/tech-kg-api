"""Unit tests for the global administrator member handlers."""

import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from biz.handler import admin_member
from biz.schemas.correction import AdminRoleUpdateRequest


def _application(*admin_ids: str) -> SimpleNamespace:
    return SimpleNamespace(settings=SimpleNamespace(initial_admin_user_ids=admin_ids))


def _request() -> SimpleNamespace:
    # get_cache 仅读取 query_params.multi_items() 组缓存键，空参数即可。
    return SimpleNamespace(query_params=SimpleNamespace(multi_items=lambda: []))


def test_get_members_includes_configured_and_current_admin(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_list_members(
        session: object, *, initial_admin_ids: tuple[str, ...]
    ) -> list[dict[str, str]]:
        captured["session"] = session
        captured["initial_admin_ids"] = initial_admin_ids
        return [{"id": "member-1"}]

    monkeypatch.setattr(admin_member, "list_members", fake_list_members)
    session = object()
    response = admin_member.get_members(
        SimpleNamespace(user_id="current-admin"),
        _application("configured-admin"),
        _request(),
        session,
    )

    assert captured == {
        "session": session,
        "initial_admin_ids": ("configured-admin", "current-admin"),
    }
    # get_cache.store 返回预序列化 Response，断言落到 JSON body 上。
    assert json.loads(response.body)["data"] == {"items": [{"id": "member-1"}], "total": 1}


def test_update_admin_role_maps_service_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing_user(*args: object, **kwargs: object) -> None:
        raise KeyError("missing")

    monkeypatch.setattr(admin_member, "set_admin_role", missing_user)

    with pytest.raises(HTTPException) as exc_info:
        admin_member.update_admin_role(
            "missing-user",
            AdminRoleUpdateRequest(is_admin=True),
            SimpleNamespace(user_id="current-admin"),
            _application("configured-admin"),
            object(),
        )

    assert exc_info.value.status_code == 404
