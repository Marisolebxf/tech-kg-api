"""图空间管理 service 单测：fake trs-graph 客户端 + SQLite 内存库。"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db_model.base import Base
from db_model.platform_governance import UserGraphSpace
from service.graph_space import GraphSpaceError, GraphSpaceService
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
    Base.metadata.create_all(engine, tables=[UserGraphSpace.__table__])
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    yield factory
    engine.dispose()


def _service(session_factory, client: FakeGraphClient) -> GraphSpaceService:
    return GraphSpaceService(session_factory(), client=client)


def test_create_space_creates_and_binds(session_factory) -> None:
    client = FakeGraphClient(spaces=["dev2"])
    service = _service(session_factory, client)

    result = service.create_space(_actor(USER_A), "u1_test")

    assert result == {"name": "u1_test", "bound": True, "mine": True}
    assert "u1_test" in client.spaces
    assert any("CREATE SPACE" in s and "u1_test" in s for s in client.statements)
    # 绑定关系落库
    assert service.is_bound(USER_A, "u1_test")
    assert not service.is_bound(USER_B, "u1_test")


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


def test_list_spaces_for_actor(session_factory) -> None:
    client = FakeGraphClient(spaces=["dev2", "techkg"])
    service = _service(session_factory, client)
    service.bind(_actor(USER_A), "dev2")

    # 普通用户只看自己的
    assert service.list_spaces_for_actor(_actor(USER_A)) == [
        {"name": "dev2", "bound": True, "mine": True}
    ]
    # 管理员看全量 + 标记自己绑定的
    admin_view = service.list_spaces_for_actor(_actor("admin", is_admin=True))
    assert {item["name"] for item in admin_view} == {"dev2", "techkg"}
    assert {item["name"] for item in admin_view if item["mine"]} == set()


def test_created_at_populated(session_factory) -> None:
    service = _service(session_factory, FakeGraphClient(spaces=["dev2"]))
    service.bind(_actor(USER_A), "dev2")
    bound = service.bound_spaces(USER_A)
    assert len(bound) == 1
    assert bound[0]["name"] == "dev2"
    assert bound[0]["createdAt"]
