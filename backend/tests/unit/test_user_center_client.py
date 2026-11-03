import hashlib
import hmac
import json
from dataclasses import replace
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from config.auth import AuthSettings
from infra.user_center import UserCenterClient, UserCenterError


def test_role_user_directory_is_signed_and_accepts_active_members_across_orgs():
    def handle(request):
        assert request.url.path == "/uc/open-api/system/permission/role-user"
        assert request.headers["authorization"].startswith("Basic ")
        body = json.loads(request.content)
        assert body["roleCode"] == "bkg_developer"
        assert "token" not in body
        public = {key: body[key] for key in ("clientId", "nonce", "timestamp")}
        signed = "&".join(f"{key}={public[key]}" for key in sorted(public))
        assert (
            body["signature"]
            == hmac.new(b"top-secret", signed.encode(), hashlib.sha256).hexdigest()
        )
        return httpx.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "roleCode": "bkg_developer",
                    "users": [
                        {"userId": 213, "status": 0, "orgId": None},
                        {"userId": 232, "status": 1, "orgId": None},
                        {"userId": 184, "status": 0, "orgId": 3},
                        {"userId": 999, "status": False, "orgId": None},
                    ],
                },
            },
        )

    client = UserCenterClient(_settings(), sync_transport=httpx.MockTransport(handle))
    assert client.role_user_ids("bkg_developer") == frozenset({"213", "184"})


@pytest.mark.parametrize(
    "data",
    [
        None,
        {"roleCode": "other", "users": []},
        {"roleCode": "bkg_developer", "users": None},
        {"roleCode": "bkg_developer", "users": [{"userId": True, "status": 0}]},
    ],
)
def test_invalid_role_directory_fails_closed(data):
    client = UserCenterClient(
        _settings(),
        sync_transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"code": 0, "data": data})
        ),
    )
    with pytest.raises(UserCenterError):
        client.role_user_ids("bkg_developer")


def _settings() -> AuthSettings:
    return replace(
        AuthSettings.from_env(),
        enabled=True,
        client_id="techkg",
        client_secret="top-secret",
        redirect_uri="https://example.test/api/v1/auth/callback",
        sso_login_url="https://sso.test/uc/sso/login",
        user_center_base_url="https://sso.test/uc/admin-api/system/oauth2",
        user_center_open_api_base_url="https://sso.test/uc/open-api/system",
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
    assert "scope" not in query


def test_build_login_url_includes_configured_scope() -> None:
    client = UserCenterClient(replace(_settings(), scope="profile read"))

    query = parse_qs(urlparse(client.build_login_url("csrf-state")).query)

    assert query["scope"] == ["profile read"]


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
    token = await client.exchange_code("authorization-code", state="csrf-state")

    form = parse_qs(captured["body"])
    assert captured["authorization"].startswith("Basic ")
    assert form == {
        "grant_type": ["authorization_code"],
        "code": ["authorization-code"],
        "redirect_uri": ["https://example.test/api/v1/auth/callback"],
        "state": ["csrf-state"],
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


async def test_portal_identity_uses_v24_signed_json_and_basic_auth() -> None:
    nonces = []

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert str(request.url) == "https://sso.test/uc/open-api/system/user/get-by-token"
        assert request.headers["authorization"] == "Basic dGVjaGtnOnRvcC1zZWNyZXQ="
        body = json.loads(request.content)
        assert body["token"] == "access-token"
        assert isinstance(body["timestamp"], int)
        assert len(body["nonce"]) == 32
        nonces.append(body["nonce"])
        # 文档要求：只按 ASCII 字典序拼接三项公共参数，不签 token，不做 URL 编码。
        payload = f"clientId=techkg&nonce={body['nonce']}&timestamp={body['timestamp']}"
        expected = hmac.new(b"top-secret", payload.encode(), hashlib.sha256).hexdigest()
        assert body["signature"] == expected
        assert "client_secret" not in body
        return httpx.Response(
            200, json={"code": 0, "data": {"id": 139, "status": 0, "gkxUser": {"role": 1}}}
        )

    client = UserCenterClient(_settings(), transport=httpx.MockTransport(handler))
    assert (await client.get_user_by_token("access-token"))["gkxUser"]["role"] == 1
    await client.get_user_by_token("access-token")
    assert len(set(nonces)) == 2
