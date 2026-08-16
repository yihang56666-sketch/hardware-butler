"""Test: firmware EXECUTES and behaves correctly (QEMU Cortex-M emulation).

Compile-level tests prove the ELF builds; this test proves the binary runs:
under QEMU (netduinoplus2 = STM32F405, same core/family as the F407 target)
the reset vector executes, HAL_Init completes, the FreeRTOS scheduler starts
(SVC/PendSV context switches), the app task runs after osDelay(500) — which
requires 500 real SysTick ticks — and the RTT heartbeat lands in the ring
buffer with a matching WrOff.

Honest labeling: this is EMULATED execution, not real hardware. It is the
strongest execution evidence available without a board and de-risks the
real-board day, but does not replace it.

Run manually (QEMU portable zip + PlatformIO toolchain gdb required):
  HARDWARE_BUTLER_QEMU=1 pytest tests/unit/test_firmware_qemu_execution.py -q --no-cov
"""

from __future__ import annotations

import glob
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, "tools")

import vendor_adapters  # noqa: E402
import workflow_runner as wr  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
GDB_PORT = "1235"


def _find_qemu() -> str:
    override = os.environ.get("HARDWARE_BUTLER_QEMU_BIN", "")
    if override and Path(override).exists():
        return override
    found = shutil.which("qemu-system-arm")
    if found:
        return found
    pattern = os.path.join(
        os.environ.get("TEMP", ""), "qemu-arm", "*", "bin", "qemu-system-arm.exe"
    )
    for candidate in sorted(glob.glob(pattern), reverse=True):
        if Path(candidate).exists():
            return candidate
    return ""


def _find_gdb() -> str:
    override = os.environ.get("HARDWARE_BUTLER_ARM_GDB", "")
    if override and Path(override).exists():
        return override
    home = Path.home()
    for pattern in (
        ".platformio/packages/toolchain-gccarmnoneeabi*/bin/arm-none-eabi-gdb.exe",
        ".platformio/packages/toolchain-gccarmnoneeabi/bin/arm-none-eabi-gdb.exe",
    ):
        for candidate in sorted(home.glob(pattern), reverse=True):
            if candidate.exists():
                return str(candidate)
    return ""


_QEMU = _find_qemu()
_GDB = _find_gdb()
_PIO = shutil.which("pio") or str(REPO_ROOT / ".venv" / "Scripts" / "pio.exe")


