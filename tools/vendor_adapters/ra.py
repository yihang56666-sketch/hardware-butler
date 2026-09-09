"""Renesas RA vendor adapter (RA4 / RA6 Cortex-M23/M33/M4F series).

Covers Renesas RA family — 32-bit Cortex-M MCUs targeting industrial and IoT
applications, replacing the legacy RX (Renesas 16/RX 32-bit CISC) line for
new designs. Toolchain:
  - Build: arm-none-eabi-gcc + make; Renesas e² studio (proprietary, GCC-based)
    also works; the Flexible Software Package (FSP) provides HAL drivers
  - Flash: J-Link (Renesas recommends J-Link for RA) via JLinkExe; pyOCD also
    supports RA6 (Cortex-M33); openocd has limited RA support
  - Observe: RTT over SWD (probe-rs/J-Link); UART fallback via FSP SCI driver

RA chips use standard ARM SWD; the on-board E2 Lite or SEGGER J-Link probe
both work. Renesas RX (RX65N/RX72N — CISC 32-bit) is a separate family not
covered here.
"""

from __future__ import annotations

import shutil
from typing import Any

from vendor_adapters import VendorAdapter, _segger_jlink, register_adapter

from . import jlink_flash_command, openocd_flash_command, serial_monitor_command


class RAAdapter(VendorAdapter):
    def __init__(self) -> None:
        super().__init__(
            vendor_id="renesas",
            family="ra",
            display_name="Renesas RA4/RA6 (Cortex-M)",
            build_tool="arm-none-eabi-gcc",
            flash_tool="JLinkExe",
            observe_tool="probe-rs",
            datasheet_term="user manual",
        )

    def detect_tools(self) -> dict[str, bool]:
        return {
            "arm-none-eabi-gcc": bool(shutil.which("arm-none-eabi-gcc")),
            "JLinkExe": bool(_segger_jlink()),
            "JLink.exe": bool(_segger_jlink()),
            "pyocd": bool(shutil.which("pyocd")),
            "openocd": bool(shutil.which("openocd")),
            "probe-rs": bool(shutil.which("probe-rs")),
            "make": bool(shutil.which("make")),
        }

    def _pick_flash_tool(self) -> str:
        """Prefer J-Link (Renesas official for RA); fall back to pyOCD (RA6
        supported) then openocd (limited RA support)."""
        if _segger_jlink():
            return "JLink.exe"
        if shutil.which("pyocd"):
            return "pyocd"
        if shutil.which("openocd"):
            return "openocd"
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
        if tool in ("JLinkExe", "JLink.exe"):
            # J-Link 需要真实存在的命令脚本（含 loadfile），否则必然失败。
            if not target:
                return []
            return jlink_flash_command(tool, target=target, elf=elf, probe=probe)
        if tool == "pyocd":
            args = ["pyocd", "flash", "-t", target or "r7fa6m5bh"]
            if probe:
                args.extend(["--probe", probe])
            args.append(elf)
            return args
        if tool == "openocd":
            cfg = ctx.get("openocd_cfg", "jlink.cfg")
            return openocd_flash_command(cfg, elf)
        return []

    def observe_command(self, ctx: dict[str, Any]) -> list[str]:
        """RTT via probe-rs/J-Link over SWD; UART via pyserial as fallback."""
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
            f"{part} user manual pdf",
            f"{part} datasheet pdf",
            f"{part} FSP",
            f"{part} hardware manual",
            f"{part} e2 studio",
        ]

    def platformio_board(self, part: str) -> str:
        """Map RA part to PlatformIO board id (renesas-ra platform).

        The official renesas-ra registry only ships the Arduino Uno R4
        boards (uno_r4_minima / uno_r4_wifi, both RA4M1-based); the EK-RA
        ids (ra6m2_ek etc.) are TinyUSB board names that PlatformIO cannot
        resolve. Unmapped parts return "" so the workflow falls back to
        arm-none-eabi-gcc + the adapter's own build_command path."""
        p = part.upper()
        if "RA4M1" in p:
            return "uno_r4_minima"  # Arduino Uno R4 (Minima/WiFi) uses RA4M1
        return ""

    def _platformio_platform(self) -> str:
        return "renesas-ra"

    def _platformio_framework(self) -> str:
        return "arduino"

    def supports_freertos_on_platformio(self) -> bool:
        # Arduino framework on Renesas-ra exposes FreeRTOS via the package
        # bundled with PlatformIO's renesas-ra platform (FSP). The workflow's
        # optimize-loop will fall back to bare-metal if RTOS codegen fails.
        return True

    def canonical_chip(self, part: str) -> str:
        """RA part numbers don't use the STM32 package-digit convention; the
        full orderable part number IS the J-Link device name (e.g. R7FA6M5BH3CFB)."""
        return part


register_adapter(RAAdapter())
