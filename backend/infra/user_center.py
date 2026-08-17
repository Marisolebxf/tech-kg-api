"""统一用户中心 OAuth2 HTTP 客户端。"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

import httpx

from config.auth import AuthSettings


class UserCenterError(RuntimeError):
    def __init__(self, message: str, *, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code


class UserCenterClient:
    """按《统一用户中心开放授权接口文档 v2.3.1》的 OAuth2 章节调用。"""

    def __init__(
        self,
        settings: AuthSettings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.settings = settings
        self._transport = transport

    def build_login_url(self, state: str) -> str:
        self.settings.require_oauth_credentials()
        parameters = {
            "response_type": "code",
            "client_id": self.settings.client_id,
            "redirect_uri": self.settings.redirect_uri,
            "state": state,
        }
        if self.settings.scope:
            parameters["scope"] = self.settings.scope
        query = urlencode(parameters)
        separator = "&" if "?" in self.settings.sso_login_url else "?"
        return f"{self.settings.sso_login_url}{separator}{query}"

    async def exchange_code(self, code: str, *, state: str | None = None) -> dict[str, Any]:
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.settings.redirect_uri,
        }
        if state:
            data["state"] = state
        return await self._request(
            "POST",
            "/token",
            data=data,
        )

    async def refresh(self, refresh_token: str) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/token",
            data={"grant_type": "refresh_token", "refresh_token": refresh_token},
        )

    async def check_token(self, access_token: str) -> dict[str, Any]:
        return await self._request("POST", "/check-token", params={"token": access_token})

    async def get_permission_info(
        self,
        access_token: str,
        *,
        org_id: int | None = None,
        include_role_menu: bool = True,
    ) -> dict[str, Any]:
        params: dict[str, str | int] = {
            "token": access_token,
            "include_role_menu": str(include_role_menu).lower(),
        }
        if org_id is not None:
            params["orgId"] = org_id
        return await self._request("GET", "/v1/get-permission-info", params=params)

    async def logout(self, access_token: str) -> bool:
        result = await self._request("GET", "/logout", params={"token": access_token})
        return bool(result)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        try:
            self.settings.require_oauth_credentials()
        except ValueError as exc:
            raise UserCenterError(str(exc), status_code=503) from exc

        try:
            async with httpx.AsyncClient(
                base_url=self.settings.user_center_base_url,
                auth=httpx.BasicAuth(
                    username=self.settings.client_id,
                    password=self.settings.client_secret,
                ),
                timeout=15,
                transport=self._transport,
            ) as client:
                response = await client.request(method, path, data=data, params=params)
        except httpx.HTTPError as exc:
            raise UserCenterError("统一用户中心暂时不可用") from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise UserCenterError("统一用户中心返回了无法解析的响应") from exc

        if not response.is_success:
            message = payload.get("msg") if isinstance(payload, dict) else None
            raise UserCenterError(
                message or "统一用户中心请求失败",
                status_code=401 if response.status_code in {400, 401, 403} else 502,
            )
        if not isinstance(payload, dict):
            raise UserCenterError("统一用户中心返回格式不正确")
        if payload.get("code") not in (0, 200):
            raise UserCenterError(
                str(payload.get("msg") or "统一用户中心业务处理失败"),
                status_code=401 if payload.get("code") in {400, 401} else 502,
            )
        return payload.get("data")
