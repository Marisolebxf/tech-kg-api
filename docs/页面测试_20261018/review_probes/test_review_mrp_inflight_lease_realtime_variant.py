"""ca0847ca review probe: realtime variant of test_review_mrp_inflight_lease.py.

Run from the backend directory of the fix branch with its test dependencies:
python -m pytest <absolute-path-to-this-file> -q

The original probe advances the fake clock by 6s in a single instant while the
writer thread is blocked inside its graph request. A real heartbeat thread
sleeps on REAL time, so an instant fake jump gives it no scheduling
opportunity at all — the "instant clock jump" trap (a healthy heartbeat must
not be declared failed because real time never passed). This variant keeps the
original's end-state assertion but gives the in-flight window real duration:

  * a background ticker keeps adding fake-clock offset while real time flows
    (FakeClock = real monotonic + offset, so the fake clock runs FASTER than
    wall time — not strictly 1:1; irrelevant to the assertions: the TTL budget
    is burned deterministically by advance(4.5) and the heartbeat waits on
    REAL Event.wait intervals),
  * 4.5s of the 5s TTL budget is burned up front (with no renewal the lease
    MUST expire inside the flight — that is exactly the 12f33156 defect shape),
  * writer B runs on a REAL thread and keeps trying to take the same-key lock
    (short acquire wait) while A's INSERT is gated on a REAL event,
  * the heartbeat interval is shrunk to 0.1s via env so several renewal
    periods fit inside the gated flight.

Expected:
  * 12f33156 (boundary renewal only, no heartbeat): FAIL — B takes the lock
    mid-flight (b_got_lock_inflight=True), writes paper_nums=999, then A's
    stale snapshot lands afterwards; final value is 210.
  * ca0847ca (heartbeat thread): PASS — the heartbeat keeps the lease alive
    through the whole flight, B is blocked (b_attempts>=1, never acquired
    in-flight), A lands and releases, only then B takes the lock; B's write
    merges over the current state so A's earlier columns survive and the
    final paper_nums is 999.
"""

import json
import threading
import time
from types import SimpleNamespace

from tests.unit import test_manual_review_merge_property_loss as support
from service import entity_write_guard as guard
from service.manual_review_production import ManualReviewService


def test_inflight_insert_preserves_later_writer_realtime(monkeypatch):
    clock = support.FakeClock()
    store = support.FakeSyncRedis(clock)
    monkeypatch.setattr(guard, "_sync_client", store)
    monkeypatch.setattr(guard, "_monotonic", clock)
    monkeypatch.setenv("ENTITY_DISAMBIGUATION_NAME_LOCK_TTL_SECONDS", "5")
    monkeypatch.setenv("ENTITY_WRITE_VID_LOCK_ENABLED", "1")
    monkeypatch.setenv("ENTITY_WRITE_VID_LOCK_HEARTBEAT_SECONDS", "0.1")
    monkeypatch.setenv("ENTITY_WRITE_VID_LOCK_WAIT_SECONDS", "0.4")
    service = object.__new__(ManualReviewService)
    graph = support.FakeTRSREST(
        existing={support.TARGET_VID: dict(support.TARGET_PROPS)}
    )
    support._install_graph(service, monkeypatch, graph)
    client = service._graph_client_for({})
    commit = graph._apply_insert

    # keep the fake clock flowing alongside real time (real base + added
    # offset, so faster than wall time — see module docstring) so lease expiry
    # / acquire deadlines still fire while the heartbeat thread gets real
    # scheduling opportunities
    ticker_stop = threading.Event()

    def ticker() -> None:
        while not ticker_stop.wait(0.05):
            clock.advance(0.05)

    threading.Thread(target=ticker, name="probe-fake-clock-ticker", daemon=True).start()

    a_applied = threading.Event()     # set the moment A's INSERT commits
    b_done = threading.Event()
    report: dict = {"b_attempts": 0, "b_got_lock_inflight": False}

    def writer_b() -> None:
        # B (a REAL second writer) keeps trying to take the same-key lock.
        # While A's INSERT is in flight (not yet applied) every attempt must
        # fail; only after A lands and releases may B acquire and write 999.
        try:
            while True:
                try:
                    with guard.vid_write_lock_sync("dev2", "Person", support.TARGET_VID) as lease:
                        lease.ensure_lease()
                        report["b_got_lock_inflight"] = not a_applied.is_set()
                        props = {**graph.state[support.TARGET_VID], "paper_nums": 999}
                        cols = ", ".join(f"`{key}`" for key in props)
                        vals = ", ".join(json.dumps(v, ensure_ascii=False) for v in props.values())
                        commit(
                            f"INSERT VERTEX `Person`({cols}) VALUES "
                            f"{json.dumps(support.TARGET_VID)}:({vals})"
                        )
                        return
                except TimeoutError:
                    report["b_attempts"] += 1
        finally:
            b_done.set()

    def delayed_commit(query):
        # A has passed ensure_lease and dispatched its actual graph request.
        # Burn 4.5s of the 5s TTL budget at once (no real time passes yet),
        # then hold the INSERT for 1.2s of REAL time — long enough for ≥2
        # heartbeat renewal periods (interval 0.1s) and several failed B
        # attempts. Without a heartbeat the lease is dead within ~0.5s of
        # (fake == real) time and B MUST take it mid-flight.
        clock.advance(4.5)
        b_thread = threading.Thread(target=writer_b, name="probe-writer-b")
        b_thread.start()
        time.sleep(1.2)  # hold A's INSERT for 1.2s of REAL in-flight time
        commit(query)  # A's earlier request finally reaches its commit point.
        a_applied.set()
        b_done.wait(3.0)
        b_thread.join(5)

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
        a_applied.set()  # safety on early failure: stop classifying as in-flight
        b_done.wait(3.0)
        ticker_stop.set()
        client.close()
    assert report["b_attempts"] >= 1, report  # B really contended in-flight
    assert not report["b_got_lock_inflight"], report  # mutual exclusion held
    assert graph.state[support.TARGET_VID]["paper_nums"] == 999, report
