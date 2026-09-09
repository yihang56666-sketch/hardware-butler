"""Command construction tests only; no vendor tool or probe is executed."""

import importlib
import tempfile
from pathlib import Path

import pytest
import vendor_adapters
from vendor_adapters.stm32 import STM32Adapter


def test_stm32_version_probe_is_not_a_build(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: "/mock/gcc" if name == "arm-none-eabi-gcc" else None)

    assert STM32Adapter().build_command({"project_root": str(tmp_path)}) == []


def test_stm32_unconfigured_cmake_is_not_a_build(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: f"/mock/{name}" if name in {"cmake", "ninja"} else None)

    assert STM32Adapter().build_command({"project_root": str(tmp_path)}) == []


def test_stm32_builds_configured_tree_under_project(tmp_path: Path, monkeypatch):
    build_dir = tmp_path / "build"
    build_dir.mkdir()
    (build_dir / "CMakeCache.txt").write_text("configured", encoding="utf-8")
    monkeypatch.setattr("shutil.which", lambda name: f"/mock/{name}" if name in {"cmake", "ninja"} else None)

    assert STM32Adapter().build_command({"project_root": str(tmp_path)}) == ["cmake", "--build", str(build_dir)]


@pytest.mark.parametrize("target", ["STM32F4\nloadfile other.elf", "STM32F4;reset", "STM32F4\rqc"])
def test_jlink_rejects_target_command_injection(tmp_path: Path, monkeypatch, target: str):
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))

    assert vendor_adapters.jlink_flash_command("JLinkExe", target=target, elf="firmware.elf") == []
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("module", ["stm32", "tiva", "riscv", "ra", "lpc", "imxrt", "max32", "rx"])
@pytest.mark.parametrize("elf", ["firmware.elf;shutdown", "[exit].elf", "${env(HOME)}.elf"])
def test_openocd_rejects_tcl_commands_in_firmware_path(monkeypatch, module: str, elf: str):
    importlib.import_module(f"vendor_adapters.{module}")
    adapter = vendor_adapters.get_adapter("ti-tiva" if module == "tiva" else module)
    monkeypatch.setattr("shutil.which", lambda name: "/mock/openocd" if name == "openocd" else None)

    assert adapter.flash_command({"elf": elf, "target": "TEST"}) == []


@pytest.mark.parametrize("module", ["stm32", "tiva", "riscv", "ra", "lpc", "imxrt", "max32", "rx"])
def test_openocd_preserves_firmware_paths_with_spaces(tmp_path: Path, monkeypatch, module: str):
    importlib.import_module(f"vendor_adapters.{module}")
    adapter = vendor_adapters.get_adapter("ti-tiva" if module == "tiva" else module)
    monkeypatch.setattr("shutil.which", lambda name: "/mock/openocd" if name == "openocd" else None)
    firmware = tmp_path / "project with spaces" / "firmware.elf"

    command = adapter.flash_command({"elf": str(firmware), "target": "TEST"})

    assert command[command.index("-c") + 1].startswith(f"program {{{firmware.as_posix()}}} ")


@pytest.mark.parametrize("rtos", [False, True])
def test_platformio_preserves_user_owned_freertos_script(tmp_path: Path, monkeypatch, rtos: bool):
    script = tmp_path / "pio_freertos.py"
    script.write_text("user-owned build script", encoding="utf-8")
    monkeypatch.setattr(STM32Adapter, "find_pio", lambda self, root: "/mock/pio")
    monkeypatch.setattr(STM32Adapter, "_pio_build_root", lambda self, root: root)
    context = {"project_root": str(tmp_path), "part": "STM32F407VGTx", "rtos": rtos}

    if rtos:
        with pytest.raises(ValueError, match="user-owned"):
            STM32Adapter().build_via_platformio(context)
    else:
        STM32Adapter().build_via_platformio(context)

    assert script.read_text(encoding="utf-8") == "user-owned build script"
