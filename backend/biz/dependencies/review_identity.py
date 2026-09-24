"""Trusted gateway identity for manual-review APIs."""

from __future__ import annotations

import hashlib
import hmac
import os
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, HTTPException, Request, Response

from biz.dependencies.auth import (
    AuthApplicationDependency,
    BearerDependency,
    require_authenticated_user,
)
from service.manual_review_domain import ReviewIdentity


def _header_env(name: str, default: str) -> str:
    return os.getenv(name, default)


async def _review_platform_actor(
    request: Request,
    response: Response,
    application: AuthApplicationDependency,
    bearer: BearerDependency,
):
    from service.business_access_control import rbac_enabled

    if not rbac_enabled():
        return None
    context = await require_authenticated_user(request, response, application, bearer)
    return application.platform_actor(context)


def get_review_identity(
    request: Request,
    actor: Annotated[object, Depends(_review_platform_actor)] = None,
) -> ReviewIdentity:
    """Read canonical or environment-configured gateway headers and verify their HMAC."""
    from service.business_access_control import rbac_enabled

    if rbac_enabled():
        if actor is None or actor.business_only or not actor.can_develop:
            raise HTTPException(status_code=403, detail="当前账号无人工审核权限")
        return ReviewIdentity(
            actor.user_id,
            actor.display_name or actor.username or actor.user_id,
            frozenset({"review_admin"} if actor.is_admin else {"reviewer"}),
            frozenset({"*"}),
            actor.business_id,
            request.headers.get("X-Request-Id") or uuid4().hex,
            platform_actor=actor,
        )

    def value(env_name: str, default: str) -> str:
        return request.headers.get(os.getenv(env_name, default), "")

    user_id = value("REVIEW_HEADER_USER_ID", "X-User-Id")
    user_name = value("REVIEW_HEADER_USER_NAME", "X-User-Name")
    roles = value("REVIEW_HEADER_ROLES", "X-User-Roles")
    domains = value("REVIEW_HEADER_DOMAINS", "X-User-Domains")
    organization = value("REVIEW_HEADER_ORGANIZATION", "X-User-Organization")
    request_id = value("REVIEW_HEADER_REQUEST_ID", "X-Request-Id")
    signature = value("REVIEW_HEADER_SIGNATURE", "X-Identity-Signature")
    require_signature = os.getenv("REVIEW_IDENTITY_REQUIRE_SIGNATURE", "true").lower() == "true"
    # 开发期 fallback：禁用签名校验时返回 dev identity，让前端无需网关头即可调
    # 审核 API。仅带 X-User-Id（前端 currentUserId 必发）但网关未注入角色头时，
    # 同样按 dev 角色放行——否则免登录部署里审核决策接口全部 403。
    # 生产保持 require_signature=true。
    if not require_signature and not roles and not signature:
        return ReviewIdentity(
            user_id=user_id or "dev-anonymous",
            user_name=user_name or "Dev Anonymous",
            roles=frozenset({"review_admin", "reviewer"}),
            domains=frozenset({"*"}),
            organization=organization or "dev",
            request_id=request_id or f"dev-{uuid4().hex[:8]}",
        )
    if not user_id:
        raise HTTPException(status_code=401, detail="缺少网关用户身份")
    secret = os.getenv("REVIEW_IDENTITY_HMAC_SECRET", "")
    payload = "\n".join((user_id, user_name, roles, domains, organization, request_id))
    if require_signature:
        if not secret:
            raise HTTPException(status_code=503, detail="身份签名密钥未配置")
        expected = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
        if not signature or not hmac.compare_digest(expected, signature):
            raise HTTPException(status_code=401, detail="网关身份签名无效")
    return ReviewIdentity(
        user_id,
        user_name or user_id,
        frozenset(x.strip() for x in roles.split(",") if x.strip()),
        frozenset(x.strip() for x in domains.split(",") if x.strip()),
        organization,
        request_id or "unknown",
    )
