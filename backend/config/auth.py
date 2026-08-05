"""统一用户中心与本系统会话配置。"""

from __future__ import annotations

import os
from dataclasses import dataclass

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


@dataclass(frozen=True, slots=True)
class AuthSettings:
    """鉴权配置，密钥只允许通过后端环境变量注入。"""

    enabled: bool
    user_center_base_url: str
    sso_login_url: str
    user_center_portal_url: str
    client_id: str
    client_secret: str
    redirect_uri: str
    frontend_url: str
    scope: str
    session_cookie_name: str
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

    @classmethod
    def from_env(cls) -> AuthSettings:
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
            "https://edu.itic-sci.com/uc/admin-api/system/oauth2",
        ).rstrip("/")
        sso_login_url = os.getenv(
            "USER_CENTER_SSO_LOGIN_URL",
            "https://edu.itic-sci.com/uc/sso/login",
        )
        cookie_samesite = os.getenv("AUTH_COOKIE_SAMESITE", "lax").lower()
        if cookie_samesite not in {"lax", "strict", "none"}:
            cookie_samesite = "lax"

        return cls(
            enabled=_env_bool("AUTH_ENABLED", True),
            user_center_base_url=base_url,
            sso_login_url=sso_login_url,
            user_center_portal_url=os.getenv(
                "USER_CENTER_ACCOUNT_URL",
                "https://edu.itic-sci.com/uc/admin/login?redirect=/index",
            ),
            client_id=os.getenv("USER_CENTER_CLIENT_ID", ""),
            client_secret=os.getenv("USER_CENTER_CLIENT_SECRET", ""),
            redirect_uri=os.getenv(
                "USER_CENTER_REDIRECT_URI",
                "http://127.0.0.1:8000/api/v1/auth/callback",
            ),
            frontend_url=os.getenv("AUTH_FRONTEND_URL", "http://127.0.0.1:5173"),
            scope=os.getenv("USER_CENTER_SCOPE", "user_info"),
            session_cookie_name=os.getenv("AUTH_SESSION_COOKIE", "techkg_session"),
            session_ttl_seconds=_env_int("AUTH_SESSION_TTL_SECONDS", 7 * 24 * 3600),
            state_ttl_seconds=_env_int("AUTH_STATE_TTL_SECONDS", 300),
            bearer_cache_ttl_seconds=_env_int("AUTH_BEARER_CACHE_TTL_SECONDS", 60),
            audit_ttl_seconds=_env_int("AUTH_AUDIT_TTL_SECONDS", 90 * 24 * 3600),
            audit_max_items=_env_int("AUTH_AUDIT_MAX_ITEMS", 200),
            cookie_secure=_env_bool("AUTH_COOKIE_SECURE", False),
            cookie_samesite=cookie_samesite,
            cookie_path=os.getenv("AUTH_COOKIE_PATH", "/"),
            redis_url=redis_url,
            session_backend=os.getenv("AUTH_SESSION_BACKEND", "redis").lower(),
            dev_user_id=os.getenv("AUTH_DEV_USER_ID", "local-dev"),
            dev_username=os.getenv("AUTH_DEV_USERNAME", "local-dev"),
            dev_nickname=os.getenv("AUTH_DEV_NICKNAME", "本地开发用户"),
        )

    def require_oauth_credentials(self) -> None:
        if not self.client_id or not self.client_secret:
            raise ValueError(
                "统一用户中心客户端未配置，请设置 USER_CENTER_CLIENT_ID 和 "
                "USER_CENTER_CLIENT_SECRET"
            )
