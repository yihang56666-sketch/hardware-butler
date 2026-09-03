"""Microchip AVR vendor adapter.

AVR covers ATmega / ATtiny / ATxmega 8-bit MCUs. Toolchain:
  - Build: avr-gcc (open source) + make; PlatformIO `atmelavr` platform
  - Flash: avrdude (open source, supports USBasp/STK500/AVRISP/etc.)
  - Observe: serial UART (AVR has no RTT/SWO)

AVR chips use ISP (6-pin) or PDI (ATxmega) for programming, not JTAG/SWD.
"""

from __future__ import annotations

import shutil
from typing import Any

from vendor_adapters import VendorAdapter, register_adapter

from . import serial_monitor_command


class AVRAdapter(VendorAdapter):
    def __init__(self) -> None:
        super().__init__(
            vendor_id="microchip",
            family="avr",
            display_name="Microchip AVR (ATmega/ATtiny/ATxmega)",
            build_tool="avr-gcc",
            flash_tool="avrdude",
            observe_tool="python",
            datasheet_term="datasheet",
        )

    def detect_tools(self) -> dict[str, bool]:
        return {
            "avr-gcc": bool(shutil.which("avr-gcc")),
            "avrdude": bool(shutil.which("avrdude")),
            "make": bool(shutil.which("make")),
            "avr-objcopy": bool(shutil.which("avr-objcopy")),
        }

    def _pick_programmer(self) -> str:
        """Choose an avrdude programmer. USBasp is the cheapest common one."""
        # avrdude -c ? lists programmers; we pick by env override or default.
        import os
        return os.environ.get("HARDWARE_BUTLER_AVR_PROGRAMMER", "usbasp")

    def build_command(self, ctx: dict[str, Any]) -> list[str]:
        project_root = ctx.get("project_root", ".")
        if shutil.which("make"):
            return ["make", "-C", str(project_root)]
        # A bare `avr-gcc --version` probe is not a build; report no toolchain.
        return []

    def flash_command(self, ctx: dict[str, Any]) -> list[str]:
        elf = ctx.get("elf", "firmware.hex")
        part = ctx.get("target", "") or ctx.get("part", "")
        part_lower = part.lower() if part else ""
        programmer = self._pick_programmer()
        args = ["avrdude", "-c", programmer, "-p", part_lower, "-U", f"flash:w:{elf}"]
        return args

    def observe_command(self, ctx: dict[str, Any]) -> list[str]:
        port = ctx.get("port", "")
        baud = ctx.get("baud", "9600")
        if port:
            return serial_monitor_command(port, baud)
        return []

    def datasheet_queries(self, part: str) -> list[str]:
        return [
            f"{part} datasheet pdf",
            f"{part} pinout",
            f"{part} programming guide",
            f"{part} application note",
        ]

    def platformio_board(self, part: str) -> str:
        """Map AVR part to PlatformIO board id (atmelavr platform)."""
        p = part.upper()
        if "ATMEGA328P" in p:
            return "uno"
        if "ATMEGA2560" in p:
            return "megaatmega2560"
        if "ATTINY85" in p:
            return "attiny85"
        if "ATMEGA32U4" in p:
            return "leonardo"
        return "uno"

    def _platformio_platform(self) -> str:
        return "atmelavr"

    def _platformio_framework(self) -> str:
        return "arduino"


register_adapter(AVRAdapter())
