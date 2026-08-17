"""Tests for the Renesas RA / NXP LPC / Microchip PIC32 vendor adapters.

Phase 12 — extends multi-MCU coverage to the three remaining mainstream
embedded ecosystems (Renesas, NXP, Microchip 32-bit). Together with the
prior 8 families, the registry now covers 11 vendor families.
"""

from __future__ import annotations

import sys
from unittest.mock import patch

sys.path.insert(0, "tools")

import vendor_adapters  # noqa: E402
import vendor_adapters.lpc  # noqa: E402
import vendor_adapters.pic32  # noqa: E402
import vendor_adapters.ra  # noqa: E402

# =========================
# Renesas RA family
# =========================


def test_detect_family_ra_r7fa_prefix() -> None:
    """RA parts ship as R7FA<digits> orderable part numbers."""
    assert vendor_adapters.detect_family("R7FA6M5BH3CFB") == "ra"
    assert vendor_adapters.detect_family("R7FA4M1AB3CFP") == "ra"


def test_detect_family_ra_short_form() -> None:
    """Short form 'RA4M1' / 'RA6M3' without the R7 prefix."""
    assert vendor_adapters.detect_family("RA4M1") == "ra"
    assert vendor_adapters.detect_family("RA6M3") == "ra"


def test_ra_adapter_registered() -> None:
    adapter = vendor_adapters.get_adapter("ra")
    assert adapter is not None
    assert adapter.family == "ra"
    assert adapter.vendor_id == "renesas"
    assert adapter.build_tool == "arm-none-eabi-gcc"
    assert adapter.flash_tool == "JLinkExe"


def test_ra_build_command_uses_make_when_present() -> None:
    adapter = vendor_adapters.get_adapter("ra")
    assert adapter is not None
    with patch("vendor_adapters.ra.shutil.which", return_value="/usr/bin/make"):
        cmd = adapter.build_command({"project_root": "/proj"})
    assert cmd == ["make", "-C", "/proj"]


def test_ra_build_command_falls_back_to_gcc_version() -> None:
    adapter = vendor_adapters.get_adapter("ra")
    assert adapter is not None
    with patch("vendor_adapters.ra.shutil.which", return_value=""):
        cmd = adapter.build_command({"project_root": "/proj"})
    assert cmd == ["arm-none-eabi-gcc", "--version"]


def test_ra_flash_command_prefers_jlink() -> None:
    adapter = vendor_adapters.get_adapter("ra")
    assert adapter is not None

    # J-Link present; pyocd/openocd also present but J-Link is preferred.
    with patch("vendor_adapters.ra._segger_jlink", return_value="/usr/bin/JLink.exe"), \
         patch("vendor_adapters.ra.shutil.which", return_value="/usr/bin/pyocd"):
        cmd = adapter.flash_command({"elf": "fw.elf", "target": "R7FA6M5BH"})
    assert cmd[0] == "JLink.exe"
    assert "-device" in cmd and "R7FA6M5BH" in cmd


def test_ra_flash_command_falls_back_to_pyocd() -> None:
    adapter = vendor_adapters.get_adapter("ra")
    assert adapter is not None

    def which(name: str) -> str:
        return "/usr/bin/" + name if name == "pyocd" else ""

    with patch("vendor_adapters.ra.shutil.which", side_effect=which):
        cmd = adapter.flash_command({"elf": "fw.elf", "target": "R7FA6M5BH"})
    assert cmd[0] == "pyocd"
    assert "flash" in cmd
    assert "-t" in cmd


def test_ra_flash_command_falls_back_to_openocd() -> None:
    adapter = vendor_adapters.get_adapter("ra")
    assert adapter is not None

    def which(name: str) -> str:
        return "/usr/bin/" + name if name == "openocd" else ""

    with patch("vendor_adapters.ra.shutil.which", side_effect=which):
        cmd = adapter.flash_command({"elf": "fw.elf", "openocd_cfg": "jlink.cfg"})
    assert cmd[0] == "openocd"
    assert "-f" in cmd and "jlink.cfg" in cmd


def test_ra_flash_command_empty_when_no_tools() -> None:
    adapter = vendor_adapters.get_adapter("ra")
    assert adapter is not None
    with patch("vendor_adapters.ra.shutil.which", return_value=""):
        assert adapter.flash_command({"elf": "fw.elf"}) == []


