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
