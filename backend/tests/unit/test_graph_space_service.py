"""图空间管理 service 单测：fake trs-graph/Milvus 客户端 + SQLite 内存库。"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db_model.base import Base
from db_model.platform_governance import GraphSpaceVectorDatabase, UserGraphSpace
from service.graph_space import (
    GraphSpaceError,
    GraphSpaceService,
    backfill_vector_databases,
)
from service.platform_access import PlatformActor

USER_A = "101"
USER_B = "202"


class FakeGraphClient:
    """记录 DDL 语句的假 trs-graph 客户端。"""

    def __init__(self, spaces: list[str] | None = None, visible_after_poll: bool = True) -> None:
        self.spaces = list(spaces or [])
        self.statements: list[str] = []

    def list_spaces(self) -> list[str]:
        return list(self.spaces)

    def execute_write(self, query: str, params=None):  # noqa: ANN001
        self.statements.append(query)
        for stmt in query.split(";"):
            stmt = stmt.strip()
            if stmt.startswith("CREATE SPACE"):
                name = stmt.split("IF NOT EXISTS", 1)[1].strip().split(" ", 1)[0].strip("`")
                if name not in self.spaces:
                    self.spaces.append(name)
        return None


class FakeMilvusClient:
    """记录建库调用的假 Milvus 客户端（list_databases/create_database）。"""

    def __init__(
        self,
        databases: list[str] | None = None,
        fail_on_connect: Exception | None = None,
        fail_on_create: Exception | None = None,
    ) -> None:
        self.databases = list(databases or ["default"])
        self.created: list[str] = []
        self.fail_on_connect = fail_on_connect
        self.fail_on_create = fail_on_create

    def list_databases(self) -> list[str]:
        if self.fail_on_connect is not None:
            raise self.fail_on_connect
        return list(self.databases)

    def create_database(self, db_name: str) -> None:
        if self.fail_on_create is not None:
            raise self.fail_on_create
        self.created.append(db_name)
        self.databases.append(db_name)


def _actor(user_id: str, is_admin: bool = False) -> PlatformActor:
    return PlatformActor(
        user_id=user_id, username="u", display_name="u", email="", is_admin=is_admin
    )


@pytest.fixture
def session_factory():
    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(
        engine, tables=[UserGraphSpace.__table__, GraphSpaceVectorDatabase.__table__]
    )
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    yield factory
    engine.dispose()


def _service(
    session_factory, client: FakeGraphClient, milvus: FakeMilvusClient | None = None
) -> GraphSpaceService:
    return GraphSpaceService(
        session_factory(), client=client, milvus_client=milvus or FakeMilvusClient()
    )


def _mapping_row(session_factory, space_name: str) -> GraphSpaceVectorDatabase | None:
    with session_factory() as session:
        return (
            session.execute(
                select(GraphSpaceVectorDatabase).where(
                    GraphSpaceVectorDatabase.graph_space == space_name
                )
            )
            .scalars()
            .first()
        )


def test_create_space_creates_and_binds(session_factory) -> None:
    client = FakeGraphClient(spaces=["dev2"])
    milvus = FakeMilvusClient()
    service = _service(session_factory, client, milvus)

    result = service.create_space(_actor(USER_A), "u1_test")

    assert result == {
        "name": "u1_test",
        "bound": True,
        "mine": True,
        "vectorDbStatus": "ready",
    }
    assert "u1_test" in client.spaces
    assert any("CREATE SPACE" in s and "u1_test" in s for s in client.statements)
    # 绑定关系落库
    assert service.is_bound(USER_A, "u1_test")
    assert not service.is_bound(USER_B, "u1_test")
    # 同名向量库已建 + 映射行 ready
    assert milvus.created == ["u1_test"]
    row = _mapping_row(session_factory, "u1_test")
    assert row is not None and row.status == "ready" and row.vector_database == "u1_test"


def test_create_space_rejects_invalid_name(session_factory) -> None:
    service = _service(session_factory, FakeGraphClient())
    for bad in ("", "1abc", "a-b", "a b", "drop;x", "A" * 65):
        with pytest.raises(GraphSpaceError):
            service.create_space(_actor(USER_A), bad)


def test_create_space_duplicate_rejected(session_factory) -> None:
    service = _service(session_factory, FakeGraphClient(spaces=["dev2"]))
    with pytest.raises(GraphSpaceError, match="已存在"):
        service.create_space(_actor(USER_A), "dev2")


def test_bind_requires_existing_space(session_factory) -> None:
    service = _service(session_factory, FakeGraphClient(spaces=["dev2"]))
    with pytest.raises(GraphSpaceError, match="不存在"):
        service.bind(_actor(USER_A), "nope")
    service.bind(_actor(USER_A), "dev2")
    assert service.is_bound(USER_A, "dev2")
    # 重复绑定幂等
    service.bind(_actor(USER_A), "dev2")
    assert service.is_bound(USER_A, "dev2")


def test_unbind_never_drops(session_factory) -> None:
    client = FakeGraphClient(spaces=["dev2"])
    service = _service(session_factory, client)
    service.bind(_actor(USER_A), "dev2")

    assert service.unbind(_actor(USER_A), "dev2") is True
    assert not service.is_bound(USER_A, "dev2")
    assert "dev2" in client.spaces  # 空间本体保留
    assert not any("DROP" in s.upper() for s in client.statements)
    assert service.unbind(_actor(USER_A), "dev2") is False  # 再解绑 404


def test_list_spaces_for_actor(session_factory, monkeypatch) -> None:
    monkeypatch.setenv("TRS_GRAPH_SPACE", "dev2")
    client = FakeGraphClient(spaces=["dev2", "techkg"])
    service = _service(session_factory, client)
    service.bind(_actor(USER_A), "dev2")

    # 默认空间与已有绑定去重，保持真实绑定标记。
    assert service.list_spaces_for_actor(_actor(USER_A)) == [
        {"name": "dev2", "bound": True, "mine": True}
    ]
    # 管理员看全量 + 标记自己绑定的
    admin_view = service.list_spaces_for_actor(_actor("admin", is_admin=True))
    assert {item["name"] for item in admin_view} == {"dev2", "techkg"}
    assert {item["name"] for item in admin_view if item["mine"]} == set()


def test_new_user_reads_configured_default_without_binding(session_factory, monkeypatch) -> None:
    monkeypatch.setenv("TRS_GRAPH_SPACE", "delivery_graph")
    client = FakeGraphClient(spaces=["delivery_graph", "private_graph"])
    service = _service(session_factory, client)

    assert service.list_spaces_for_actor(_actor(USER_A)) == [
        {"name": "delivery_graph", "bound": False, "mine": False}
    ]
    assert service.bound_spaces(USER_A) == []
    assert client.statements == []


def test_shared_default_preserves_other_bound_spaces(session_factory, monkeypatch) -> None:
    monkeypatch.setenv("TRS_GRAPH_SPACE", "delivery_graph")
    client = FakeGraphClient(spaces=["delivery_graph", "private_graph", "another_users_graph"])
    service = _service(session_factory, client)
    service.bind(_actor(USER_A), "private_graph")
    service.bind(_actor(USER_B), "another_users_graph")

    assert service.list_spaces_for_actor(_actor(USER_A)) == [
        {"name": "delivery_graph", "bound": False, "mine": False},
        {"name": "private_graph", "bound": True, "mine": True},
    ]


def test_created_at_populated(session_factory) -> None:
    service = _service(session_factory, FakeGraphClient(spaces=["dev2"]))
    service.bind(_actor(USER_A), "dev2")
    bound = service.bound_spaces(USER_A)
    assert len(bound) == 1
    assert bound[0]["name"] == "dev2"
    assert bound[0]["createdAt"]


# ---------- 图空间 ↔ 向量库一一对应 ----------


def test_ensure_vector_database_idempotent(session_factory) -> None:
    milvus = FakeMilvusClient(databases=["dev2", "default"])
    service = _service(session_factory, FakeGraphClient(spaces=["dev2"]), milvus)

    service.bind(_actor(USER_A), "dev2")

    assert milvus.created == []  # 已存在不重复建
    row = _mapping_row(session_factory, "dev2")
    assert row is not None and row.status == "ready"


def test_create_space_survives_milvus_outage(session_factory) -> None:
    client = FakeGraphClient(spaces=["dev2"])
    milvus = FakeMilvusClient(fail_on_connect=RuntimeError("connect refused"))
    service = _service(session_factory, client, milvus)

    result = service.create_space(_actor(USER_A), "u1_outage")

    # 图空间创建/绑定不受向量侧失败影响
    assert "u1_outage" in client.spaces
    assert service.is_bound(USER_A, "u1_outage")
    assert result["vectorDbStatus"] == "failed"
    assert "vectorDbWarning" in result
    row = _mapping_row(session_factory, "u1_outage")
    assert row is not None and row.status == "failed" and "connect refused" in row.last_error


def test_ensure_vector_database_already_exist_race(session_factory) -> None:
    # 并发竞态：预查缺失后 create_database 收到 already exist → 视为成功
    milvus = FakeMilvusClient(fail_on_create=RuntimeError("database already exists"))
    service = _service(session_factory, FakeGraphClient(spaces=["dev2"]), milvus)

    status, error = service._ensure_vector_database("dev2")

    assert status == "ready" and error == ""
    row = _mapping_row(session_factory, "dev2")
    assert row is not None and row.status == "ready"


def test_bind_ensures_vector_database_for_existing_space(session_factory) -> None:
    milvus = FakeMilvusClient()
    service = _service(session_factory, FakeGraphClient(spaces=["legacy_space"]), milvus)

    result = service.bind(_actor(USER_A), "legacy_space")

    assert result["vectorDbStatus"] == "ready"
    assert milvus.created == ["legacy_space"]
    row = _mapping_row(session_factory, "legacy_space")
    assert row is not None and row.status == "ready"


def test_backfill_retries_failed_rows(session_factory) -> None:
    client = FakeGraphClient(spaces=["dev2"])
    milvus = FakeMilvusClient()
    # 前置：u1 创建时 Milvus 挂（failed 行）；dev2 无映射行
    outage = _service(
        session_factory, client, FakeMilvusClient(fail_on_connect=RuntimeError("down"))
    )
    outage.create_space(_actor(USER_A), "u1_retry")
    outage.bind(_actor(USER_B), "dev2")
    assert _mapping_row(session_factory, "u1_retry").status == "failed"
    assert _mapping_row(session_factory, "dev2").status == "failed"

    summary = backfill_vector_databases(session_factory(), milvus_client=milvus)

    assert summary == {"bound": 2, "pending": 2, "ensured": 2, "failed": 0}
    assert sorted(milvus.created) == ["dev2", "u1_retry"]
    assert _mapping_row(session_factory, "u1_retry").status == "ready"
    assert _mapping_row(session_factory, "dev2").status == "ready"
    # 幂等：全部 ready 后再跑为空操作
    assert backfill_vector_databases(session_factory(), milvus_client=milvus) == {
        "bound": 2,
        "pending": 0,
        "ensured": 0,
        "failed": 0,
    }
