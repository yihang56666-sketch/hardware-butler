"""Tests for the TI Tiva C and C2000 vendor adapters.

Covers family detection, registry lookup, command generation (build / flash /
observe fallbacks), PlatformIO board mapping (Tiva only — C2000 has no
PlatformIO support), and FreeRTOS support flags. Runs offline.
"""

from __future__ import annotations

import sys
from unittest.mock import patch

sys.path.insert(0, "tools")

import vendor_adapters  # noqa: E402
import vendor_adapters.c2000  # noqa: E402
import vendor_adapters.tiva  # noqa: E402

# --- family detection ---


def test_detect_family_ti_tiva_tm4c() -> None:
    assert vendor_adapters.detect_family("TM4C123GH6PM") == "ti-tiva"
    assert vendor_adapters.detect_family("TM4C1294NCPDT") == "ti-tiva"


def test_detect_family_ti_tiva_lm4f() -> None:
    assert vendor_adapters.detect_family("LM4F120H5QR") == "ti-tiva"


def test_detect_family_ti_tiva_cc26xx() -> None:
    assert vendor_adapters.detect_family("CC2650F128") == "ti-tiva"
    assert vendor_adapters.detect_family("CC2640R2F") == "ti-tiva"


def test_detect_family_c2000_tms320() -> None:
    assert vendor_adapters.detect_family("TMS320F28069") == "c2000"
    assert vendor_adapters.detect_family("TMS320F28377D") == "c2000"


def test_detect_family_c2000_f280() -> None:
    """Short form 'F280xx' without the TMS320 prefix is also a C2000."""
    assert vendor_adapters.detect_family("F28069") == "c2000"
    assert vendor_adapters.detect_family("F28377D") == "c2000"


# --- tiva adapter ---


def test_tiva_adapter_registered() -> None:
    adapter = vendor_adapters.get_adapter("ti-tiva")
    assert adapter is not None
    assert adapter.family == "ti-tiva"
    assert adapter.vendor_id == "ti"
    assert adapter.build_tool == "arm-none-eabi-gcc"
    assert adapter.flash_tool == "dslite"


def test_tiva_build_command_uses_make_when_present() -> None:
    adapter = vendor_adapters.get_adapter("ti-tiva")
    assert adapter is not None
    with patch("vendor_adapters.tiva.shutil.which", return_value="/usr/bin/make"):
        cmd = adapter.build_command({"project_root": "/proj"})
    assert cmd == ["make", "-C", "/proj"]


def test_tiva_build_command_falls_back_to_gcc_version() -> None:
    adapter = vendor_adapters.get_adapter("ti-tiva")
    assert adapter is not None
    with patch("vendor_adapters.tiva.shutil.which", return_value=""):
        cmd = adapter.build_command({"project_root": "/proj"})
    assert cmd == ["arm-none-eabi-gcc", "--version"]


def test_tiva_flash_command_prefers_dslite() -> None:
    adapter = vendor_adapters.get_adapter("ti-tiva")
    assert adapter is not None

    def which(name: str) -> str:
        return "/usr/bin/" + name if name in ("dslite", "lm4flash", "openocd") else ""

    with patch("vendor_adapters.tiva.shutil.which", side_effect=which):
        cmd = adapter.flash_command({"elf": "fw.bin", "target": "TM4C123GH6PM"})
    assert cmd[0] == "dslite"
    assert "flash" in cmd
    assert "--config" in cmd and "TM4C123GH6PM.ccxml" in cmd
    assert "fw.bin" in cmd


def test_tiva_flash_command_falls_back_to_lm4flash() -> None:
    adapter = vendor_adapters.get_adapter("ti-tiva")
    assert adapter is not None

    def which(name: str) -> str:
        return "/usr/bin/" + name if name == "lm4flash" else ""

    with patch("vendor_adapters.tiva.shutil.which", side_effect=which):
        cmd = adapter.flash_command({"elf": "fw.bin"})
    assert cmd[0] == "lm4flash"
    assert "fw.bin" in cmd


