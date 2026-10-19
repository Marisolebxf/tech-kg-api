"""12f33156 review probe: an in-flight INSERT outlives the sync VID lease.

Run from the backend directory of that fix branch with its test dependencies:
python -m pytest <absolute-path-to-this-file> -q

Uses only the branch's MockTransport, in-memory graph and fake Redis. No server
or database connection is needed. On 12f33156 the final assertion should FAIL:
the later writer's paper_nums=999 is overwritten by the stale value 210.
"""

from types import SimpleNamespace
import json

from tests.unit import test_manual_review_merge_property_loss as support
from service import entity_write_guard as guard
from service.manual_review_production import ManualReviewService


def test_inflight_insert_preserves_later_writer(monkeypatch):
    clock = support.FakeClock()
    store = support.FakeSyncRedis(clock)
    monkeypatch.setattr(guard, "_sync_client", store)
    monkeypatch.setattr(guard, "_monotonic", clock)
    monkeypatch.setenv("ENTITY_DISAMBIGUATION_NAME_LOCK_TTL_SECONDS", "5")
    monkeypatch.setenv("ENTITY_WRITE_VID_LOCK_ENABLED", "1")
    service = object.__new__(ManualReviewService)
    graph = support.FakeTRSREST(
        existing={support.TARGET_VID: dict(support.TARGET_PROPS)}
    )
    support._install_graph(service, monkeypatch, graph)
    client = service._graph_client_for({})
    commit = graph._apply_insert

    def delayed_commit(query):
        # A has passed ensure_lease and dispatched its actual graph request.
        # Redis stays healthy, but no heartbeat runs during the in-flight write.
        clock.advance(6)
        with guard.vid_write_lock_sync("dev2", "Person", support.TARGET_VID) as lease:
            lease.ensure_lease()
            props = {**graph.state[support.TARGET_VID], "paper_nums": 999}
            cols = ", ".join(f"`{key}`" for key in props)
            vals = ", ".join(json.dumps(v, ensure_ascii=False) for v in props.values())
            commit(
                f"INSERT VERTEX `Person`({cols}) VALUES "
                f"{json.dumps(support.TARGET_VID)}:({vals})"
            )
        commit(query)  # A's earlier request finally reaches its commit point.

    graph._apply_insert = delayed_commit
    snapshot = support._link_kwargs()["candidate"]
    try:
        service._insert_withheld_vertex(
            client,
            SimpleNamespace(object_name="review-probe"),
            {**snapshot, "_nodeLabel": "Person"},
            snapshot["_incoming"],
            support.TARGET_VID,
            "dev2",
        )
    finally:
        client.close()
    assert graph.state[support.TARGET_VID]["paper_nums"] == 999
