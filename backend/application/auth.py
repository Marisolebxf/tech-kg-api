"""统一用户中心登录应用层门面。"""

from __future__ import annotations

from biz.schemas.auth import AccountSecurityData, AuthProfile, OperationLogPage
from config.auth import AuthSettings
from infra.redis import AsyncJsonStore, get_json_store
from infra.user_center import UserCenterClient
from service.auth import AuthContext, AuthService


class AuthApplication:
    def __init__(
        self,
        settings: AuthSettings | None = None,
        store: AsyncJsonStore | None = None,
        user_center: UserCenterClient | None = None,
    ) -> None:
        self.settings = settings or AuthSettings.from_env()
        self.store = store or get_json_store(self.settings)
        self.user_center = user_center or UserCenterClient(self.settings)
        self.service = AuthService(self.settings, self.store, self.user_center)

    async def create_login_url(self, next_path: str) -> tuple[str, int, str]:
        return await self.service.create_login_url(next_path)

    async def complete_login(self, code: str, state: str) -> tuple[AuthContext, str]:
        return await self.service.complete_login(code, state)

    async def get_session(self, session_id: str) -> AuthContext:
        return await self.service.get_session(session_id)

    async def resolve_bearer(self, access_token: str) -> AuthContext:
        return await self.service.resolve_bearer(access_token)

    async def create_session_from_access_token(self, access_token: str) -> AuthContext:
        return await self.service.create_session_from_access_token(access_token)

    async def refresh_session(self, context: AuthContext) -> AuthContext:
        if not context.session_id:
            return context
        return await self.service.refresh_session(context.session_id, context=context)

    async def logout(self, context: AuthContext) -> bool:
        return await self.service.logout(context)

    async def record_operation(self, context: AuthContext, **kwargs: str) -> None:
        await self.service.record_operation(context, **kwargs)

    async def operation_logs(self, context: AuthContext, **kwargs) -> OperationLogPage:
        return await self.service.operation_logs(context, **kwargs)

    def account_security(self, context: AuthContext) -> AccountSecurityData:
        return self.service.account_security(context)

    def profile(self, context: AuthContext) -> AuthProfile:
        return self.service.profile(context)

    def dev_context(self) -> AuthContext:
        return self.service.dev_context()

    def frontend_redirect(self, next_path: str) -> str:
        safe_path = (
            next_path
            if next_path.startswith("/") and not next_path.startswith("//")
            else "/overview"
        )
        return f"{self.settings.frontend_url.rstrip('/')}/#{safe_path}"


_application: AuthApplication | None = None


def get_auth_application() -> AuthApplication:
    global _application
    if _application is None:
        _application = AuthApplication()
    return _application


def reset_auth_application() -> None:
    global _application
    _application = None
