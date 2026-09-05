"""图空间管理 service：创建（真实 CREATE SPACE）、绑定/解绑、按用户列出。

图空间本体在 NebulaGraph 侧；本 service 通过 trs-graph 的默认空间客户端执行 DDL。
删除一律只解绑，绝不 DROP 空间。
"""

from __future__ import annotations

import logging
import os
import re
import time
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from db_model.platform_governance import UserGraphSpace
from infra.graph_db import TRSGraphClient, get_trs_graph_client
from service.platform_access import PlatformActor

logger = logging.getLogger(__name__)

SPACE_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")

# CREATE SPACE 后的 schema 传播延迟，轮询上限
_PROPAGATION_ATTEMPTS = 20
_PROPAGATION_INTERVAL_SECONDS = 0.5


class GraphSpaceError(Exception):
    """图空间操作业务错误（message 直接作为 API detail）。"""


def _validate_name(name: str) -> str:
    name = (name or "").strip()
    if not SPACE_NAME_PATTERN.fullmatch(name):
        raise GraphSpaceError("图空间名称仅支持字母、数字、下划线，且以字母或下划线开头（最长 64）")
    return name


class GraphSpaceService:
    def __init__(self, session: Session, client: TRSGraphClient | None = None) -> None:
        self._session = session
        self._client = client

    @property
    def client(self) -> TRSGraphClient:
        if self._client is None:
            self._client = get_trs_graph_client()
        return self._client

    # ---------- 查询 ----------

    def bound_spaces(self, user_id: str) -> list[dict]:
        rows = (
            self._session.execute(
                select(UserGraphSpace)
                .where(UserGraphSpace.user_id == user_id)
                .order_by(UserGraphSpace.created_at.asc())
            )
            .scalars()
            .all()
        )
        return [{"name": r.space_name, "createdAt": r.created_at.isoformat()} for r in rows]

    def is_bound(self, user_id: str, space_name: str) -> bool:
        stmt = select(UserGraphSpace).where(
            UserGraphSpace.user_id == user_id,
            UserGraphSpace.space_name == space_name,
        )
        return self._session.execute(stmt).scalars().first() is not None

    def list_spaces_for_actor(self, actor: PlatformActor) -> list[dict]:
        """管理员返回 SHOW SPACES 全量；普通用户仅返回自己绑定的空间。"""
        try:
            all_spaces = self.client.list_spaces()
        except Exception as exc:  # noqa: BLE001
            logger.warning("列出图空间失败: %s", exc)
            all_spaces = []
        if actor.is_admin:
            bound = {item["name"] for item in self.bound_spaces(actor.user_id)}
            return [{"name": s, "bound": s in bound, "mine": s in bound} for s in all_spaces]
        return [
            {"name": item["name"], "bound": True, "mine": True}
            for item in self.bound_spaces(actor.user_id)
        ]

    # ---------- 绑定 / 解绑 ----------

    def bind(self, actor: PlatformActor, space_name: str) -> dict:
        space_name = _validate_name(space_name)
        try:
            existing = self.client.list_spaces()
        except Exception as exc:  # noqa: BLE001
            raise GraphSpaceError(f"图服务不可用，无法校验空间: {exc}") from exc
        if space_name not in existing:
            raise GraphSpaceError(f"图空间 {space_name} 不存在")
        if not self.is_bound(actor.user_id, space_name):
            self._session.add(
                UserGraphSpace(
                    user_id=actor.user_id, space_name=space_name, created_at=datetime.now(UTC)
                )
            )
            self._session.commit()
        return {"name": space_name, "bound": True, "mine": True}

    def unbind(self, actor: PlatformActor, space_name: str) -> bool:
        """解除当前用户与空间的绑定；只删绑定行，不动图数据。"""
        space_name = _validate_name(space_name)
        stmt = select(UserGraphSpace).where(
            UserGraphSpace.user_id == actor.user_id,
            UserGraphSpace.space_name == space_name,
        )
        row = self._session.execute(stmt).scalars().first()
        if row is None:
            return False
        self._session.delete(row)
        self._session.commit()
        return True

    # ---------- 创建 ----------

    def create_space(self, actor: PlatformActor, space_name: str) -> dict:
        """真实创建图空间并绑定到创建者。

        CREATE SPACE 需要一个已存在的空间作为执行上下文，因此走默认 env 空间客户端；
        创建后有 schema 传播延迟，轮询 SHOW SPACES 确认后再绑定。
        """
        space_name = _validate_name(space_name)
        try:
            existing = self.client.list_spaces()
        except Exception as exc:  # noqa: BLE001
            raise GraphSpaceError(f"图服务不可用: {exc}") from exc
        if space_name in existing:
            raise GraphSpaceError(f"图空间 {space_name} 已存在")
        # 副本数与分区数可按集群规模配置：单存储节点集群 replica_factor=3 会
        # "Host not enough!"（Nebula 按副本数找主机），默认 3 适配生产多节点
        replica = int(os.getenv("GRAPH_SPACE_REPLICA_FACTOR", "3"))
        partition = int(os.getenv("GRAPH_SPACE_PARTITION_NUM", "100"))
        try:
            self.client.execute_write(
                f"CREATE SPACE IF NOT EXISTS `{space_name}` "
                f"(vid_type = FIXED_STRING(64), partition_num = {partition}, replica_factor = {replica});"
            )
        except Exception as exc:  # noqa: BLE001
            raise GraphSpaceError(f"创建图空间失败: {exc}") from exc

        if not self._wait_for_space(space_name):
            logger.warning(
                "图空间 %s 创建后未在 %s 秒内可见，继续绑定",
                space_name,
                _PROPAGATION_ATTEMPTS * _PROPAGATION_INTERVAL_SECONDS,
            )
        if not self.is_bound(actor.user_id, space_name):
            self._session.add(
                UserGraphSpace(
                    user_id=actor.user_id, space_name=space_name, created_at=datetime.now(UTC)
                )
            )
            self._session.commit()
        return {"name": space_name, "bound": True, "mine": True}

    def _wait_for_space(self, space_name: str) -> bool:
        for _ in range(_PROPAGATION_ATTEMPTS):
            try:
                if space_name in self.client.list_spaces():
                    return True
            except Exception:  # noqa: BLE001
                pass
            time.sleep(_PROPAGATION_INTERVAL_SECONDS)
        return False
