"""Microchip PIC32 vendor adapter (PIC32MX / PIC32MZ / PIC32MZ EF / PIC32WK).

Covers Microchip's 32-bit MIPS-core MCUs (PIC32). Toolchain:
  - Build: xc32-gcc (Microchip proprietary, GCC-based, free); make or MPLAB X
    IDE projects
  - Flash: mplab IPE CLI (ipemd) or pic32prog (open source, supports PICkit3/4,
    Snap, ICD3/4); avrdude does NOT support PIC32
  - Observe: serial UART (PIC32 has no SWD/RTT — MIPS EJTAG debug is via
    PICkit/ICD only, and the production observe path is printf-to-UART)

PIC32 uses 6-pin ICSP (PGC/PGD/MCLR) — NOT SWD/JTAG. The 4-wire EJTAG
interface exists on PIC32MZ but is rarely used outside MPLAB X debugging.
"""

from __future__ import annotations

import shutil
from typing import Any

from vendor_adapters import VendorAdapter, register_adapter

from . import serial_monitor_command


class PIC32Adapter(VendorAdapter):
    def __init__(self) -> None:
        super().__init__(
            vendor_id="microchip",
            family="pic32",
            display_name="Microchip PIC32 (MX/MZ, MIPS core)",
            build_tool="xc32-gcc",
            flash_tool="pic32prog",
            observe_tool="python",
            datasheet_term="datasheet",
        )

    def detect_tools(self) -> dict[str, bool]:
        return {
            "xc32-gcc": bool(shutil.which("xc32-gcc")),
            "pic32prog": bool(shutil.which("pic32prog")),
            "ipe": bool(shutil.which("ipe")),
            "mplab_ipe": bool(shutil.which("mplab_ipe")),
            "make": bool(shutil.which("make")),
        }

    def _pick_flash_tool(self) -> str:
        """Prefer pic32prog (open source, supports most programmers); fall
        back to MPLAB IPE CLI (Microchip official, requires MPLAB X install)."""
        if shutil.which("pic32prog"):
            return "pic32prog"
        if shutil.which("ipe"):
            return "ipe"
        return ""

    def _pick_programmer(self) -> str:
        """Default programmer: PICkit3 (most common). Env override available."""
        import os
        return os.environ.get("HARDWARE_BUTLER_PIC32_PROGRAMMER", "pickit3")

    def build_command(self, ctx: dict[str, Any]) -> list[str]:
        project_root = ctx.get("project_root", ".")
        if shutil.which("make"):
            return ["make", "-C", str(project_root)]
        # A bare `xc32-gcc --version` probe is not a build; report no toolchain.
        return []

    def flash_command(self, ctx: dict[str, Any]) -> list[str]:
        elf = ctx.get("elf", "firmware.hex")
        tool = self._pick_flash_tool()
        part = ctx.get("target", "") or ctx.get("part", "")
        programmer = self._pick_programmer()
        if tool == "pic32prog":
            args = ["pic32prog"]
            # pic32prog auto-detects a single attached programmer; the
            # --programmer flag is only useful when multiple probes are
            # present AND the user explicitly overrides. Default: omit.
            if programmer and programmer not in ("pickit3", "auto"):
                args.extend(["--programmer", programmer])
            args.append(elf)
            return args
        if tool == "ipe":
            # MPLAB IPE CLI: ipe -P<part> -F<hex> -TP<programmer> -M
            args = ["ipe"]
            if part:
                args.extend([f"-P{part}"])
            args.extend([f"-F{elf}", f"-TP{programmer}", "-M"])
            return args
        return []

    def observe_command(self, ctx: dict[str, Any]) -> list[str]:
        port = ctx.get("port", "")
        baud = ctx.get("baud", "115200")
        if port:
            return serial_monitor_command(port, baud)
        return []

    def datasheet_queries(self, part: str) -> list[str]:
        return [
            f"{part} datasheet pdf",
            f"{part} pinout",
            f"{part} MPLAB X",
            f"{part} harmony",
            f"{part} reference manual",
        ]

    def platformio_board(self, part: str) -> str:
        """PIC32 is NOT supported by PlatformIO (MIPS core has no GCC port in
        PlatformIO's framework set). Return empty — workflow uses xc32-gcc."""
        return ""

    def _platformio_platform(self) -> str:
        return ""

    def _platformio_framework(self) -> str:
        return ""

    def supports_freertos_on_platformio(self) -> bool:
        # No PlatformIO support at all for PIC32.
        return False


register_adapter(PIC32Adapter())