def test_ra_observe_prefers_probe_rs_rtt() -> None:
    adapter = vendor_adapters.get_adapter("ra")
    assert adapter is not None
    with patch("vendor_adapters.ra.shutil.which", side_effect=lambda n: "/usr/bin/" + n if n == "probe-rs" else ""):
        cmd = adapter.observe_command({"target": "R7FA6M5BH"})
    assert cmd[0] == "probe-rs"
    assert "rtt" in cmd and "attach" in cmd
    assert "--chip" in cmd


def test_ra_observe_falls_back_to_uart() -> None:
    adapter = vendor_adapters.get_adapter("ra")
    assert adapter is not None
    with patch("vendor_adapters.ra.shutil.which", return_value=""):
        cmd = adapter.observe_command({"port": "/dev/ttyUSB0"})
    assert cmd[0] == "python"
    assert "/dev/ttyUSB0" in cmd


def test_ra_platformio_board_mapping() -> None:
    adapter = vendor_adapters.get_adapter("ra")
    assert adapter is not None
    assert adapter.platformio_board("RA4M1") == "uno_r4"
    # RA4M2/RA4M3 have no stock PlatformIO board matching their memory map;
    # fall back to uno_r4 (RA4M1) rather than wrong portenta_c33 (RA6M5).
    assert adapter.platformio_board("RA4M2") == "uno_r4"
    assert adapter.platformio_board("RA4M3") == "uno_r4"
    assert adapter.platformio_board("RA6M3") == "ra6m3_ek"
    assert adapter.platformio_board("RA6M5") == "ra6m5_ek"


def test_ra_supports_freertos_on_platformio() -> None:
    adapter = vendor_adapters.get_adapter("ra")
    assert adapter is not None
    assert adapter.supports_freertos_on_platformio() is True


def test_ra_datasheet_queries_include_fsp() -> None:
    adapter = vendor_adapters.get_adapter("ra")
    assert adapter is not None
    queries = adapter.datasheet_queries("R7FA6M5BH")
    assert any("FSP" in q for q in queries)
    assert any("pdf" in q for q in queries)


def test_ra_canonical_chip_passes_through() -> None:
    """RA part numbers ARE the J-Link device name."""
    adapter = vendor_adapters.get_adapter("ra")
    assert adapter is not None
    assert adapter.canonical_chip("R7FA6M5BH3CFB") == "R7FA6M5BH3CFB"


# =========================
# NXP LPC family
# =========================


def test_detect_family_lpc() -> None:
    assert vendor_adapters.detect_family("LPC1768") == "lpc"
    assert vendor_adapters.detect_family("LPC11U24") == "lpc"
    assert vendor_adapters.detect_family("LPC55S69JBD100") == "lpc"


def test_lpc_adapter_registered() -> None:
    adapter = vendor_adapters.get_adapter("lpc")
    assert adapter is not None
    assert adapter.family == "lpc"
    assert adapter.vendor_id == "nxp"
    assert adapter.build_tool == "arm-none-eabi-gcc"
    assert adapter.flash_tool == "probe-rs"


def test_lpc_build_command_uses_make_when_present() -> None:
    adapter = vendor_adapters.get_adapter("lpc")
    assert adapter is not None
    with patch("vendor_adapters.lpc.shutil.which", return_value="/usr/bin/make"):
        cmd = adapter.build_command({"project_root": "/proj"})
    assert cmd == ["make", "-C", "/proj"]


def test_lpc_flash_command_prefers_probe_rs() -> None:
    adapter = vendor_adapters.get_adapter("lpc")
    assert adapter is not None

    def which(name: str) -> str:
        return "/usr/bin/" + name if name in ("probe-rs", "pyocd", "openocd", "JLinkExe") else ""

    with patch("vendor_adapters.lpc.shutil.which", side_effect=which):
        cmd = adapter.flash_command({"elf": "fw.elf", "target": "LPC55S69JBD100"})
    assert cmd[0] == "probe-rs"
    assert "download" in cmd
    assert "--verify" in cmd
    assert "--chip" in cmd and "LPC55S69JBD100" in cmd


def test_lpc_flash_command_falls_back_to_pyocd() -> None:
    adapter = vendor_adapters.get_adapter("lpc")
    assert adapter is not None

    def which(name: str) -> str:
        return "/usr/bin/" + name if name == "pyocd" else ""

    with patch("vendor_adapters.lpc.shutil.which", side_effect=which):
        cmd = adapter.flash_command({"elf": "fw.elf", "target": "LPC55S69"})
    assert cmd[0] == "pyocd"
    assert "flash" in cmd
    assert "-t" in cmd and "LPC55S69" in cmd


