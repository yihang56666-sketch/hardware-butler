"""NXP LPC vendor adapter (LPC11xx/LPC17xx/LPC40xx/LPC55xx Cortex-M series).

Covers NXP's Cortex-M LPC family — 32-bit MCUs spanning low-power (LPC11xx
Cortex-M0+), general-purpose (LPC17xx/LPC40xx Cortex-M3/M4F), and modern
(LPC55xx Cortex-M33 with TrustZone-M). Toolchain:
  - Build: arm-none-eabi-gcc + make; MCUXpresso IDE (proprietary, GCC-based)
    also works via the MCUXpresso SDK
  - Flash: probe-rs (Cortex-M, supports LPC); pyOCD; J-Link; openocd; LPCXpresso
    ISP (for LPC11xx/LPC17xx USB-CDC bootloader)
  - Observe: SWO/RTT over SWD (probe-rs/J-Link/pyOCD); UART via pyserial

LPC chips use standard ARM SWD; the on-board LPC-Link2 (CMSIS-DAP) probe works
with pyOCD and probe-rs. LPC55xx supports TrustZone-M (separate secure/non-secure
partitions) — the workflow does not model secure partitioning.
"""

from __future__ import annotations

import shutil
from typing import Any

from vendor_adapters import VendorAdapter, _segger_jlink, register_adapter

from . import jlink_flash_command, openocd_flash_command, serial_monitor_command


class LPCAdapter(VendorAdapter):
    def __init__(self) -> None:
        super().__init__(
            vendor_id="nxp",
            family="lpc",
            display_name="NXP LPC11xx/17xx/40xx/55xx (Cortex-M)",
            build_tool="arm-none-eabi-gcc",
            flash_tool="probe-rs",
            observe_tool="probe-rs",
            datasheet_term="user manual",
        )

    def detect_tools(self) -> dict[str, bool]:
        return {
            "arm-none-eabi-gcc": bool(shutil.which("arm-none-eabi-gcc")),
            "probe-rs": bool(shutil.which("probe-rs")),
            "pyocd": bool(shutil.which("pyocd")),
            "openocd": bool(shutil.which("openocd")),
            "JLinkExe": bool(_segger_jlink()),
            "JLink.exe": bool(_segger_jlink()),
            "make": bool(shutil.which("make")),
        }

    def _pick_flash_tool(self) -> str:
        """Prefer probe-rs (cross-vendor, open source); fall back to pyOCD,
        J-Link, or openocd."""
        for tool in ("probe-rs", "pyocd", "_jlink", "openocd"):
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
        if tool == "probe-rs":
            args = ["probe-rs", "download", "--verify", elf]
            if target:
                args.extend(["--chip", target])
            if probe:
                args.extend(["--probe", probe])
            return args
        if tool == "pyocd":
            args = ["pyocd", "flash", "-t", target or "lpc55s69"]
            if probe:
                args.extend(["--probe", probe])
            args.append(elf)
            return args
        if tool in ("JLinkExe", "JLink.exe"):
            # J-Link 需要真实存在的命令脚本（含 loadfile），否则必然失败。
            if not target:
                return []
            return jlink_flash_command(tool, target=target, elf=elf)
        if tool == "openocd":
            cfg = ctx.get("openocd_cfg", "jlink.cfg")
            return openocd_flash_command(cfg, elf)
        return []

    def observe_command(self, ctx: dict[str, Any]) -> list[str]:
        if shutil.which("probe-rs"):
            args = ["probe-rs", "rtt", "attach"]
            target = ctx.get("target", "")
            if target:
                args.extend(["--chip", target])
            return args
        if shutil.which("pyocd"):
            args = ["pyocd", "rtt"]
            target = ctx.get("target", "")
            if target:
                args.extend(["-t", target])
            return args
        port = ctx.get("port", "")
        if port:
            return serial_monitor_command(port)
        return []

    def datasheet_queries(self, part: str) -> list[str]:
        return [
            f"{part} user manual pdf",
            f"{part} datasheet pdf",
            f"{part} MCUXpresso",
            f"{part} reference manual",
            f"{part} LPCOpen",
        ]

    def platformio_board(self, part: str) -> str:
        """Map LPC part to PlatformIO board id (nxplpc platform)."""
        p = part.upper()
        if "LPC11U" in p or "LPC1114" in p:
            return "lpc11u24"
        if "LPC1768" in p:
            return "lpc1768"
        if "LPC1769" in p:
            return "lpc1769"
        if "LPC4088" in p:
            return "lpc4088"
        if "LPC55S69" in p or "LPC55S28" in p:
            return "lpcxpresso55s69"
        return "lpc1768"

    def _platformio_platform(self) -> str:
        return "nxplpc"

    def _platformio_framework(self) -> str:
        return "mbed"

    def supports_freertos_on_platformio(self) -> bool:
        # NXP LPC mbed framework on PlatformIO vendors FreeRTOS via the
        # rtos subdirectory; the workflow's codegen works on LPC55xx (M33).
        return True

    def canonical_chip(self, part: str) -> str:
        """LPC part numbers pass through to probe-rs target name directly;
        e.g. LPC55S69JBD100 is the orderable part AND the probe-rs target."""
        return part


register_adapter(LPCAdapter())
