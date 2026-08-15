"""STM32 vendor adapter.

STM32 ecosystem uses arm-none-eabi-gcc + CMake/Ninja for build, and one of
several flashers depending on probe type:
  - ST-Link: STM32_Programmer_CLI (CubeProgrammer) or st-flash (openocd-based)
  - J-Link: JLink.exe (Segger)
  - CMSIS-DAP: pyOCD or OpenOCD

The adapter prefers whatever is available on the host. observe uses serial
(UART) or RTT (via J-Link) or SWO (via pyOCD).
"""

from __future__ import annotations

import shutil
from typing import Any

from vendor_adapters import VendorAdapter, register_adapter


class STM32Adapter(VendorAdapter):
    def __init__(self) -> None:
        super().__init__(
            vendor_id="st",
            family="stm32",
            display_name="STMicroelectronics STM32",
            build_tool="arm-none-eabi-gcc",
            flash_tool="pyocd",  # default; will switch based on probe
            observe_tool="python",
            datasheet_term="reference manual",
        )

    def detect_tools(self) -> dict[str, bool]:
        return {
            "arm-none-eabi-gcc": bool(shutil.which("arm-none-eabi-gcc")),
            "cmake": bool(shutil.which("cmake")),
            "ninja": bool(shutil.which("ninja")),
            "STM32_Programmer_CLI": bool(shutil.which("STM32_Programmer_CLI")),
            "JLink.exe": bool(shutil.which("JLink.exe")),
            "openocd": bool(shutil.which("openocd")),
            "pyocd": bool(shutil.which("pyocd")),
            "st-flash": bool(shutil.which("st-flash")),
        }

    def _pick_flash_tool(self, ctx: dict[str, Any]) -> str:
        probe = str(ctx.get("probe", "")).lower()
        tools = self.detect_tools()
        if "jlink" in probe and tools["JLink.exe"]:
            return "JLink.exe"
        if ("stlink" in probe or "cmsis" in probe or "dap" in probe) and tools["pyocd"]:
            return "pyocd"
        if tools["STM32_Programmer_CLI"]:
            return "STM32_Programmer_CLI"
        if tools["openocd"]:
            return "openocd"
        if tools["pyocd"]:
            return "pyocd"
        if tools["st-flash"]:
            return "st-flash"
        return ""

    def build_command(self, ctx: dict[str, Any]) -> list[str]:
        project_root = ctx.get("project_root", ".")
        build_dir = ctx.get("build_dir", "build")
        if shutil.which("cmake") and shutil.which("ninja"):
            return ["cmake", "-S", str(project_root), "-B", build_dir, "-G", "Ninja"]
        return ["arm-none-eabi-gcc", "--version"]

    def flash_command(self, ctx: dict[str, Any]) -> list[str]:
        tool = self._pick_flash_tool(ctx)
        elf = ctx.get("elf", "build/firmware.elf")
        target = ctx.get("target", "")
        port = ctx.get("port", "")
        if tool == "pyocd":
            args = ["pyocd", "flash", elf]
            if target:
                args.extend(["--target", target])
            return args
        if tool == "STM32_Programmer_CLI":
            args = ["STM32_Programmer_CLI", "-c", "port=SWD", "-w", elf, "0x08000000"]
            if port:
                args[2] = f"port=SWD index={port}"
            return args
        if tool == "openocd":
            args = ["openocd", "-f", "interface/stlink.cfg", "-c", f"program {elf} reset exit"]
            return args
        if tool == "JLink.exe":
            args = ["JLink.exe", "-device", target or "STM32F407VG", "-if", "SWD", "-speed", "4000"]
            return args
        if tool == "st-flash":
            return ["st-flash", "write", elf, "0x08000000"]
        return []

    def observe_command(self, ctx: dict[str, Any]) -> list[str]:
        port = ctx.get("port", "")
        baud = ctx.get("baud", "115200")
        if port:
            return ["python", "-m", "serial.tools.miniterm", port, baud]
        return ["python", "-c", "import pyocd; print('no serial port configured')"]

    def datasheet_queries(self, part: str) -> list[str]:
        return [
            f"{part} reference manual pdf",
            f"{part} datasheet pdf",
            f"{part} development board schematic",
            f"{part} pinout alternate functions",
        ]


register_adapter(STM32Adapter())
