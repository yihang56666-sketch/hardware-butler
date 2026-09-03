"""Tests for the RISC-V vendor adapter (CH32V / GD32V series).

Covers family detection (V-suffix discrimination from Cortex-M GD32/CH32),
registry lookup, command generation (build / flash / observe fallbacks),
PlatformIO board mapping, and the FreeRTOS support flag. Runs offline.
"""

from __future__ import annotations

import sys
from unittest.mock import patch

sys.path.insert(0, "tools")

import vendor_adapters  # noqa: E402
import vendor_adapters.riscv  # noqa: E402


def test_detect_family_riscv_ch32v() -> None:
    assert vendor_adapters.detect_family("CH32V103R8T6") == "riscv"
    assert vendor_adapters.detect_family("CH32V203C8T6") == "riscv"
    assert vendor_adapters.detect_family("CH32V307VCT6") == "riscv"


def test_detect_family_riscv_gd32v() -> None:
    assert vendor_adapters.detect_family("GD32VF103C8T6") == "riscv"
    assert vendor_adapters.detect_family("GD32VF103CBT6") == "riscv"


def test_detect_family_cortex_m_gd32_still_stm32() -> None:
    """GD32 (no V suffix) is Cortex-M and should stay stm32-compatible."""
    assert vendor_adapters.detect_family("GD32F103C8T6") == "stm32"
    assert vendor_adapters.detect_family("CH32F103C8T6") == "stm32"


def test_riscv_adapter_registered() -> None:
    adapter = vendor_adapters.get_adapter("riscv")
    assert adapter is not None
    assert adapter.family == "riscv"
    assert adapter.vendor_id == "wch"
    assert adapter.build_tool == "riscv64-unknown-elf-gcc"
    assert adapter.flash_tool == "wlink"


def test_riscv_build_command_uses_make_when_present() -> None:
    adapter = vendor_adapters.get_adapter("riscv")
    assert adapter is not None
    with patch("vendor_adapters.riscv.shutil.which", return_value="/usr/bin/make"):
        cmd = adapter.build_command({"project_root": "/proj"})
    assert cmd == ["make", "-C", "/proj"]


def test_riscv_build_command_reports_no_toolchain_when_no_make() -> None:
    adapter = vendor_adapters.get_adapter("riscv")
    assert adapter is not None
    with patch("vendor_adapters.riscv.shutil.which", return_value=""):
        cmd = adapter.build_command({"project_root": "/proj"})
    # A bare `gcc --version` probe would be counted as a successful build.
    assert cmd == []


def test_riscv_flash_command_prefers_wlink() -> None:
    adapter = vendor_adapters.get_adapter("riscv")
    assert adapter is not None
    with patch("vendor_adapters.riscv.shutil.which", side_effect=lambda n: "/usr/bin/" + n if n == "wlink" else ""):
        cmd = adapter.flash_command({"elf": "fw.hex"})
    assert cmd[0] == "wlink"
    assert "flash" in cmd
    assert "fw.hex" in cmd


def test_riscv_flash_command_falls_back_to_openocd() -> None:
    adapter = vendor_adapters.get_adapter("riscv")
    assert adapter is not None
    with patch("vendor_adapters.riscv.shutil.which", side_effect=lambda n: "/usr/bin/" + n if n == "openocd" else ""):
        cmd = adapter.flash_command({"elf": "fw.elf", "openocd_cfg": "wch-link.cfg"})
    assert cmd[0] == "openocd"
    assert "-f" in cmd and "wch-link.cfg" in cmd
    assert "program" in " ".join(cmd)
    assert "fw.elf" in " ".join(cmd)


def test_riscv_flash_command_empty_when_no_tools() -> None:
    adapter = vendor_adapters.get_adapter("riscv")
    assert adapter is not None
    with patch("vendor_adapters.riscv.shutil.which", return_value=""):
        assert adapter.flash_command({"elf": "fw.hex"}) == []


def test_riscv_observe_command_requires_port() -> None:
    adapter = vendor_adapters.get_adapter("riscv")
    assert adapter is not None
    assert adapter.observe_command({}) == []
    cmd = adapter.observe_command({"port": "/dev/ttyUSB0", "baud": "115200"})
    assert cmd[0] == sys.executable
    assert "/dev/ttyUSB0" in cmd
    assert "115200" in cmd


def test_riscv_platformio_board_mapping() -> None:
    adapter = vendor_adapters.get_adapter("riscv")
    assert adapter is not None
    # No stock `platform = wch-riscv` exists in PlatformIO: CH32V needs the
    # community git-URL platform and GD32V lives under the sipeed gd32v
    # platform. All parts opt out ("" -> native make/gcc build path).
    assert adapter.platformio_board("CH32V103R8T6") == ""
    assert adapter.platformio_board("CH32V203C8T6") == ""
    assert adapter.platformio_board("CH32V307VCT6") == ""
    assert adapter.platformio_board("GD32VF103C8T6") == ""
    assert adapter.platformio_board("UNKNOWN") == ""


def test_riscv_platformio_platform_and_framework() -> None:
    adapter = vendor_adapters.get_adapter("riscv")
    assert adapter is not None
    assert adapter._platformio_platform() == ""
    assert adapter._platformio_framework() == ""


def test_riscv_supports_freertos_on_platformio() -> None:
    adapter = vendor_adapters.get_adapter("riscv")
    assert adapter is not None
    # PlatformIO is disabled for this family (no stock registry platform);
    # FreeRTOS codegen goes through the native make/gcc build path.
    assert adapter.supports_freertos_on_platformio() is False


def test_riscv_datasheet_queries_include_mounriver() -> None:
    adapter = vendor_adapters.get_adapter("riscv")
    assert adapter is not None
    queries = adapter.datasheet_queries("CH32V103")
    assert any("CH32V103" in q for q in queries)
    assert any("pdf" in q for q in queries)
    # The official IDE name is included so the research stage finds WCH docs.
    assert any("MounRiver" in q for q in queries)


def test_riscv_detect_tools_returns_all_expected_keys() -> None:
    adapter = vendor_adapters.get_adapter("riscv")
    assert adapter is not None
    tools = adapter.detect_tools()
    for key in (
        "riscv64-unknown-elf-gcc",
        "riscv-none-embed-gcc",
        "riscv-none-elf-gcc",
        "wlink",
        "openocd",
        "make",
    ):
        assert key in tools
        assert isinstance(tools[key], bool)


def test_riscv_canonical_chip_passes_through() -> None:
    """RISC-V part numbers don't use the STM32 package-digit convention."""
    adapter = vendor_adapters.get_adapter("riscv")
    assert adapter is not None
    assert adapter.canonical_chip("CH32V103R8T6") == "CH32V103R8T6"
    assert adapter.canonical_chip("GD32VF103CBT6") == "GD32VF103CBT6"
