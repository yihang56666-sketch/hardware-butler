"""Texas Instruments C2000 vendor adapter (TMS320F280xx / F2837x).

Covers TI's 32-bit real-time control MCUs targeted at motor control, power
conversion, and digital power applications. Architecture is C28x (not ARM,
not RISC-V) with a 16-bit word address space. Toolchain:
  - Build: cl2000 (TI proprietary, bundled with C2000Ware); there is no
    open-source GCC for C28x (the abandoned c2000-gcc port doesn't support
    modern F28x parts). Makefile or Code Composer Studio projects.
  - Flash: TI's UniFlash CLI (dslite) or C2KProg (third party); openocd does
    NOT support C2000 (the debug probe is XDS110/XDS100, dslite-only).
  - Observe: serial UART via the XDS110 virtual COM port; no RTT/SWO on C28x.

C2000 uses XDS-class debug probes (XDS110 on LaunchPads, XDS100v2 on older
boards). SCI (UART) is the production observe path; JTAG debug via CCS.
"""

from __future__ import annotations

import shutil
from typing import Any

from vendor_adapters import VendorAdapter, register_adapter


class C2000Adapter(VendorAdapter):
    def __init__(self) -> None:
        super().__init__(
            vendor_id="ti",
            family="c2000",
            display_name="Texas Instruments C2000 (TMS320F280xx/F2837x)",
            build_tool="cl2000",
            flash_tool="dslite",
            observe_tool="python",
            datasheet_term="technical reference manual",
        )

    def detect_tools(self) -> dict[str, bool]:
        return {
            "cl2000": bool(shutil.which("cl2000")),
            "dslite": bool(shutil.which("dslite")),
            "c2kprog": bool(shutil.which("c2kprog")),
            "uniflash": bool(shutil.which("uniflash")),
            "make": bool(shutil.which("make")),
        }

    def _pick_flash_tool(self) -> str:
        if shutil.which("dslite"):
            return "dslite"
        if shutil.which("c2kprog"):
            return "c2kprog"
        return ""

    def build_command(self, ctx: dict[str, Any]) -> list[str]:
        project_root = ctx.get("project_root", ".")
        if shutil.which("make"):
            return ["make", "-C", str(project_root)]
        if shutil.which("cl2000"):
            return ["cl2000", "--version"]
        return []

    def flash_command(self, ctx: dict[str, Any]) -> list[str]:
        elf = ctx.get("elf", "firmware.out")
        target = ctx.get("target", "") or ctx.get("part", "")
        tool = self._pick_flash_tool()
        if tool == "dslite":
            args = ["dslite", "flash"]
            if target:
                args.extend(["--config", f"{target}.ccxml"])
            args.append(elf)
            return args
        if tool == "c2kprog":
            return ["c2kprog", elf]
        return []

    def observe_command(self, ctx: dict[str, Any]) -> list[str]:
        port = ctx.get("port", "")
        baud = ctx.get("baud", "115200")
        if port:
            return ["python", "-m", "serial.tools.miniterm", port, baud]
        return []

    def datasheet_queries(self, part: str) -> list[str]:
        return [
            f"{part} technical reference manual pdf",
            f"{part} datasheet pdf",
            f"{part} C2000Ware",
            f"{part} launchpad schematic",
        ]

    def platformio_board(self, part: str) -> str:
        """C2000 is NOT supported by PlatformIO (no GCC port for C28x)."""
        return ""

    def _platformio_platform(self) -> str:
        return ""

    def _platformio_framework(self) -> str:
        return ""

    def supports_freertos_on_platformio(self) -> bool:
        # No PlatformIO support at all for C2000.
        return False


register_adapter(C2000Adapter())
