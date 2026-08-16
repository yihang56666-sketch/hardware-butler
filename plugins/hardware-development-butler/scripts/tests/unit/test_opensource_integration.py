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


# --- FreeRTOS on the PlatformIO backend (stm32cube framework) ---

def test_freertos_capability_by_family() -> None:
    """STM32 stm32cube builds can compile FreeRTOS; arduino/energia backends
    on other families cannot via this mechanism (esp32 arduino has its own
    FreeRTOS but a different codegen path that is not wired yet)."""
    stm32 = vendor_adapters.get_adapter("stm32")
    esp32 = vendor_adapters.get_adapter("esp32")
    msp430 = vendor_adapters.get_adapter("msp430")
    assert stm32 is not None and stm32.supports_freertos_on_platformio() is True
    assert esp32 is not None and esp32.supports_freertos_on_platformio() is False
    assert msp430 is not None and msp430.supports_freertos_on_platformio() is False


@pytest.mark.enable_platformio
def test_platformio_ini_rtos_adds_freertos_extra_script(tmp_path: Path) -> None:
    """rtos=True must wire the generated pre-script that compiles the
    framework-bundled FreeRTOS (stock stm32cube builder skips it)."""
    adapter = vendor_adapters.get_adapter("stm32")
    assert adapter is not None
    project = tmp_path / "proj"
    (project / "Core" / "Src").mkdir(parents=True)
    (project / "Core" / "Inc").mkdir(parents=True)
    with patch("shutil.which", return_value="/fake/pio"):
        cmd = adapter.build_via_platformio(
            {"project_root": str(project), "part": "STM32F407VGT6", "rtos": True}
        )
    assert cmd, "pio command expected"
    build_root = adapter.pio_build_root({"project_root": str(project)})
    ini = (build_root / "platformio.ini").read_text(encoding="utf-8")
    assert "extra_scripts = pre:pio_freertos.py" in ini
    script = build_root / "pio_freertos.py"
    assert script.exists()
    text = script.read_text(encoding="utf-8")
    assert "BuildSources" in text
    assert "CMSIS_RTOS" in text
    assert "Third_Party" in text
    # FPU flags: the ARM_CM4F port needs them (boards declare plain m4).
    assert "-mfloat-abi=hard" in text


@pytest.mark.enable_platformio
def test_platformio_ini_bare_metal_has_no_extra_script(tmp_path: Path) -> None:
    adapter = vendor_adapters.get_adapter("stm32")
    assert adapter is not None
    project = tmp_path / "proj"
    (project / "Core" / "Src").mkdir(parents=True)
    with patch("shutil.which", return_value="/fake/pio"):
        adapter.build_via_platformio({"project_root": str(project), "part": "STM32F407VGT6"})
    build_root = adapter.pio_build_root({"project_root": str(project)})
    ini = (build_root / "platformio.ini").read_text(encoding="utf-8")
    assert "extra_scripts" not in ini
    assert not (build_root / "pio_freertos.py").exists()


@pytest.mark.enable_platformio
def test_platformio_ini_rtos_ignored_for_unsupported_family(tmp_path: Path) -> None:
    """esp32/msp430: rtos flag in ctx must not fabricate a FreeRTOS script."""
    adapter = vendor_adapters.get_adapter("esp32")
    assert adapter is not None
    project = tmp_path / "esp"
    project.mkdir()
    with patch("shutil.which", return_value="/fake/pio"):
        adapter.build_via_platformio({"project_root": str(project), "rtos": True})
    build_root = adapter.pio_build_root({"project_root": str(project)})
    ini = (build_root / "platformio.ini").read_text(encoding="utf-8")
    assert "extra_scripts" not in ini
    assert not (build_root / "pio_freertos.py").exists()


@pytest.mark.enable_platformio
def test_platformio_user_ini_never_modified_for_freertos(tmp_path: Path) -> None:
    """When the user already has a platformio.ini, the workflow must not
    append FreeRTOS wiring to it (user owns that file)."""
    adapter = vendor_adapters.get_adapter("stm32")
    assert adapter is not None
    project = tmp_path / "user-proj"
    project.mkdir()
    original_ini = "[env:custom]\nplatform = ststm32\n"
    (project / "platformio.ini").write_text(original_ini, encoding="utf-8")
    with patch("shutil.which", return_value="/fake/pio"):
        adapter.build_via_platformio({"project_root": str(project), "part": "STM32F407VGT6", "rtos": True})
    assert (project / "platformio.ini").read_text(encoding="utf-8") == original_ini
    assert not (project / "pio_freertos.py").exists()


@pytest.mark.enable_platformio
def test_platformio_workflow_ini_refreshes_with_rtos_decision(tmp_path: Path) -> None:
    """A workflow-generated ini (marker line) must track the RTOS decision
    across optimize-loop iterations: bare-metal first, RTOS later upgrades
    the ini + writes the script, and a downgrade removes the stale script.
    This matters because the ASCII staging dir persists between builds."""
    adapter = vendor_adapters.get_adapter("stm32")
    assert adapter is not None
    project = tmp_path / "iter"
    (project / "Core" / "Src").mkdir(parents=True)
    with patch("shutil.which", return_value="/fake/pio"):
        adapter.build_via_platformio({"project_root": str(project), "part": "STM32F407VGT6"})
        build_root = adapter.pio_build_root({"project_root": str(project)})
        ini = (build_root / "platformio.ini").read_text(encoding="utf-8")
        assert "extra_scripts" not in ini
        assert not (build_root / "pio_freertos.py").exists()

        # optimize-loop re-runs with RTOS on: marker ini is regenerated
        adapter.build_via_platformio(
            {"project_root": str(project), "part": "STM32F407VGT6", "rtos": True}
        )
        ini = (build_root / "platformio.ini").read_text(encoding="utf-8")
        assert "extra_scripts = pre:pio_freertos.py" in ini
        assert (build_root / "pio_freertos.py").exists()

        # downgrade again: stale script must be removed
        adapter.build_via_platformio({"project_root": str(project), "part": "STM32F407VGT6"})
        ini = (build_root / "platformio.ini").read_text(encoding="utf-8")
        assert "extra_scripts" not in ini
        assert not (build_root / "pio_freertos.py").exists()


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
