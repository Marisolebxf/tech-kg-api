"""OAuth2 登录、本地会话和 API Bearer 鉴权业务逻辑。"""

from __future__ import annotations

import hashlib
import secrets
import time
from dataclasses import dataclass
from typing import Any

from biz.schemas.auth import AuthProfile, RoleSummary, UserProfile
from config.auth import AuthSettings
from infra.redis import AsyncJsonStore
from infra.user_center import UserCenterClient, UserCenterError


class AuthenticationError(RuntimeError):
    def __init__(self, message: str, *, status_code: int = 401) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(slots=True)
class AuthContext:
    access_token: str
    permission_info: dict[str, Any]
    expires_at: int | None
    session_id: str | None = None
    refresh_token: str = ""

    def to_record(self) -> dict[str, Any]:
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expires_at": self.expires_at,
            "permission_info": self.permission_info,
        }

    @classmethod
    def from_record(cls, record: dict[str, Any], *, session_id: str) -> AuthContext:
        return cls(
            access_token=str(record.get("access_token", "")),
            refresh_token=str(record.get("refresh_token", "")),
            expires_at=record.get("expires_at"),
            permission_info=dict(record.get("permission_info") or {}),
            session_id=session_id,
        )


class AuthService:
    STATE_KEY_PREFIX = "techkg:auth:state:"
    SESSION_KEY_PREFIX = "techkg:auth:session:"
    BEARER_KEY_PREFIX = "techkg:auth:bearer:"

    def __init__(
        self,
        settings: AuthSettings,
        store: AsyncJsonStore,
        user_center: UserCenterClient,
    ) -> None:
        self.settings = settings
        self.store = store
        self.user_center = user_center

    async def create_login_url(self, next_path: str = "/overview") -> tuple[str, int, str]:
        if not next_path.startswith("/") or next_path.startswith("//"):
            next_path = "/overview"
        state = secrets.token_urlsafe(32)
        try:
            url = self.user_center.build_login_url(state)
        except ValueError as exc:
            raise AuthenticationError(str(exc), status_code=503) from exc
        await self.store.set_json(
            f"{self.STATE_KEY_PREFIX}{state}",
            {"next": next_path},
            self.settings.state_ttl_seconds,
        )
        return url, self.settings.state_ttl_seconds, state

    async def complete_login(self, code: str, state: str) -> tuple[AuthContext, str]:
        state_data = await self.store.pop_json(f"{self.STATE_KEY_PREFIX}{state}")
        if state_data is None:
            raise AuthenticationError("登录状态已过期或无效，请重新登录", status_code=400)
        try:
            token = await self.user_center.exchange_code(code)
            context = await self._context_from_token(token)
        except UserCenterError as exc:
            raise AuthenticationError(str(exc), status_code=exc.status_code) from exc

        session_id = secrets.token_urlsafe(32)
        context.session_id = session_id
        await self._save_session(context)
        return context, str(state_data.get("next") or "/overview")

    async def get_session(self, session_id: str) -> AuthContext:
        record = await self.store.get_json(f"{self.SESSION_KEY_PREFIX}{session_id}")
        if record is None:
            raise AuthenticationError("登录已过期，请重新登录")
        context = AuthContext.from_record(record, session_id=session_id)
        if context.expires_at is not None and context.expires_at <= int(time.time()) + 30:
            context = await self.refresh_session(session_id, context=context)
        return context

    async def refresh_session(
        self,
        session_id: str,
        *,
        context: AuthContext | None = None,
    ) -> AuthContext:
        if context is None:
            record = await self.store.get_json(f"{self.SESSION_KEY_PREFIX}{session_id}")
            if record is None:
                raise AuthenticationError("登录已过期，请重新登录")
            current = AuthContext.from_record(record, session_id=session_id)
        else:
            current = context
        if not current.refresh_token:
            await self.delete_session(session_id)
            raise AuthenticationError("刷新令牌不存在，请重新登录")
        try:
            token = await self.user_center.refresh(current.refresh_token)
            if not token.get("refresh_token"):
                token["refresh_token"] = current.refresh_token
            refreshed = await self._context_from_token(token)
        except UserCenterError as exc:
            await self.delete_session(session_id)
            raise AuthenticationError(str(exc), status_code=exc.status_code) from exc
        refreshed.session_id = session_id
        await self._save_session(refreshed)
        return refreshed

    async def resolve_bearer(self, access_token: str) -> AuthContext:
        digest = hashlib.sha256(access_token.encode("utf-8")).hexdigest()
        key = f"{self.BEARER_KEY_PREFIX}{digest}"
        cached = await self.store.get_json(key)
        if cached is not None:
            return AuthContext.from_record(cached, session_id="")

        try:
            checked = await self.user_center.check_token(access_token)
            permission_info = await self.user_center.get_permission_info(access_token)
        except UserCenterError as exc:
            raise AuthenticationError(str(exc), status_code=exc.status_code) from exc
        expires_at = int(checked.get("exp")) if checked.get("exp") else None
        if expires_at is not None and expires_at <= int(time.time()):
            raise AuthenticationError("访问令牌已过期")
        context = AuthContext(
            access_token=access_token,
            permission_info=dict(permission_info or {}),
            expires_at=expires_at,
        )
        ttl = self.settings.bearer_cache_ttl_seconds
        if expires_at is not None:
            ttl = max(1, min(ttl, expires_at - int(time.time())))
        await self.store.set_json(key, context.to_record(), ttl)
        return context

    async def logout(self, context: AuthContext) -> bool:
        remote_revoked = False
        try:
            if context.access_token and self.settings.enabled:
                remote_revoked = await self.user_center.logout(context.access_token)
        except UserCenterError:
            remote_revoked = False
        if context.session_id:
            await self.delete_session(context.session_id)
        return remote_revoked

    async def delete_session(self, session_id: str) -> None:
        await self.store.delete(f"{self.SESSION_KEY_PREFIX}{session_id}")

    def profile(self, context: AuthContext) -> AuthProfile:
        permission_info = context.permission_info
        raw_user = dict(permission_info.get("userInfo") or {})
        if not raw_user:
            raise AuthenticationError("统一用户中心未返回用户信息")
        permission_set = dict(permission_info.get("allPermissions") or {})
        roles = [
            RoleSummary.model_validate(role)
            for role in permission_set.get("roles", [])
            if isinstance(role, dict)
        ]
        permissions = sorted({str(item) for item in permission_set.get("permissions", [])})
        return AuthProfile(
            user=UserProfile.model_validate(raw_user),
            roles=roles,
            permissions=permissions,
            organizations=[
                dict(item) for item in permission_info.get("orgs", []) if isinstance(item, dict)
            ],
            expires_at=context.expires_at,
            auth_enabled=self.settings.enabled,
        )

    def dev_context(self) -> AuthContext:
        return AuthContext(
            access_token="",
            permission_info={
                "userInfo": {
                    "id": self.settings.dev_user_id,
                    "username": self.settings.dev_username,
                    "nickname": self.settings.dev_nickname,
                    "userType": 1,
                },
                "allPermissions": {
                    "roles": [
                        {
                            "id": "local-admin",
                            "name": "本地管理员",
                            "code": "local_admin",
                            "type": 1,
                        }
                    ],
                    "permissions": ["*"],
                    "menus": [],
                },
                "appPermissions": {"roles": [], "permissions": [], "menus": []},
                "orgPermissions": {"roles": [], "permissions": [], "menus": []},
                "roleMenuList": [],
                "orgs": [],
            },
            expires_at=None,
        )

    async def _context_from_token(self, token: dict[str, Any]) -> AuthContext:
        access_token = str(token.get("access_token") or "")
        if not access_token:
            raise AuthenticationError("统一用户中心未返回 access_token", status_code=502)
        try:
            permission_info = await self.user_center.get_permission_info(access_token)
        except UserCenterError as exc:
            raise AuthenticationError(str(exc), status_code=exc.status_code) from exc
        expires_in = max(1, int(token.get("expires_in") or 3600))
        return AuthContext(
            access_token=access_token,
            refresh_token=str(token.get("refresh_token") or ""),
            expires_at=int(time.time()) + expires_in,
            permission_info=dict(permission_info or {}),
        )

    async def _save_session(self, context: AuthContext) -> None:
        if not context.session_id:
            raise ValueError("session_id 不能为空")
        await self.store.set_json(
            f"{self.SESSION_KEY_PREFIX}{context.session_id}",
            context.to_record(),
            self.settings.session_ttl_seconds,
        )
