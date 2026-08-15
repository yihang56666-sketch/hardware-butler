"""Tests for Step F: open-source integration (PlatformIO + probe-rs + pyserial)."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, "tools")

import vendor_adapters  # noqa: E402
import vendor_adapters.esp32  # noqa: E402
import vendor_adapters.msp430  # noqa: E402
import vendor_adapters.stm32  # noqa: E402

# --- PlatformIO build integration ---

def test_build_via_platformio_returns_empty_when_pio_missing() -> None:
    adapter = vendor_adapters.get_adapter("stm32")
    assert adapter is not None
    with patch("shutil.which", return_value=None):
        cmd = adapter.build_via_platformio({"project_root": "/tmp/proj"})
    assert cmd == []


def test_build_via_platformio_returns_pio_run_when_available() -> None:
    adapter = vendor_adapters.get_adapter("stm32")
    assert adapter is not None
    with patch("shutil.which", return_value="/fake/pio"):
        cmd = adapter.build_via_platformio({"project_root": "/tmp/proj"})
    assert cmd == ["pio", "run", "-d", "/tmp/proj"]


def test_build_via_platformio_for_esp32() -> None:
    adapter = vendor_adapters.get_adapter("esp32")
    assert adapter is not None
    with patch("shutil.which", return_value="/fake/pio"):
        cmd = adapter.build_via_platformio({"project_root": "/tmp/esp"})
    assert cmd[0] == "pio"
    assert "esp" in cmd[3]


# --- probe-rs flash integration ---

def test_flash_via_probe_rs_returns_empty_when_tool_missing() -> None:
    adapter = vendor_adapters.get_adapter("stm32")
    assert adapter is not None
    with patch("shutil.which", return_value=None):
        cmd = adapter.flash_via_probe_rs({"target": "STM32F407VG"})
    assert cmd == []


def test_flash_via_probe_rs_includes_target_and_probe() -> None:
    adapter = vendor_adapters.get_adapter("stm32")
    assert adapter is not None
    with patch("shutil.which", return_value="/fake/probe-rs"):
        cmd = adapter.flash_via_probe_rs({
            "target": "STM32F407VG",
            "probe": "ST-Link",
            "elf": "build/fw.elf",
        })
    assert cmd[0] == "probe-rs"
    assert "download" in cmd
    assert "build/fw.elf" in cmd
    assert "--chip" in cmd
    assert "STM32F407VG" in cmd
    assert "--probe" in cmd
    assert "ST-Link" in cmd


def test_flash_via_probe_rs_omits_target_when_empty() -> None:
    adapter = vendor_adapters.get_adapter("esp32")
    assert adapter is not None
    with patch("shutil.which", return_value="/fake/probe-rs"):
        cmd = adapter.flash_via_probe_rs({"elf": "build/fw.bin"})
    assert "--chip" not in cmd


# --- probe-rs RTT observe integration ---

def test_observe_via_probe_rs_returns_empty_when_tool_missing() -> None:
    adapter = vendor_adapters.get_adapter("stm32")
    assert adapter is not None
    with patch("shutil.which", return_value=None):
        cmd = adapter.observe_via_probe_rs({"target": "STM32F407VG"})
    assert cmd == []


def test_observe_via_probe_rs_includes_target() -> None:
    adapter = vendor_adapters.get_adapter("stm32")
    assert adapter is not None
    with patch("shutil.which", return_value="/fake/probe-rs"):
        cmd = adapter.observe_via_probe_rs({"target": "STM32F407VG"})
    assert cmd[0] == "probe-rs"
    assert "rtt" in cmd
    assert "attach" in cmd
    assert "--chip" in cmd
    assert "STM32F407VG" in cmd


# --- pyserial observe integration ---

def test_observe_via_pyserial_returns_empty_without_port() -> None:
    adapter = vendor_adapters.get_adapter("esp32")
    assert adapter is not None
    cmd = adapter.observe_via_pyserial({})
    assert cmd == []


def test_observe_via_pyserial_with_port() -> None:
    adapter = vendor_adapters.get_adapter("esp32")
    assert adapter is not None
    cmd = adapter.observe_via_pyserial({"port": "COM5", "baud": "460800"})
    assert cmd == ["python", "-m", "serial.tools.miniterm", "COM5", "460800"]


def test_observe_via_pyserial_default_baud() -> None:
    adapter = vendor_adapters.get_adapter("stm32")
    assert adapter is not None
    cmd = adapter.observe_via_pyserial({"port": "COM3"})
    assert cmd == ["python", "-m", "serial.tools.miniterm", "COM3", "115200"]


# --- platformio_board mapping ---

def test_stm32_platformio_board_nucleo_f407() -> None:
    adapter = vendor_adapters.get_adapter("stm32")
    assert adapter is not None
    board = adapter.platformio_board("STM32F407VGT6")
    assert "nucleo" in board


def test_esp32_platformio_board_devkit() -> None:
    adapter = vendor_adapters.get_adapter("esp32")
    assert adapter is not None
    board = adapter.platformio_board("ESP32-WROOM-32")
    assert "esp32" in board


def test_msp430_platformio_board_launchpad() -> None:
    adapter = vendor_adapters.get_adapter("msp430")
    assert adapter is not None
    board = adapter.platformio_board("MSP430G2553")
    assert "launchpad" in board


# --- workflow build/flash/observe prefer open-source backends ---

def _make_state(family: str = "stm32", part: str = "STM32F407VGT6") -> dict:
    """Build a minimal workflow state with chip-selection completed."""
    return {
        "workflow_id": "wf-test",
        "stages": [
            {
                "id": "chip-selection",
                "status": "completed",
                "evidence": {
                    "selected_part": part,
                    "backends": {
                        "vendor_adapter": {"family": family},
                        "backends": {"build": "gcc", "flash": "pyocd", "observe": "serial"},
                    },
                },
            },
        ],
        "context": {"part": part, "target": "", "probe": ""},
    }


def test_stage_build_prefers_platformio_when_available(tmp_path: Path) -> None:
    """When pio is on PATH, _stage_build uses platformio backend, not native."""
    import workflow_runner as wr

    state = _make_state("stm32")
    with patch("shutil.which", side_effect=lambda name: "/fake/pio" if name == "pio" else None):
        with patch("workflow_runner._run_subprocess", return_value={"status": "ok", "stdout": "build ok", "stderr": ""}) as mock_run:
            with patch("build_plan.generate_plan", return_value={"steps": [{"command": "gcc"}]}):
                result = wr._stage_build(tmp_path, wr.WorkflowContext(), state)
    assert result.status == "completed"
    assert result.evidence["build_backend"] == "platformio"
    assert mock_run.called
    called_cmd = mock_run.call_args[0][0]
    assert called_cmd[0] == "pio"


def test_stage_build_falls_back_when_pio_missing(tmp_path: Path) -> None:
    """When pio is not on PATH, _stage_build falls back to adapter native."""
    import workflow_runner as wr

    state = _make_state("stm32")
    with patch("shutil.which", return_value=None):
        with patch("workflow_runner._run_subprocess", return_value={"status": "ok", "stdout": "", "stderr": ""}):
            with patch("build_plan.generate_plan", return_value={"steps": [{"command": "gcc"}]}):
                result = wr._stage_build(tmp_path, wr.WorkflowContext(), state)
    assert result.status == "completed"
    assert result.evidence["build_executed"] is False
    assert "plan-only" in result.evidence.get("reason", "")
