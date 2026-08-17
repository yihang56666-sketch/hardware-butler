"""TI MSP430 vendor adapter.

MSP430 is TI's 16-bit ultra-low-power MCU. Toolchain:
  - Build: msp430-gcc (open source) or TI's cl430 (proprietary)
  - Flash/Debug: UniFlash CLI (dslite) or mspdebug (open source)
  - Observe: serial UART (MSP430 has no RTT/SWO equivalent)

MSP430 doesn't use JTAG/SWD for flash; it uses a 2-wire Spy-Bi-Wire (SBW)
or 4-wire JTAG protocol specific to TI.
"""

from __future__ import annotations

import shutil
from typing import Any

from vendor_adapters import VendorAdapter, register_adapter


class MSP430Adapter(VendorAdapter):
    def __init__(self) -> None:
        super().__init__(
            vendor_id="ti",
            family="msp430",
            display_name="Texas Instruments MSP430",
            build_tool="msp430-gcc",
            flash_tool="dslite",
            observe_tool="python",
            datasheet_term="user guide",
        )

    def detect_tools(self) -> dict[str, bool]:
        return {
            "msp430-gcc": bool(shutil.which("msp430-gcc")),
            "cl430": bool(shutil.which("cl430")),
            "dslite": bool(shutil.which("dslite")),
            "mspdebug": bool(shutil.which("mspdebug")),
            "uniflash": bool(shutil.which("uniflash")),
            "make": bool(shutil.which("make")),
        }

    def _pick_flash_tool(self) -> str:
        tools = self.detect_tools()
        if tools["mspdebug"]:
            return "mspdebug"
        if tools["dslite"]:
            return "dslite"
        return ""

    def _pick_transport(self) -> str:
        """Choose the mspdebug transport. rf2500 is the MSP430 LaunchPad's
        ezFET/UIF default; tilib is for XDS110/libmsp430.so; uif is for
        eZ430-UIF; bsl is the bootstrap loader. Env-overridable."""
        import os
        return os.environ.get("HARDWARE_BUTLER_MSP430_TRANSPORT", "rf2500")

    def build_command(self, ctx: dict[str, Any]) -> list[str]:
        project_root = ctx.get("project_root", ".")
        if shutil.which("make"):
            return ["make", "-C", str(project_root)]
        return ["msp430-gcc", "--version"]

    def flash_command(self, ctx: dict[str, Any]) -> list[str]:
        tool = self._pick_flash_tool()
        elf = ctx.get("elf", "firmware.elf")
        target = ctx.get("target", "MSP430G2553")
        if tool == "mspdebug":
            transport = self._pick_transport()
            args = ["mspdebug", "--allow-flash-write", transport, "prog", elf]
            if target:
                args.extend(["-d", str(target)])
            return args
        if tool == "dslite":
            return ["dslite", "flash", "--config", f"{target}.ccxml", elf]
        return []

    def observe_command(self, ctx: dict[str, Any]) -> list[str]:
        port = ctx.get("port", "")
        baud = ctx.get("baud", "9600")
        if port:
            return ["python", "-m", "serial.tools.miniterm", port, baud]
        return []

    def datasheet_queries(self, part: str) -> list[str]:
        return [
            f"{part} user guide pdf",
            f"{part} datasheet pdf",
            f"{part} programming guide",
            f"{part} launchpad schematic",
        ]

    def platformio_board(self, part: str) -> str:
        """Map MSP430 part number to PlatformIO board id (timsp430 platform)."""
        p = part.upper()
        if "G2553" in p:
            return "launchpad"
        if "F5529" in p:
            return "launchpadf5529"
        if "FR5969" in p:
            return "launchpadfr5969"
        return "launchpad"

    def _platformio_platform(self) -> str:
        return "timsp430"

    def _platformio_framework(self) -> str:
        return "energia"


register_adapter(MSP430Adapter())
