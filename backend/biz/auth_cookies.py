"""本系统会话 Cookie；不修改统一门户共享的登录 Cookie。"""

import hashlib
import hmac

from fastapi import Request, Response
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from config.auth import AuthSettings


class AuthSessionMiddleware:
    """在最终响应续 Cookie，兼容业务接口直接返回 Response/流式响应。"""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_response(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                path = scope["path"]
                root_path = scope.get("root_path", "").rstrip("/")
                if root_path and path.startswith(f"{root_path}/"):
                    path = path[len(root_path) :]
                if path.startswith("/api/v1/auth/"):
                    headers["Cache-Control"] = "no-store"
                pending = scope.get("state", {}).get("auth_session_cookie")
                if pending is not None and message["status"] < 400:
                    settings, session_id = pending
                    cookie_response = Response()
                    set_session_cookie(cookie_response, settings, session_id)
                    headers["Cache-Control"] = "no-store"
                    headers.append("Set-Cookie", cookie_response.headers["set-cookie"])
            await send(message)

        await self.app(scope, receive, send_response)


def set_session_cookie(response: Response, settings: AuthSettings, session_id: str) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.set_cookie(
        settings.session_cookie_name,
        session_id,
        max_age=settings.session_ttl_seconds,
        path=settings.cookie_path,
        secure=settings.cookie_secure,
        httponly=True,
        samesite=settings.cookie_samesite,
    )


def _logout_cookie_name(settings: AuthSettings) -> str:
    return f"{settings.session_cookie_name}_portal_logout"


def portal_sso_blocked(request: Request, settings: AuthSettings, token: str | None = None) -> bool:
    if token is None:
        token = request.cookies.get(settings.portal_token_cookie_name, "")
    marker = request.cookies.get(_logout_cookie_name(settings), "")
    return bool(
        token and marker and hmac.compare_digest(marker, hashlib.sha256(token.encode()).hexdigest())
    )


def clear_portal_logout_cookie(response: Response, settings: AuthSettings) -> None:
    response.delete_cookie(
        _logout_cookie_name(settings),
        path=settings.cookie_path,
        secure=settings.cookie_secure,
        httponly=True,
        samesite=settings.cookie_samesite,
    )


def clear_browser_session(request: Request, response: Response, settings: AuthSettings) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.delete_cookie(
        settings.session_cookie_name,
        path=settings.cookie_path,
        secure=settings.cookie_secure,
        httponly=True,
        samesite=settings.cookie_samesite,
    )
    token = request.cookies.get(settings.portal_token_cookie_name, "")
    if token:
        # 只阻止同一门户令牌静默登录；门户重新登录换发令牌后仍可正常进入。
        response.set_cookie(
            _logout_cookie_name(settings),
            hashlib.sha256(token.encode()).hexdigest(),
            path=settings.cookie_path,
            secure=settings.cookie_secure,
            httponly=True,
            samesite=settings.cookie_samesite,
        )
    else:
        clear_portal_logout_cookie(response, settings)
