"""ESP32 vendor adapter.

ESP32 ecosystem uses Espressif's own toolchain:
  - Build: idf.py (ESP-IDF) or standalone xtensa-esp32-elf-gcc
  - Flash: esptool.py (Python, comes with ESP-IDF)
  - Observe: idf.py monitor (handles core dump decoding) or plain serial
  - Debug: xtensa-esp32-elf-gdb + OpenOCD with JTAG

ESP32 doesn't use ST-Link or SWD; its debug is via JTAG (ESP32 has built-in
JTAG via USB on some boards) or UART only.
"""

from __future__ import annotations

import shutil
from typing import Any

from vendor_adapters import VendorAdapter, register_adapter


class ESP32Adapter(VendorAdapter):
    def __init__(self) -> None:
        super().__init__(
            vendor_id="espressif",
            family="esp32",
            display_name="Espressif ESP32 / ESP8266",
            build_tool="idf.py",
            flash_tool="esptool.py",
            observe_tool="python",
            datasheet_term="technical reference",
        )

    def detect_tools(self) -> dict[str, bool]:
        return {
            "idf.py": bool(shutil.which("idf.py")),
            "esptool.py": bool(shutil.which("esptool.py")),
            "esptool": bool(shutil.which("esptool")),
            "xtensa-esp32-elf-gcc": bool(shutil.which("xtensa-esp32-elf-gcc")),
            "openocd": bool(shutil.which("openocd")),
        }

    def _pick_flash_tool(self) -> str:
        tools = self.detect_tools()
        if tools["esptool.py"]:
            return "esptool.py"
        if tools["esptool"]:
            return "esptool"
        return ""

    def build_command(self, ctx: dict[str, Any]) -> list[str]:
        project_root = ctx.get("project_root", ".")
        if shutil.which("idf.py"):
            return ["idf.py", "-C", str(project_root), "build"]
        return ["xtensa-esp32-elf-gcc", "--version"]

    def flash_command(self, ctx: dict[str, Any]) -> list[str]:
        tool = self._pick_flash_tool()
        port = ctx.get("port", "")
        baud = ctx.get("baud", "460800")
        addr = ctx.get("flash_addr", "0x10000")
        image = ctx.get("elf", "build/firmware.bin")
        if not tool:
            return []
        args = [tool, "--port", port, "--baud", baud, "write_flash", addr, image]
        return args

    def observe_command(self, ctx: dict[str, Any]) -> list[str]:
        port = ctx.get("port", "")
        baud = ctx.get("baud", "115200")
        if shutil.which("idf.py"):
            return ["idf.py", "-p", port, "monitor"]
        return ["python", "-m", "serial.tools.miniterm", port, baud]

    def datasheet_queries(self, part: str) -> list[str]:
        return [
            f"{part} technical reference manual pdf",
            f"{part} datasheet pdf",
            f"{part} getting started guide",
            f"{part} pinout",
        ]

    def platformio_board(self, part: str) -> str:
        """Map ESP32 part number to PlatformIO board id (espressif32 platform)."""
        p = part.upper()
        if "ESP32-C3" in p:
            return "esp32-c3-devkitm-1"
        if "ESP32-S2" in p:
            return "esp32-s2-saola-1"
        if "ESP32-S3" in p:
            return "esp32-s3-devkitc-1"
        if "ESP8266" in p:
            return "esp01"
        return "esp32dev"

    def _platformio_platform(self) -> str:
        return "espressif32"

    def _platformio_framework(self) -> str:
        return "arduino"


register_adapter(ESP32Adapter())
