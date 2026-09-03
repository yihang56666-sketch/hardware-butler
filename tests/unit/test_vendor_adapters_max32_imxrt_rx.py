"""Tests for the Maxim MAX32 / NXP i.MX RT / Renesas RX vendor adapters.

Phase 13 — extends multi-MCU coverage to three more mainstream embedded
ecosystems: Maxim MAX32 (Cortex-M4F for wearables), NXP i.MX RT (Cortex-M7
crossover, high-performance), Renesas RX (32-bit CISC, distinct from the
Cortex-M RA family).
"""

from __future__ import annotations

import sys
from unittest.mock import patch

sys.path.insert(0, "tools")

import vendor_adapters  # noqa: E402
import vendor_adapters.imxrt  # noqa: E402
import vendor_adapters.max32  # noqa: E402
import vendor_adapters.rx  # noqa: E402

# =========================
# Maxim MAX32 family
# =========================


def test_detect_family_max32() -> None:
    assert vendor_adapters.detect_family("MAX32660") == "max32"
    assert vendor_adapters.detect_family("MAX32666") == "max32"
    assert vendor_adapters.detect_family("MAX32670") == "max32"
    assert vendor_adapters.detect_family("MAX32690") == "max32"


def test_max32_adapter_registered() -> None:
    adapter = vendor_adapters.get_adapter("max32")
    assert adapter is not None
    assert adapter.family == "max32"
    assert adapter.vendor_id == "maxim"
    assert adapter.build_tool == "arm-none-eabi-gcc"
    assert adapter.flash_tool == "openocd"


def test_max32_build_command_uses_make_when_present() -> None:
    adapter = vendor_adapters.get_adapter("max32")
    assert adapter is not None
    with patch("vendor_adapters.max32.shutil.which", return_value="/usr/bin/make"):
        cmd = adapter.build_command({"project_root": "/proj"})
    assert cmd == ["make", "-C", "/proj"]


def test_max32_build_command_reports_no_toolchain_without_make() -> None:
    adapter = vendor_adapters.get_adapter("max32")
    assert adapter is not None
    with patch("vendor_adapters.max32.shutil.which", return_value=""):
        cmd = adapter.build_command({"project_root": "/proj"})
    # A bare `gcc --version` probe would be counted as a successful build.
    assert cmd == []


def test_max32_flash_command_prefers_openocd() -> None:
    adapter = vendor_adapters.get_adapter("max32")
    assert adapter is not None

    def which(name: str) -> str:
        return "/usr/bin/" + name if name in ("openocd", "pyocd", "probe-rs", "JLinkExe") else ""

    with patch("vendor_adapters.max32.shutil.which", side_effect=which):
        cmd = adapter.flash_command({"elf": "fw.elf", "openocd_cfg": "max32665.cfg"})
    assert cmd[0] == "openocd"
    assert "-f" in cmd and "max32665.cfg" in cmd


def test_max32_flash_command_falls_back_to_pyocd() -> None:
    adapter = vendor_adapters.get_adapter("max32")
    assert adapter is not None

    def which(name: str) -> str:
        return "/usr/bin/" + name if name == "pyocd" else ""

    with patch("vendor_adapters.max32.shutil.which", side_effect=which):
        cmd = adapter.flash_command({"elf": "fw.elf", "target": "max32665"})
    assert cmd[0] == "pyocd"
    assert "flash" in cmd
    assert "-t" in cmd


def test_max32_flash_command_falls_back_to_probe_rs() -> None:
    adapter = vendor_adapters.get_adapter("max32")
    assert adapter is not None

    def which(name: str) -> str:
        return "/usr/bin/" + name if name == "probe-rs" else ""

    with patch("vendor_adapters.max32.shutil.which", side_effect=which):
        cmd = adapter.flash_command({"elf": "fw.elf", "target": "max32660"})
    assert cmd[0] == "probe-rs"
    assert "download" in cmd
    assert "--verify" in cmd


def test_max32_flash_command_empty_when_no_tools() -> None:
    adapter = vendor_adapters.get_adapter("max32")
    assert adapter is not None
    with patch("vendor_adapters.max32.shutil.which", return_value=""):
        assert adapter.flash_command({"elf": "fw.elf"}) == []


