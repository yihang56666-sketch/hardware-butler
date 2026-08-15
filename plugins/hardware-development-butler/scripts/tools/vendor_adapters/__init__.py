"""Vendor adapter base class.

Each MCU vendor gets one adapter that declares how to build / flash / observe
for that vendor's chips. The workflow runner does NOT hardcode any vendor —
it routes to the right adapter based on chip family detection.

Adapters expose command templates, not commands themselves. The runner fills
in {port}, {target}, {elf}, {part} from workflow context. This keeps each
adapter a thin declaration layer; the actual execution goes through the
existing embeddedskills backend scripts or direct subprocess calls.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class VendorAdapter:
    """Base class for all vendor adapters.

    Subclasses set vendor_id + family + the command templates. The runner
    uses detect_tools() to probe the host, build_command() / flash_command()
    / observe_command() to get argv lists, datasheet_queries() for the
    datasheet-collect stage.
    """

    vendor_id: str = ""
    family: str = ""  # e.g. "stm32", "esp32", "msp430"
    display_name: str = ""
    build_tool: str = ""
    flash_tool: str = ""
    observe_tool: str = ""
    datasheet_term: str = "datasheet"

    def detect_tools(self) -> dict[str, bool]:
        """Probe the host for this vendor's tools. Returns {tool_name: available}."""
        import shutil
        return {
            "build": bool(shutil.which(self.build_tool)),
            "flash": bool(shutil.which(self.flash_tool)),
            "observe": bool(shutil.which(self.observe_tool)),
        }

    def build_command(self, ctx: dict[str, Any]) -> list[str]:
        """Return argv to build the firmware. ctx carries project_root, target, elf, etc."""
        raise NotImplementedError

    def flash_command(self, ctx: dict[str, Any]) -> list[str]:
        """Return argv to flash the firmware. ctx carries port, target, elf, etc."""
        raise NotImplementedError

    def observe_command(self, ctx: dict[str, Any]) -> list[str]:
        """Return argv to observe (serial/RTT/ITM). ctx carries port, baud."""
        raise NotImplementedError

    def datasheet_queries(self, part: str) -> list[str]:
        """Return search queries for the datasheet-collect stage."""
        return [
            f"{part} {self.datasheet_term} pdf",
            f"{part} reference manual",
            f"{part} pinout",
            f"{part} programming guide",
        ]

    def to_dict(self) -> dict[str, Any]:
        return {
            "vendor_id": self.vendor_id,
            "family": self.family,
            "display_name": self.display_name,
            "build_tool": self.build_tool,
            "flash_tool": self.flash_tool,
            "observe_tool": self.observe_tool,
            "datasheet_term": self.datasheet_term,
        }


# Registry of available adapters, keyed by family. Populated by each adapter
# module on import. The runner looks up adapters via get_adapter(family).
_ADAPTERS: dict[str, VendorAdapter] = {}


def register_adapter(adapter: VendorAdapter) -> None:
    _ADAPTERS[adapter.family] = adapter


def get_adapter(family: str) -> VendorAdapter | None:
    return _ADAPTERS.get(family)


def list_adapters() -> list[VendorAdapter]:
    return list(_ADAPTERS.values())


def detect_family(part: str) -> str:
    """Heuristic: map a chip part number to its vendor family.

    STM32xx → stm32, ESP32-xx → esp32, MSP430-xx → msp430, LM4F/TM4C → ti-tiva,
    TMS320 → c2000, ATmega/ATtiny → avr, CH32/GD32 → riscv (if RISC-V core)
    or stm32-compatible (if Cortex-M). Conservative: unknown → "".
    """
    p = part.upper()
    if p.startswith("STM32"):
        return "stm32"
    if p.startswith("ESP32") or p.startswith("ESP8266"):
        return "esp32"
    if p.startswith("MSP430"):
        return "msp430"
    if p.startswith(("TM4C", "LM4F", "CC2538", "CC2650", "CC2640")):
        return "ti-tiva"
    if p.startswith(("TMS320", "F280")):
        return "c2000"
    if p.startswith(("ATMEGA", "ATTINY", "ATXMEGA")):
        return "avr"
    if p.startswith("GD32") or p.startswith("CH32"):
        # GD32/CH32 Cortex-M variants act like STM32; RISC-V variants differ
        # but detection by part number alone is unreliable. Default to stm32.
        return "stm32"
    if p.startswith("NRF5"):
        return "nordic"
    return ""
