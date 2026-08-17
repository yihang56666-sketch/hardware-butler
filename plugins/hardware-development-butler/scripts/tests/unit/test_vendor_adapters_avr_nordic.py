"""Tests for AVR + Nordic vendor adapters (registered 2026-08-17).

Covers family detection, registry lookup, command generation, and
PlatformIO board mapping. Runs offline (no toolchain needed).
"""

from __future__ import annotations

import sys

sys.path.insert(0, "tools")

import vendor_adapters  # noqa: E402
import vendor_adapters.avr  # noqa: E402
import vendor_adapters.nordic  # noqa: E402


def test_detect_family_avr() -> None:
    assert vendor_adapters.detect_family("ATmega328P") == "avr"
    assert vendor_adapters.detect_family("ATtiny85") == "avr"
    assert vendor_adapters.detect_family("ATxmega128A1") == "avr"


def test_detect_family_nordic() -> None:
    assert vendor_adapters.detect_family("nRF52832") == "nordic"
    assert vendor_adapters.detect_family("NRF52840") == "nordic"
    assert vendor_adapters.detect_family("nRF5340") == "nordic"


def test_avr_adapter_registered() -> None:
    adapter = vendor_adapters.get_adapter("avr")
    assert adapter is not None
    assert adapter.family == "avr"
    assert adapter.vendor_id == "microchip"
    assert adapter.build_tool == "avr-gcc"
    assert adapter.flash_tool == "avrdude"


def test_nordic_adapter_registered() -> None:
    adapter = vendor_adapters.get_adapter("nordic")
    assert adapter is not None
    assert adapter.family == "nordic"
    assert adapter.vendor_id == "nordic"
    assert adapter.build_tool == "arm-none-eabi-gcc"


def test_avr_flash_command_uses_avrdude() -> None:
    adapter = vendor_adapters.get_adapter("avr")
    assert adapter is not None
    cmd = adapter.flash_command({"elf": "fw.hex", "target": "ATmega328P"})
    assert cmd[0] == "avrdude"
    assert "usbasp" in cmd  # default programmer
    assert "ATmega328P".lower() in cmd  # part normalized to lowercase
    assert "flash:w:fw.hex" in cmd


def test_nordic_flash_command_prefers_probe_rs() -> None:
    """Nordic adapter prefers probe-rs when available (cross-vendor open source)."""
    from unittest.mock import patch
    adapter = vendor_adapters.get_adapter("nordic")
    assert adapter is not None
    with patch("vendor_adapters.nordic.shutil.which", return_value="/usr/bin/probe-rs"):
        cmd = adapter.flash_command({"elf": "fw.elf", "target": "nRF52832_xxAA"})
    assert cmd[0] == "probe-rs"
    assert "--verify" in cmd
    assert "fw.elf" in cmd


def test_nordic_flash_command_falls_back_to_nrfjprog() -> None:
    """When probe-rs absent but nrfjprog present, use nrfjprog."""
    from unittest.mock import patch

    def which(name: str) -> str:
        return "/usr/bin/nrfjprog" if name == "nrfjprog" else ""

    adapter = vendor_adapters.get_adapter("nordic")
    assert adapter is not None
    with patch("vendor_adapters.nordic.shutil.which", side_effect=which):
        cmd = adapter.flash_command({"elf": "fw.elf"})
    assert cmd[0] == "nrfjprog"
    assert "--program" in cmd
    assert "fw.elf" in cmd


def test_avr_platformio_board_mapping() -> None:
    adapter = vendor_adapters.get_adapter("avr")
    assert adapter is not None
    assert adapter.platformio_board("ATmega328P") == "uno"
    assert adapter.platformio_board("ATMEGA2560") == "megaatmega2560"
    assert adapter.platformio_board("ATTINY85") == "attiny85"


def test_nordic_platformio_board_mapping() -> None:
    adapter = vendor_adapters.get_adapter("nordic")
    assert adapter is not None
    assert adapter.platformio_board("nRF52832") == "nrf52_dk"
    assert adapter.platformio_board("nRF52840") == "nrf52840_dk"


def test_nordic_supports_freertos_on_platformio() -> None:
    adapter = vendor_adapters.get_adapter("nordic")
    assert adapter is not None
    assert adapter.supports_freertos_on_platformio() is True


def test_avr_datasheet_queries_use_part_number() -> None:
    adapter = vendor_adapters.get_adapter("avr")
    assert adapter is not None
    queries = adapter.datasheet_queries("ATmega328P")
    assert any("ATmega328P" in q for q in queries)
    assert any("pdf" in q for q in queries)


def test_nordic_datasheet_queries_use_product_spec_term() -> None:
    adapter = vendor_adapters.get_adapter("nordic")
    assert adapter is not None
    queries = adapter.datasheet_queries("nRF52832")
    assert any("product specification" in q for q in queries)


# --- build_command paths ---


def test_avr_build_command_uses_make_when_present() -> None:
    from unittest.mock import patch

    adapter = vendor_adapters.get_adapter("avr")
    assert adapter is not None
    with patch("vendor_adapters.avr.shutil.which", return_value="/usr/bin/make"):
        cmd = adapter.build_command({"project_root": "/proj"})
    assert cmd == ["make", "-C", "/proj"]


