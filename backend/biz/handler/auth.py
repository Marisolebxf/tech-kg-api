"""统一用户中心登录、会话、权限和退出 API。"""

from __future__ import annotations

import hmac
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse

from application.auth import AuthApplication
from biz.dependencies.auth import AuthApplicationDependency, CurrentUser
from biz.schemas.auth import (
    AuthProfileResponse,
    LoginUrlData,
    LoginUrlResponse,
    LogoutData,
    LogoutResponse,
    PermissionInfoResponse,
)
from service.auth import AuthenticationError

router = APIRouter(prefix="/auth", tags=["auth"])


def _raise_auth_error(exc: AuthenticationError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


def _login_error_url(application: AuthApplication, message: str) -> str:
    query = urlencode({"error": message})
    return f"{application.settings.frontend_url.rstrip('/')}/#/login?{query}"


def _state_cookie_name(application: AuthApplication) -> str:
    return f"{application.settings.session_cookie_name}_oauth_state"


def _clear_state_cookie(response: Response, application: AuthApplication) -> None:
    response.delete_cookie(
        _state_cookie_name(application),
        path=application.settings.cookie_path,
        secure=application.settings.cookie_secure,
        httponly=True,
        samesite=application.settings.cookie_samesite,
    )


@router.get("/login-url", response_model=LoginUrlResponse)
async def get_login_url(
    response: Response,
    application: AuthApplicationDependency,
    next_path: str = Query("/overview", alias="next"),
) -> LoginUrlResponse:
    if not application.settings.enabled:
        return LoginUrlResponse(
            data=LoginUrlData(
                url=application.frontend_redirect(next_path),
                expires_in=application.settings.state_ttl_seconds,
            )
        )
    try:
        url, expires_in, state = await application.create_login_url(next_path)
    except AuthenticationError as exc:
        _raise_auth_error(exc)
    response.set_cookie(
        key=_state_cookie_name(application),
        value=state,
        max_age=expires_in,
        secure=application.settings.cookie_secure,
        httponly=True,
        samesite=application.settings.cookie_samesite,
        path=application.settings.cookie_path,
    )
    return LoginUrlResponse(data=LoginUrlData(url=url, expires_in=expires_in))


@router.get("/callback", include_in_schema=False)
async def oauth_callback(
    request: Request,
    application: AuthApplicationDependency,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
) -> Response:
    if error:
        response = RedirectResponse(
            _login_error_url(application, error_description or error),
            status_code=302,
        )
        _clear_state_cookie(response, application)
        return response
    if not code or not state:
        response = RedirectResponse(
            _login_error_url(application, "统一用户中心没有返回授权码或 state"),
            status_code=302,
        )
        _clear_state_cookie(response, application)
        return response
    state_cookie = request.cookies.get(_state_cookie_name(application))
    if not state_cookie or not hmac.compare_digest(state_cookie, state):
        response = RedirectResponse(
            _login_error_url(application, "登录请求与当前浏览器不匹配，请重新登录"),
            status_code=302,
        )
        _clear_state_cookie(response, application)
        return response
    try:
        context, next_path = await application.complete_login(code, state)
    except AuthenticationError as exc:
        response = RedirectResponse(_login_error_url(application, str(exc)), status_code=302)
        _clear_state_cookie(response, application)
        return response

    response = RedirectResponse(application.frontend_redirect(next_path), status_code=302)
    _clear_state_cookie(response, application)
    response.set_cookie(
        key=application.settings.session_cookie_name,
        value=context.session_id or "",
        max_age=application.settings.session_ttl_seconds,
        secure=application.settings.cookie_secure,
        httponly=True,
        samesite=application.settings.cookie_samesite,
        path=application.settings.cookie_path,
    )
    return response


@router.get("/me", response_model=AuthProfileResponse)
async def get_current_profile(
    context: CurrentUser,
    application: AuthApplicationDependency,
) -> AuthProfileResponse:
    try:
        return AuthProfileResponse(data=application.profile(context))
    except AuthenticationError as exc:
        _raise_auth_error(exc)


@router.get("/permissions", response_model=PermissionInfoResponse)
async def get_current_permissions(context: CurrentUser) -> PermissionInfoResponse:
    return PermissionInfoResponse(data=context.permission_info)


@router.post("/refresh", response_model=AuthProfileResponse)
async def refresh_session(
    context: CurrentUser,
    application: AuthApplicationDependency,
) -> AuthProfileResponse:
    try:
        refreshed = await application.refresh_session(context)
        return AuthProfileResponse(data=application.profile(refreshed))
    except AuthenticationError as exc:
        _raise_auth_error(exc)


@router.post("/logout", response_model=LogoutResponse)
async def logout(
    response: Response,
    context: CurrentUser,
    application: AuthApplicationDependency,
) -> LogoutResponse:
    remote_revoked = await application.logout(context)
    response.delete_cookie(
        application.settings.session_cookie_name,
        path=application.settings.cookie_path,
        secure=application.settings.cookie_secure,
        httponly=True,
        samesite=application.settings.cookie_samesite,
    )
    return LogoutResponse(data=LogoutData(remote_revoked=remote_revoked))