def test_lpc_flash_command_falls_back_to_jlink() -> None:
    adapter = vendor_adapters.get_adapter("lpc")
    assert adapter is not None

    with patch("vendor_adapters.lpc._segger_jlink", return_value="/usr/bin/JLink.exe"), \
         patch("vendor_adapters.lpc.shutil.which", return_value=""):
        cmd = adapter.flash_command({"elf": "fw.elf", "target": "LPC1768"})
    assert cmd[0] == "JLink.exe"
    assert "-device" in cmd and "LPC1768" in cmd


def test_lpc_flash_command_empty_when_no_tools() -> None:
    adapter = vendor_adapters.get_adapter("lpc")
    assert adapter is not None
    with patch("vendor_adapters.lpc.shutil.which", return_value=""):
        assert adapter.flash_command({"elf": "fw.elf"}) == []


def test_lpc_observe_prefers_probe_rs_rtt() -> None:
    adapter = vendor_adapters.get_adapter("lpc")
    assert adapter is not None
    with patch("vendor_adapters.lpc.shutil.which", side_effect=lambda n: "/usr/bin/" + n if n == "probe-rs" else ""):
        cmd = adapter.observe_command({"target": "LPC55S69"})
    assert cmd[0] == "probe-rs"
    assert "rtt" in cmd


def test_lpc_observe_falls_back_to_pyocd_rtt() -> None:
    adapter = vendor_adapters.get_adapter("lpc")
    assert adapter is not None
    with patch("vendor_adapters.lpc.shutil.which", side_effect=lambda n: "/usr/bin/" + n if n == "pyocd" else ""):
        cmd = adapter.observe_command({"target": "LPC55S69"})
    assert cmd[0] == "pyocd"
    assert "rtt" in cmd


def test_lpc_observe_falls_back_to_uart() -> None:
    adapter = vendor_adapters.get_adapter("lpc")
    assert adapter is not None
    with patch("vendor_adapters.lpc.shutil.which", return_value=""):
        cmd = adapter.observe_command({"port": "/dev/ttyACM0"})
    assert cmd[0] == "python"
    assert "/dev/ttyACM0" in cmd


def test_lpc_platformio_board_mapping() -> None:
    adapter = vendor_adapters.get_adapter("lpc")
    assert adapter is not None
    assert adapter.platformio_board("LPC1768") == "lpc1768"
    assert adapter.platformio_board("LPC11U24") == "lpc11u24"
    assert adapter.platformio_board("LPC55S69JBD100") == "lpcxpresso55s69"
    assert adapter.platformio_board("LPC4088") == "lpc4088"


def test_lpc_supports_freertos_on_platformio() -> None:
    adapter = vendor_adapters.get_adapter("lpc")
    assert adapter is not None
    assert adapter.supports_freertos_on_platformio() is True


def test_lpc_datasheet_queries_include_mcuxpresso() -> None:
    adapter = vendor_adapters.get_adapter("lpc")
    assert adapter is not None
    queries = adapter.datasheet_queries("LPC55S69")
    assert any("MCUXpresso" in q for q in queries)
    assert any("pdf" in q for q in queries)


def test_lpc_canonical_chip_passes_through() -> None:
    adapter = vendor_adapters.get_adapter("lpc")
    assert adapter is not None
    assert adapter.canonical_chip("LPC55S69JBD100") == "LPC55S69JBD100"


# =========================
# Microchip PIC32 family
# =========================


def test_detect_family_pic32() -> None:
    assert vendor_adapters.detect_family("PIC32MX795F512L") == "pic32"
    assert vendor_adapters.detect_family("PIC32MZ2048EFH144") == "pic32"
    assert vendor_adapters.detect_family("PIC32WK") == "pic32"


def test_pic32_adapter_registered() -> None:
    adapter = vendor_adapters.get_adapter("pic32")
    assert adapter is not None
    assert adapter.family == "pic32"
    assert adapter.vendor_id == "microchip"
    assert adapter.build_tool == "xc32-gcc"
    assert adapter.flash_tool == "pic32prog"


def test_pic32_build_command_uses_make_when_present() -> None:
    adapter = vendor_adapters.get_adapter("pic32")
    assert adapter is not None
    with patch("vendor_adapters.pic32.shutil.which", return_value="/usr/bin/make"):
        cmd = adapter.build_command({"project_root": "/proj"})
    assert cmd == ["make", "-C", "/proj"]


