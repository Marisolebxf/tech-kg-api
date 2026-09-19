"""图空间管理 service：创建（真实 CREATE SPACE）、绑定/解绑、按用户列出。

图空间本体在 NebulaGraph 侧；本 service 通过 trs-graph 的默认空间客户端执行 DDL。
删除一律只解绑，绝不 DROP 空间。
创建/绑定时同步在 Milvus 建同名 database 并登记映射（kg_graph_space_vector_db），
向量侧失败只降级登记 failed，不影响图空间操作本身。
"""

from __future__ import annotations

import logging
import os
import re
import time
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from db_model.platform_governance import GraphSpaceVectorDatabase, UserGraphSpace
from infra.graph_db import TRSGraphClient, TRSGraphSettings, get_trs_graph_client
from infra.milvus import get_milvus_client
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


def default_graph_space() -> str:
    """复用图客户端的真实配置，默认业务空间向已登录用户开放读取。"""
    return TRSGraphSettings.from_env().space


class GraphSpaceService:
    def __init__(
        self,
        session: Session,
        client: TRSGraphClient | None = None,
        milvus_client: Any | None = None,
    ) -> None:
        self._session = session
        self._client = client
        self._milvus_client = milvus_client

    @property
    def client(self) -> TRSGraphClient:
        if self._client is None:
            self._client = get_trs_graph_client()
        return self._client

    @property
    def milvus_client(self) -> Any:
        if self._milvus_client is None:
            self._milvus_client = get_milvus_client()
        return self._milvus_client

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

    def list_work_spaces_for_actor(self, actor: PlatformActor) -> list[dict]:
        """当前用户可工作空间：默认业务空间 + 本人绑定，绑定对所有用户（含管理员）生效。

        共享读取不落永久绑定，也不赋予创建空间或图写入权限。
        """
        bound_names = [item["name"] for item in self.bound_spaces(actor.user_id)]
        bound = set(bound_names)
        names = dict.fromkeys([default_graph_space(), *bound_names])
        return [{"name": name, "bound": name in bound, "mine": name in bound} for name in names]

    # Nebula SHOW SPACES 结果做 30s 进程内缓存：空间列表极少变化，而压测/高频
    # 访问下每次请求都打 Nebula 会拖垮图服务（2026-09-19 用例 08）。
    _all_spaces_cached_at: float = 0.0
    _all_spaces_cache: list = []

    def _all_spaces(self) -> list:
        now = time.monotonic()
        if now - GraphSpaceService._all_spaces_cached_at < 30.0:
            return GraphSpaceService._all_spaces_cache
        try:
            names = self.client.list_spaces()
        except Exception as exc:  # noqa: BLE001
            # 失败时回退旧值（可能为空列表）：空结果不缓存，避免短暂故障被
            # 放大成 30s 的"空间不存在"
            logger.warning("列出图空间失败，回退旧缓存: %s", exc)
            return GraphSpaceService._all_spaces_cache
        if not names:
            return GraphSpaceService._all_spaces_cache
        GraphSpaceService._all_spaces_cached_at = now
        GraphSpaceService._all_spaces_cache = names
        return names

    def list_spaces_for_actor(self, actor: PlatformActor) -> list[dict]:
        """配置页绑定入口：管理员看全量（需可选列表），普通用户按可工作空间收敛。"""
        if not actor.is_admin:
            return self.list_work_spaces_for_actor(actor)
        bound_names = [item["name"] for item in self.bound_spaces(actor.user_id)]
        bound = set(bound_names)
        all_spaces = self._all_spaces()
        return [{"name": s, "bound": s in bound, "mine": s in bound} for s in all_spaces]

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
        # 已有空间（可能早于向量库登记机制存在）绑定时同样 ensure
        db_status, _ = self._ensure_vector_database(space_name)
        return self._space_result(space_name, db_status)

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
        # 副本数与分区数可按集群规模配置：副本数超过在线 storaged 主机数时 Nebula 报
        # "Host not enough!"（按副本数找主机）。交付环境 storaged 单副本（config.py
        # 文档同述），默认 1；多节点生产集群设 GRAPH_SPACE_REPLICA_FACTOR=3
        replica = int(os.getenv("GRAPH_SPACE_REPLICA_FACTOR", "1"))
        partition = int(os.getenv("GRAPH_SPACE_PARTITION_NUM", "100"))
        try:
            self.client.execute_write(
                f"CREATE SPACE IF NOT EXISTS `{space_name}` "
                f"(vid_type = FIXED_STRING(64), partition_num = {partition}, replica_factor = {replica});"
            )
        except Exception as exc:  # noqa: BLE001
            hint = ""
            if "host not enough" in str(exc).lower():
                hint = f"（副本数 {replica} 超过集群在线 storaged 主机数，可调小 GRAPH_SPACE_REPLICA_FACTOR）"
            raise GraphSpaceError(f"创建图空间失败: {exc}{hint}") from exc

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
        db_status, _ = self._ensure_vector_database(space_name)
        return self._space_result(space_name, db_status)

    def _wait_for_space(self, space_name: str) -> bool:
        for _ in range(_PROPAGATION_ATTEMPTS):
            try:
                if space_name in self.client.list_spaces():
                    return True
            except Exception:  # noqa: BLE001
                pass
            time.sleep(_PROPAGATION_INTERVAL_SECONDS)
        return False

    # ---------- 向量库一一对应登记 ----------

    def _space_result(self, space_name: str, vector_db_status: str) -> dict:
        result = {
            "name": space_name,
            "bound": True,
            "mine": True,
            "vectorDbStatus": vector_db_status,
        }
        if vector_db_status != "ready":
            result["vectorDbWarning"] = "图空间已创建，但同名向量库创建失败，将在服务重启时自动重试"
        return result

    def _ensure_vector_database(self, space_name: str) -> tuple[str, str]:
        """确保 Milvus 同名 database 存在并登记映射（幂等、可降级）。

        返回 (status, error)，status ∈ {'ready', 'failed'}。Milvus 不可达或建库
        失败不影响图空间创建/绑定本身，仅登记 failed 行，由启动 backfill 重试。
        pymilvus 的 create_database 不幂等（已存在报 "already exist"），先
        list_databases 预查；并发竞态下收到 already exist 视为成功。
        """
        try:
            client = self.milvus_client
            if space_name not in client.list_databases():
                client.create_database(space_name)
        except Exception as exc:  # noqa: BLE001
            if "already exist" in str(exc).lower():
                self._upsert_vector_db_mapping(space_name, "ready", "")
                return ("ready", "")
            logger.warning("图空间 %s 向量库确保失败: %s", space_name, exc)
            error = str(exc)[:2000]
            self._upsert_vector_db_mapping(space_name, "failed", error)
            return ("failed", error)
        self._upsert_vector_db_mapping(space_name, "ready", "")
        return ("ready", "")

    def _upsert_vector_db_mapping(self, space_name: str, status: str, error: str) -> None:
        row = (
            self._session.execute(
                select(GraphSpaceVectorDatabase).where(
                    GraphSpaceVectorDatabase.graph_space == space_name
                )
            )
            .scalars()
            .first()
        )
        if row is None:
            self._session.add(
                GraphSpaceVectorDatabase(
                    graph_space=space_name,
                    vector_database=space_name,
                    status=status,
                    last_error=error,
                )
            )
        else:
            row.vector_database = space_name
            row.status = status
            row.last_error = error
        self._session.commit()


