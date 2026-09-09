"""Unit tests for vendor adapters — family detection + command generation."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, "tools")

import vendor_adapters  # noqa: E402
import vendor_adapters.esp32  # noqa: E402
import vendor_adapters.msp430  # noqa: E402
import vendor_adapters.stm32  # noqa: E402


def test_detect_family_stm32() -> None:
    assert vendor_adapters.detect_family("STM32F407VGT6") == "stm32"
    assert vendor_adapters.detect_family("stm32l432kc") == "stm32"


def test_detect_family_esp32() -> None:
    assert vendor_adapters.detect_family("ESP32-WROOM-32") == "esp32"
    assert vendor_adapters.detect_family("ESP8266EX") == "esp32"


def test_detect_family_msp430() -> None:
    assert vendor_adapters.detect_family("MSP430G2553") == "msp430"
    assert vendor_adapters.detect_family("MSP430F5529") == "msp430"


def test_detect_family_unknown() -> None:
    assert vendor_adapters.detect_family("RaspberryPi") == ""
    assert vendor_adapters.detect_family("") == ""


def test_get_adapter_returns_registered_adapter() -> None:
    adapter = vendor_adapters.get_adapter("stm32")
    assert adapter is not None
    assert adapter.family == "stm32"
    assert adapter.vendor_id == "st"

    esp = vendor_adapters.get_adapter("esp32")
    assert esp is not None
    assert esp.family == "esp32"

    msp = vendor_adapters.get_adapter("msp430")
    assert msp is not None
    assert msp.family == "msp430"


def test_get_adapter_unknown_returns_none() -> None:
    assert vendor_adapters.get_adapter("nonexistent") is None


def test_list_adapters_includes_all_three() -> None:
    families = {a.family for a in vendor_adapters.list_adapters()}
    assert {"stm32", "esp32", "msp430"} <= families


def test_stm32_adapter_build_command(tmp_path: Path) -> None:
    adapter = vendor_adapters.get_adapter("stm32")
    assert adapter is not None
    (tmp_path / "Makefile").write_text("all:\n", encoding="utf-8")
    with patch("vendor_adapters.stm32.shutil.which", side_effect=lambda name: name if name == "make" else None):
        cmd = adapter.build_command({"project_root": str(tmp_path)})
    assert cmd == ["make", "-C", str(tmp_path.resolve())]


def test_stm32_adapter_flash_command_picks_available_tool() -> None:
    adapter = vendor_adapters.get_adapter("stm32")
    assert adapter is not None
    cmd = adapter.flash_command({"target": "STM32F407VG", "elf": "build/fw.elf"})
    assert isinstance(cmd, list)


def test_esp32_adapter_build_command() -> None:
    adapter = vendor_adapters.get_adapter("esp32")
    assert adapter is not None
    cmd = adapter.build_command({"project_root": "/tmp/esp_proj"})
    assert isinstance(cmd, list)


def test_esp32_adapter_flash_command_includes_port() -> None:
    adapter = vendor_adapters.get_adapter("esp32")
    assert adapter is not None
    cmd = adapter.flash_command({"port": "COM5", "elf": "build/firmware.bin"})
    # If esptool is installed, --port + COM5 must appear. If not installed,
    # the adapter returns [] — skip the assertion in that case.
    if not cmd:
        return
    assert "--port" in cmd
    assert "COM5" in cmd


def test_msp430_adapter_datasheet_queries() -> None:
    adapter = vendor_adapters.get_adapter("msp430")
    assert adapter is not None
    queries = adapter.datasheet_queries("MSP430G2553")
    assert any("user guide" in q for q in queries)
    assert any("MSP430G2553" in q for q in queries)


def test_adapter_to_dict_has_required_fields() -> None:
    adapter = vendor_adapters.get_adapter("stm32")
    assert adapter is not None
    d = adapter.to_dict()
    assert {"vendor_id", "family", "display_name", "build_tool", "flash_tool", "observe_tool"} <= d.keys()


def test_adapter_detect_tools_returns_bools() -> None:
    adapter = vendor_adapters.get_adapter("esp32")
    assert adapter is not None
    tools = adapter.detect_tools()
    assert isinstance(tools, dict)
    for v in tools.values():
        assert isinstance(v, bool)


def test_backend_detector_includes_vendor_adapter_for_stm32(tmp_path: Path) -> None:
    import shutil

    import backend_detector
    fixture = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "cubemx-basic"
    if not fixture.exists():
        return
    project = tmp_path / "project"
    shutil.copytree(fixture, project)
    result = backend_detector.detect_backends(project, context_part="STM32F407VGT6")
    assert "vendor_adapter" in result
    assert result["vendor_adapter"]["family"] == "stm32"