@pytest.mark.enable_platformio
@pytest.mark.skipif(
    not os.environ.get("HARDWARE_BUTLER_QEMU"),
    reason="set HARDWARE_BUTLER_QEMU=1 to run QEMU execution tests",
)
@pytest.mark.skipif(not _QEMU, reason="qemu-system-arm not found")
@pytest.mark.skipif(not _GDB, reason="arm-none-eabi-gdb not found (PlatformIO toolchain)")
@pytest.mark.skipif(not Path(_PIO).exists(), reason="PlatformIO not installed")
def test_firmware_executes_under_qemu_and_writes_rtt_heartbeat(
    cubemx_basic_fixture: Path,
) -> None:
    project = cubemx_basic_fixture.parent.parent / ".tmp-wf-tests" / "qemu-exec" / "project"
    if project.exists():
        shutil.rmtree(project, ignore_errors=True)
    project.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(cubemx_basic_fixture, project)

    ctx = wr.WorkflowContext(feature="led-blink", pin="PD12", function="gpio-output")
    state = wr.init_workflow(project, intent="develop-feature", goal="LED blink", context=ctx)
    for sid in ("requirement-parse", "chip-selection", "datasheet-collect", "cubemx-config"):
        stage = next(s for s in state["stages"] if s["id"] == sid)
        stage["status"] = "completed"
        stage["evidence"] = {"placeholder": True}
    req = next(s for s in state["stages"] if s["id"] == "requirement-parse")
    req["evidence"] = {"parsed_requirements": {"feature": "led-blink", "pin": "PD12", "function": "gpio-output"}}
    chip = next(s for s in state["stages"] if s["id"] == "chip-selection")
    chip["evidence"] = {
        "selected_part": "STM32F407VGT6",
        "backends": {"vendor_adapter": {"family": "stm32"}, "backends": {}},
    }

    adapter = vendor_adapters.get_adapter("stm32")
    assert adapter is not None
    with patch.object(adapter, "find_pio", return_value=_PIO):
        result = wr._stage_firmware_plan(project, ctx, state)
        assert result.status == "completed"
        argv = adapter.build_via_platformio(
            {"project_root": str(project), "part": "STM32F407VGT6", "rtos": True}
        )
    assert argv, "pio command expected"
    build = subprocess.run(
        [str(tok) for tok in argv], shell=False, capture_output=True, text=True, timeout=420
    )
    assert build.returncode == 0, build.stdout[-3000:] + build.stderr[-3000:]
    build_root = Path(argv[-1])
    elfs = list((build_root / ".pio" / "build").rglob("firmware.elf"))
    assert elfs, "firmware.elf missing after build"
    elf = str(elfs[0]).replace("\\", "/")

    qemu = subprocess.Popen(
        [
            _QEMU,
            "-M", "netduinoplus2",
            "-nographic",
            "-monitor", "none",
            "-serial", "none",
            "-kernel", elf,
            "-S",
            "-gdb", f"tcp::{GDB_PORT}",
        ],
        shell=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        time.sleep(2)
        gdb = subprocess.run(
            [
                _GDB,
                "-batch",
                "-ex", "set pagination off",
                "-ex", f"file {elf}",
                "-ex", f"target remote localhost:{GDB_PORT}",
                "-ex", "break app_rtt_puts",
                "-ex", "continue",
                "-ex", "finish",
                "-ex", "x/wx ((char*)&app_rtt_cb)+32",
                "-ex", "x/s (char*)&app_rtt_up_storage",
            ],
            shell=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
        out = gdb.stdout + gdb.stderr
        assert "Breakpoint 1" in out and "app_rtt_puts" in out, out
        # The heartbeat is called from the FreeRTOS app task (thread context).
        assert "app_led_blink_task" in out, out
        # WrOff advanced past zero (control-block offset +32).
        assert "0x00000000" not in "\n".join(
            line for line in out.splitlines() if "app_rtt_cb+32" in line
        ), out
        # The heartbeat string is in the ring buffer.
        assert "app_led_blink: on" in out, out
    finally:
        qemu.terminate()
        try:
            qemu.wait(timeout=10)
        except subprocess.TimeoutExpired:
            qemu.kill()


@pytest.mark.enable_platformio
@pytest.mark.skipif(
    not os.environ.get("HARDWARE_BUTLER_QEMU"),
    reason="set HARDWARE_BUTLER_QEMU=1 to run QEMU execution tests",
)
@pytest.mark.skipif(not _QEMU, reason="qemu-system-arm not found")
@pytest.mark.skipif(not _GDB, reason="arm-none-eabi-gdb not found (PlatformIO toolchain)")
@pytest.mark.skipif(not Path(_PIO).exists(), reason="PlatformIO not installed")
def test_workflow_observe_uses_qemu_backend_end_to_end(cubemx_basic_fixture: Path) -> None:
    """Full workflow wiring: build the firmware for real, then debug-observe
    picks the QEMU backend (no probe attached) and verify-goal labels the
    result behavior-emulated from the actually-executed heartbeat."""
    import qemu_behavior_check as qbc

    project = cubemx_basic_fixture.parent.parent / ".tmp-wf-tests" / "qemu-exec" / "project"
    assert project.exists(), "run test_firmware_executes_under_qemu first (shares the build)"

    ctx = wr.WorkflowContext(feature="led-blink", pin="PD12", function="gpio-output")
    state = wr.init_workflow(project, intent="develop-feature", goal="LED blink", context=ctx)
    for sid in ("requirement-parse", "chip-selection", "datasheet-collect", "cubemx-config", "firmware-plan", "build", "flash"):
        stage = next(s for s in state["stages"] if s["id"] == sid)
        stage["status"] = "completed"
        stage["evidence"] = {"placeholder": True}
    fw = next(s for s in state["stages"] if s["id"] == "firmware-plan")
    fw["evidence"] = {"firmware_plan": {"status": "plan-only", "verification": ["LED on PD12 toggles"]}}
    chip = next(s for s in state["stages"] if s["id"] == "chip-selection")
    chip["evidence"] = {
        "selected_part": "STM32F407VGT6",
        "backends": {"vendor_adapter": {"family": "stm32"}, "backends": {}},
    }

    adapter = vendor_adapters.get_adapter("stm32")
    assert adapter is not None
    with patch.object(adapter, "find_pio", return_value=_PIO):
        argv = adapter.build_via_platformio(
            {"project_root": str(project), "part": "STM32F407VGT6", "rtos": True}
        )
    assert argv
    build = subprocess.run(
        [str(tok) for tok in argv], shell=False, capture_output=True, text=True, timeout=420
    )
    assert build.returncode == 0, build.stderr[-2000:]
    elfs = list((Path(argv[-1]) / ".pio" / "build").rglob("firmware.elf"))
    assert elfs
    state["context"]["elf"] = str(elfs[0])

    observe = wr._stage_debug_observe(project, ctx, state)
    assert observe.status == "completed"
    assert observe.evidence["mode"] == "qemu-emulated", observe.evidence["observe_errors"]
    assert observe.evidence["emulated_execution"]["task_symbol"] == "app_led_blink_task"
    observe_stage = next(s for s in state["stages"] if s["id"] == "debug-observe")
    observe_stage["status"] = "completed"
    observe_stage["evidence"] = observe.evidence

    verify = wr._stage_verify_goal(project, ctx, state)
    assert verify.status == "completed"
    assert verify.evidence["verification_level"] == "behavior-emulated"
    assert qbc.available()