def test_avr_build_command_falls_back_to_gcc_version_when_no_make() -> None:
    from unittest.mock import patch

    adapter = vendor_adapters.get_adapter("avr")
    assert adapter is not None
    with patch("vendor_adapters.avr.shutil.which", return_value=""):
        cmd = adapter.build_command({"project_root": "/proj"})
    assert cmd == ["avr-gcc", "--version"]


def test_nordic_build_command_prefers_cmake_ninja() -> None:
    from unittest.mock import patch

    def which(name: str) -> str:
        return {"/usr/bin/cmake": "", "cmake": "/usr/bin/cmake", "ninja": "/usr/bin/ninja"}.get(name, "")

    adapter = vendor_adapters.get_adapter("nordic")
    assert adapter is not None
    with patch("vendor_adapters.nordic.shutil.which", side_effect=lambda n: "/usr/bin/" + n if n in ("cmake", "ninja") else ""):
        cmd = adapter.build_command({"project_root": "/proj"})
    assert cmd == ["cmake", "--build", "/proj"]


def test_nordic_build_command_falls_back_to_gcc_version() -> None:
    from unittest.mock import patch

    adapter = vendor_adapters.get_adapter("nordic")
    assert adapter is not None
    with patch("vendor_adapters.nordic.shutil.which", return_value=""):
        cmd = adapter.build_command({"project_root": "/proj"})
    assert cmd == ["arm-none-eabi-gcc", "--version"]


# --- observe_command paths ---


def test_avr_observe_command_requires_port() -> None:
    adapter = vendor_adapters.get_adapter("avr")
    assert adapter is not None
    assert adapter.observe_command({}) == []
    cmd = adapter.observe_command({"port": "/dev/ttyUSB0", "baud": "115200"})
    assert cmd[0] == "python"
    assert "/dev/ttyUSB0" in cmd
    assert "115200" in cmd


def test_nordic_observe_command_prefers_probe_rs_rtt() -> None:
    from unittest.mock import patch

    adapter = vendor_adapters.get_adapter("nordic")
    assert adapter is not None
    with patch("vendor_adapters.nordic.shutil.which", return_value="/usr/bin/probe-rs"):
        cmd = adapter.observe_command({"target": "nRF52832_xxAA"})
    assert cmd[0] == "probe-rs"
    assert "rtt" in cmd and "attach" in cmd
    assert "--chip" in cmd and "nRF52832_xxAA" in cmd


def test_nordic_observe_command_falls_back_to_uart() -> None:
    from unittest.mock import patch

    adapter = vendor_adapters.get_adapter("nordic")
    assert adapter is not None
    with patch("vendor_adapters.nordic.shutil.which", return_value=""):
        cmd = adapter.observe_command({"port": "/dev/ttyACM0"})
    assert cmd[0] == "python"
    assert "/dev/ttyACM0" in cmd


def test_nordic_observe_command_empty_without_probe_or_port() -> None:
    from unittest.mock import patch

    adapter = vendor_adapters.get_adapter("nordic")
    assert adapter is not None
    with patch("vendor_adapters.nordic.shutil.which", return_value=""):
        assert adapter.observe_command({}) == []


# --- programmer override + canonical chip ---


def test_avr_programmer_respects_env_override(monkeypatch) -> None:
    monkeypatch.setenv("HARDWARE_BUTLER_AVR_PROGRAMMER", "avrispmkii")
    adapter = vendor_adapters.get_adapter("avr")
    assert adapter is not None
    cmd = adapter.flash_command({"elf": "fw.hex", "target": "ATmega328P"})
    assert "avrispmkii" in cmd


def test_avr_programmer_default_is_usbasp(monkeypatch) -> None:
    monkeypatch.delenv("HARDWARE_BUTLER_AVR_PROGRAMMER", raising=False)
    adapter = vendor_adapters.get_adapter("avr")
    assert adapter is not None
    cmd = adapter.flash_command({"elf": "fw.hex", "target": "ATmega328P"})
    assert "usbasp" in cmd


def test_avr_flash_command_uses_part_when_no_target() -> None:
    """The adapter accepts either `target` or `part` as the chip identifier."""
    adapter = vendor_adapters.get_adapter("avr")
    assert adapter is not None
    cmd = adapter.flash_command({"elf": "fw.hex", "part": "ATtiny85"})
    assert "attiny85" in cmd  # lowercase normalized


def test_nordic_canonical_chip_passes_through_nrf_part_numbers() -> None:
    """Nordic parts (nRF52832 etc.) don't end in a package digit, so the
    canonicalizer must NOT strip trailing characters."""
    adapter = vendor_adapters.get_adapter("nordic")
    assert adapter is not None
    assert adapter.canonical_chip("nRF52832") == "nRF52832"
    assert adapter.canonical_chip("nRF52840_xxAA") == "nRF52840_xxAA"


# --- tool detection ---


def test_avr_detect_tools_returns_all_expected_keys() -> None:
    adapter = vendor_adapters.get_adapter("avr")
    assert adapter is not None
    tools = adapter.detect_tools()
    for key in ("avr-gcc", "avrdude", "make", "avr-objcopy"):
        assert key in tools
        assert isinstance(tools[key], bool)


def test_nordic_detect_tools_returns_all_expected_keys() -> None:
    adapter = vendor_adapters.get_adapter("nordic")
    assert adapter is not None
    tools = adapter.detect_tools()
    for key in ("arm-none-eabi-gcc", "probe-rs", "pyocd", "nrfjprog", "JLinkExe", "cmake", "ninja"):
        assert key in tools
        assert isinstance(tools[key], bool)