def backfill_vector_databases(
    session: Session | None = None, milvus_client: Any | None = None
) -> dict:
    """对所有已绑定空间 ensure 向量库登记（best-effort、幂等）。

    映射行缺失或 status != ready 的空间重试。session 缺省时从 infra.mysql 取
    业务库会话；可注入参数供单测使用。挂 main.py lifespan 启动钩子。
    """
    if session is not None:
        return _backfill_vector_databases_with(session, milvus_client)
    from infra.mysql import session_scope

    with session_scope() as scoped:
        return _backfill_vector_databases_with(scoped, milvus_client)


def _backfill_vector_databases_with(session: Session, milvus_client: Any | None) -> dict:
    bound_spaces = sorted({r.space_name for r in session.execute(select(UserGraphSpace)).scalars()})
    status_by_space = {
        r.graph_space: r.status for r in session.execute(select(GraphSpaceVectorDatabase)).scalars()
    }
    targets = [name for name in bound_spaces if status_by_space.get(name) != "ready"]
    service = GraphSpaceService(session, milvus_client=milvus_client)
    ensured = failed = 0
    for name in targets:
        status, _ = service._ensure_vector_database(name)
        if status == "ready":
            ensured += 1
        else:
            failed += 1
    return {
        "bound": len(bound_spaces),
        "pending": len(targets),
        "ensured": ensured,
        "failed": failed,
    }