def test_tiva_flash_command_falls_back_to_openocd() -> None:
    adapter = vendor_adapters.get_adapter("ti-tiva")
    assert adapter is not None

    def which(name: str) -> str:
        return "/usr/bin/" + name if name == "openocd" else ""

    with patch("vendor_adapters.tiva.shutil.which", side_effect=which):
        cmd = adapter.flash_command({"elf": "fw.elf", "openocd_cfg": "ti-cs-dap.cfg"})
    assert cmd[0] == "openocd"
    assert "-f" in cmd and "ti-cs-dap.cfg" in cmd


def test_tiva_flash_command_empty_when_no_tools() -> None:
    adapter = vendor_adapters.get_adapter("ti-tiva")
    assert adapter is not None
    with patch("vendor_adapters.tiva.shutil.which", return_value=""):
        assert adapter.flash_command({"elf": "fw.bin"}) == []


def test_tiva_observe_command_requires_port() -> None:
    adapter = vendor_adapters.get_adapter("ti-tiva")
    assert adapter is not None
    assert adapter.observe_command({}) == []
    cmd = adapter.observe_command({"port": "/dev/ttyACM0", "baud": "115200"})
    assert cmd[0] == "python"
    assert "/dev/ttyACM0" in cmd
    assert "115200" in cmd


def test_tiva_platformio_board_mapping() -> None:
    adapter = vendor_adapters.get_adapter("ti-tiva")
    assert adapter is not None
    assert adapter.platformio_board("TM4C123GH6PM") == "lptm4c1230c6pd"
    assert adapter.platformio_board("TM4C1294NCPDT") == "lptm4c1294ncpdt"
    assert adapter.platformio_board("CC2650F128") == "cc2650_launchpad"
    assert adapter.platformio_board("CC2640R2F") == "cc2640r2_launchpad"
    assert adapter.platformio_board("LM4F120H5QR") == "lptm4c1230c6pd"
    # Unknown -> conservative default
    assert adapter.platformio_board("UNKNOWN") == "lptm4c1230c6pd"


def test_tiva_platformio_platform_and_framework() -> None:
    adapter = vendor_adapters.get_adapter("ti-tiva")
    assert adapter is not None
    assert adapter._platformio_platform() == "titiva"
    assert adapter._platformio_framework() == "libopencm3"


def test_tiva_does_not_support_freertos_on_platformio() -> None:
    """Tiva's libopencm3 framework doesn't vendor CMSIS-RTOS, so FreeRTOS
    codegen is bare-metal-only on Tiva. The optimize-loop falls back."""
    adapter = vendor_adapters.get_adapter("ti-tiva")
    assert adapter is not None
    assert adapter.supports_freertos_on_platformio() is False


def test_tiva_datasheet_queries_include_tivaware() -> None:
    adapter = vendor_adapters.get_adapter("ti-tiva")
    assert adapter is not None
    queries = adapter.datasheet_queries("TM4C123GH6PM")
    assert any("TivaWare" in q for q in queries)
    assert any("pdf" in q for q in queries)


def test_tiva_detect_tools_returns_all_expected_keys() -> None:
    adapter = vendor_adapters.get_adapter("ti-tiva")
    assert adapter is not None
    tools = adapter.detect_tools()
    for key in ("arm-none-eabi-gcc", "cl470", "dslite", "lm4flash", "openocd", "uniflash", "make"):
        assert key in tools
        assert isinstance(tools[key], bool)


# --- c2000 adapter ---


def test_c2000_adapter_registered() -> None:
    adapter = vendor_adapters.get_adapter("c2000")
    assert adapter is not None
    assert adapter.family == "c2000"
    assert adapter.vendor_id == "ti"
    assert adapter.build_tool == "cl2000"
    assert adapter.flash_tool == "dslite"


