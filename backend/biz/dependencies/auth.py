"""浏览器 Session Cookie 与第三方 Bearer Token 统一鉴权。"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from application.auth import AuthApplication, get_auth_application
from service.auth import AuthContext, AuthenticationError

bearer_scheme = HTTPBearer(auto_error=False)

AuthApplicationDependency = Annotated[AuthApplication, Depends(get_auth_application)]
BearerDependency = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)]


async def require_authenticated_user(
    request: Request,
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

        session_id = request.cookies.get(application.settings.session_cookie_name)
        if not session_id:
            raise AuthenticationError("尚未登录")
        return await application.get_session(session_id)
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


CurrentUser = Annotated[AuthContext, Depends(require_authenticated_user)]


def require_permission(permission: str):
    async def dependency(
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
