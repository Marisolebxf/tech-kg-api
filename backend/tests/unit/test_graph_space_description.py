"""图空间说明（kg_graph_space_profile）单元测试：创建时落库、列表附带展示。"""

from __future__ import annotations

from typing import Any, cast

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from db_model.base import Base
from db_model.platform_governance import GraphSpaceProfile, UserGraphSpace
from service.graph_space import GraphSpaceService
from service.platform_access import PlatformActor


class _StubGraphClient:
    """只实现 create/list 空间所需的最小接口。"""

    def __init__(self, spaces: set[str]) -> None:
        self.spaces = spaces

    def list_spaces(self) -> list[str]:
        return sorted(self.spaces)

    def execute_write(self, statement: str) -> None:
        # CREATE SPACE `xxx` (...); 取反引号里的空间名
        self.spaces.add(statement.split("`")[1])


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine, tables=[UserGraphSpace.__table__, GraphSpaceProfile.__table__])
    with Session(engine) as session:
        yield session


def _admin() -> PlatformActor:
    return PlatformActor(
        user_id="admin1", username="admin", display_name="管理员", email="", is_admin=True
    )


def _service(session: Session, spaces: set[str]) -> GraphSpaceService:
    service = GraphSpaceService(
        session, client=cast(Any, _StubGraphClient(spaces)), milvus_client=object()
    )
    # 向量库登记与本测试无关，直接视为 ready
    service._ensure_vector_database = lambda space_name: ("ready", "")  # noqa: SLF001
    return service


def test_create_space_persists_description(session, monkeypatch):
    monkeypatch.setenv("BUSINESS_RBAC_ENABLED", "false")
    # 作废 _all_spaces 进程缓存，避免跨测试串空间列表
    monkeypatch.setattr(GraphSpaceService, "_all_spaces_cache", [])
    monkeypatch.setattr(GraphSpaceService, "_all_spaces_cached_at", 0.0)
    service = _service(session, {"legacy"})

    result = service.create_space(_admin(), "demo", " 演示用途空间 ")
    assert result["description"] == "演示用途空间"  # 提交前去空白
    assert session.get(GraphSpaceProfile, "demo").description == "演示用途空间"
    # 创建者旧模式自动绑定
    assert service.is_bound("admin1", "demo")


def test_list_spaces_attach_description(session, monkeypatch):
    monkeypatch.setenv("BUSINESS_RBAC_ENABLED", "false")
    monkeypatch.setattr(GraphSpaceService, "_all_spaces_cache", [])
    monkeypatch.setattr(GraphSpaceService, "_all_spaces_cached_at", 0.0)
    session.add(UserGraphSpace(user_id="admin1", space_name="legacy"))
    session.add(GraphSpaceProfile(space_name="legacy", description="存量空间"))
    service = _service(session, {"legacy", "bare"})
    service.bind(_admin(), "bare")

    items = {item["name"]: item for item in service.list_spaces_for_actor(_admin())}
    assert items["legacy"]["description"] == "存量空间"
    assert items["bare"]["description"] == ""  # 无说明的空间留空，不占第二行
    # 普通用户（工作空间口径）同样附带
    actor = PlatformActor(user_id="user1", username="u", display_name="u", email="", is_admin=False)
    session.add(UserGraphSpace(user_id="user1", space_name="legacy"))
    work = {item["name"]: item for item in service.list_work_spaces_for_actor(actor)}
    assert work["legacy"]["description"] == "存量空间"


def test_list_spaces_rbac_mode_attach_description(session, monkeypatch):
    """RBAC 模式列表委托 space_items，同样要补挂说明（dev2 实际运行模式）。"""
    monkeypatch.setenv("BUSINESS_RBAC_ENABLED", "true")
    import service.business_access_control as bac

    monkeypatch.setattr(
        bac,
        "space_items",
        lambda actor: [
            {"name": "legacy", "bound": True, "mine": True, "groupKind": "unassigned"},
            {"name": "bare", "bound": True, "mine": True, "groupKind": "public"},
        ],
    )
    session.add(GraphSpaceProfile(space_name="legacy", description="存量空间"))
    service = _service(session, set())

    items = {item["name"]: item for item in service.list_spaces_for_actor(_admin())}
    assert items["legacy"]["description"] == "存量空间"
    assert items["bare"]["description"] == ""
    # 普通用户工作空间口径（顶栏选择器）同一委托路径
    actor = PlatformActor(user_id="user1", username="u", display_name="u", email="", is_admin=False)
    work = {item["name"]: item for item in service.list_work_spaces_for_actor(actor)}
    assert work["legacy"]["description"] == "存量空间"
