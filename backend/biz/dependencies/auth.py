"""浏览器 Session Cookie 与第三方 Bearer Token 统一鉴权。"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from application.auth import AuthApplication, get_auth_application
from service.auth import AuthContext, AuthenticationError
from service.platform_access import PlatformActor

bearer_scheme = HTTPBearer(auto_error=False)

AuthApplicationDependency = Annotated[AuthApplication, Depends(get_auth_application)]
BearerDependency = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)]


async def require_authenticated_user(
    request: Request,
    response: Response,
    application: AuthApplicationDependency,
    bearer: BearerDependency,
) -> AuthContext:
    if not application.settings.enabled:
        return application.dev_context()
    try:
        if bearer is not None:
            if bearer.scheme.lower() != "bearer" or not bearer.credentials:
                raise AuthenticationError("Authorization 请求头格式不正确")
            return await application.resolve_bearer(bearer.credentials)

        session_error: AuthenticationError | None = None
        session_id = request.cookies.get(application.settings.session_cookie_name)
        if session_id:
            try:
                return await application.get_session(session_id)
            except AuthenticationError as exc:
                session_error = exc

        if application.settings.portal_cookie_login_enabled:
            access_token = request.cookies.get(application.settings.portal_token_cookie_name)
            if access_token:
                context = await application.create_session_from_access_token(access_token)
                await application.record_operation(
                    context,
                    action="复用门户登录态",
                    category="登录",
                    detail="通过统一用户中心门户 Cookie 创建本地会话",
                    ip_address=request.client.host if request.client else "",
                    user_agent=request.headers.get("user-agent", ""),
                )
                response.set_cookie(
                    key=application.settings.session_cookie_name,
                    value=context.session_id or "",
                    max_age=application.settings.session_ttl_seconds,
                    secure=application.settings.cookie_secure,
                    httponly=True,
                    samesite=application.settings.cookie_samesite,
                    path=application.settings.cookie_path,
                )
                return context
        if session_error is not None:
            raise session_error
        raise AuthenticationError("尚未登录")
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


CurrentUser = Annotated[AuthContext, Depends(require_authenticated_user)]


def require_platform_actor(
    context: CurrentUser,
    application: AuthApplicationDependency,
) -> PlatformActor:
    return application.platform_actor(context)


CurrentActor = Annotated[PlatformActor, Depends(require_platform_actor)]


def require_platform_admin(
    actor: CurrentActor,
) -> PlatformActor:
    if not actor.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="仅全局管理员可以执行该操作",
        )
    return actor


CurrentAdmin = Annotated[PlatformActor, Depends(require_platform_admin)]


def require_permission(permission: str):
    def dependency(
        context: CurrentUser,
        application: AuthApplicationDependency,
    ) -> AuthContext:
        granted = set(application.profile(context).permissions)
        if "*" not in granted and permission not in granted:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"缺少操作权限: {permission}",
            )
        return context

    return dependency
