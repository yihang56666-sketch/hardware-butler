"""RISC-V vendor adapter (WCH CH32V / GigaDevice GD32V series).

Covers 32-bit RISC-V MCUs from WCH (CH32V103/203/307/xxx) and GigaDevice
(GD32VF103). Toolchain:
  - Build: riscv64-unknown-elf-gcc (WCH official toolchain) or
    riscv-none-embed-gcc (open source, xpack); WCH also offers MounRiver Studio
  - Flash: WCH-LinkUtility (wlink) or openocd with wch-link cfg;
    prog_wlink.py for ch32v; for GD32VF103, openocd + J-Link work too
  - Observe: serial UART (no SWD/RTT on RISC-V); PD5/PD3 SWD on CH32V is
    debug-only (printf via UART is the production path)

RISC-V parts use WCH-Link (a CMSIS-DAP-compatible debug probe) or JTAG.
The CH32V series is single-wire debug (SDI/SDO), similar to ARM SWD.
"""

from __future__ import annotations

import shutil
from typing import Any

from vendor_adapters import VendorAdapter, register_adapter

from . import serial_monitor_command


class RISCVAdapter(VendorAdapter):
    def __init__(self) -> None:
        super().__init__(
            vendor_id="wch",
            family="riscv",
            display_name="RISC-V 32-bit (WCH CH32V / GigaDevice GD32V)",
            build_tool="riscv64-unknown-elf-gcc",
            flash_tool="wlink",
            observe_tool="python",
            datasheet_term="datasheet",
        )

    def detect_tools(self) -> dict[str, bool]:
        return {
            "riscv64-unknown-elf-gcc": bool(shutil.which("riscv64-unknown-elf-gcc")),
            "riscv-none-embed-gcc": bool(shutil.which("riscv-none-embed-gcc")),
            "riscv-none-elf-gcc": bool(shutil.which("riscv-none-elf-gcc")),
            "wlink": bool(shutil.which("wlink")),
            "openocd": bool(shutil.which("openocd")),
            "make": bool(shutil.which("make")),
        }

    def _pick_gcc(self) -> str:
        for tool in (
            "riscv64-unknown-elf-gcc",
            "riscv-none-embed-gcc",
            "riscv-none-elf-gcc",
        ):
            if shutil.which(tool):
                return tool
        return "riscv64-unknown-elf-gcc"

    def _pick_flash_tool(self) -> str:
        """Prefer wlink (WCH official, supports CH32V); fall back to openocd
        with a wch-link cfg (works for GD32VF103 with J-Link too)."""
        if shutil.which("wlink"):
            return "wlink"
        if shutil.which("openocd"):
            return "openocd"
        return ""

    def build_command(self, ctx: dict[str, Any]) -> list[str]:
        project_root = ctx.get("project_root", ".")
        if shutil.which("make"):
            return ["make", "-C", str(project_root)]
        # A bare `gcc --version` probe used to be returned here; the runner
        # counted its rc 0 as a completed build and the flash stage then
        # chased a nonexistent artifact. Report "no build tool" instead.
        return []

    def flash_command(self, ctx: dict[str, Any]) -> list[str]:
        elf = ctx.get("elf", "firmware.hex")
        tool = self._pick_flash_tool()
        if tool == "wlink":
            return ["wlink", "flash", elf]
        if tool == "openocd":
            cfg = ctx.get("openocd_cfg", "wch-link.cfg")
            return ["openocd", "-f", cfg, "-c", f"program {elf} verify reset exit"]
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
            f"{part} reference manual",
            f"{part} pinout",
            f"{part} programming manual",
            f"{part} MounRiver",
        ]

    def platformio_board(self, part: str) -> str:
        """Map RISC-V part to PlatformIO board id.

        There is no stock `platform = wch-riscv` in PlatformIO: CH32V parts
        are only reachable through the community platform referenced by git
        URL (Community-PIO-CH32V/platform-ch32v) with its own framework
        naming, and GD32V boards live under the separate sipeed gd32v
        platform — neither can be rendered as a plain `platform = <name>`
        ini here. Return "" so builds fall back to the adapter's native
        make + riscv-none-elf-gcc path instead of a guaranteed failure."""
        return ""

    def _platformio_platform(self) -> str:
        return ""

    def _platformio_framework(self) -> str:
        return ""

    def supports_freertos_on_platformio(self) -> bool:
        # PlatformIO is disabled for this family (see platformio_board);
        # FreeRTOS codegen on RISC-V goes through the native build path.
        return False


register_adapter(RISCVAdapter())
