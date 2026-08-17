from dataclasses import replace
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest

from biz.schemas.auth import MenuSummary, PermissionSetSummary, RoleMenuSummary
from config.auth import AuthSettings
from infra.redis import MemoryJsonStore
from service.auth import AuthenticationError, AuthService


class FakeUserCenter:
    def __init__(self, settings: AuthSettings) -> None:
        self.settings = settings
        self.check_count = 0
        self.permission_count = 0
        self.logout_count = 0

    def build_login_url(self, state: str) -> str:
        return f"https://sso.test/uc/sso/login?state={state}"

    async def exchange_code(self, code: str, *, state: str | None = None) -> dict[str, Any]:
        assert code == "valid-code"
        assert state
        return {
            "access_token": "access-token",
            "refresh_token": "refresh-token",
            "expires_in": 3600,
        }

    async def refresh(self, refresh_token: str) -> dict[str, Any]:
        assert refresh_token == "refresh-token"
        return {
            "access_token": "refreshed-token",
            "refresh_token": "refresh-token",
            "expires_in": 7200,
        }

    async def check_token(self, access_token: str) -> dict[str, Any]:
        self.check_count += 1
        return {"access_token": access_token, "exp": 4_102_444_800}

    async def get_permission_info(
        self,
        access_token: str,
        *,
        org_id: int | None = None,
        include_role_menu: bool = True,
    ) -> dict[str, Any]:
        self.permission_count += 1
        return {
            "userInfo": {
                "id": 139,
                "username": "test",
                "nickname": "普通用户",
                "email": "test@example.com",
                "userType": 1,
            },
            "allPermissions": {
                "roles": [
                    {
                        "id": 5,
                        "name": "研究院管理员",
                        "code": "research_admin",
                        "orgId": 2,
                        "type": 2,
                    }
                ],
                "menus": [],
                "permissions": ["schema:read", "operator:invoke"],
            },
            "appPermissions": {"roles": [], "menus": [], "permissions": []},
            "orgPermissions": {"roles": [], "menus": [], "permissions": []},
            "roleMenuList": [],
            "orgs": [{"id": 2, "orgName": "研究院"}],
        }

    async def logout(self, access_token: str) -> bool:
        self.logout_count += 1
        return access_token in {"access-token", "refreshed-token"}


def _service() -> tuple[AuthService, FakeUserCenter]:
    settings = replace(
        AuthSettings.from_env(),
        enabled=True,
        client_id="techkg",
        client_secret="secret",
        session_backend="memory",
    )
    user_center = FakeUserCenter(settings)
    return AuthService(settings, MemoryJsonStore(), user_center), user_center


async def test_authorization_state_is_one_time_and_creates_session() -> None:
    service, _ = _service()
    login_url, _, _ = await service.create_login_url("/schema")
    state = parse_qs(urlparse(login_url).query)["state"][0]

    context, next_path = await service.complete_login("valid-code", state)
    restored = await service.get_session(context.session_id or "")
    profile = service.profile(restored)

    assert next_path == "/schema"
    assert restored.access_token == "access-token"
    assert profile.user.nickname == "普通用户"
    assert profile.roles[0].code == "research_admin"
    assert profile.permissions == ["operator:invoke", "schema:read"]
    assert profile.organizations[0]["orgName"] == "研究院"

    with pytest.raises(AuthenticationError, match="状态已过期或无效"):
        await service.complete_login("valid-code", state)


async def test_unsafe_next_url_is_replaced() -> None:
    service, _ = _service()
    login_url, _, _ = await service.create_login_url("//attacker.example/path")
    state = parse_qs(urlparse(login_url).query)["state"][0]

    _, next_path = await service.complete_login("valid-code", state)

    assert next_path == "/overview"


async def test_bearer_validation_is_cached_without_storing_plain_token_in_key() -> None:
    service, user_center = _service()

    first = await service.resolve_bearer("vendor-access-token")
    second = await service.resolve_bearer("vendor-access-token")

    assert first.permission_info == second.permission_info
    assert user_center.check_count == 1
    assert user_center.permission_count == 1


async def test_refresh_and_logout_rotate_then_remove_session() -> None:
    service, user_center = _service()
    login_url, _, _ = await service.create_login_url("/overview")
    state = parse_qs(urlparse(login_url).query)["state"][0]
    context, _ = await service.complete_login("valid-code", state)

    refreshed = await service.refresh_session(context.session_id or "", context=context)
    revoked = await service.logout(refreshed)

    assert refreshed.access_token == "refreshed-token"
    assert revoked is True
    assert user_center.logout_count == 1
    with pytest.raises(AuthenticationError, match="登录已过期"):
        await service.get_session(context.session_id or "")


async def test_account_security_and_operation_logs_use_current_user() -> None:
    service, _ = _service()
    login_url, _, _ = await service.create_login_url("/overview")
    state = parse_qs(urlparse(login_url).query)["state"][0]
    context, _ = await service.complete_login("valid-code", state)

    security = service.account_security(context)
    await service.record_operation(
        context,
        action="登录平台",
        category="登录",
        detail="OAuth2 登录",
        ip_address="127.0.0.1",
        user_agent="pytest",
    )
    await service.record_operation(
        context,
        action="刷新登录会话",
        category="安全",
        detail="刷新令牌",
        ip_address="127.0.0.1",
        user_agent="pytest",
    )
    page = await service.operation_logs(context, category="安全", keyword="刷新")

    assert security.account_status == "正常"
    assert security.authentication_method == "统一用户中心 OAuth2"
    assert security.email_bound is True
    assert security.mobile_bound is False
    assert security.password_editable_here is False
    assert page.total == 1
    assert page.items[0].action == "刷新登录会话"
    assert page.items[0].ip_address == "127.0.0.1"


def test_v21_menu_link_type_and_role_menu_mapping_are_exposed() -> None:
    service, _ = _service()
    context = service.dev_context()
    context.permission_info["allPermissions"]["menus"] = [
        {
            "id": 100,
            "name": "外部服务",
            "path": "https://example.test/service",
            "linkType": 1,
            "children": [],
        }
    ]
    context.permission_info["roleMenuList"] = [
        {
            "role": {
                "id": 1,
                "name": "管理员",
                "code": "admin",
                "type": 1,
            },
            "menus": context.permission_info["allPermissions"]["menus"],
        }
    ]

    profile = service.profile(context)

    assert profile.menus[0].link_type == 1
    assert profile.role_menus[0].menus[0].link_type == 1
    assert profile.app_permissions.roles == []
    assert profile.org_permissions.roles == []

def test_menu_summary_normalizes_nested_null_children() -> None:
    menu = MenuSummary.model_validate(
        {
            "id": 1,
            "name": "一级菜单",
            "children": [{"id": 2, "name": "二级菜单", "children": None}],
        }
    )

    assert menu.children[0].children == []

def test_permission_models_normalize_null_lists() -> None:
    permission_set = PermissionSetSummary.model_validate(
        {"roles": None, "menus": None, "permissions": None}
    )
    role_menu = RoleMenuSummary.model_validate(
        {
            "role": {"id": 1, "name": "测试角色", "code": "tester"},
            "menus": None,
        }
    )

    assert permission_set.roles == []
    assert permission_set.menus == []
    assert permission_set.permissions == []
    assert role_menu.menus == []
