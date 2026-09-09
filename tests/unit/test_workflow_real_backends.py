"""Offline tests for build routing and fail-closed physical workflow requests.

Subprocesses and adapter methods are mocked. Environment opt-in plus a
workflow goal token must not bypass hardware_action_executor authorization.
These tests do not validate a physical board or enable a real backend.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, "tools")

import workflow_runner as wr  # noqa: E402


def _state_with_stages(
    project: Path, *, chip_family: str | None = "stm32", probe: str = ""
) -> tuple[object, dict]:
    ctx = wr.WorkflowContext(feature="led-blink", pin="PD12", function="gpio-output", probe=probe)
    state = wr.init_workflow(project, intent="develop-feature", goal="LED blink", context=ctx)
    for sid in ("requirement-parse", "chip-selection", "datasheet-collect", "cubemx-config", "firmware-plan"):
        stage = next(s for s in state["stages"] if s["id"] == sid)
        stage["status"] = "completed"
        stage["evidence"] = {"placeholder": True}
    chip = next(s for s in state["stages"] if s["id"] == "chip-selection")
    chip["evidence"] = {
        "selected_part": "STM32F407VGT6",
        "backends": {
            "vendor_adapter": {"family": chip_family} if chip_family else {},
            "backends": {"build": "gcc", "flash": "openocd", "observe": "serial"},
        },
    }
    fw = next(s for s in state["stages"] if s["id"] == "firmware-plan")
    fw["evidence"] = {"firmware_patch": {"rtos_codegen": False}}
    return ctx, state


# --- build stage: no-adapter embeddedskills fallback ---

def test_build_no_adapter_routes_to_embeddedskills_script(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    ctx, state = _state_with_stages(project, chip_family=None)
    captured: dict[str, object] = {}

    def fake_script(script: str, args: list[str], *, timeout_s: int = 120) -> dict:
        captured["script"] = script
        captured["args"] = args
        return {"status": "ok", "stdout": "build ok", "stderr": ""}

    with patch("workflow_runner._run_embeddedskills_script", side_effect=fake_script):
        result = wr._stage_build(project, ctx, state)
    assert result.status == "completed"
    assert result.evidence["build_backend"] == "gcc"
    assert result.evidence["build_executed"] is True
    assert captured["script"] == "gcc/scripts/gcc_build.py"
    assert "--action" in captured["args"] and "build" in captured["args"]


def test_build_no_adapter_unknown_backend_is_plan_only(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    ctx, state = _state_with_stages(project, chip_family=None)
    chip = next(s for s in state["stages"] if s["id"] == "chip-selection")
    chip["evidence"]["backends"]["backends"]["build"] = "mystery-tool"
    result = wr._stage_build(project, ctx, state)
    assert result.status == "completed"
    assert result.evidence["build_executed"] is False
    assert "no script mapping" in result.evidence["reason"]


# --- flash stage: real-backend block behind HARDWARE_BUTLER_ENABLE_REAL_FLASH ---

@pytest.fixture
def real_flash_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("HARDWARE_BUTLER_ENABLE_REAL_FLASH", "1")
    yield
    monkeypatch.delenv("HARDWARE_BUTLER_ENABLE_REAL_FLASH", raising=False)


@pytest.mark.parametrize(
    ("chip_family", "probe", "probe_command", "subprocess_status"),
    [
        ("stm32", "", ["probe-rs", "download", "build/firmware.elf"], "ok"),
        ("stm32", "", ["probe-rs", "download", "build/firmware.elf"], "error"),
        ("stm32", "stlink-v3", [], "ok"),
        (None, "cmsis-dap", [], "ok"),
    ],
    ids=["probe-available", "probe-error", "native-available", "embeddedskills-available"],
)
def test_flash_real_backend_requires_reviewed_executor(
    tmp_path: Path, real_flash_env, chip_family, probe, probe_command, subprocess_status
) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    ctx, state = _state_with_stages(project, chip_family=chip_family, probe=probe)
    import vendor_adapters

    adapter = vendor_adapters.get_adapter("stm32")
    assert adapter is not None
    with (
        patch("bench_runbook.generate_runbook", return_value={"action_plan": {"steps": []}}),
        patch.object(adapter, "flash_via_probe_rs", return_value=probe_command) as probe_run,
        patch.object(adapter, "flash_command", return_value=["pyocd", "flash", "build/firmware.elf"]) as native,
        patch("workflow_runner._run_embeddedskills_script", return_value={"status": "ok"}) as script,
        patch("workflow_runner._run_subprocess", return_value={"status": subprocess_status}) as run,
    ):
        result = wr._stage_flash(project, ctx, state)
    assert result.status == "blocked-needs-input"
    assert result.evidence["flash_executed"] is False
    assert result.evidence["flash_result"]["status"] == "blocked-real-backend-not-enabled"
    assert "hardware_action_executor" in result.error
    probe_run.assert_not_called()
    native.assert_not_called()
    script.assert_not_called()
    run.assert_not_called()


def test_flash_real_backend_exhausted_token_blocks_execution(tmp_path: Path, real_flash_env) -> None:
    """A pre-existing exhausted goal token (uses >= max_uses) must block the
    stage before any flash subprocess is attempted (replay prevention)."""
    project = tmp_path / "proj"
    project.mkdir()
    ctx, state = _state_with_stages(project)
    from safety_gate import check_goal_token, mint_goal_token

    minted = mint_goal_token(
        workflow_id=state["workflow_id"], scope="build-flash,flash-debug", max_uses=1, ttl_seconds=3600
    )
    state["goal_token"] = {
        "token_hash": minted["token_hash"],
        "workflow_id": minted["workflow_id"],
        "scope": minted["scope"],
        "max_uses": minted["max_uses"],
        "expires_at": minted["expires_at"],
        "uses": minted.get("uses", 0),
        "_plaintext": minted["token"],
    }
    # Burn the single use.
    check_goal_token(
        project,
        workflow_id=state["workflow_id"],
        token=minted["token"],
        record=state["goal_token"],
        action="build-flash",
        consume=True,
    )
    with patch("bench_runbook.generate_runbook", return_value={"action_plan": {"steps": []}}):
        with patch("workflow_runner._run_subprocess") as run:
            result = wr._stage_flash(project, ctx, state)
    assert result.status == "failed"
    assert result.evidence["flash_executed"] is False
    run.assert_not_called()
