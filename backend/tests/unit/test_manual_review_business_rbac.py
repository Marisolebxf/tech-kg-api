"""Review authorization must follow the persisted space, including warm caches."""

from __future__ import annotations

import json

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.requests import Request

from biz.dependencies.review_identity import get_review_identity
from db_model.base import Base
from db_model.business_access import BusinessClient, BusinessGraphSpace
from db_model.manual_review import ReviewCase
from service import business_access_control as access
from service.manual_review_domain import ReviewForbiddenError
from service.manual_review_production import ManualReviewService
from service.platform_access import PlatformActor


def identity(business="a", role="developer", *, restricted=False):
    actor = PlatformActor(
        user_id=f"{business}-{role}",
        username="reviewer",
        display_name="Reviewer",
        email="",
        is_admin=role == "admin",
        business_id=business,
        business_role=role,
        business_only=restricted,
    )
    request = Request(
        {
            "type": "http",
            "headers": [(b"x-user-roles", b"review_admin"), (b"x-user-id", b"forged")],
        }
    )
    return get_review_identity(request, actor)


@pytest.fixture
def review_service(monkeypatch):
    from service import manual_review_production
    from service.graph_space import GraphSpaceService

    monkeypatch.setenv("BUSINESS_RBAC_ENABLED", "true")
    engine = create_engine(
        "sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    sf = sessionmaker(engine, expire_on_commit=False)
    with sf() as session:
        session.add_all([BusinessClient(client_id=x, name=x) for x in ("a", "b")])
        session.add_all(
            [
                BusinessGraphSpace(space_name="space_a", client_id="a"),
                BusinessGraphSpace(space_name="space_b", client_id="b"),
                BusinessGraphSpace(space_name="production", is_shared_production=True),
            ]
        )
        session.commit()
    monkeypatch.setattr(access, "session_scope", sf)
    monkeypatch.setattr(
        GraphSpaceService, "_all_spaces", lambda self: ["space_a", "space_b", "production"]
    )
    monkeypatch.setattr(manual_review_production, "resolve_job_ids", lambda values: {})
    return ManualReviewService(sf)


def create_case(service, space, **overrides):
    values = {
        "task_id": "task",
        "execution_id": "execution",
        "step_id": "align",
        "kind": "entity",
        "candidate": {"id": f"object-{space}", "name": "example"},
        "template_id": "T_LINK",
        "graph_space": space,
    }
    values.update(overrides)
    return service.create_direct_case(**values)["reviewId"]


def test_trusted_identity_ignores_browser_roles(review_service):
    developer = identity()
    assert developer.user_id == "a-developer"
    assert developer.roles == frozenset({"reviewer"})
    with pytest.raises(HTTPException) as denied:
        identity(role="user")
    assert denied.value.status_code == 403
    with pytest.raises(HTTPException):
        identity(role="admin", restricted=True)


def test_queue_view_scope_includes_shared_readonly(review_service):
    for space in ("space_a", "space_b", "production", None):
        create_case(review_service, space)
    # 开发维护查看档=业务空间+共享生产空间；共享空间行只读（canOperate=False）
    own = review_service.list_cases({}, identity())
    assert own["total"] == 2
    operate = {item["graphSpace"]: item["canOperate"] for item in own["items"]}
    assert operate == {"space_a": True, "production": False}
    admin = review_service.list_cases({}, identity(role="admin"))
    assert admin["total"] == 3
    assert all(item["canOperate"] for item in admin["items"])


def test_queue_graph_space_filter_intersects_rbac_spaces(review_service):
    # 队列页跟随图空间选择：graph_space 过滤与查看档集合 AND 相交，
    # 请求未授权空间得到空列表而非报错（不额外 403）
    for space in ("space_a", "space_b", "production"):
        create_case(review_service, space)
    own = review_service.list_cases({"graph_space": "space_a"}, identity())
    assert own["total"] == 1
    assert own["items"][0]["graphSpace"] == "space_a"
    # 共享空间：查看档可见（只读行）
    shared = review_service.list_cases({"graph_space": "production"}, identity())
    assert shared["total"] == 1
    assert shared["items"][0]["canOperate"] is False
    assert review_service.list_cases({"graph_space": "space_b"}, identity())["total"] == 0
    admin = review_service.list_cases({"graph_space": "space_b"}, identity(role="admin"))
    assert admin["total"] == 1


@pytest.mark.parametrize("space", ["space_b", "production", None])
@pytest.mark.parametrize(
    "operation",
    [
        "claim",
        "heartbeat",
        "release",
        "transfer",
        "draft",
        "submit",
        "direct",
        "cancel",
        "delete",
        "evidence",
    ],
)
def test_every_case_operation_rejects_unreviewable_space(review_service, space, operation):
    case_id = create_case(review_service, space)
    actor = identity()
    operations = {
        "claim": lambda: review_service.claim(case_id, 1, actor),
        "heartbeat": lambda: review_service.heartbeat(case_id, 1, actor),
        "release": lambda: review_service.release(case_id, 1, actor),
        "transfer": lambda: review_service.transfer(case_id, 1, "target", "Target", actor),
        "draft": lambda: review_service.draft(case_id, 1, {}, actor),
        "submit": lambda: review_service.submit(case_id, 1, "reject-candidate", {}, "", actor),
        "direct": lambda: review_service.direct_decide(case_id, 1, False, "", actor),
        "cancel": lambda: review_service.cancel(case_id, 1, "", actor),
        "delete": lambda: review_service.delete_case(case_id, actor),
        "evidence": lambda: review_service.evidence_upload(
            case_id, "a.pdf", "application/pdf", 1, "a" * 64, actor
        ),
    }
    with pytest.raises((HTTPException, ReviewForbiddenError)):
        operations[operation]()
    with review_service.sf() as session:
        row = session.get(ReviewCase, case_id)
        assert row.status == "OPEN"
        assert row.version == 1


@pytest.mark.parametrize(
    "space,viewable,operable",
    [
        ("space_a", True, True),
        ("production", True, False),
        ("space_b", False, False),
        (None, False, False),
    ],
)
def test_detail_and_logs_follow_view_tier(review_service, space, viewable, operable):
    """读路径（detail/logs）按查看档：共享空间可见只读；操作档仍只认业务空间。"""
    case_id = create_case(review_service, space)
    developer = identity()
    if viewable:
        detail = review_service.get_case(case_id, developer)
        assert detail["canOperate"] is operable
        review_service.logs(case_id, developer)
    else:
        with pytest.raises((HTTPException, ReviewForbiddenError)):
            review_service.get_case(case_id, developer)
        with pytest.raises((HTTPException, ReviewForbiddenError)):
            review_service.logs(case_id, developer)


def test_developer_reviews_own_space_and_admin_reviews_production(review_service):
    private_case = create_case(review_service, "space_a")
    production_case = create_case(review_service, "production")
    result = review_service.submit(private_case, 1, "reject-candidate", {}, "", identity())
    assert result["status"] == "RESOLVED"
    result = review_service.submit(
        production_case, 1, "reject-candidate", {}, "", identity(role="admin")
    )
    assert result["status"] == "RESOLVED"


def test_batch_rerun_rejects_mixed_space_before_any_work(review_service):
    allowed = create_case(
        review_service, "space_a", template_id="T_EXTRACT_FAIL", source_record_id="1"
    )
    denied = create_case(
        review_service, "production", template_id="T_EXTRACT_FAIL", source_record_id="2"
    )
    assert review_service.authorize_rerun(identity(), case_ids=[allowed]) == [allowed]
    with pytest.raises(HTTPException):
        review_service.authorize_rerun(identity(), case_ids=[allowed, denied])
    with pytest.raises(HTTPException):
        review_service.authorize_rerun(identity(), execution_id="execution")


async def test_warm_detail_cache_does_not_bypass_space_reassignment(review_service, monkeypatch):
    from biz.handler import manual_review as handler

    monkeypatch.setattr(handler, "production_service", review_service)
    handler._queue_cache_clear()
    case_id = create_case(review_service, "space_a")
    actor = identity()
    response = await handler.production_detail(case_id, actor)
    assert json.loads(response.body)["data"]["id"] == case_id
    # 移到他人业务空间（查看档也不可见）后热缓存不得放行；移共享空间则只读可见
    with review_service.sf() as session:
        session.get(ReviewCase, case_id).graph_space = "space_b"
        session.commit()
    with pytest.raises(HTTPException) as denied:
        await handler.production_detail(case_id, actor)
    assert denied.value.status_code == 403
    handler._queue_cache_clear()


def test_unknown_historical_space_cannot_fall_back_to_default(review_service):
    case_id = create_case(review_service, None)
    with pytest.raises(ReviewForbiddenError):
        review_service.get_case(case_id, identity(role="admin"))


def test_unknown_named_space_cannot_be_reviewed_by_admin(review_service):
    case_id = create_case(review_service, "missing_space")
    with pytest.raises(ReviewForbiddenError):
        review_service.get_case(case_id, identity(role="admin"))


async def test_queue_rechecks_rows_after_direct_sql_move(review_service, monkeypatch):
    import inspect

    from biz.handler import manual_review as handler

    monkeypatch.setattr(handler, "production_service", review_service)
    handler._queue_cache_clear()
    case_id = create_case(review_service, "space_a")
    arguments = {
        key: parameter.default.default
        if hasattr(parameter.default, "default")
        else parameter.default
        for key, parameter in inspect.signature(handler.production_queue).parameters.items()
        if key != "identity"
    }
    actor = identity()
    response = await handler.production_queue(actor, **arguments)
    assert json.loads(response.body)["data"]["total"] == 1
    with review_service.sf() as session:
        # 移到他人业务空间：查看档也不可见，队列即时收敛（共享空间则只读可见）
        session.get(ReviewCase, case_id).graph_space = "space_b"
        session.commit()
    response = await handler.production_queue(actor, **arguments)
    assert json.loads(response.body)["data"]["total"] == 0


async def test_admin_cached_detail_and_logs_cannot_leak_to_developer(review_service, monkeypatch):
    from biz.handler import manual_review as handler

    monkeypatch.setattr(handler, "production_service", review_service)
    handler._queue_cache_clear()
    # 他人业务空间的 case 对开发维护两级都不可见（共享空间已改为只读可见，测不出隔离）
    case_id = create_case(review_service, "space_b")
    for endpoint in (handler.production_detail, handler.case_audit_logs):
        await endpoint(case_id, identity(role="admin"))
        with pytest.raises(HTTPException) as denied:
            await endpoint(case_id, identity())
        assert denied.value.status_code == 403


def test_evidence_complete_cannot_attach_another_cases_object(review_service, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import Mock

    case_id = create_case(review_service, "space_a")
    client = Mock()
    monkeypatch.setattr(
        review_service, "storage", lambda: SimpleNamespace(bucket="evidence", client=client)
    )
    with pytest.raises(ReviewForbiddenError):
        review_service.evidence_complete(
            case_id,
            {
                "evidenceId": "EVD-1",
                "fileName": "a.pdf",
                "bucket": "evidence",
                "objectKey": "other_case/EVD-1/a.pdf",
            },
            identity(),
        )
    client.head_object.assert_not_called()


@pytest.mark.parametrize("role,business", [("user", "a"), ("developer", "b")])
def test_transfer_rejects_target_without_review_permission(
    review_service, monkeypatch, role, business
):
    from db_model.business_access import BusinessMember
    from db_model.platform_governance import PlatformUser
    from infra import mysql

    monkeypatch.setattr(mysql, "session_scope", review_service.sf)
    with review_service.sf() as session:
        session.add(PlatformUser(user_id="target", username="target"))
        session.add(BusinessMember(user_id="target", client_id=business, role=role))
        session.commit()
    case_id = create_case(review_service, "space_a")
    with pytest.raises(HTTPException):
        review_service.transfer(case_id, 1, "target", "Target", identity())
    with review_service.sf() as session:
        row = session.get(ReviewCase, case_id)
        assert row.assignee_id is None and row.version == 1


def test_transfer_to_same_business_developer(review_service, monkeypatch):
    from db_model.business_access import BusinessMember
    from db_model.platform_governance import PlatformUser
    from infra import mysql

    monkeypatch.setattr(mysql, "session_scope", review_service.sf)
    with review_service.sf() as session:
        session.add(PlatformUser(user_id="target", username="target"))
        session.add(BusinessMember(user_id="target", client_id="a", role="developer"))
        session.commit()
    case_id = create_case(review_service, "space_a")
    result = review_service.transfer(case_id, 1, "target", "Target", identity())
    assert result["assigneeId"] == "target"


def test_direct_accept_uses_persisted_space_not_candidate_metadata(review_service, monkeypatch):
    from infra import graph_db

    case_id = create_case(
        review_service,
        "space_a",
        template_id="T_DIRECT",
        node_label="Expert",
        candidate={"id": "item", "_graphSpace": "production"},
    )
    seen = []

    def stop_at_graph_client(space):
        seen.append(space)
        raise RuntimeError("stop before graph mutation")

    monkeypatch.setattr(graph_db, "get_space_client", stop_at_graph_client)
    with pytest.raises(RuntimeError, match="stop before graph mutation"):
        review_service.direct_decide(
            case_id, 1, True, "", identity(), {"id": "item", "_graphSpace": "production"}
        )
    assert seen == ["space_a"]
