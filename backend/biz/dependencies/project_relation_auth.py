"""仅项目关系接口接受业务方 API Key，同时兼容既有用户认证。"""

import asyncio
from typing import Annotated

from fastapi import Depends, HTTPException, Request, Response

from biz.dependencies.auth import (
    AuthApplicationDependency,
    BearerDependency,
    require_authenticated_user,
)
from service.external_api_client import (
    ExternalClientError,
    ExternalClientIdentity,
    authenticate_client,
)
from service.platform_access import PlatformActor


async def require_project_relation_identity(
    request: Request,
    response: Response,
    application: AuthApplicationDependency,
    bearer: BearerDependency,
) -> ExternalClientIdentity | PlatformActor:
    client_ids = request.headers.getlist("x-client-id")
    keys = request.headers.getlist("x-api-key")
    # 提供任一 API Key Header 即选择机器认证，不允许错误密钥回退到浏览器身份。
    if client_ids or keys:
        try:
            if len(client_ids) != 1 or len(keys) != 1:
                raise ExternalClientError("请提供唯一的 X-Client-Id 和 X-API-Key")
            identity = await asyncio.to_thread(authenticate_client, client_ids[0], keys[0])
            request.state.external_client_id = identity.client_id
            return identity
        except ExternalClientError as exc:
            raise HTTPException(
                status_code=exc.status_code,
                detail=str(exc),
                headers={"Cache-Control": "no-store"},
            ) from exc
    context = await require_authenticated_user(request, response, application, bearer)
    # 保留原 CurrentActor 的用户资料校验和角色解析，机器身份不进入用户表。
    return await asyncio.to_thread(application.platform_actor, context)


ProjectRelationIdentity = Annotated[
    ExternalClientIdentity | PlatformActor, Depends(require_project_relation_identity)
]
