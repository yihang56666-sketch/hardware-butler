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

from vendor_adapters import VendorAdapter, _segger_jlink, register_adapter

from . import jlink_flash_command, openocd_flash_command, serial_monitor_command


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
            "JLinkExe": bool(_segger_jlink()),
            "JLink.exe": bool(_segger_jlink()),
            "make": bool(shutil.which("make")),
        }

    def _pick_flash_tool(self) -> str:
        """Prefer openocd (Maxim official, well-supported); fall back to
        pyOCD, J-Link, probe-rs."""
        for tool in ("openocd", "pyocd", "_jlink", "probe-rs"):
            if tool == "_jlink":
                if _segger_jlink():
                    return "JLink.exe"
            elif shutil.which(tool):
                return tool
        return ""

    def build_command(self, ctx: dict[str, Any]) -> list[str]:
        project_root = ctx.get("project_root", ".")
        if shutil.which("make"):
            return ["make", "-C", str(project_root)]
        # 版本探测命令 rc=0 会被 runner 记成"构建成功"，改报无工具链。
        return []

    def flash_command(self, ctx: dict[str, Any]) -> list[str]:
        elf = ctx.get("elf", "firmware.elf")
        tool = self._pick_flash_tool()
        target = self.canonical_chip(str(ctx.get("target", "") or ctx.get("part", "")))
        probe = ctx.get("probe", "")
        if tool == "openocd":
            cfg = ctx.get("openocd_cfg", "max32665.cfg")
            return openocd_flash_command(cfg, elf)
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
            # J-Link 需要真实存在的命令脚本（含 loadfile），否则必然失败。
            if not target:
                return []
            return jlink_flash_command(tool, target=target, elf=elf)
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
            return serial_monitor_command(port)
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
        """Map MAX32 part to PlatformIO board id (maxim32 platform).

        platform-maxim32 does NOT support MAX32660/66/70/90 (its board list
        stops at MAX32600/32620/32625/32630; the MAX32660 gap is a known
        upstream issue). Unmapped parts return "" so builds fall back to
        the adapter's native arm-none-eabi-gcc path."""
        return ""

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
