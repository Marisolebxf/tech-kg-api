"""kg-open 对外查询接口鉴权：沿用项目关系接口的双通道模式。

机器密钥（X-Client-Id + X-API-Key，scope=kg-open:read）钉死默认共享生产空间；
浏览器用户沿用平台认证并按请求选择空间（复用 space RBAC 读校验）。
"""

import asyncio
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Request, Response

from biz.dependencies.auth import (
    AuthApplicationDependency,
    BearerDependency,
    require_authenticated_user,
)
from service.external_api_client import (
    KG_OPEN_READ,
    ExternalClientError,
    ExternalClientIdentity,
    authenticate_client,
)
from service.platform_access import PlatformActor


@dataclass(frozen=True)
class KgOpenContext:
    """一次 kg-open 请求的身份与生效空间。"""

    identity: ExternalClientIdentity | PlatformActor
    space: str
    is_machine: bool


async def require_kg_open_identity(
    request: Request,
    response: Response,
    application: AuthApplicationDependency,
    bearer: BearerDependency,
) -> KgOpenContext:
    from service.graph_space import default_graph_space

    client_ids = request.headers.getlist("x-client-id")
    keys = request.headers.getlist("x-api-key")
    # 提供任一 API Key Header 即选择机器认证，不允许错误密钥回退到浏览器身份。
    if client_ids or keys:
        # 共享生产空间门禁与项目关系接口同一份实现，两处对外口子保持同口径。
        from biz.dependencies.project_relation_auth import _ensure_external_shared_space

        try:
            if len(client_ids) != 1 or len(keys) != 1:
                raise ExternalClientError("请提供唯一的 X-Client-Id 和 X-API-Key")
            identity = await asyncio.to_thread(
                authenticate_client,
                client_ids[0],
                keys[0],
                required_scope=KG_OPEN_READ,
            )
            await asyncio.to_thread(_ensure_external_shared_space)
            request.state.external_client_id = identity.client_id
            return KgOpenContext(identity=identity, space=default_graph_space(), is_machine=True)
        except ExternalClientError as exc:
            raise HTTPException(
                status_code=exc.status_code,
                detail=str(exc),
                headers={"Cache-Control": "no-store"},
            ) from exc
    context = await require_authenticated_user(request, response, application, bearer)
    # 保留原 CurrentActor 的用户资料校验和角色解析，机器身份不进入用户表。
    actor = await asyncio.to_thread(application.platform_actor, context)
    from biz.dependencies.selected_graph_space import read_request_graph_space
    from service.business_access_control import ensure_space_access

    space = await read_request_graph_space(request)
    await asyncio.to_thread(ensure_space_access, actor, space, "read")
    return KgOpenContext(identity=actor, space=space or default_graph_space(), is_machine=False)


KgOpenAuth = Annotated[KgOpenContext, Depends(require_kg_open_identity)]
