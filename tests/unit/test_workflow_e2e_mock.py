"""Offline end-to-end mock workflow and fail-closed physical mode tests.

The default simulated workflow completes its nine stages. A physical request
must stop at the execution boundary rather than reusing mock authorization.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.path.insert(0, "tools")

import workflow_runner as wr  # noqa: E402


def _copy_fixture(src: Path, tmp_path: Path) -> Path:
    """Copy fixture into a repo-local temp dir (safe_io refuses writes outside repo)."""
    scratch_root = Path(__file__).resolve().parents[2] / ".tmp-wf-tests"
    dst = scratch_root / tmp_path.name / "project"
    if dst.exists():
        shutil.rmtree(dst, ignore_errors=True)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst)
    evidence_path = dst / ".hardware-butler" / "datasheet-evidence.json"
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(
        '{"part": "STM32F407VGTx", "sources": [{"url": "stub", "title": "stub", "type": "manual"}], '
        '"summary": {"has_reference_manual": true}, "evidence_status": "evidence-collected"}'
    )
    return dst


def test_e2e_mock_mode_all_9_stages_complete(cubemx_basic_fixture: Path, tmp_path: Path) -> None:
    """End-to-end workflow in mock mode must complete all 9 stages."""
    project = _copy_fixture(cubemx_basic_fixture, tmp_path)
    ctx = wr.WorkflowContext(feature="led-blink", pin="PD12", function="gpio-output")
    state = wr.init_workflow(project, intent="develop-feature", goal="LED blink on PD12", context=ctx)
    result = wr.run_workflow(project, state)

    assert result["status"] == "completed"
    assert result["current_stage"] == ""
    assert len(result["stages"]) == 9
    assert all(s["status"] == "completed" for s in result["stages"]), [
        (s["id"], s["status"]) for s in result["stages"]
    ]


def test_e2e_mock_mode_produces_firmware_files(cubemx_basic_fixture: Path, tmp_path: Path) -> None:
    """End-to-end mock-mode workflow must produce real .c/.h firmware files."""
    project = _copy_fixture(cubemx_basic_fixture, tmp_path)
    ctx = wr.WorkflowContext(feature="led-blink", pin="PD12", function="gpio-output")
    state = wr.init_workflow(project, intent="develop-feature", goal="LED blink", context=ctx)
    result = wr.run_workflow(project, state)

    fw_stage = next(s for s in result["stages"] if s["id"] == "firmware-plan")
    assert fw_stage["evidence"]["firmware_patch"]["files_written"]
    for entry in fw_stage["evidence"]["firmware_patch"]["files_written"]:
        assert Path(entry["path"]).exists()


def test_e2e_mock_mode_writes_workflow_state_json(cubemx_basic_fixture: Path, tmp_path: Path) -> None:
    """End-to-end mock-mode workflow must persist workflow-state.json."""
    project = _copy_fixture(cubemx_basic_fixture, tmp_path)
    ctx = wr.WorkflowContext(feature="led-blink", pin="PD12", function="gpio-output")
    state = wr.init_workflow(project, intent="develop-feature", goal="LED blink", context=ctx)
    result = wr.run_workflow(project, state)

    state_path = wr.workflow_state_path(project)
    assert state_path.exists()
    import json
    saved = json.loads(state_path.read_text(encoding="utf-8"))
    assert saved["workflow_id"] == result["workflow_id"]
    assert saved["status"] == "completed"
    assert len(saved["stages"]) == 9


def test_e2e_mock_mode_verify_goal_returns_behavior_mock(cubemx_basic_fixture: Path, tmp_path: Path) -> None:
    """verify-goal in mock mode returns verification_level='behavior-mock'."""
    project = _copy_fixture(cubemx_basic_fixture, tmp_path)
    ctx = wr.WorkflowContext(feature="led-blink", pin="PD12", function="gpio-output")
    state = wr.init_workflow(project, intent="develop-feature", goal="LED blink on PD12", context=ctx)
    result = wr.run_workflow(project, state)
    verify_stage = next(s for s in result["stages"] if s["id"] == "verify-goal")
    assert verify_stage["evidence"]["verification_level"] == "behavior-mock"
    assert verify_stage["evidence"]["observe_mode"] == "sim"


def test_e2e_real_request_stops_before_physical_flash(cubemx_basic_fixture: Path, tmp_path: Path) -> None:
    """Environment opt-in cannot upgrade a simulated workflow to physical execution."""
    from unittest.mock import patch

    project = _copy_fixture(cubemx_basic_fixture, tmp_path)
    ctx = wr.WorkflowContext(feature="led-blink", pin="PD12", function="gpio-output")
    state = wr.init_workflow(project, intent="develop-feature", goal="LED blink", context=ctx)
    with (
        patch.dict("os.environ", {"HARDWARE_BUTLER_ENABLE_REAL_FLASH": "1"}),
        patch("workflow_runner._run_subprocess") as run,
    ):
        result = wr.run_workflow(project, state)

    assert result["status"] == "blocked-needs-input"
    flash_stage = next(stage for stage in result["stages"] if stage["id"] == "flash")
    assert flash_stage["evidence"]["flash_executed"] is False
    assert flash_stage["evidence"]["flash_result"]["status"] == "blocked-real-backend-not-enabled"
    observe_stage = next(stage for stage in result["stages"] if stage["id"] == "debug-observe")
    assert observe_stage["status"] == "pending"
    run.assert_not_called()
