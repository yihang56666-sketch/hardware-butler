"""Regression tests for Phase 16 audit-discovered bugs in hardware_action_audit.

Covers:
- consume_token atomicity (TOCTOU fix): check+write now happen under the
  same lock, so two concurrent calls with the same token cannot both succeed.
- append_event cross-process safety: uses true append mode (open("a"))
  instead of read-modify-rewrite, so concurrent appends don't lose entries.
"""

from __future__ import annotations

import sys
import threading
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "tools"))

import hardware_action_audit as audit  # noqa: E402


def _make_plan(*, token: str = "test-token-123", action: str = "build-flash") -> dict[str, object]:
    return {
        "action": action,
        "confirmation_record": {"plan_id": "plan-001"},
        "hardware_side_effect": True,
        "controlled_local_action": False,
    }


def test_consume_token_succeeds_on_first_call(tmp_path: Path) -> None:
    """First consume of a token must succeed and record the event."""
    plan = _make_plan()
    result = audit.consume_token(tmp_path, token="abc-123", plan=plan, backend="probe-rs")
    assert result["status"] == "ok"
    assert result["consumed"] is True
    assert result["token_hash"]


def test_consume_token_blocks_replay_on_second_call(tmp_path: Path) -> None:
    """Second consume of the same token must be blocked as token-replay."""
    plan = _make_plan()
    audit.consume_token(tmp_path, token="abc-123", plan=plan, backend="probe-rs")
    result = audit.consume_token(tmp_path, token="abc-123", plan=plan, backend="probe-rs")
    assert result["status"] == "blocked-token-replay"
    assert result["consumed"] is False


def test_consume_token_atomic_under_concurrent_threads(tmp_path: Path) -> None:
    """Two threads calling consume_token with the same token concurrently:
    exactly one must succeed, the other must be blocked. The previous
    implementation had a TOCTOU race where both could pass is_token_consumed
    before either wrote. The fix acquires the lock across check+write."""
    plan = _make_plan()
    results: list[dict[str, object]] = []
    results_lock = threading.Lock()
    barrier = threading.Barrier(2)

    def consume():
        barrier.wait()  # ensure both threads hit consume_token simultaneously
        r = audit.consume_token(tmp_path, token="race-token", plan=plan, backend="probe-rs")
        with results_lock:
            results.append(r)

    t1 = threading.Thread(target=consume)
    t2 = threading.Thread(target=consume)
    t1.start()
    t2.start()
    t1.join(timeout=5)
    t2.join(timeout=5)

    assert len(results) == 2
    statuses = sorted(r["status"] for r in results)
    # Exactly one ok + one blocked-token-replay.
    assert statuses == ["blocked-token-replay", "ok"], statuses


def test_append_event_uses_true_append_mode(tmp_path: Path) -> None:
    """append_event must use open('a') (true append), not read-modify-rewrite.
    Two concurrent appends must both land in the log — no lost entries."""
    barrier = threading.Barrier(4)
    threads: list[threading.Thread] = []

    def append_one(i: int):
        barrier.wait()
        audit.append_event(tmp_path, {"event": "test", "index": i})

    for i in range(4):
        threads.append(threading.Thread(target=append_one, args=(i,)))
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)

    events = audit.read_events(tmp_path)
    # All 4 entries must be present — no lost writes.
    assert len(events) == 4, f"expected 4 events, got {len(events)}: {events}"
    indices = sorted(e["index"] for e in events)
    assert indices == [0, 1, 2, 3]


def test_append_event_preserves_existing_entries(tmp_path: Path) -> None:
    """Appending after entries exist must not overwrite the existing entries."""
    audit.append_event(tmp_path, {"event": "first"})
    audit.append_event(tmp_path, {"event": "second"})
    events = audit.read_events(tmp_path)
    assert len(events) == 2
    assert events[0]["event"] == "first"
    assert events[1]["event"] == "second"
