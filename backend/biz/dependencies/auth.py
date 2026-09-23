"""浏览器 Session Cookie 与第三方 Bearer Token 统一鉴权。"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from application.auth import AuthApplication, get_auth_application
from biz.auth_cookies import portal_sso_blocked
from service.auth import AuthContext, AuthenticationError
from service.business_access import enforce_business_access
from service.platform_access import PlatformActor

bearer_scheme = HTTPBearer(auto_error=False)

AuthApplicationDependency = Annotated[AuthApplication, Depends(get_auth_application)]
BearerDependency = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)]


def _enforce_account_scope(request: Request, application: AuthApplication, context: AuthContext):
    if application.settings.business_only_user_ids:
        # 只需比对用户 id：直接读会话 userInfo，不走 profile() 的完整模型校验
        # （可选字段为 null 的账号会让 profile() 抛 ValidationError，且逐请求构建
        # AuthProfile 的开销也大——此前导致名单非空时全部受保护接口 500）
        raw_user = context.permission_info.get("userInfo") or {}
        user_id = str(raw_user.get("id", ""))
        if user_id and user_id in application.settings.business_only_user_ids:
            enforce_business_access(request)
    return context


async def require_authenticated_user(
    request: Request,
    response: Response,
    application: AuthApplicationDependency,
    bearer: BearerDependency,
) -> AuthContext:
    if not application.settings.enabled:
        if application.settings.allow_insecure_dev_context:
            return _enforce_account_scope(request, application, application.dev_context())
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="认证服务未启用，受保护接口已拒绝访问",
            headers={"Cache-Control": "no-store"},
        )
    try:
        if bearer is not None:
            if bearer.scheme.lower() != "bearer" or not bearer.credentials:
                raise AuthenticationError("Authorization 请求头格式不正确")
            context = await application.resolve_bearer(bearer.credentials)
            return _enforce_account_scope(request, application, context)

        session_error: AuthenticationError | None = None
        session_id = request.cookies.get(application.settings.session_cookie_name)
        if session_id:
            try:
                context = await application.get_session(session_id)
                if context.token_source in {"portal", "unknown"} and portal_sso_blocked(
                    request, application.settings, context.access_token
                ):
                    raise AuthenticationError("尚未登录")
                request.state.auth_session_cookie = (application.settings, session_id)
                return _enforce_account_scope(request, application, context)
            except AuthenticationError as exc:
                session_error = exc

        if application.settings.portal_cookie_login_enabled and not portal_sso_blocked(
            request, application.settings
        ):
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
                request.state.auth_session_cookie = (
                    application.settings,
                    context.session_id or "",
                )
                return _enforce_account_scope(request, application, context)
        if session_error is not None:
            raise session_error
        raise AuthenticationError("尚未登录")
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer", "Cache-Control": "no-store"},
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
    if not actor.is_admin or actor.business_only:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="仅全局管理员可以执行该操作",
        )
    return actor


CurrentAdmin = Annotated[PlatformActor, Depends(require_platform_admin)]


def require_platform_maintainer(actor: CurrentActor) -> PlatformActor:
    from service.business_access_control import rbac_enabled

    if not (actor.can_develop if rbac_enabled() else actor.is_admin):
        raise HTTPException(status_code=403, detail="仅开发维护或管理员可以执行该操作")
    return actor


CurrentMaintainer = Annotated[PlatformActor, Depends(require_platform_maintainer)]


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