def test_c2000_build_command_uses_make_when_present() -> None:
    adapter = vendor_adapters.get_adapter("c2000")
    assert adapter is not None
    with patch("vendor_adapters.c2000.shutil.which", return_value="/usr/bin/make"):
        cmd = adapter.build_command({"project_root": "/proj"})
    assert cmd == ["make", "-C", "/proj"]


def test_c2000_build_command_falls_back_to_cl2000_version() -> None:
    adapter = vendor_adapters.get_adapter("c2000")
    assert adapter is not None
    with patch("vendor_adapters.c2000.shutil.which", side_effect=lambda n: "/usr/bin/cl2000" if n == "cl2000" else ""):
        cmd = adapter.build_command({"project_root": "/proj"})
    assert cmd == ["cl2000", "--version"]


def test_c2000_build_command_empty_when_no_tools() -> None:
    """Neither make nor cl2000 present — the adapter must return [] so the
    workflow's optimize-loop can surface a build_backend_missing risk rather
    than crash."""
    adapter = vendor_adapters.get_adapter("c2000")
    assert adapter is not None
    with patch("vendor_adapters.c2000.shutil.which", return_value=""):
        assert adapter.build_command({"project_root": "/proj"}) == []


def test_c2000_flash_command_prefers_dslite() -> None:
    adapter = vendor_adapters.get_adapter("c2000")
    assert adapter is not None

    def which(name: str) -> str:
        return "/usr/bin/" + name if name in ("dslite", "c2kprog") else ""

    with patch("vendor_adapters.c2000.shutil.which", side_effect=which):
        cmd = adapter.flash_command({"elf": "fw.out", "target": "TMS320F28069"})
    assert cmd[0] == "dslite"
    assert "flash" in cmd
    assert "--config" in cmd and "TMS320F28069.ccxml" in cmd
    assert "fw.out" in cmd


def test_c2000_flash_command_falls_back_to_c2kprog() -> None:
    adapter = vendor_adapters.get_adapter("c2000")
    assert adapter is not None
    with patch("vendor_adapters.c2000.shutil.which", side_effect=lambda n: "/usr/bin/" + n if n == "c2kprog" else ""):
        cmd = adapter.flash_command({"elf": "fw.out"})
    assert cmd[0] == "c2kprog"
    assert "fw.out" in cmd


def test_c2000_flash_command_empty_when_no_tools() -> None:
    adapter = vendor_adapters.get_adapter("c2000")
    assert adapter is not None
    with patch("vendor_adapters.c2000.shutil.which", return_value=""):
        assert adapter.flash_command({"elf": "fw.out"}) == []


def test_c2000_observe_command_requires_port() -> None:
    adapter = vendor_adapters.get_adapter("c2000")
    assert adapter is not None
    assert adapter.observe_command({}) == []
    cmd = adapter.observe_command({"port": "/dev/ttyUSB0", "baud": "115200"})
    assert cmd[0] == "python"
    assert "/dev/ttyUSB0" in cmd


def test_c2000_has_no_platformio_support() -> None:
    """C2000's C28x architecture has no GCC port — PlatformIO cannot build it.
    The adapter returns empty board id and empty platform."""
    adapter = vendor_adapters.get_adapter("c2000")
    assert adapter is not None
    assert adapter.platformio_board("TMS320F28069") == ""
    assert adapter._platformio_platform() == ""
    assert adapter._platformio_framework() == ""
    assert adapter.supports_freertos_on_platformio() is False


def test_c2000_datasheet_queries_use_technical_reference_manual_term() -> None:
    adapter = vendor_adapters.get_adapter("c2000")
    assert adapter is not None
    queries = adapter.datasheet_queries("TMS320F28069")
    assert any("technical reference manual" in q for q in queries)
    assert any("C2000Ware" in q for q in queries)


def test_c2000_detect_tools_returns_all_expected_keys() -> None:
    adapter = vendor_adapters.get_adapter("c2000")
    assert adapter is not None
    tools = adapter.detect_tools()
    for key in ("cl2000", "dslite", "c2kprog", "uniflash", "make"):
        assert key in tools
        assert isinstance(tools[key], bool)
