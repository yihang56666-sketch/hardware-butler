"""Tests for Step B: firmware_code_patcher wired into workflow firmware-plan stage."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.path.insert(0, "tools")

import workflow_runner as wr  # noqa: E402


def _copy_fixture(cubemx_basic_fixture: Path, tmp_path: Path) -> Path:
    """Copy fixture into a repo-local temp dir (safe_io refuses writes outside repo)."""
    scratch_root = Path(__file__).resolve().parents[2] / ".tmp-wf-tests"
    project = scratch_root / tmp_path.name / "project"
    if project.exists():
        shutil.rmtree(project, ignore_errors=True)
    project.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(cubemx_basic_fixture, project)
    evidence_path = project / ".hardware-butler" / "datasheet-evidence.json"
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(
        '{"part": "STM32F407VGTx", "sources": [{"url": "stub", "title": "stub", "type": "manual"}], '
        '"summary": {"has_reference_manual": true}, "evidence_status": "evidence-collected"}'
    )
    return project


def test_firmware_plan_writes_real_c_files(cubemx_basic_fixture: Path, tmp_path: Path) -> None:
    project = _copy_fixture(cubemx_basic_fixture, tmp_path)
    ctx = wr.WorkflowContext(feature="led-blink", pin="PD12", function="gpio-output")
    state = wr.init_workflow(project, intent="develop-feature", goal="LED blink", context=ctx)
    result = wr.run_workflow(project, state)

    fw_stage = next(s for s in result["stages"] if s["id"] == "firmware-plan")
    assert fw_stage["status"] == "completed"
    patch = fw_stage["evidence"]["firmware_patch"]
    assert patch["files_written"], "firmware-plan should write at least one .c/.h file"
    written_paths = [f["path"] for f in patch["files_written"]]
    assert any("app_led_blink" in p or "app_led" in p for p in written_paths), written_paths
    for entry in patch["files_written"]:
        assert Path(entry["path"]).exists(), entry["path"]
    assert patch["contains_hal_call"], "generated firmware should reference HAL_ symbols"


def test_gpio_template_is_observable_via_rtt(cubemx_basic_fixture: Path, tmp_path: Path) -> None:
    """The led-blink task must emit per-cycle RTT heartbeats — without them
    a real debug-observe window captures nothing and verify-goal cannot
    match any signal (the real closed loop would spin empty)."""
    project = _copy_fixture(cubemx_basic_fixture, tmp_path)
    ctx = wr.WorkflowContext(feature="led-blink", pin="PD12", function="gpio-output")
    state = wr.init_workflow(project, intent="develop-feature", goal="LED blink", context=ctx)
    result = wr.run_workflow(project, state)

    fw_stage = next(s for s in result["stages"] if s["id"] == "firmware-plan")
    assert fw_stage["status"] == "completed"
    app_src = (project / "Core" / "Src" / "app_led_blink.c").read_text(encoding="utf-8")
    assert '#include "app_rtt.h"' in app_src
    assert 'app_rtt_puts("app_led_blink: on\\n");' in app_src
    assert 'app_rtt_puts("app_led_blink: off\\n");' in app_src
    assert (project / "Core" / "Src" / "app_rtt.c").exists()


def test_firmware_plan_evidence_includes_firmware_patch_field(cubemx_basic_fixture: Path, tmp_path: Path) -> None:
    project = _copy_fixture(cubemx_basic_fixture, tmp_path)
    ctx = wr.WorkflowContext(feature="led-blink", pin="PD12", function="gpio-output")
    state = wr.init_workflow(project, intent="develop-feature", goal="LED blink", context=ctx)
    result = wr.run_workflow(project, state)
    fw_stage = next(s for s in result["stages"] if s["id"] == "firmware-plan")
    assert "firmware_patch" in fw_stage["evidence"]
    assert "files_written" in fw_stage["evidence"]["firmware_patch"]


def test_firmware_plan_blocked_without_feature(cubemx_basic_fixture: Path, tmp_path: Path) -> None:
    """Directly invoke _stage_firmware_plan with empty feature to verify the guard."""
    project = _copy_fixture(cubemx_basic_fixture, tmp_path)
    ctx = wr.WorkflowContext(feature="", pin="PD12", function="gpio-output")
    state = wr.init_workflow(project, intent="develop-feature", goal="LED blink", context=ctx)
    # Manually mark requirement-parse as completed with empty feature to reach firmware-plan
    req_stage = next(s for s in state["stages"] if s["id"] == "requirement-parse")
    req_stage["status"] = "completed"
    req_stage["evidence"] = {"parsed_requirements": {"feature": "", "function": "gpio-output", "pin": "PD12"}}
    result = wr._dispatch_stage("firmware-plan", project, ctx, state)
    assert result.status == "blocked-needs-input"
    assert "feature" in (result.error or "")
