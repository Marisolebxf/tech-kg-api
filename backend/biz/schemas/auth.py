"""登录、会话和用户权限接口模型。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from biz.schemas.common import ApiResponse


def _to_camel(value: str) -> str:
    first, *rest = value.split("_")
    return first + "".join(part.capitalize() for part in rest)


class CamelCaseModel(BaseModel):
    model_config = ConfigDict(alias_generator=_to_camel, populate_by_name=True)


class LoginUrlData(CamelCaseModel):
    url: str
    expires_in: int


class UserProfile(CamelCaseModel):
    id: int | str
    username: str
    nickname: str
    email: str = ""
    mobile: str = ""
    sex: int = 0
    avatar: str = ""
    status: int = 0
    user_type: int = 1


class RoleSummary(CamelCaseModel):
    id: int | str
    name: str
    code: str
    status: int = 0
    org_id: int | str | None = None
    type: int = 1


class AuthProfile(CamelCaseModel):
    user: UserProfile
    roles: list[RoleSummary] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    organizations: list[dict[str, Any]] = Field(default_factory=list)
    expires_at: int | None = None
    auth_enabled: bool = True


class LogoutData(CamelCaseModel):
    logged_out: bool = True
    remote_revoked: bool = False


class LoginUrlResponse(ApiResponse):
    data: LoginUrlData


class AuthProfileResponse(ApiResponse):
    data: AuthProfile


class PermissionInfoResponse(ApiResponse):
    data: dict[str, Any]


class LogoutResponse(ApiResponse):
    data: LogoutData
