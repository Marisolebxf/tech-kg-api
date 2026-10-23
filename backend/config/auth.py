"""统一用户中心与本系统会话配置。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlsplit

from dotenv import load_dotenv

load_dotenv()


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    return int(value) if value not in (None, "") else default


def _valid_web_url(value: str, *, allow_path: bool = False) -> bool:
    """部署配置中的浏览器地址，禁止协议相对地址、凭据和控制字符。"""
    if (
        not value
        or "\\" in value
        or any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        return False
    if allow_path and value.startswith("/") and not value.startswith("//"):
        return True
    try:
        parts = urlsplit(value)
        _ = parts.port
        return (
            parts.scheme in {"http", "https"}
            and bool(parts.hostname)
            and parts.username is None
            and parts.password is None
        )
    except ValueError:
        return False


def _public_base_url() -> str:
    value = os.getenv("PUBLIC_BASE_URL", "")
    if not value:
        return ""
    if not _valid_web_url(value):
        raise ValueError("PUBLIC_BASE_URL 必须是完整的 HTTP(S) 网站入口")
    parts = urlsplit(value)
    if parts.path not in {"", "/"} or parts.query or parts.fragment:
        raise ValueError("PUBLIC_BASE_URL 只填写网站入口，应用路径请使用 APP_BASE")
    return value.rstrip("/")


def _app_base() -> str:
    value = os.getenv("APP_BASE", "").strip().rstrip("/")
    if not value:
        return ""
    if (
        not _valid_web_url(value, allow_path=True)
        or not value.startswith("/")
        or "?" in value
        or "#" in value
        or any(segment in {".", ".."} for segment in value.split("/"))
    ):
        raise ValueError("APP_BASE 必须是站内应用路径，例如 /bkg_zp")
    return value


@dataclass(frozen=True, slots=True)
class AuthSettings:
    """鉴权配置，密钥只允许通过后端环境变量注入。"""

    enabled: bool
    allow_insecure_dev_context: bool
    user_center_base_url: str
    sso_login_url: str
    user_center_portal_url: str
    client_id: str
    client_secret: str
    redirect_uri: str
    frontend_url: str
    scope: str
    session_cookie_name: str
    portal_token_cookie_name: str
    portal_cookie_login_enabled: bool
    session_ttl_seconds: int
    state_ttl_seconds: int
    bearer_cache_ttl_seconds: int
    audit_ttl_seconds: int
    audit_max_items: int
    cookie_secure: bool
    cookie_samesite: str
    cookie_path: str
    redis_url: str
    session_backend: str
    dev_user_id: str
    dev_username: str
    dev_nickname: str
    initial_admin_user_ids: tuple[str, ...]
    bootstrap_first_admin: bool
    dev_first_user_admin: bool
    user_center_open_api_base_url: str = ""
    portal_admin_enabled: bool = True
    portal_admin_role_codes: tuple[str, ...] = ()
    portal_role_cache_ttl_seconds: int = 60
    business_only_user_ids: tuple[str, ...] = ()
    login_mode: str = "oauth"
    portal_login_url: str = ""

    @classmethod
    def from_env(cls) -> AuthSettings:
        app_env = os.getenv("APP_ENV", "prod").strip().lower()
        login_mode = os.getenv("AUTH_LOGIN_MODE", "oauth").strip().lower()
        if login_mode not in {"oauth", "portal"}:
            raise ValueError("AUTH_LOGIN_MODE 仅支持 oauth 或 portal")
        portal_login_url = os.getenv("USER_CENTER_PORTAL_LOGIN_URL", "")
        if portal_login_url and not _valid_web_url(portal_login_url, allow_path=True):
            raise ValueError("USER_CENTER_PORTAL_LOGIN_URL 必须是站内路径或完整 HTTP(S) 地址")
        public_base = _public_base_url()
        app_base = _app_base() if public_base else ""
        user_center_web_base = f"{public_base or 'https://edu.itic-sci.com'}/uc"
        frontend_url = os.getenv(
            "AUTH_FRONTEND_URL",
            f"{public_base}{app_base}" if public_base else "http://127.0.0.1:5173",
        ).rstrip("/")
        redis_url = os.getenv("REDIS_URL")
        if not redis_url:
            host = os.getenv("REDIS_HOST", "127.0.0.1")
            port = os.getenv("REDIS_PORT", "6379")
            database = os.getenv("REDIS_DATABASE", "0")
            password = os.getenv("REDIS_PASSWORD", "")
            credentials = f":{password}@" if password else ""
            redis_url = f"redis://{credentials}{host}:{port}/{database}"

        base_url = os.getenv(
            "USER_CENTER_OAUTH_BASE_URL",
            f"{user_center_web_base}/admin-api/system/oauth2",
        ).rstrip("/")
        sso_login_url = os.getenv(
            "USER_CENTER_SSO_LOGIN_URL",
            f"{user_center_web_base}/sso/login",
        )
        cookie_samesite = os.getenv("AUTH_COOKIE_SAMESITE", "lax").lower()
        if cookie_samesite not in {"lax", "strict", "none"}:
            cookie_samesite = "lax"

        return cls(
            login_mode=login_mode,
            portal_login_url=portal_login_url,
            business_only_user_ids=tuple(
                value.strip()
                for value in os.getenv("PLATFORM_BUSINESS_ONLY_USER_IDS", "").split(",")
                if value.strip()
            ),
            user_center_open_api_base_url=(
                os.getenv("USER_CENTER_OPEN_API_BASE_URL")
                or f"{base_url.split('/admin-api/', 1)[0]}/open-api/system"
            ).rstrip("/"),
            portal_admin_enabled=_env_bool("USER_CENTER_PORTAL_ADMIN_ENABLED", True),
            portal_admin_role_codes=tuple(
                sorted(
                    {
                        value.strip()
                        for value in os.getenv("USER_CENTER_PORTAL_ADMIN_ROLE_CODES", "").split(",")
                        if value.strip()
                    }
                )
            ),
            portal_role_cache_ttl_seconds=max(
                1, _env_int("USER_CENTER_PORTAL_ROLE_CACHE_TTL_SECONDS", 60)
            ),
            enabled=_env_bool("AUTH_ENABLED", True),
            # 禁用真实鉴权时默认拒绝访问。仅允许本地/测试环境通过第二个显式开关
            # 启用模拟管理员，避免生产环境误配 AUTH_ENABLED=false 后匿名提权。
            allow_insecure_dev_context=(
                app_env in {"dev", "development", "local", "test"}
                and _env_bool("AUTH_ALLOW_INSECURE_DEV_CONTEXT", False)
            ),
            user_center_base_url=base_url,
            sso_login_url=sso_login_url,
            user_center_portal_url=os.getenv(
                "USER_CENTER_ACCOUNT_URL",
                f"{user_center_web_base}/admin/login?redirect=/index",
            ),
            client_id=os.getenv("USER_CENTER_CLIENT_ID", ""),
            client_secret=os.getenv("USER_CENTER_CLIENT_SECRET", ""),
            redirect_uri=os.getenv(
                "USER_CENTER_REDIRECT_URI",
                f"{frontend_url}/api/v1/auth/callback"
                if public_base
                else "http://127.0.0.1:8000/api/v1/auth/callback",
            ),
            frontend_url=frontend_url,
            # 新建应用默认可能没有任何可申请的 scope；只有用户中心明确为
            # 应用分配了授权范围时才通过环境变量声明，避免登录页报“授权范围过大”。
            scope=os.getenv("USER_CENTER_SCOPE", "").strip(),
            session_cookie_name=os.getenv("AUTH_SESSION_COOKIE", "techkg_session"),
            portal_token_cookie_name=os.getenv(
                "USER_CENTER_PORTAL_TOKEN_COOKIE",
                "portal_access_token",
            ),
            portal_cookie_login_enabled=_env_bool(
                "USER_CENTER_PORTAL_COOKIE_LOGIN_ENABLED",
                False,
            ),
            # 本地会话采用 30 分钟空闲超时；每次已认证请求会续期，
            # 连续无操作超过该时长后必须重新登录。
            session_ttl_seconds=_env_int("AUTH_SESSION_TTL_SECONDS", 30 * 60),
            state_ttl_seconds=_env_int("AUTH_STATE_TTL_SECONDS", 300),
            bearer_cache_ttl_seconds=_env_int("AUTH_BEARER_CACHE_TTL_SECONDS", 60),
            audit_ttl_seconds=_env_int("AUTH_AUDIT_TTL_SECONDS", 90 * 24 * 3600),
            audit_max_items=_env_int("AUTH_AUDIT_MAX_ITEMS", 200),
            cookie_secure=_env_bool("AUTH_COOKIE_SECURE", urlsplit(public_base).scheme == "https"),
            cookie_samesite=cookie_samesite,
            cookie_path=os.getenv("AUTH_COOKIE_PATH", app_base or "/"),
            redis_url=redis_url,
            session_backend=os.getenv("AUTH_SESSION_BACKEND", "redis").lower(),
            dev_user_id=os.getenv("AUTH_DEV_USER_ID", "local-dev"),
            dev_username=os.getenv("AUTH_DEV_USERNAME", "local-dev"),
            dev_nickname=os.getenv("AUTH_DEV_NICKNAME", "本地开发用户"),
            initial_admin_user_ids=tuple(
                item.strip()
                for item in os.getenv("PLATFORM_INITIAL_ADMIN_USER_IDS", "").split(",")
                if item.strip()
            ),
            bootstrap_first_admin=_env_bool(
                "PLATFORM_BOOTSTRAP_FIRST_ADMIN",
                _env_bool("PLATFORM_BOOTSTRAP_EXISTING_USERS_ADMIN", False),
            ),
            dev_first_user_admin=(
                app_env in {"dev", "development", "local", "test"}
                and _env_bool("PLATFORM_DEV_FIRST_USER_ADMIN", False)
            ),
        )

    def require_oauth_credentials(self) -> None:
        if not self.client_id or not self.client_secret:
            raise ValueError(
                "统一用户中心客户端未配置，请设置 USER_CENTER_CLIENT_ID 和 "
                "USER_CENTER_CLIENT_SECRET"
            )

    def require_portal_login_url(self) -> str:
        if not self.portal_cookie_login_enabled:
            raise ValueError("门户登录模式需要启用 USER_CENTER_PORTAL_COOKIE_LOGIN_ENABLED")
        if not _valid_web_url(self.portal_login_url, allow_path=True):
            raise ValueError("请配置有效的 USER_CENTER_PORTAL_LOGIN_URL 门户登录入口")
        return self.portal_login_url
