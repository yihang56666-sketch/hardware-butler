"""Tests: QEMU emulation backend wired into debug-observe / verify-goal.

When no probe is attached but QEMU + arm-none-eabi-gdb are available and the
build stage produced an ELF, debug-observe EXECUTES the firmware and reads
the RTT heartbeat (mode "qemu-emulated"), and verify-goal labels the result
"behavior-emulated" — honest one-level-below-real evidence instead of the
synthesized behavior-mock.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, "tools")

import qemu_behavior_check as qbc  # noqa: E402
import workflow_runner as wr  # noqa: E402

GDB_SAMPLE = """Breakpoint 1 at 0x800174c

Breakpoint 1, 0x0800174c in app_rtt_puts ()
0x080016a2 in app_led_blink_task ()
Run till exit from #0  0x0800174c in app_rtt_puts ()
0x2000002c <app_rtt_cb+32>:\t0x00000012
0x200041d8 <app_rtt_up_storage>:\t"app_led_blink: on\\n"
"""


def test_parse_gdb_output_extracts_behavior_facts() -> None:
    parsed = qbc.parse_gdb_output(GDB_SAMPLE)
    assert parsed["status"] == "ok"
    assert parsed["breakpoint_hit"] is True
    assert parsed["task_symbol"] == "app_led_blink_task"
    assert parsed["heartbeat"] == "app_led_blink: on\\n"
    assert parsed["wr_off"] == 18


def test_parse_gdb_output_rejects_incomplete_transcript() -> None:
    assert qbc.parse_gdb_output("")["status"] == "error"
    # Breakpoint hit but no buffer read: not ok.
    partial = "Breakpoint 1, 0x0800174c in app_rtt_puts ()\n"
    assert qbc.parse_gdb_output(partial)["status"] == "error"


def _observe_state(project: Path, elf: str) -> tuple[object, dict]:
    ctx = wr.WorkflowContext(feature="led-blink", pin="PD12", function="gpio-output")
    state = wr.init_workflow(project, intent="develop-feature", goal="LED blink", context=ctx)
    for sid in ("requirement-parse", "chip-selection", "datasheet-collect", "cubemx-config", "firmware-plan", "build", "flash"):
        stage = next(s for s in state["stages"] if s["id"] == sid)
        stage["status"] = "completed"
        stage["evidence"] = {"placeholder": True}
    fw = next(s for s in state["stages"] if s["id"] == "firmware-plan")
    fw["evidence"] = {
        "firmware_plan": {"status": "plan-only", "verification": ["LED on PD12 toggles"]}
    }
    state["context"]["elf"] = elf
    return ctx, state


def test_debug_observe_uses_qemu_backend_when_available(tmp_path: Path) -> None:
    elf = tmp_path / "firmware.elf"
    elf.write_bytes(b"fake-elf")
    ctx, state = _observe_state(tmp_path, str(elf))
    fake_check = {
        "status": "ok",
        "backend": "qemu",
        "machine": "netduinoplus2",
        "task_symbol": "app_led_blink_task",
        "heartbeat": "app_led_blink: on\\n",
        "wr_off": 18,
        "capture": "app_led_blink: on\\n",
    }
    with patch.object(qbc, "available", return_value=True):
        with patch.object(qbc, "run_behavior_check", return_value=fake_check) as run:
            result = wr._stage_debug_observe(tmp_path, ctx, state)
    assert result.status == "completed"
    assert result.evidence["mode"] == "qemu-emulated"
    assert result.evidence["hardware_observed"] is False  # emulated, not hardware
    assert result.evidence["emulated_execution"]["task_symbol"] == "app_led_blink_task"
    assert result.evidence["capture"].startswith("app_led_blink: on")
    run.assert_called_once()


def test_debug_observe_falls_back_to_sim_when_check_fails(tmp_path: Path) -> None:
    elf = tmp_path / "firmware.elf"
    elf.write_bytes(b"fake-elf")
    ctx, state = _observe_state(tmp_path, str(elf))
    with patch.object(qbc, "available", return_value=True):
        with patch.object(qbc, "run_behavior_check", return_value={"status": "error", "reason": "no heartbeat"}):
            result = wr._stage_debug_observe(tmp_path, ctx, state)
    assert result.evidence["mode"] == "sim"
    assert any(err["backend"] == "qemu" for err in result.evidence["observe_errors"])


def test_debug_observe_skips_emulation_without_elf(tmp_path: Path) -> None:
    ctx, state = _observe_state(tmp_path, "")
    with patch.object(qbc, "available", return_value=True) as avail:
        result = wr._stage_debug_observe(tmp_path, ctx, state)
    assert result.evidence["mode"] == "sim"
    avail.assert_not_called()  # no ELF -> emulation never attempted


def test_verify_goal_labels_emulated_level(tmp_path: Path) -> None:
    ctx, state = _observe_state(tmp_path, "")
    observe = next(s for s in state["stages"] if s["id"] == "debug-observe")
    observe["status"] = "completed"
    observe["evidence"] = {
        "mode": "qemu-emulated",
        "signals": [{"kind": "led", "pin": "PD12"}],
        "observations": [
            {"signal": {"kind": "led"}, "mode": "qemu-emulated", "matched": True, "reason": "toggle markers", "evidence_snippet": ""}
        ],
        "capture": "app_led_blink: on\\n",
    }
    result = wr._stage_verify_goal(tmp_path, ctx, state)
    assert result.status == "completed"
    assert result.evidence["verification_level"] == "behavior-emulated"
