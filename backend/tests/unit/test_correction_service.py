from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from biz.dependencies.auth import require_platform_admin
from db_model.base import Base
from db_model.platform_governance import (
    AdminAuditLog,
    CorrectionProjection,
    CorrectionReview,
    CorrectionSyncTask,
    ManualCorrection,
    PlatformUser,
    PlatformUserRole,
)
from service import platform_access
from service.correction import CorrectionService, process_due_sync_tasks
from service.platform_access import PlatformActor, list_members, set_admin_role


class FakeGraph:
    def __init__(self) -> None:
        self.fail = False
        self.node_merges: list[tuple[list[str], dict, dict]] = []

    def merge_node(self, labels: list[str], identity: dict, properties: dict):
        if self.fail:
            raise RuntimeError("graph unavailable")
        self.node_merges.append((labels, identity, properties))
        return object()


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(
        engine,
        tables=[
            PlatformUser.__table__,
            PlatformUserRole.__table__,
            ManualCorrection.__table__,
            CorrectionReview.__table__,
            CorrectionSyncTask.__table__,
            CorrectionProjection.__table__,
            AdminAuditLog.__table__,
        ],
    )
    return Session(engine, expire_on_commit=False)


def _admin(user_id: str = "admin-1") -> PlatformActor:
    return PlatformActor(
        user_id=user_id,
        username=user_id,
        display_name="测试管理员",
        email="",
        is_admin=True,
    )


def _payload() -> dict:
    return {
        "target_type": "expert",
        "operation": "update",
        "target_id": "person_001",
        "title": "修正专家姓名",
        "reason": "原始数据存在错别字",
        "before_data": {"name_zh": "张三三"},
        "after_data": {"name_zh": "张三"},
    }


def test_self_approval_uses_outbox_and_sync_is_idempotent() -> None:
    session = _session()
    graph = FakeGraph()
    actor = _admin()
    service = CorrectionService(session, graph_factory=lambda: graph, sync_mode="dual")

    created = service.create(_payload(), actor)
    approved = service.decide(created["id"], "approve", "确认修正", actor)

    assert approved["status"] == "PENDING_SYNC"
    assert approved["reviewerId"] == actor.user_id
    assert graph.node_merges == []
    session.commit()

    assert process_due_sync_tasks(session, graph_factory=lambda: graph, sync_mode="dual") == 1
    session.commit()

    correction = session.get(ManualCorrection, created["id"])
    projection = session.scalar(select(CorrectionProjection))
    task = session.scalar(select(CorrectionSyncTask))
    assert correction is not None and correction.status == "COMPLETED"
    assert projection is not None and projection.version == 1
    assert task is not None and task.status == "SUCCEEDED"
    assert graph.node_merges[0][1] == {"scholar_id": "person_001"}
    assert [item["action"] for item in service.get(created["id"], actor)["history"]] == [
        "SUBMIT",
        "APPROVE",
        "SYNC_SUCCEEDED",
    ]

    service.process_task(task.id)
    assert projection.version == 1
    assert len(graph.node_merges) == 1


def test_graph_failure_is_recorded_and_can_be_retried() -> None:
    session = _session()
    graph = FakeGraph()
    graph.fail = True
    actor = _admin()
    service = CorrectionService(session, graph_factory=lambda: graph, sync_mode="dual")

    created = service.create(_payload(), actor)
    service.decide(created["id"], "approve", "", actor)
    session.commit()

    assert process_due_sync_tasks(session, graph_factory=lambda: graph, sync_mode="dual") == 1
    session.commit()
    task = session.scalar(select(CorrectionSyncTask))
    correction = session.get(ManualCorrection, created["id"])
    projection = session.scalar(select(CorrectionProjection))
    assert task is not None and task.status == "RETRYING"
    assert task.mysql_status == "SUCCEEDED"
    assert task.graph_status == "FAILED"
    assert "graph unavailable" in task.last_error
    assert correction is not None and correction.status == "SYNC_FAILED"
    assert projection is not None and projection.version == 1

    graph.fail = False
    retried = service.retry(created["id"], "恢复后重试", actor)
    assert retried["status"] == "PENDING_SYNC"
    assert retried["sync"]["status"] == "PENDING"
    session.commit()

    assert process_due_sync_tasks(session, graph_factory=lambda: graph, sync_mode="dual") == 1
    session.commit()
    assert correction.status == "COMPLETED"
    assert task.status == "SUCCEEDED"
    assert projection.version == 1