def test_pic32_build_command_falls_back_to_xc32_version() -> None:
    adapter = vendor_adapters.get_adapter("pic32")
    assert adapter is not None
    with patch("vendor_adapters.pic32.shutil.which", side_effect=lambda n: "/usr/bin/xc32-gcc" if n == "xc32-gcc" else ""):
        cmd = adapter.build_command({"project_root": "/proj"})
    assert cmd == ["xc32-gcc", "--version"]


def test_pic32_flash_command_prefers_pic32prog() -> None:
    adapter = vendor_adapters.get_adapter("pic32")
    assert adapter is not None

    def which(name: str) -> str:
        return "/usr/bin/" + name if name in ("pic32prog", "ipe") else ""

    with patch("vendor_adapters.pic32.shutil.which", side_effect=which):
        cmd = adapter.flash_command({"elf": "fw.hex"})
    assert cmd[0] == "pic32prog"
    assert "fw.hex" in cmd


def test_pic32_flash_command_falls_back_to_ipe() -> None:
    adapter = vendor_adapters.get_adapter("pic32")
    assert adapter is not None

    def which(name: str) -> str:
        return "/usr/bin/ipe" if name == "ipe" else ""

    with patch("vendor_adapters.pic32.shutil.which", side_effect=which):
        cmd = adapter.flash_command({"elf": "fw.hex", "target": "PIC32MZ2048EFH144"})
    assert cmd[0] == "ipe"
    assert any(arg.startswith("-P") for arg in cmd)  # -P<part>
    assert any(arg.startswith("-F") for arg in cmd)  # -F<hex>


def test_pic32_flash_command_empty_when_no_tools() -> None:
    adapter = vendor_adapters.get_adapter("pic32")
    assert adapter is not None
    with patch("vendor_adapters.pic32.shutil.which", return_value=""):
        assert adapter.flash_command({"elf": "fw.hex"}) == []


def test_pic32_observe_command_requires_port() -> None:
    """PIC32 has no SWD/RTT — observe is UART only."""
    adapter = vendor_adapters.get_adapter("pic32")
    assert adapter is not None
    assert adapter.observe_command({}) == []
    cmd = adapter.observe_command({"port": "/dev/ttyUSB0", "baud": "115200"})
    assert cmd[0] == "python"
    assert "/dev/ttyUSB0" in cmd


def test_pic32_has_no_platformio_support() -> None:
    """PIC32's MIPS core has no PlatformIO framework. Empty board/platform."""
    adapter = vendor_adapters.get_adapter("pic32")
    assert adapter is not None
    assert adapter.platformio_board("PIC32MZ2048EFH144") == ""
    assert adapter._platformio_platform() == ""
    assert adapter._platformio_framework() == ""
    assert adapter.supports_freertos_on_platformio() is False


def test_pic32_datasheet_queries_include_mplabx_and_harmony() -> None:
    adapter = vendor_adapters.get_adapter("pic32")
    assert adapter is not None
    queries = adapter.datasheet_queries("PIC32MZ2048EFH144")
    assert any("MPLAB X" in q for q in queries)
    assert any("harmony" in q.lower() for q in queries)


def test_pic32_detect_tools_returns_all_expected_keys() -> None:
    adapter = vendor_adapters.get_adapter("pic32")
    assert adapter is not None
    tools = adapter.detect_tools()
    for key in ("xc32-gcc", "pic32prog", "ipe", "mplab_ipe", "make"):
        assert key in tools
        assert isinstance(tools[key], bool)


def test_pic32_programmer_respects_env_override(monkeypatch) -> None:
    monkeypatch.setenv("HARDWARE_BUTLER_PIC32_PROGRAMMER", "snap")
    adapter = vendor_adapters.get_adapter("pic32")
    assert adapter is not None
    with patch("vendor_adapters.pic32.shutil.which", side_effect=lambda n: "/usr/bin/" + n if n == "pic32prog" else ""):
        cmd = adapter.flash_command({"elf": "fw.hex"})
    assert "snap" in cmd


