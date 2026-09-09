"""Offline regressions for execution-plan integrity boundaries."""

from pathlib import Path
from unittest.mock import Mock

import bench_runbook
import hardware_action_executor as executor
import hardware_action_plan as planner
import pytest
import runtime_context


def test_action_flags_cannot_remove_confirmation(tmp_path: Path):
    plan = planner.plan_action(tmp_path, action="build", backend="fake")
    plan["controlled_local_action"] = False
    plan["hardware_side_effect"] = False

    result = executor.execute_plan(plan, token="")

    assert result["status"] == "blocked-confirmation-required"
    assert result["executed"] is False


@pytest.mark.parametrize("change_record", [False, True])
def test_confirmed_plan_cannot_change_workspace(tmp_path: Path, change_record: bool):
    original = tmp_path / "original"
    other = tmp_path / "other"
    original.mkdir()
    other.mkdir()
    plan = planner.plan_action(original, action="build", backend="fake")
    plan["root"] = str(other)
    if change_record:
        plan["confirmation_record"]["root"] = str(other)

    result = executor.execute_plan(plan, token=plan["confirmation_token"])

    assert result["status"].startswith("blocked-")
    assert result["executed"] is False
    assert not (other / ".embeddedskills").exists()


def test_backend_override_cannot_upgrade_fake_plan(tmp_path: Path, monkeypatch):
    plan = planner.plan_action(tmp_path, action="build", backend="fake")
    build = Mock(return_value={"status": "ok", "executed": True})
    monkeypatch.setattr(executor, "execute_workflow_build", build)

    result = executor.execute_plan(plan, token=plan["confirmation_token"], backend="workflow-build")

    assert result["status"] == "blocked-backend-mismatch"
    build.assert_not_called()


def test_runbook_rejects_untrusted_interpreter():
    script = runtime_context.embeddedskills_root() / "workflow/scripts/workflow_run.py"

    assert not bench_runbook.argv_uses_trusted_workflow_run(["untrusted-python", str(script), "--dry-run", "--json"])
