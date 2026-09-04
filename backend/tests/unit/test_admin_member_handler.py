"""Unit tests for the global administrator member handlers."""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from biz.handler import admin_member
from biz.schemas.correction import AdminRoleUpdateRequest


def _application(*admin_ids: str) -> SimpleNamespace:
    return SimpleNamespace(settings=SimpleNamespace(initial_admin_user_ids=admin_ids))


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
        session,
    )

    assert captured == {
        "session": session,
        "initial_admin_ids": ("configured-admin", "current-admin"),
    }
    assert response.data == {"items": [{"id": "member-1"}], "total": 1}


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
