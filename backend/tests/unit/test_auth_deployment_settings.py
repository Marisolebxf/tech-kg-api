"""公共入口与门户登录模式配置；不连接外部服务。"""

import pytest

from config.auth import AuthSettings


@pytest.fixture(autouse=True)
def isolated_auth_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "PUBLIC_BASE_URL",
        "APP_BASE",
        "AUTH_LOGIN_MODE",
        "USER_CENTER_PORTAL_LOGIN_URL",
        "USER_CENTER_OAUTH_BASE_URL",
        "USER_CENTER_OPEN_API_BASE_URL",
        "USER_CENTER_SSO_LOGIN_URL",
        "USER_CENTER_ACCOUNT_URL",
        "USER_CENTER_REDIRECT_URI",
        "AUTH_FRONTEND_URL",
        "AUTH_COOKIE_PATH",
        "AUTH_COOKIE_SECURE",
    ):
        monkeypatch.delenv(name, raising=False)


def test_unconfigured_environment_preserves_oauth_defaults() -> None:
    settings = AuthSettings.from_env()
    assert settings.login_mode == "oauth"
    assert settings.portal_login_url == ""
    assert settings.frontend_url == "http://127.0.0.1:5173"
    assert settings.redirect_uri == "http://127.0.0.1:8000/api/v1/auth/callback"
    assert settings.user_center_base_url == "https://edu.itic-sci.com/uc/admin-api/system/oauth2"
    assert settings.cookie_path == "/"
    assert settings.cookie_secure is False


@pytest.mark.parametrize(
    ("origin", "secure"),
    [
        ("http://183.62.232.63", False),
        ("https://portal.example.test", True),
        ("HTTPS://portal.example.test", True),
    ],
)
def test_public_origin_derives_application_and_user_center_addresses(
    monkeypatch: pytest.MonkeyPatch, origin: str, secure: bool
) -> None:
    monkeypatch.setenv("PUBLIC_BASE_URL", origin)
    monkeypatch.setenv("APP_BASE", "/bkg_zp/")
    settings = AuthSettings.from_env()
    assert settings.frontend_url.rstrip("/") == f"{origin}/bkg_zp"
    assert settings.redirect_uri == f"{origin}/bkg_zp/api/v1/auth/callback"
    assert settings.user_center_base_url == f"{origin}/uc/admin-api/system/oauth2"
    assert settings.user_center_open_api_base_url == f"{origin}/uc/open-api/system"
    assert settings.sso_login_url == f"{origin}/uc/sso/login"
    assert settings.user_center_portal_url == f"{origin}/uc/admin/login?redirect=/index"
    assert settings.cookie_path.rstrip("/") == "/bkg_zp"
    assert settings.cookie_secure is secure


def test_root_application_does_not_duplicate_url_slashes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://portal.example.test/")
    monkeypatch.setenv("APP_BASE", "/")
    settings = AuthSettings.from_env()
    assert settings.frontend_url.rstrip("/") == "https://portal.example.test"
    assert settings.redirect_uri == "https://portal.example.test/api/v1/auth/callback"
    assert settings.cookie_path == "/"


def test_explicit_deployment_values_override_public_origin_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = {
        "PUBLIC_BASE_URL": "https://portal.example.test",
        "APP_BASE": "/bkg_zp/",
        "AUTH_FRONTEND_URL": "/custom-app",
        "USER_CENTER_REDIRECT_URI": "https://callback.example.test/custom",
        "USER_CENTER_OAUTH_BASE_URL": "http://uc.internal/custom/admin-api/system/oauth2",
        "USER_CENTER_SSO_LOGIN_URL": "https://login.example.test/login",
        "USER_CENTER_ACCOUNT_URL": "/account/",
        "AUTH_COOKIE_PATH": "/custom-app",
        "AUTH_COOKIE_SECURE": "false",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    settings = AuthSettings.from_env()
    assert settings.frontend_url == values["AUTH_FRONTEND_URL"]
    assert settings.redirect_uri == values["USER_CENTER_REDIRECT_URI"]
    assert settings.user_center_base_url == values["USER_CENTER_OAUTH_BASE_URL"]
    assert settings.user_center_open_api_base_url == "http://uc.internal/custom/open-api/system"
    assert settings.sso_login_url == values["USER_CENTER_SSO_LOGIN_URL"]
    assert settings.user_center_portal_url == "/account/"
    assert settings.cookie_path == "/custom-app"
    assert settings.cookie_secure is False

    # Compose 将未填写的可选地址传为空字符串，仍应跟随真实的 UC API 入口。
    monkeypatch.setenv("USER_CENTER_OPEN_API_BASE_URL", "")
    assert (
        AuthSettings.from_env().user_center_open_api_base_url
        == "http://uc.internal/custom/open-api/system"
    )

    monkeypatch.setenv("USER_CENTER_OPEN_API_BASE_URL", "https://open.example.test/custom/")
    assert (
        AuthSettings.from_env().user_center_open_api_base_url == "https://open.example.test/custom"
    )


@pytest.mark.parametrize(
    "origin",
    [
        "//portal.example.test",
        "ftp://portal.example.test",
        "https://user:password@portal.example.test",
        "https://portal.example.test/subsystem",
        "https://portal.example.test?target=other",
        "https://portal.example.test#fragment",
        "https://portal.example.test\\other",
        "https://portal.example.test/\n",
        "https://portal.example.test /",
    ],
)
def test_public_base_requires_an_http_origin(monkeypatch: pytest.MonkeyPatch, origin: str) -> None:
    monkeypatch.setenv("PUBLIC_BASE_URL", origin)
    with pytest.raises(ValueError):
        AuthSettings.from_env()


@pytest.mark.parametrize(
    "entry",
    ["/portal/", "/portal/sub_base?pathCode=overview", "https://portal.example.test/portal/"],
)
def test_portal_login_entry_is_preserved_without_guessing_parameters(
    monkeypatch: pytest.MonkeyPatch, entry: str
) -> None:
    monkeypatch.setenv("AUTH_LOGIN_MODE", "portal")
    monkeypatch.setenv("USER_CENTER_PORTAL_LOGIN_URL", entry)
    monkeypatch.setenv("USER_CENTER_PORTAL_COOKIE_LOGIN_ENABLED", "true")
    settings = AuthSettings.from_env()
    assert settings.login_mode == "portal"
    assert settings.portal_login_url == entry


def test_unknown_login_mode_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTH_LOGIN_MODE", "automatic")
    with pytest.raises(ValueError):
        AuthSettings.from_env()


@pytest.mark.parametrize(
    "entry",
    [
        "//other.example.test/portal/",
        "/\\other.example.test/portal/",
        "javascript:alert(1)",
        "ftp://portal.example.test/",
        "https://user:password@portal.example.test/",
        "portal/",
        "/portal/\n",
        "/portal/has space",
    ],
)
def test_portal_entry_rejects_ambiguous_or_non_web_urls(
    monkeypatch: pytest.MonkeyPatch, entry: str
) -> None:
    monkeypatch.setenv("AUTH_LOGIN_MODE", "portal")
    monkeypatch.setenv("USER_CENTER_PORTAL_LOGIN_URL", entry)
    with pytest.raises(ValueError):
        AuthSettings.from_env()
