"""Tests for Step F: open-source integration (PlatformIO + probe-rs + pyserial)."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, "tools")

import vendor_adapters  # noqa: E402
import vendor_adapters.esp32  # noqa: E402
import vendor_adapters.msp430  # noqa: E402
import vendor_adapters.stm32  # noqa: E402

# --- PlatformIO build integration ---

@pytest.mark.enable_platformio
def test_build_via_platformio_returns_empty_when_pio_missing(tmp_path: Path) -> None:
    adapter = vendor_adapters.get_adapter("stm32")
    assert adapter is not None
    with patch("shutil.which", return_value=None):
        with patch("pathlib.Path.exists", return_value=False):
            cmd = adapter.build_via_platformio({"project_root": str(tmp_path / "proj")})
    assert cmd == []


@pytest.mark.enable_platformio
def test_build_via_platformio_returns_pio_run_when_available(tmp_path: Path) -> None:
    adapter = vendor_adapters.get_adapter("stm32")
    assert adapter is not None
    project = tmp_path / "proj"
    project.mkdir()
    with patch("shutil.which", return_value="/fake/pio"):
        cmd = adapter.build_via_platformio({"project_root": str(project)})
    assert cmd[0] == "/fake/pio"
    assert "run" in cmd
    # platformio.ini should have been auto-generated. On non-ASCII project
    # paths (e.g. this workspace) the build is staged to an ASCII temp dir,
    # so resolve the actual build root instead of assuming project root.
    build_root = adapter.pio_build_root({"project_root": str(project)})
    assert (build_root / "platformio.ini").exists()
    assert cmd[-1] == str(build_root)


@pytest.mark.enable_platformio
def test_platformio_ini_matches_generated_hal_layout(tmp_path: Path) -> None:
    """Auto-generated ini must build the HAL code we actually generate:
    stm32cube framework (vendors HAL), src_dir=Core/Src, board from part."""
    adapter = vendor_adapters.get_adapter("stm32")
    assert adapter is not None
    project = tmp_path / "proj"
    (project / "Core" / "Src").mkdir(parents=True)
    (project / "Core" / "Inc").mkdir(parents=True)
    with patch("shutil.which", return_value="/fake/pio"):
        cmd = adapter.build_via_platformio({"project_root": str(project), "part": "STM32F407VGT6"})
    assert cmd, "pio command expected"
    build_root = adapter.pio_build_root({"project_root": str(project)})
    ini = (build_root / "platformio.ini").read_text(encoding="utf-8")
    assert "framework = stm32cube" in ini
    assert "board = disco_f407vg" in ini
    assert "src_dir = Core/Src" in ini
    assert "-ICore/Inc" in ini


@pytest.mark.enable_platformio
def test_build_via_platformio_for_esp32(tmp_path: Path) -> None:
    adapter = vendor_adapters.get_adapter("esp32")
    assert adapter is not None
    project = tmp_path / "esp"
    project.mkdir()
    with patch("shutil.which", return_value="/fake/pio"):
        cmd = adapter.build_via_platformio({"project_root": str(project)})
    assert cmd[0] == "/fake/pio"
    build_root = adapter.pio_build_root({"project_root": str(project)})
    assert (build_root / "platformio.ini").exists()


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

def test_stm32_platformio_board_disco_f407() -> None:
    adapter = vendor_adapters.get_adapter("stm32")
    assert adapter is not None
    # STM32F407VGT6 is the Discovery board chip; nucleo_f429zi was a wrong
    # mapping (F429 part on a Nucleo-144 board).
    board = adapter.platformio_board("STM32F407VGT6")
    assert board == "disco_f407vg"


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


@pytest.mark.enable_platformio
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
    assert "pio" in called_cmd[0] or called_cmd[0].endswith("pio")


@pytest.mark.enable_platformio
def test_stage_build_falls_back_when_pio_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """When pio is not on PATH, _stage_build falls back to adapter native."""
    import workflow_runner as wr

    # The adapter also searches parent dirs for a project-local .venv pio;
    # disable PlatformIO entirely so this test is isolated from the host env.
    monkeypatch.setenv("HARDWARE_BUTLER_DISABLE_PLATFORMIO", "1")
    state = _make_state("stm32")
    with patch("shutil.which", return_value=None):
        with patch("workflow_runner._run_subprocess", return_value={"status": "ok", "stdout": "", "stderr": ""}):
            with patch("build_plan.generate_plan", return_value={"steps": [{"command": "gcc"}]}):
                result = wr._stage_build(tmp_path, wr.WorkflowContext(), state)
    assert result.status == "completed"
    assert result.evidence["build_executed"] is False
    assert "plan-only" in result.evidence.get("reason", "")