def test_owner_can_create_read_update_list_and_cancel() -> None:
    session = _session()
    actor = PlatformActor(
        user_id="user-1",
        username="user-1",
        display_name="普通用户",
        email="user-1@example.com",
        is_admin=False,
    )
    service = CorrectionService(session, sync_mode="projection")

    created = service.create(_payload(), actor)
    loaded = service.get(created["id"], actor)
    updated = service.update(
        created["id"],
        {"title": "修正专家中文姓名", "reason": "已补充权威来源"},
        actor,
    )
    listed = service.list(actor)
    cancelled = service.cancel(created["id"], actor)

    assert loaded["id"] == created["id"]
    assert updated["title"] == "修正专家中文姓名"
    assert updated["version"] == 2
    assert listed["total"] == 1
    assert cancelled["status"] == "CANCELLED"


def test_list_uses_database_filters_and_pagination_beyond_one_hundred_rows() -> None:
    session = _session()
    actor = _admin()
    for index in range(105):
        session.add(
            ManualCorrection(
                target_type="organization" if index == 104 else "expert",
                operation="update",
                target_id=f"target-{index:03d}",
                title="唯一检索标记" if index == 104 else f"普通修正 {index}",
                reason="分页查询验证",
                before_data={},
                after_data={"index": index},
                status="REJECTED" if index == 104 else "PENDING_REVIEW",
                submitter_id=actor.user_id,
                submitter_name=actor.display_name,
            )
        )
    session.flush()
    service = CorrectionService(session, sync_mode="projection")

    second_page = service.list(actor, all_users=True, page=2, page_size=20)
    filtered = service.list(
        actor,
        all_users=True,
        statuses=("PENDING_REVIEW", "SYNC_FAILED"),
        page=1,
        page_size=20,
    )
    searched = service.list(
        actor,
        all_users=True,
        keyword="唯一检索标记",
        target_type="organization",
    )

    assert second_page["total"] == 105
    assert len(second_page["items"]) == 20
    assert second_page["statusCounts"] == {"PENDING_REVIEW": 104, "REJECTED": 1}
    assert filtered["total"] == 104
    assert searched["total"] == 1
    assert searched["items"][0]["targetId"] == "target-104"


def test_projection_mode_soft_deletes_without_touching_graph() -> None:
    session = _session()
    graph = FakeGraph()
    actor = _admin()
    service = CorrectionService(session, graph_factory=lambda: graph, sync_mode="projection")
    payload = {
        **_payload(),
        "operation": "delete",
        "title": "删除无效专家记录",
        "after_data": {},
    }

    created = service.create(payload, actor)
    service.decide(created["id"], "approve", "确认软删除", actor)
    session.commit()

    assert (
        process_due_sync_tasks(
            session,
            graph_factory=lambda: graph,
            sync_mode="projection",
        )
        == 1
    )
    session.commit()

    correction = session.get(ManualCorrection, created["id"])
    projection = session.scalar(select(CorrectionProjection))
    task = session.scalar(select(CorrectionSyncTask))
    assert correction is not None and correction.status == "COMPLETED"
    assert projection is not None and projection.active is False
    assert task is not None and task.graph_status == "SKIPPED"
    assert graph.node_merges == []


def test_initial_admin_is_visible_in_member_list() -> None:
    session = _session()
    session.add(
        PlatformUser(
            user_id="bootstrap-admin",
            username="bootstrap",
            nickname="首批管理员",
            email="admin@example.com",
        )
    )
    session.commit()

    members = list_members(session, initial_admin_ids=("bootstrap-admin",))

    assert members[0]["isAdmin"] is True

    with pytest.raises(ValueError, match="首批管理员"):
        set_admin_role(
            session,
            user_id="bootstrap-admin",
            enabled=False,
            actor=_admin(),
            immutable_admin_ids=("bootstrap-admin",),
        )


