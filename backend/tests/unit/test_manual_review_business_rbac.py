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


def test_queue_filters_business_and_shared_production(review_service):
    for space in ("space_a", "space_b", "production", None):
        create_case(review_service, space)
    own = review_service.list_cases({}, identity())
    assert own["total"] == 1
    assert [item["graphSpace"] for item in own["items"]] == ["space_a"]
    admin = review_service.list_cases({}, identity(role="admin"))
    assert admin["total"] == 3


def test_queue_graph_space_filter_intersects_rbac_spaces(review_service):
    # 队列页跟随图空间选择：graph_space 过滤与授权空间集合 AND 相交，
    # 请求未授权空间得到空列表而非报错（不额外 403）
    for space in ("space_a", "space_b", "production"):
        create_case(review_service, space)
    own = review_service.list_cases({"graph_space": "space_a"}, identity())
    assert own["total"] == 1
    assert own["items"][0]["graphSpace"] == "space_a"
    assert review_service.list_cases({"graph_space": "space_b"}, identity())["total"] == 0
    admin = review_service.list_cases({"graph_space": "space_b"}, identity(role="admin"))
    assert admin["total"] == 1


@pytest.mark.parametrize("space", ["space_b", "production", None])
@pytest.mark.parametrize(
    "operation", ["detail", "claim", "draft", "submit", "cancel", "delete", "logs"]
)
def test_every_case_operation_rejects_unreviewable_space(review_service, space, operation):
    case_id = create_case(review_service, space)
    actor = identity()
    operations = {
        "detail": lambda: review_service.get_case(case_id, actor),
        "claim": lambda: review_service.claim(case_id, 1, actor),
        "draft": lambda: review_service.draft(case_id, 1, {}, actor),
        "submit": lambda: review_service.submit(case_id, 1, "reject-candidate", {}, "", actor),
        "cancel": lambda: review_service.cancel(case_id, 1, "", actor),
        "delete": lambda: review_service.delete_case(case_id, actor),
        "logs": lambda: review_service.logs(case_id, actor),
    }
    with pytest.raises((HTTPException, ReviewForbiddenError)):
        operations[operation]()
    with review_service.sf() as session:
        row = session.get(ReviewCase, case_id)
        assert row.status == "OPEN"
        assert row.version == 1


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
    with review_service.sf() as session:
        session.get(ReviewCase, case_id).graph_space = "production"
        session.commit()
    with pytest.raises(HTTPException) as denied:
        await handler.production_detail(case_id, actor)
    assert denied.value.status_code == 403
    handler._queue_cache_clear()


def test_unknown_historical_space_cannot_fall_back_to_default(review_service):
    case_id = create_case(review_service, None)
    with pytest.raises(ReviewForbiddenError):
        review_service.get_case(case_id, identity(role="admin"))


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
