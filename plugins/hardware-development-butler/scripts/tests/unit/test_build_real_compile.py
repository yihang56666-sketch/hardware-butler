"""Tests for Step G: real compile validation + optimize-loop on build failure."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, "tools")

import workflow_runner as wr  # noqa: E402


def _copy_fixture(src: Path, dst: Path) -> Path:
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


@pytest.mark.enable_platformio
def test_build_stage_returns_failed_when_pio_compile_fails(tmp_path: Path) -> None:
    """When pio is on PATH but build fails, stage returns failed (triggers optimize-loop)."""
    fixture = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "cubemx-basic"
    project = _copy_fixture(fixture, tmp_path / "build-fail" / "project")
    ctx = wr.WorkflowContext(feature="led-blink", pin="PD12", function="gpio-output")
    state = wr.init_workflow(project, intent="develop-feature", goal="LED blink", context=ctx)
    # Mark prior stages as completed to reach build
    for sid in ("requirement-parse", "chip-selection", "datasheet-collect", "cubemx-config", "firmware-plan"):
        stage = next(s for s in state["stages"] if s["id"] == sid)
        stage["status"] = "completed"
        stage["evidence"] = {"placeholder": True}
    state["stages"][1]["evidence"] = {
        "selected_part": "STM32F407VGT6",
        "backends": {
            "vendor_adapter": {"family": "stm32"},
            "backends": {"build": "gcc", "flash": "pyocd", "observe": "serial"},
        },
    }
    state["stages"][4]["evidence"] = {
        "firmware_plan": {"status": "plan-only", "verification": []},
        "firmware_patch": {"files_written": []},
    }

    with patch("shutil.which", side_effect=lambda name: "/fake/pio" if name == "pio" else None):
        with patch("workflow_runner._run_subprocess", return_value={
            "status": "error",
            "returncode": 2,
            "stdout": "",
            "stderr": "main.c:10:5: error: 'HAL_GPIO_TogglePin' undeclared",
        }):
            with patch("build_plan.generate_plan", return_value={"steps": [{"command": "gcc"}]}):
                result = wr._stage_build(project, ctx, state)
    assert result.status == "failed"
    assert "PlatformIO build failed" in (result.error or "")
    assert result.evidence["build_executed"] is False
    assert "HAL_GPIO_TogglePin" in result.evidence["build_log"]


@pytest.mark.enable_platformio
def test_build_stage_returns_completed_when_pio_compile_succeeds(tmp_path: Path) -> None:
    """When pio build succeeds, stage returns completed."""
    fixture = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "cubemx-basic"
    project = _copy_fixture(fixture, tmp_path / "build-ok" / "project")
    ctx = wr.WorkflowContext(feature="led-blink", pin="PD12", function="gpio-output")
    state = wr.init_workflow(project, intent="develop-feature", goal="LED blink", context=ctx)
    for sid in ("requirement-parse", "chip-selection", "datasheet-collect", "cubemx-config", "firmware-plan"):
        stage = next(s for s in state["stages"] if s["id"] == sid)
        stage["status"] = "completed"
        stage["evidence"] = {"placeholder": True}
    state["stages"][1]["evidence"] = {
        "selected_part": "STM32F407VGT6",
        "backends": {
            "vendor_adapter": {"family": "stm32"},
            "backends": {"build": "gcc", "flash": "pyocd", "observe": "serial"},
        },
    }
    state["stages"][4]["evidence"] = {
        "firmware_plan": {"status": "plan-only", "verification": []},
        "firmware_patch": {"files_written": []},
    }

    with patch("shutil.which", side_effect=lambda name: "/fake/pio" if name == "pio" else None):
        with patch("workflow_runner._run_subprocess", return_value={
            "status": "ok",
            "returncode": 0,
            "stdout": "Linking firmware.elf\nDone",
            "stderr": "",
        }):
            with patch("build_plan.generate_plan", return_value={"steps": [{"command": "gcc"}]}):
                result = wr._stage_build(project, ctx, state)
    assert result.status == "completed"
    assert result.evidence["build_executed"] is True


@pytest.mark.enable_platformio
def test_build_stage_stays_completed_when_no_pio_no_tools(tmp_path: Path) -> None:
    """When pio is not on PATH and no build tools, stage stays plan-only (completed)."""
    fixture = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "cubemx-basic"
    project = _copy_fixture(fixture, tmp_path / "build-plan" / "project")
    ctx = wr.WorkflowContext(feature="led-blink", pin="PD12", function="gpio-output")
    state = wr.init_workflow(project, intent="develop-feature", goal="LED blink", context=ctx)
    for sid in ("requirement-parse", "chip-selection", "datasheet-collect", "cubemx-config", "firmware-plan"):
        stage = next(s for s in state["stages"] if s["id"] == sid)
        stage["status"] = "completed"
        stage["evidence"] = {"placeholder": True}
    state["stages"][1]["evidence"] = {
        "selected_part": "STM32F407VGT6",
        "backends": {
            "vendor_adapter": {"family": "stm32"},
            "backends": {"build": "gcc", "flash": "pyocd", "observe": "serial"},
        },
    }
    state["stages"][4]["evidence"] = {
        "firmware_plan": {"status": "plan-only", "verification": []},
        "firmware_patch": {"files_written": []},
    }

    with patch("shutil.which", return_value=None):
        with patch("build_plan.generate_plan", return_value={"steps": [{"command": "gcc"}]}):
            result = wr._stage_build(project, ctx, state)
    assert result.status == "completed"
    assert result.evidence["build_executed"] is False
    assert "plan-only" in result.evidence.get("reason", "")