def test_member_admin_can_be_granted_and_revoked_without_removing_last_admin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _session()
    session.add_all(
        [
            PlatformUser(user_id="admin-1", username="admin", nickname="管理员"),
            PlatformUser(user_id="user-2", username="user", nickname="普通用户"),
            PlatformUserRole(
                user_id="admin-1",
                role_code="platform_admin",
                granted_by="system-bootstrap",
            ),
        ]
    )
    session.commit()

    @contextmanager
    def test_session_scope():
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise

    monkeypatch.setattr(platform_access, "session_scope", test_session_scope)
    user_profile = SimpleNamespace(
        user=SimpleNamespace(
            id="user-2",
            username="user",
            nickname="普通用户",
            email="user@example.com",
        )
    )

    granted = set_admin_role(
        session,
        user_id="user-2",
        enabled=True,
        actor=_admin(),
        immutable_admin_ids=(),
    )
    session.flush()
    assert granted == {"userId": "user-2", "isAdmin": True}
    assert (
        platform_access.actor_from_profile(
            user_profile,
            initial_admin_ids=(),
            auth_enabled=True,
        ).is_admin
        is True
    )

    revoked = set_admin_role(
        session,
        user_id="user-2",
        enabled=False,
        actor=_admin(),
        immutable_admin_ids=(),
    )
    session.flush()
    assert revoked == {"userId": "user-2", "isAdmin": False}
    assert (
        platform_access.actor_from_profile(
            user_profile,
            initial_admin_ids=(),
            auth_enabled=True,
        ).is_admin
        is False
    )
    assert session.scalar(
        select(PlatformUserRole.id).where(
            PlatformUserRole.user_id == "admin-1",
            PlatformUserRole.role_code == "platform_admin",
        )
    )


def test_local_development_login_is_recorded_in_member_table(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _session()

    @contextmanager
    def test_session_scope():
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise

    monkeypatch.setattr(platform_access, "session_scope", test_session_scope)
    actor = platform_access.actor_from_profile(
        SimpleNamespace(
            user=SimpleNamespace(
                id="local-dev",
                username="local-dev",
                nickname="本地开发用户",
                email="",
            )
        ),
        initial_admin_ids=(),
        auth_enabled=False,
    )

    assert actor.is_admin is True
    assert session.get(PlatformUser, "local-dev") is not None


def test_bootstrap_promotes_only_first_login_once(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _session()
    session.add(
        PlatformUser(
            user_id="legacy-user",
            username="legacy",
            nickname="已有开发账号",
            email="legacy@example.com",
        )
    )
    session.commit()

    @contextmanager
    def test_session_scope():
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise

    monkeypatch.setattr(platform_access, "session_scope", test_session_scope)

    first = platform_access.actor_from_profile(
        SimpleNamespace(
            user=SimpleNamespace(
                id="first-login",
                username="first",
                nickname="首位登录者",
                email="first@example.com",
            )
        ),
        initial_admin_ids=(),
        auth_enabled=True,
        bootstrap_first_admin=True,
    )
    later = platform_access.actor_from_profile(
        SimpleNamespace(
            user=SimpleNamespace(
                id="new-user",
                username="new",
                nickname="后续账号",
                email="new@example.com",
            )
        ),
        initial_admin_ids=(),
        auth_enabled=True,
        bootstrap_first_admin=True,
    )

    admin_ids = set(
        session.scalars(
            select(PlatformUserRole.user_id).where(PlatformUserRole.role_code == "platform_admin")
        )
    )
    assert first.is_admin is True
    assert later.is_admin is False
    assert admin_ids == {"first-login"}


@pytest.mark.asyncio
async def test_normal_user_cannot_pass_admin_dependency() -> None:
    actor = PlatformActor(
        user_id="user-1",
        username="user-1",
        display_name="普通用户",
        email="",
        is_admin=False,
    )

    with pytest.raises(HTTPException) as exc_info:
        await require_platform_admin(actor)

    assert exc_info.value.status_code == 403
