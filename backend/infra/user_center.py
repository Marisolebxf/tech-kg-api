"""统一用户中心 OAuth2 HTTP 客户端。"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from typing import Any
from urllib.parse import urlencode

import httpx

from config.auth import AuthSettings


class UserCenterError(RuntimeError):
    def __init__(self, message: str, *, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code


class UserCenterClient:
    """按统一用户中心 v2.4 调用 OAuth2 与签名开放接口。"""

    def __init__(
        self,
        settings: AuthSettings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        sync_transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.settings = settings
        self._transport = transport
        self._sync_transport = sync_transport

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

    async def get_user_by_token(self, access_token: str) -> dict[str, Any]:
        """v2.4 2.5：服务端获取原官网角色，业务参数不参与签名。"""
        result = await self._request(
            "POST",
            "/user/get-by-token",
            base_url=self.settings.user_center_open_api_base_url
            or f"{self.settings.user_center_base_url.split('/admin-api/', 1)[0]}/open-api/system",
            json_body=self._signed_body(token=access_token),
        )
        if not isinstance(result, dict):
            raise UserCenterError("统一用户中心未返回有效的门户用户信息")
        return result

    def _signed_body(self, **business_params: Any) -> dict[str, Any]:
        public_params = {
            "clientId": self.settings.client_id,
            "timestamp": int(time.time() * 1000),
            "nonce": secrets.token_hex(16),
        }
        payload = "&".join(f"{key}={public_params[key]}" for key in sorted(public_params))
        signature = hmac.new(
            self.settings.client_secret.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return {**public_params, "signature": signature, **business_params}

    def role_user_ids(self, role_code: str) -> frozenset[str]:
        """v2.5.1 §2.7：后端签名查询授权成员，供无浏览器令牌的 worker 同步校验。"""
        try:
            self.settings.require_oauth_credentials()
        except ValueError as exc:
            raise UserCenterError(str(exc), status_code=503) from exc
        try:
            with httpx.Client(
                base_url=self.settings.user_center_open_api_base_url
                or f"{self.settings.user_center_base_url.split('/admin-api/', 1)[0]}/open-api/system",
                auth=httpx.BasicAuth(self.settings.client_id, self.settings.client_secret),
                timeout=15,
                transport=self._sync_transport,
            ) as client:
                response = client.post(
                    "/permission/role-user", json=self._signed_body(roleCode=role_code)
                )
        except httpx.HTTPError as exc:
            raise UserCenterError("统一用户中心暂时不可用") from exc
        result = self._response_data(response)
        if (
            not isinstance(result, dict)
            or result.get("roleCode") != role_code
            or not isinstance(result.get("users"), list)
        ):
            raise UserCenterError("统一用户中心未返回匹配角色的授权用户集合")
        users = set()
        for user in result["users"]:
            if not isinstance(user, dict) or type(user.get("userId")) not in (int, str):
                raise UserCenterError("统一用户中心返回的授权用户编号无效")
            if (
                type(user.get("status")) is int
                and user["status"] == 0
                and str(user["userId"]).strip()
            ):
                users.add(str(user["userId"]))
        return frozenset(users)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        base_url: str | None = None,
    ) -> Any:
        try:
            self.settings.require_oauth_credentials()
        except ValueError as exc:
            raise UserCenterError(str(exc), status_code=503) from exc

        try:
            async with httpx.AsyncClient(
                base_url=base_url or self.settings.user_center_base_url,
                auth=httpx.BasicAuth(
                    username=self.settings.client_id,
                    password=self.settings.client_secret,
                ),
                timeout=15,
                transport=self._transport,
            ) as client:
                response = await client.request(
                    method, path, data=data, params=params, json=json_body
                )
        except httpx.HTTPError as exc:
            raise UserCenterError("统一用户中心暂时不可用") from exc

        return self._response_data(response)

    @staticmethod
    def _response_data(response: httpx.Response) -> Any:
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
