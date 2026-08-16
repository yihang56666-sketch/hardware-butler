"""Tests: workflow build/flash real-backend branches (safety-gated).

These are the exact code paths a real-board day takes: the flash stage's
HARDWARE_BUTLER_ENABLE_REAL_FLASH block (probe-rs preferred, adapter native
fallback, embeddedskills script fallback) and the no-adapter build fallback
through the embeddedskills script map. Subprocesses are mocked — the safety
gate itself (env var + goal token) runs for real.
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


def test_flash_real_backend_probe_rs_success(tmp_path: Path, real_flash_env) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    ctx, state = _state_with_stages(project)
    import vendor_adapters

    adapter = vendor_adapters.get_adapter("stm32")
    assert adapter is not None
    probe_cmd = ["probe-rs", "download", "--verify", "build/firmware.elf"]
    with patch("bench_runbook.generate_runbook", return_value={"action_plan": {"steps": []}}):
        with patch.object(adapter, "flash_via_probe_rs", return_value=probe_cmd):
            with patch(
                "workflow_runner._run_subprocess",
                return_value={"status": "ok", "returncode": 0, "stdout": "downloaded", "stderr": ""},
            ) as run:
                result = wr._stage_flash(project, ctx, state)
    assert result.status == "completed"
    assert result.evidence["flash_executed"] is True
    assert result.evidence["flash_backend"] == "probe-rs"
    assert run.call_args.args[0] == probe_cmd
    # goal token was consumed by the gated action
    assert state["goal_token"]["uses"] >= 1


def test_flash_real_backend_probe_rs_failure_fails_stage(tmp_path: Path, real_flash_env) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    ctx, state = _state_with_stages(project)
    import vendor_adapters

    adapter = vendor_adapters.get_adapter("stm32")
    assert adapter is not None
    with patch("bench_runbook.generate_runbook", return_value={"action_plan": {"steps": []}}):
        with patch.object(adapter, "flash_via_probe_rs", return_value=["probe-rs", "download", "--verify", "build/firmware.elf"]):
            with patch("workflow_runner._run_subprocess", return_value={"status": "error", "returncode": 1, "stdout": "", "stderr": "no probe"}):
                result = wr._stage_flash(project, ctx, state)
    assert result.status == "failed"
    assert result.evidence["flash_executed"] is False
    assert result.evidence["flash_backend"] == "probe-rs"


def test_flash_real_backend_adapter_native_fallback(tmp_path: Path, real_flash_env) -> None:
    """probe-rs absent -> adapter native flash_command (pyOCD for stlink)."""
    project = tmp_path / "proj"
    project.mkdir()
    ctx, state = _state_with_stages(project, probe="stlink-v3")
    import vendor_adapters

    adapter = vendor_adapters.get_adapter("stm32")
    assert adapter is not None
    with patch("bench_runbook.generate_runbook", return_value={"action_plan": {"steps": []}}):
        with patch.object(adapter, "flash_via_probe_rs", return_value=[]):
            with patch.object(
                adapter, "flash_command", return_value=["pyocd", "flash", "--target", "STM32F407VGT6", "build/firmware.elf"]
            ) as native:
                with patch(
                    "workflow_runner._run_subprocess",
                    return_value={"status": "ok", "returncode": 0, "stdout": "flashed", "stderr": ""},
                ) as run:
                    result = wr._stage_flash(project, ctx, state)
    assert result.status == "completed"
    assert result.evidence["flash_backend"] == "stm32"
    assert result.evidence["flash_executed"] is True
    native.assert_called_once()
    assert run.call_args.args[0][0] == "pyocd"


def test_flash_real_backend_embeddedskills_fallback(tmp_path: Path, real_flash_env) -> None:
    """No vendor adapter at all -> embeddedskills script from chip evidence."""
    project = tmp_path / "proj"
    project.mkdir()
    ctx, state = _state_with_stages(project, chip_family=None, probe="cmsis-dap")
    captured: dict[str, object] = {}

    def fake_script(script: str, args: list[str], *, timeout_s: int = 120) -> dict:
        captured["script"] = script
        captured["args"] = args
        return {"status": "ok", "stdout": "flashed", "stderr": ""}

    with patch("bench_runbook.generate_runbook", return_value={"action_plan": {"steps": []}}):
        with patch("workflow_runner._run_embeddedskills_script", side_effect=fake_script):
            result = wr._stage_flash(project, ctx, state)
    assert result.status == "completed"
    assert result.evidence["flash_backend"] == "openocd"
    assert captured["script"] == "openocd/scripts/openocd_run.py"
    args = captured["args"]
    assert "--action" in args and "flash" in args
    assert "--target" in args  # target from chip-selection evidence
    assert "--probe" in args  # probe from context


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
