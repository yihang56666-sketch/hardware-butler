"""Analog Devices (Maxim) MAX32 vendor adapter (MAX326xx Cortex-M4F series).

Covers Analog Devices / Maxim Integrated's MAX32 family — 32-bit Cortex-M4F
MCUs targeting wearables, IoT, and biomedical sensors (MAX32660/MAX32666/
MAX32670/MAX32690). Toolchain:
  - Build: arm-none-eabi-gcc + make; Maxim's MSDK (Micro SDK) provides the
    Maxim HAL and toolchain wrappers
  - Flash: openocd with maxim-specific cfg; pyOCD (MAX32665/66 supported);
    J-Link works for most parts; probe-rs has partial MAX32 support
  - Observe: RTT over SWD (probe-rs/J-Link); UART via Maxim's standard SCI
    peripheral; Semihosting via the ARM DAP

MAX32 chips use standard ARM SWD. The MAX32625PICO is a $20 debugger+target
combo that bridges to openocd/pyOCD. The MAX326xx series is popular for
wearables due to its low-power BLE (MAX32666) and integrated sensor fusion
(MAX32660 with motion coprocessor).
"""

from __future__ import annotations

import shutil
from typing import Any

from vendor_adapters import VendorAdapter, register_adapter


class MAX32Adapter(VendorAdapter):
    def __init__(self) -> None:
        super().__init__(
            vendor_id="maxim",
            family="max32",
            display_name="Analog Devices Maxim MAX32 (Cortex-M4F)",
            build_tool="arm-none-eabi-gcc",
            flash_tool="openocd",
            observe_tool="probe-rs",
            datasheet_term="user guide",
        )

    def detect_tools(self) -> dict[str, bool]:
        return {
            "arm-none-eabi-gcc": bool(shutil.which("arm-none-eabi-gcc")),
            "openocd": bool(shutil.which("openocd")),
            "pyocd": bool(shutil.which("pyocd")),
            "probe-rs": bool(shutil.which("probe-rs")),
            "JLinkExe": bool(shutil.which("JLinkExe")),
            "JLink.exe": bool(shutil.which("JLink.exe")),
            "make": bool(shutil.which("make")),
        }

    def _pick_flash_tool(self) -> str:
        """Prefer openocd (Maxim official, well-supported); fall back to
        pyOCD, J-Link, probe-rs."""
        for tool in ("openocd", "pyocd", "JLinkExe", "JLink.exe", "probe-rs"):
            if shutil.which(tool):
                return tool
        return ""

    def build_command(self, ctx: dict[str, Any]) -> list[str]:
        project_root = ctx.get("project_root", ".")
        if shutil.which("make"):
            return ["make", "-C", str(project_root)]
        return ["arm-none-eabi-gcc", "--version"]

    def flash_command(self, ctx: dict[str, Any]) -> list[str]:
        elf = ctx.get("elf", "firmware.elf")
        tool = self._pick_flash_tool()
        target = self.canonical_chip(str(ctx.get("target", "") or ctx.get("part", "")))
        probe = ctx.get("probe", "")
        if tool == "openocd":
            cfg = ctx.get("openocd_cfg", "max32665.cfg")
            return ["openocd", "-f", cfg, "-c", f"program {elf} verify reset exit"]
        if tool == "pyocd":
            args = ["pyocd", "flash", "-t", target or "max32665"]
            if probe:
                args.extend(["--probe", probe])
            args.append(elf)
            return args
        if tool == "probe-rs":
            args = ["probe-rs", "download", "--verify", elf]
            if target:
                args.extend(["--chip", target])
            if probe:
                args.extend(["--probe", probe])
            return args
        if tool in ("JLinkExe", "JLink.exe"):
            args = [tool, "-autoconnect", "1", "-commanderscript", "flash.jlink"]
            if target:
                args.extend(["-device", target])
            return args
        return []

    def observe_command(self, ctx: dict[str, Any]) -> list[str]:
        if shutil.which("probe-rs"):
            args = ["probe-rs", "rtt", "attach"]
            target = ctx.get("target", "")
            if target:
                args.extend(["--chip", target])
            return args
        port = ctx.get("port", "")
        if port:
            return ["python", "-m", "serial.tools.miniterm", port, "115200"]
        return []

    def datasheet_queries(self, part: str) -> list[str]:
        return [
            f"{part} user guide pdf",
            f"{part} datasheet pdf",
            f"{part} MSDK",
            f"{part} reference manual",
            f"{part} Maxim Integrated",
        ]

    def platformio_board(self, part: str) -> str:
        """Map MAX32 part to PlatformIO board id (maxim32 platform)."""
        p = part.upper()
        if "MAX32660" in p:
            return "max32660evsys"
        if "MAX32666" in p:
            return "max32666fthr"
        if "MAX32670" in p:
            return "max32670evkit"
        if "MAX32690" in p:
            return "max32690evkit"
        return "max32660evsys"

    def _platformio_platform(self) -> str:
        return "maxim32"

    def _platformio_framework(self) -> str:
        return "mbed"

    def supports_freertos_on_platformio(self) -> bool:
        # Maxim's mbed framework on PlatformIO vendors FreeRTOS via the
        # rtos subdirectory on MAX326xx.
        return True

    def canonical_chip(self, part: str) -> str:
        """MAX32 part numbers pass through to pyOCD/probe-rs target names."""
        return part


register_adapter(MAX32Adapter())
