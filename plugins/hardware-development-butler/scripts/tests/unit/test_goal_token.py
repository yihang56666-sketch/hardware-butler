"""Unit tests for goal_token — workflow_id-bound, multi-use, time-limited token."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, "tools")
sys.path.insert(0, "embeddedskills")

import safety_gate as sg  # noqa: E402


def test_mint_goal_token_returns_hash_and_plaintext() -> None:
    record = sg.mint_goal_token(workflow_id="wf-1", scope="build-flash", max_uses=3, ttl_seconds=60)
    assert record["token"].startswith("hwg1-")
    assert len(record["token_hash"]) == 64
    assert record["workflow_id"] == "wf-1"
    assert record["scope"] == "build-flash"
    assert record["max_uses"] == 3
    assert "expires_at" in record


def test_check_goal_token_allows_first_use(tmp_path: Path) -> None:
    record = sg.mint_goal_token(workflow_id="wf-2", scope="build-flash", max_uses=3, ttl_seconds=60)
    result = sg.check_goal_token(tmp_path, workflow_id="wf-2", token=record["token"], record=record, action="build-flash", consume=True)
    assert result["allowed"] is True
    assert result["uses"] == 0


def test_check_goal_token_counts_uses(tmp_path: Path) -> None:
    record = sg.mint_goal_token(workflow_id="wf-3", scope="build-flash", max_uses=3, ttl_seconds=60)
    for _ in range(3):
        r = sg.check_goal_token(tmp_path, workflow_id="wf-3", token=record["token"], record=record, action="build-flash", consume=True)
        assert r["allowed"] is True
    exhausted = sg.check_goal_token(tmp_path, workflow_id="wf-3", token=record["token"], record=record, action="build-flash", consume=True)
    assert exhausted["allowed"] is False
    assert exhausted["error_code"] == "exhausted"


def test_check_goal_token_blocks_cross_workflow(tmp_path: Path) -> None:
    record = sg.mint_goal_token(workflow_id="wf-A", scope="build-flash", max_uses=3, ttl_seconds=60)
    result = sg.check_goal_token(tmp_path, workflow_id="wf-B", token=record["token"], record=record, action="build-flash")
    assert result["allowed"] is False
    assert result["error_code"] == "cross_workflow"


def test_check_goal_token_blocks_out_of_scope(tmp_path: Path) -> None:
    record = sg.mint_goal_token(workflow_id="wf-4", scope="build-flash,flash-debug", max_uses=3, ttl_seconds=60)
    result = sg.check_goal_token(tmp_path, workflow_id="wf-4", token=record["token"], record=record, action="erase-chip")
    assert result["allowed"] is False
    assert result["error_code"] == "out_of_scope"


def test_check_goal_token_blocks_expired() -> None:
    record = sg.mint_goal_token(workflow_id="wf-5", scope="build-flash", max_uses=3, ttl_seconds=1)
    expired_record = {**record, "expires_at": "2020-01-01T00:00:00+00:00"}
    with tempfile.TemporaryDirectory() as tmp:
        result = sg.check_goal_token(Path(tmp), workflow_id="wf-5", token=record["token"], record=expired_record, action="build-flash")
    assert result["allowed"] is False
    assert result["error_code"] == "expired"


def test_check_goal_token_blocks_invalid_token(tmp_path: Path) -> None:
    record = sg.mint_goal_token(workflow_id="wf-6", scope="build-flash", max_uses=3, ttl_seconds=60)
    result = sg.check_goal_token(tmp_path, workflow_id="wf-6", token="hwg1-wrongtoken", record=record, action="build-flash")
    assert result["allowed"] is False
    assert result["error_code"] == "invalid_token"


def test_check_goal_token_no_consume_does_not_increment(tmp_path: Path) -> None:
    record = sg.mint_goal_token(workflow_id="wf-7", scope="build-flash", max_uses=2, ttl_seconds=60)
    sg.check_goal_token(tmp_path, workflow_id="wf-7", token=record["token"], record=record, action="build-flash", consume=False)
    sg.check_goal_token(tmp_path, workflow_id="wf-7", token=record["token"], record=record, action="build-flash", consume=False)
    r = sg.check_goal_token(tmp_path, workflow_id="wf-7", token=record["token"], record=record, action="build-flash", consume=False)
    assert r["allowed"] is True
    assert r["uses"] == 0


def test_mint_goal_token_rejects_invalid_args() -> None:
    import pytest
    with pytest.raises(ValueError):
        sg.mint_goal_token(workflow_id="", scope="x", max_uses=1, ttl_seconds=1)
    with pytest.raises(ValueError):
        sg.mint_goal_token(workflow_id="wf", scope="x", max_uses=0, ttl_seconds=1)
    with pytest.raises(ValueError):
        sg.mint_goal_token(workflow_id="wf", scope="x", max_uses=1, ttl_seconds=0)