def test_pic32_programmer_default_is_pickit3(monkeypatch) -> None:
    monkeypatch.delenv("HARDWARE_BUTLER_PIC32_PROGRAMMER", raising=False)
    adapter = vendor_adapters.get_adapter("pic32")
    assert adapter is not None
    with patch("vendor_adapters.pic32.shutil.which", side_effect=lambda n: "/usr/bin/" + n if n == "pic32prog" else ""):
        cmd = adapter.flash_command({"elf": "fw.hex"})
    # pic32prog auto-detects; explicit programmer only added when env override
    # is set. Default behavior: no --programmer flag.
    assert "--programmer" not in cmd


# --- Phase 16 regression: _segger_jlink JDK guard ---


def test_segger_jlink_rejects_jdk_paths() -> None:
    """shutil.which('JLink.exe') on Windows resolves to the JDK's jlink.exe
    (Java module linker) on case-insensitive filesystems. The _segger_jlink
    helper must reject paths containing JDK markers."""
    from unittest.mock import patch

    import vendor_adapters.imxrt  # noqa: F401 — ensure adapter is registered
    import vendor_adapters.lpc  # noqa: F401
    import vendor_adapters.max32  # noqa: F401
    import vendor_adapters.ra  # noqa: F401
    import vendor_adapters.rx  # noqa: F401
    # JDK path — must be rejected.
    with patch("vendor_adapters.shutil.which", return_value="C:/Program Files/Java/jdk-17/bin/JLink.exe"):
        assert vendor_adapters._segger_jlink() == ""
    # Temurin path — must be rejected.
    with patch("vendor_adapters.shutil.which", return_value="C:/adoptium/temurin-17/bin/JLink.exe"):
        assert vendor_adapters._segger_jlink() == ""
    # Zulu path — must be rejected.
    with patch("vendor_adapters.shutil.which", return_value="C:/zulu/bin/JLink.exe"):
        assert vendor_adapters._segger_jlink() == ""
    # Real SEGGER path — must be accepted.
    with patch("vendor_adapters.shutil.which", return_value="C:/Program Files/SEGGER/JLink/JLink.exe"):
        assert vendor_adapters._segger_jlink() == "C:/Program Files/SEGGER/JLink/JLink.exe"


def test_ra_adapter_uses_segger_jlink_guard_for_jlink_detection() -> None:
    """The RA adapter's detect_tools must use _segger_jlink() (which rejects
    JDK paths) rather than raw shutil.which('JLink.exe'). Otherwise Windows
    hosts with a JDK installed would false-positive detect J-Link and break
    the flash fallback chain."""
    from unittest.mock import patch
    adapter = vendor_adapters.get_adapter("ra")
    assert adapter is not None
    # JDK path present — JLink.exe must report False, not True.
    with patch("vendor_adapters.shutil.which", return_value="C:/Program Files/Java/jdk-17/bin/JLink.exe"):
        tools = adapter.detect_tools()
    assert tools["JLink.exe"] is False
    assert tools["JLinkExe"] is False


def test_imxrt_adapter_uses_segger_jlink_guard() -> None:
    """Same JDK-guard check for the i.MX RT adapter."""
    from unittest.mock import patch
    adapter = vendor_adapters.get_adapter("imxrt")
    assert adapter is not None
    with patch("vendor_adapters.shutil.which", return_value="C:/adoptium/temurin-17/bin/JLink.exe"):
        tools = adapter.detect_tools()
    assert tools["JLink.exe"] is False


def test_lpc_adapter_uses_segger_jlink_guard() -> None:
    from unittest.mock import patch
    adapter = vendor_adapters.get_adapter("lpc")
    assert adapter is not None
    with patch("vendor_adapters.shutil.which", return_value="C:/zulu/bin/JLink.exe"):
        tools = adapter.detect_tools()
    assert tools["JLink.exe"] is False


def test_max32_adapter_uses_segger_jlink_guard() -> None:
    from unittest.mock import patch
    adapter = vendor_adapters.get_adapter("max32")
    assert adapter is not None
    with patch("vendor_adapters.shutil.which", return_value="C:/Program Files/Java/jdk-17/bin/JLink.exe"):
        tools = adapter.detect_tools()
    assert tools["JLink.exe"] is False


def test_rx_adapter_uses_segger_jlink_guard() -> None:
    from unittest.mock import patch
    adapter = vendor_adapters.get_adapter("rx")
    assert adapter is not None
    with patch("vendor_adapters.shutil.which", return_value="C:/Program Files/Java/jdk-17/bin/JLink.exe"):
        tools = adapter.detect_tools()
    assert tools["JLink.exe"] is False
