"""Renesas RX vendor adapter (RX65N/RX72N/RX130/RX231 32-bit CISC).

Covers Renesas's RX family — 32-bit CISC (CISC-style with FPU + DSP) MCUs
targeting industrial control, home appliances, and motor control. Distinct
from the ARM-based RA family: RX is Renesas's in-house CISC architecture,
not Cortex-M. Toolchain:
  - Build: rx-elf-gcc (open source, GCC); Renesas CC-RX (proprietary);
    rx-elf-gcc via the Renesas e² studio IDE
  - Flash: Renesas E2 Lite (1-wire or 2-wire UART debug) via rfp-cli (Renesas
    Flash Programmer CLI); openocd has limited RX support; the SEGGER
    J-Link supports RX65N/RX72N when configured as RX target
  - Observe: serial UART via the RX SCI peripheral; ITM/RTT-equivalent
    debugging is via the Renesas E2 Lite trace — printf-to-UART is the
    production path

RX uses a Renesas-proprietary 1-wire (or 2-wire) debug interface, NOT SWD
or JTAG. The E2 Lite probe is the canonical debugger; J-Link works for RX
but requires a different probe setup than ARM mode.
"""

from __future__ import annotations

import shutil
from typing import Any

from vendor_adapters import VendorAdapter, register_adapter


class RXAdapter(VendorAdapter):
    def __init__(self) -> None:
        super().__init__(
            vendor_id="renesas",
            family="rx",
            display_name="Renesas RX (32-bit CISC, RX65N/RX72N)",
            build_tool="rx-elf-gcc",
            flash_tool="rfp-cli",
            observe_tool="python",
            datasheet_term="user manual",
        )

    def detect_tools(self) -> dict[str, bool]:
        return {
            "rx-elf-gcc": bool(shutil.which("rx-elf-gcc")),
            "cc-rx": bool(shutil.which("cc-rx")),
            "rfp-cli": bool(shutil.which("rfp-cli")),
            "JLinkExe": bool(shutil.which("JLinkExe")),
            "JLink.exe": bool(shutil.which("JLink.exe")),
            "openocd": bool(shutil.which("openocd")),
            "make": bool(shutil.which("make")),
        }

    def _pick_flash_tool(self) -> str:
        """Prefer rfp-cli (Renesas official for RX via E2 Lite); fall back
        to J-Link (supports RX65N/RX72N in RX mode); openocd last resort."""
        if shutil.which("rfp-cli"):
            return "rfp-cli"
        for tool in ("JLinkExe", "JLink.exe"):
            if shutil.which(tool):
                return tool
        if shutil.which("openocd"):
            return "openocd"
        return ""

    def build_command(self, ctx: dict[str, Any]) -> list[str]:
        project_root = ctx.get("project_root", ".")
        if shutil.which("make"):
            return ["make", "-C", str(project_root)]
        if shutil.which("rx-elf-gcc"):
            return ["rx-elf-gcc", "--version"]
        return []

    def flash_command(self, ctx: dict[str, Any]) -> list[str]:
        elf = ctx.get("elf", "firmware.mot")
        tool = self._pick_flash_tool()
        target = ctx.get("target", "") or ctx.get("part", "")
        probe = ctx.get("probe", "")
        if tool == "rfp-cli":
            # rfp-cli: -device <part> -tool e2 -port <probe> -file <elf> -auto
            args = ["rfp-cli"]
            if target:
                args.extend(["-device", target])
            args.extend(["-tool", "e2"])
            if probe:
                args.extend(["-port", probe])
            args.extend(["-file", elf, "-auto"])
            return args
        if tool in ("JLinkExe", "JLink.exe"):
            args = [tool, "-autoconnect", "1", "-commanderscript", "flash.jlink"]
            if target:
                args.extend(["-device", target])
            return args
        if tool == "openocd":
            cfg = ctx.get("openocd_cfg", "e2lite.cfg")
            return ["openocd", "-f", cfg, "-c", f"program {elf} verify reset exit"]
        return []

    def observe_command(self, ctx: dict[str, Any]) -> list[str]:
        """RX has no RTT equivalent — the E2 Lite trace is the in-circuit
        path, but production observe is printf-to-UART via pyserial."""
        port = ctx.get("port", "")
        baud = ctx.get("baud", "115200")
        if port:
            return ["python", "-m", "serial.tools.miniterm", port, baud]
        return []

    def datasheet_queries(self, part: str) -> list[str]:
        return [
            f"{part} user manual pdf",
            f"{part} datasheet pdf",
            f"{part} hardware manual",
            f"{part} e2 studio",
            f"{part} CC-RX",
        ]

    def platformio_board(self, part: str) -> str:
        """RX is NOT supported by PlatformIO (Renesas CISC has no PlatformIO
        framework — only the RA Cortex-M family has renesas-ra)."""
        return ""

    def _platformio_platform(self) -> str:
        return ""

    def _platformio_framework(self) -> str:
        return ""

    def supports_freertos_on_platformio(self) -> bool:
        return False


register_adapter(RXAdapter())