def test_max32_observe_prefers_probe_rs_rtt() -> None:
    adapter = vendor_adapters.get_adapter("max32")
    assert adapter is not None
    with patch("vendor_adapters.max32.shutil.which", side_effect=lambda n: "/usr/bin/" + n if n == "probe-rs" else ""):
        cmd = adapter.observe_command({"target": "max32660"})
    assert cmd[0] == "probe-rs"
    assert "rtt" in cmd


def test_max32_observe_falls_back_to_uart() -> None:
    adapter = vendor_adapters.get_adapter("max32")
    assert adapter is not None
    with patch("vendor_adapters.max32.shutil.which", return_value=""):
        cmd = adapter.observe_command({"port": "/dev/ttyUSB0"})
    assert cmd[0] == sys.executable


def test_max32_platformio_board_mapping() -> None:
    adapter = vendor_adapters.get_adapter("max32")
    assert adapter is not None
    # platform-maxim32 does not support MAX32660/66/70/90 (upstream board
    # list stops at MAX32600/32620/32625/32630) -> opt out to native build.
    assert adapter.platformio_board("MAX32660") == ""
    assert adapter.platformio_board("MAX32666") == ""
    assert adapter.platformio_board("MAX32670") == ""
    assert adapter.platformio_board("MAX32690") == ""


def test_max32_supports_freertos_on_platformio() -> None:
    adapter = vendor_adapters.get_adapter("max32")
    assert adapter is not None
    assert adapter.supports_freertos_on_platformio() is True


def test_max32_datasheet_queries_include_msd() -> None:
    adapter = vendor_adapters.get_adapter("max32")
    assert adapter is not None
    queries = adapter.datasheet_queries("MAX32660")
    assert any("MSDK" in q for q in queries)
    assert any("pdf" in q for q in queries)


def test_max32_canonical_chip_passes_through() -> None:
    adapter = vendor_adapters.get_adapter("max32")
    assert adapter is not None
    assert adapter.canonical_chip("MAX32660") == "MAX32660"


# =========================
# NXP i.MX RT family
# =========================


def test_detect_family_imxrt_mimxrt_prefix() -> None:
    assert vendor_adapters.detect_family("MIMXRT1052DVL6B") == "imxrt"
    assert vendor_adapters.detect_family("MIMXRT1062DVL6B") == "imxrt"


def test_detect_family_imxrt_short_form() -> None:
    assert vendor_adapters.detect_family("RT1050") == "imxrt"
    assert vendor_adapters.detect_family("RT1060") == "imxrt"
    assert vendor_adapters.detect_family("RT1170") == "imxrt"


def test_imxrt_adapter_registered() -> None:
    adapter = vendor_adapters.get_adapter("imxrt")
    assert adapter is not None
    assert adapter.family == "imxrt"
    assert adapter.vendor_id == "nxp"
    assert adapter.build_tool == "arm-none-eabi-gcc"
    assert adapter.flash_tool == "probe-rs"


def test_imxrt_build_command_prefers_cmake_ninja() -> None:
    adapter = vendor_adapters.get_adapter("imxrt")
    assert adapter is not None

    def which(name: str) -> str:
        return "/usr/bin/" + name if name in ("cmake", "ninja") else ""

    with patch("vendor_adapters.imxrt.shutil.which", side_effect=which):
        cmd = adapter.build_command({"project_root": "/proj"})
    assert cmd == ["cmake", "--build", "/proj"]


def test_imxrt_build_command_falls_back_to_make() -> None:
    adapter = vendor_adapters.get_adapter("imxrt")
    assert adapter is not None
    with patch("vendor_adapters.imxrt.shutil.which", side_effect=lambda n: "/usr/bin/" + n if n == "make" else ""):
        cmd = adapter.build_command({"project_root": "/proj"})
    assert cmd == ["make", "-C", "/proj"]


def test_imxrt_build_command_reports_no_toolchain_without_cmake_make() -> None:
    adapter = vendor_adapters.get_adapter("imxrt")
    assert adapter is not None
    with patch("vendor_adapters.imxrt.shutil.which", return_value=""):
        cmd = adapter.build_command({"project_root": "/proj"})
    assert cmd == []


