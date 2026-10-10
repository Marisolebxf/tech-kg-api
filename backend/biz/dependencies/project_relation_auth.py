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
            await asyncio.to_thread(_ensure_external_shared_space)
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
    actor = await asyncio.to_thread(application.platform_actor, context)
    from biz.dependencies.selected_graph_space import read_request_graph_space
    from service.business_access_control import ensure_space_access

    space = await read_request_graph_space(request)
    await asyncio.to_thread(ensure_space_access, actor, space, "read")
    return actor


async def project_relation_space(
    request: Request,
    identity: Annotated[
        ExternalClientIdentity | PlatformActor, Depends(require_project_relation_identity)
    ],
):
    from service.graph_space import default_graph_space
    from service.graph_space_context import selected_graph_space

    space = default_graph_space()
    if isinstance(identity, PlatformActor):
        from biz.dependencies.selected_graph_space import read_request_graph_space

        space = await read_request_graph_space(request) or space
    token = selected_graph_space.set(space)
    try:
        yield identity
    finally:
        selected_graph_space.reset(token)


ProjectRelationIdentity = Annotated[
    ExternalClientIdentity | PlatformActor, Depends(project_relation_space)
]


def _ensure_external_shared_space() -> None:
    """机器密钥只能查询显式登记的共享生产数据，不复用 OAuth 或业务 ID。"""
    from sqlalchemy.exc import SQLAlchemyError

    from infra.mysql import session_scope
    from service.business_access_control import rbac_enabled, space_registration
    from service.graph_space import default_graph_space

    if not rbac_enabled():
        return
    try:
        with session_scope() as session:
            row = space_registration(session, default_graph_space())
            if row is not None and row.is_shared_production:
                return
    except SQLAlchemyError as exc:
        raise HTTPException(503, "无法校验共享生产空间权限") from exc
    raise HTTPException(403, "外部接口仅允许查询已配置的共享生产空间")
