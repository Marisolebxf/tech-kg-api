from dataclasses import replace
from urllib.parse import parse_qs, urlparse

import httpx

from config.auth import AuthSettings
from infra.user_center import UserCenterClient, UserCenterError


def _settings() -> AuthSettings:
    return replace(
        AuthSettings.from_env(),
        enabled=True,
        client_id="techkg",
        client_secret="top-secret",
        redirect_uri="https://example.test/api/v1/auth/callback",
        sso_login_url="https://sso.test/uc/sso/login",
        user_center_base_url="https://sso.test/uc/admin-api/system/oauth2",
    )


def test_build_login_url_contains_authorization_code_parameters() -> None:
    client = UserCenterClient(_settings())

    parsed = urlparse(client.build_login_url("csrf-state"))
    query = parse_qs(parsed.query)

    assert parsed.path == "/uc/sso/login"
    assert query["response_type"] == ["code"]
    assert query["client_id"] == ["techkg"]
    assert query["redirect_uri"] == ["https://example.test/api/v1/auth/callback"]
    assert query["state"] == ["csrf-state"]


async def test_exchange_code_uses_basic_auth_and_form_body() -> None:
    captured: dict[str, str] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers["authorization"]
        captured["body"] = request.content.decode()
        return httpx.Response(
            200,
            json={
                "code": 0,
                "msg": "",
                "data": {
                    "access_token": "access-1",
                    "refresh_token": "refresh-1",
                    "expires_in": 3600,
                },
            },
        )

    client = UserCenterClient(_settings(), transport=httpx.MockTransport(handler))
    token = await client.exchange_code("authorization-code")

    form = parse_qs(captured["body"])
    assert captured["authorization"].startswith("Basic ")
    assert form == {
        "grant_type": ["authorization_code"],
        "code": ["authorization-code"],
        "redirect_uri": ["https://example.test/api/v1/auth/callback"],
    }
    assert token["access_token"] == "access-1"


async def test_user_center_business_error_is_not_treated_as_success() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"code": 401, "msg": "token 已过期", "data": None})

    client = UserCenterClient(_settings(), transport=httpx.MockTransport(handler))

    try:
        await client.check_token("expired")
    except UserCenterError as exc:
        assert exc.status_code == 401
        assert "过期" in str(exc)
    else:
        raise AssertionError("无效 token 必须抛出 UserCenterError")


async def test_permission_request_enables_v21_role_menu_mapping() -> None:
    captured: dict[str, str] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["query"] = request.url.query.decode()
        return httpx.Response(200, json={"code": 0, "msg": "", "data": {}})

    client = UserCenterClient(_settings(), transport=httpx.MockTransport(handler))
    await client.get_permission_info("access-1")

    query = parse_qs(captured["query"])
    assert query["token"] == ["access-1"]
    assert query["include_role_menu"] == ["true"]
