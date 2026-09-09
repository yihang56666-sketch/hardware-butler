"""Texas Instruments Tiva C vendor adapter (TM4C / LM4F / CC2538/CC26xx).

Covers TI's Cortex-M4F Tiva C series (TM4C123G/TM4C1294 — the rebrand of
the Stellaris LM4F line) and the SimpleLink CC26xx/CC13xx family (Cortex-M3/M4
with integrated radio). Toolchain:
  - Build: arm-none-eabi-gcc + make; TI's Code Composer Studio (proprietary)
    also works via the cl470 compiler
  - Flash: TI's UniFlash CLI (dslite, based on OpenOCD) or openocd with the
    `ti-cs-dap` interface; lm4flash is the open source alternative
  - Observe: serial UART; the ICdi virtual COM port on the LaunchPad enumerates
    automatically. SWO/RTT are not supported on Tiva.

Tiva uses a CMSIS-DAP-compatible debug probe on the LaunchPad (ICdi).
"""

from __future__ import annotations

import shutil
from typing import Any

from vendor_adapters import VendorAdapter, register_adapter

from . import openocd_flash_command, serial_monitor_command


class TivaAdapter(VendorAdapter):
    def __init__(self) -> None:
        super().__init__(
            vendor_id="ti",
            family="ti-tiva",
            display_name="Texas Instruments Tiva C / SimpleLink CC26xx",
            build_tool="arm-none-eabi-gcc",
            flash_tool="dslite",
            observe_tool="python",
            datasheet_term="datasheet",
        )

    def detect_tools(self) -> dict[str, bool]:
        return {
            "arm-none-eabi-gcc": bool(shutil.which("arm-none-eabi-gcc")),
            "cl470": bool(shutil.which("cl470")),
            "dslite": bool(shutil.which("dslite")),
            "lm4flash": bool(shutil.which("lm4flash")),
            "openocd": bool(shutil.which("openocd")),
            "uniflash": bool(shutil.which("uniflash")),
            "make": bool(shutil.which("make")),
        }

    def _pick_flash_tool(self) -> str:
        """Prefer dslite (TI official, integrated with UniFlash); fall back to
        lm4flash (open source, bundled with TivaWare); openocd last resort."""
        if shutil.which("dslite"):
            return "dslite"
        if shutil.which("lm4flash"):
            return "lm4flash"
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
        elf = ctx.get("elf", "firmware.bin")
        tool = self._pick_flash_tool()
        target = ctx.get("target", "") or ctx.get("part", "")
        if tool == "dslite":
            args = ["dslite", "flash"]
            if target:
                args.extend(["--config", f"{target}.ccxml"])
            args.append(elf)
            return args
        if tool == "lm4flash":
            return ["lm4flash", elf]
        if tool == "openocd":
            cfg = ctx.get("openocd_cfg", "ti-cs-dap.cfg")
            return openocd_flash_command(cfg, elf)
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
            f"{part} TivaWare",
            f"{part} launchpad schematic",
        ]

    def platformio_board(self, str_part: str) -> str:
        """Map Tiva part to PlatformIO board id (titiva platform).

        The real titiva board id for TM4C123 parts is lptm4c123gh6pm (the
        launchpad's TM4C123GH6PM chip); lptm4c1230c6pd does not exist in the
        registry and makes every build fail with "unknown board"."""
        p = str_part.upper()
        if "TM4C123" in p:
            return "lptm4c123gh6pm"
        if "TM4C129" in p:
            return "lptm4c1294ncpdt"
        if "CC2650" in p:
            return "cc2650_launchpad"
        if "CC2640" in p:
            return "cc2640r2_launchpad"
        if "CC1310" in p:
            return "cc1310_launchpad"
        if "LM4F" in p:
            return "lptm4c123gh6pm"  # LM4F → TM4C123 launchpad equivalent
        return "lptm4c123gh6pm"

    def _platformio_platform(self) -> str:
        return "titiva"

    def _platformio_framework(self) -> str:
        return "libopencm3"

    def supports_freertos_on_platformio(self) -> bool:
        # Tiva's libopencm3 framework on PlatformIO doesn't vendor CMSIS-RTOS
        # out of the box; FreeRTOS codegen on Tiva would need manual wiring.
        # Conservative: report False — the optimize-loop falls back to bare-metal.
        return False


register_adapter(TivaAdapter())
