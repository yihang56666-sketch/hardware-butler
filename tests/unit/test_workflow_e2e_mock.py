"""Tests for Step H: end-to-end mock-mode 9-stage workflow + real-mode switch docs.

Verifies that all 9 stages run to completion in mock mode (default, no
HARDWARE_BUTLER_ENABLE_REAL_FLASH) on the cubemx-basic fixture. The code
path is identical to real mode — only the data source differs (mock returns
fake data, real mode calls real tools).
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


def test_e2e_mock_mode_real_mode_switch_keeps_code_path_identical(cubemx_basic_fixture: Path, tmp_path: Path) -> None:
    """Setting HARDWARE_BUTLER_ENABLE_REAL_FLASH=1 switches data source
    but the stage dispatch code path is identical (same _dispatch_stage call).

    We stub _run_subprocess so that real tool invocation doesn't actually
    happen (no toolchain on host); this verifies the code path is wired up
    correctly without requiring real hardware.
    """
    import os
    from unittest.mock import patch
    project = _copy_fixture(cubemx_basic_fixture, tmp_path)
    ctx = wr.WorkflowContext(feature="led-blink", pin="PD12", function="gpio-output")
    state = wr.init_workflow(project, intent="develop-feature", goal="LED blink", context=ctx)

    def stub_subprocess(cmd, *, timeout_s=120):
        # Return content that satisfies _verify_signal for LED signal.
        # Applies to all subprocess calls (build, flash, observe) since this
        # test verifies code path wiring, not actual tool behavior.
        return {"status": "ok", "returncode": 0, "stdout": "LED toggle on", "stderr": ""}

    old = os.environ.get("HARDWARE_BUTLER_ENABLE_REAL_FLASH")
    os.environ["HARDWARE_BUTLER_ENABLE_REAL_FLASH"] = "1"
    try:
        with patch("workflow_runner._run_subprocess", side_effect=stub_subprocess):
            result = wr.run_workflow(project, state)
    finally:
        if old is None:
            os.environ.pop("HARDWARE_BUTLER_ENABLE_REAL_FLASH", None)
        else:
            os.environ["HARDWARE_BUTLER_ENABLE_REAL_FLASH"] = old

    assert result["status"] == "completed"
    obs_stage = next(s for s in result["stages"] if s["id"] == "debug-observe")
    assert obs_stage["status"] == "completed"