def test_imxrt_flash_command_prefers_probe_rs() -> None:
    adapter = vendor_adapters.get_adapter("imxrt")
    assert adapter is not None

    def which(name: str) -> str:
        return "/usr/bin/" + name if name in ("probe-rs", "pyocd", "JLinkExe", "openocd") else ""

    with patch("vendor_adapters.imxrt.shutil.which", side_effect=which):
        cmd = adapter.flash_command({"elf": "fw.elf", "target": "MIMXRT1052"})
    assert cmd[0] == "probe-rs"
    assert "download" in cmd
    assert "--verify" in cmd
    assert "--chip" in cmd


def test_imxrt_flash_command_falls_back_to_pyocd() -> None:
    adapter = vendor_adapters.get_adapter("imxrt")
    assert adapter is not None
    with patch("vendor_adapters.imxrt.shutil.which", side_effect=lambda n: "/usr/bin/" + n if n == "pyocd" else ""):
        cmd = adapter.flash_command({"elf": "fw.elf", "target": "MIMXRT1052"})
    assert cmd[0] == "pyocd"


def test_imxrt_flash_command_falls_back_to_jlink() -> None:
    adapter = vendor_adapters.get_adapter("imxrt")
    assert adapter is not None
    with patch("vendor_adapters.imxrt._segger_jlink", return_value="/usr/bin/JLink.exe"), \
         patch("vendor_adapters.imxrt.shutil.which", return_value=""):
        cmd = adapter.flash_command({"elf": "fw.elf", "target": "MIMXRT1062"})
    assert cmd[0] == "JLink.exe"


def test_imxrt_flash_command_empty_when_no_tools() -> None:
    adapter = vendor_adapters.get_adapter("imxrt")
    assert adapter is not None
    with patch("vendor_adapters.imxrt.shutil.which", return_value=""):
        assert adapter.flash_command({"elf": "fw.elf"}) == []


def test_imxrt_observe_prefers_probe_rs_rtt() -> None:
    adapter = vendor_adapters.get_adapter("imxrt")
    assert adapter is not None
    with patch("vendor_adapters.imxrt.shutil.which", side_effect=lambda n: "/usr/bin/" + n if n == "probe-rs" else ""):
        cmd = adapter.observe_command({"target": "MIMXRT1052"})
    assert cmd[0] == "probe-rs"
    assert "rtt" in cmd


def test_imxrt_observe_falls_back_to_pyocd_rtt() -> None:
    adapter = vendor_adapters.get_adapter("imxrt")
    assert adapter is not None
    with patch("vendor_adapters.imxrt.shutil.which", side_effect=lambda n: "/usr/bin/" + n if n == "pyocd" else ""):
        cmd = adapter.observe_command({"target": "MIMXRT1052"})
    assert cmd[0] == "pyocd"


def test_imxrt_platformio_board_mapping() -> None:
    adapter = vendor_adapters.get_adapter("imxrt")
    assert adapter is not None
    assert adapter.platformio_board("MIMXRT1011") == "imxrt1010_evk"
    assert adapter.platformio_board("MIMXRT1052") == "imxrt1050_evk"
    assert adapter.platformio_board("MIMXRT1062") == "imxrt1060_evk"
    assert adapter.platformio_board("MIMXRT1176") == "imxrt1170_evk_cm7"


def test_imxrt_supports_freertos_on_platformio() -> None:
    adapter = vendor_adapters.get_adapter("imxrt")
    assert adapter is not None
    assert adapter.supports_freertos_on_platformio() is True


def test_imxrt_datasheet_queries_include_flexspi() -> None:
    adapter = vendor_adapters.get_adapter("imxrt")
    assert adapter is not None
    queries = adapter.datasheet_queries("MIMXRT1052")
    assert any("flexspi" in q for q in queries)
    assert any("pdf" in q for q in queries)


# =========================
# Renesas RX family (CISC, distinct from RA)
# =========================


def test_detect_family_rx_risc() -> None:
    assert vendor_adapters.detect_family("RX65N") == "rx"
    assert vendor_adapters.detect_family("RX72N") == "rx"
    assert vendor_adapters.detect_family("RX130") == "rx"
    assert vendor_adapters.detect_family("RX231") == "rx"


def test_detect_family_does_not_confuse_rx_with_ra() -> None:
    """RA parts start with 'RA4'/'RA6' or 'R7FA'; RX parts start with 'RX<digit>'.
    They must NOT collide."""
    assert vendor_adapters.detect_family("RX65N") == "rx"
    assert vendor_adapters.detect_family("RA6M3") == "ra"
    assert vendor_adapters.detect_family("R7FA6M5BH") == "ra"


def test_rx_adapter_registered() -> None:
    adapter = vendor_adapters.get_adapter("rx")
    assert adapter is not None
    assert adapter.family == "rx"
    assert adapter.vendor_id == "renesas"
    assert adapter.build_tool == "rx-elf-gcc"
    assert adapter.flash_tool == "rfp-cli"


def test_rx_build_command_uses_make_when_present() -> None:
    adapter = vendor_adapters.get_adapter("rx")
    assert adapter is not None
    with patch("vendor_adapters.rx.shutil.which", return_value="/usr/bin/make"):
        cmd = adapter.build_command({"project_root": "/proj"})
    assert cmd == ["make", "-C", "/proj"]


def test_rx_build_command_reports_no_toolchain_without_make() -> None:
    adapter = vendor_adapters.get_adapter("rx")
    assert adapter is not None
    with patch("vendor_adapters.rx.shutil.which", side_effect=lambda n: "/usr/bin/rx-elf-gcc" if n == "rx-elf-gcc" else ""):
        cmd = adapter.build_command({"project_root": "/proj"})
    assert cmd == []


def test_rx_flash_command_prefers_rfp_cli() -> None:
    adapter = vendor_adapters.get_adapter("rx")
    assert adapter is not None

    def which(name: str) -> str:
        return "/usr/bin/" + name if name in ("rfp-cli", "JLinkExe", "openocd") else ""

    with patch("vendor_adapters.rx.shutil.which", side_effect=which):
        cmd = adapter.flash_command({"elf": "fw.mot", "target": "RX65N", "probe": "E2Lite"})
    assert cmd[0] == "rfp-cli"
    assert "-device" in cmd and "RX65N" in cmd
    assert "-tool" in cmd and "e2" in cmd
    assert "-port" in cmd and "E2Lite" in cmd
    assert "-file" in cmd and "fw.mot" in cmd


def test_rx_flash_command_falls_back_to_jlink() -> None:
    adapter = vendor_adapters.get_adapter("rx")
    assert adapter is not None

    with patch("vendor_adapters.rx._segger_jlink", return_value="/usr/bin/JLink.exe"), \
         patch("vendor_adapters.rx.shutil.which", return_value=""):
        cmd = adapter.flash_command({"elf": "fw.mot", "target": "RX65N"})
    assert cmd[0] == "JLink.exe"


def test_rx_flash_command_empty_when_no_tools() -> None:
    adapter = vendor_adapters.get_adapter("rx")
    assert adapter is not None
    with patch("vendor_adapters.rx.shutil.which", return_value=""):
        assert adapter.flash_command({"elf": "fw.mot"}) == []


def test_rx_observe_command_requires_port() -> None:
    """RX has no RTT — observe is UART only."""
    adapter = vendor_adapters.get_adapter("rx")
    assert adapter is not None
    assert adapter.observe_command({}) == []
    cmd = adapter.observe_command({"port": "/dev/ttyUSB0", "baud": "115200"})
    assert cmd[0] == sys.executable
    assert "/dev/ttyUSB0" in cmd


def test_rx_has_no_platformio_support() -> None:
    """RX's CISC architecture has no PlatformIO framework. Empty board/platform."""
    adapter = vendor_adapters.get_adapter("rx")
    assert adapter is not None
    assert adapter.platformio_board("RX65N") == ""
    assert adapter._platformio_platform() == ""
    assert adapter._platformio_framework() == ""
    assert adapter.supports_freertos_on_platformio() is False


def test_rx_datasheet_queries_include_e2_studio() -> None:
    adapter = vendor_adapters.get_adapter("rx")
    assert adapter is not None
    queries = adapter.datasheet_queries("RX65N")
    assert any("e2 studio" in q for q in queries)
    assert any("CC-RX" in q for q in queries)


def test_rx_detect_tools_returns_all_expected_keys() -> None:
    adapter = vendor_adapters.get_adapter("rx")
    assert adapter is not None
    tools = adapter.detect_tools()
    for key in ("rx-elf-gcc", "cc-rx", "rfp-cli", "JLinkExe", "JLink.exe", "openocd", "make"):
        assert key in tools
        assert isinstance(tools[key], bool)
