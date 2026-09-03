"""Nordic Semiconductor vendor adapter.

Covers nRF52 / nRF53 (Cortex-M) BLE + multi-protocol MCUs. Toolchain:
  - Build: arm-none-eabi-gcc + cmake/ninja; PlatformIO `nordicnrf52` platform
  - Flash: probe-rs (Cortex-M SWD), pyOCD, J-Link, or nrfjprog (proprietary)
  - Observe: RTT (probe-rs / pyOCD) over SWD; UART as fallback

Nordic chips are Cortex-M so probe-rs and pyOCD both support them; the
canonical chip-name normalization for probe-rs follows the same pattern as
STM32 (trailing package digit -> 'x') but Nordic part numbers like
nRF52832 don't end in a package digit, so pass-through is the default.
"""

from __future__ import annotations

import shutil
from typing import Any

from vendor_adapters import VendorAdapter, _segger_jlink, register_adapter

from . import serial_monitor_command


class NordicAdapter(VendorAdapter):
    def __init__(self) -> None:
        super().__init__(
            vendor_id="nordic",
            family="nordic",
            display_name="Nordic Semiconductor nRF52/nRF53",
            build_tool="arm-none-eabi-gcc",
            flash_tool="probe-rs",
            observe_tool="probe-rs",
            datasheet_term="product specification",
        )

    def detect_tools(self) -> dict[str, bool]:
        return {
            "arm-none-eabi-gcc": bool(shutil.which("arm-none-eabi-gcc")),
            "probe-rs": bool(shutil.which("probe-rs")),
            "pyocd": bool(shutil.which("pyocd")),
            "nrfjprog": bool(shutil.which("nrfjprog")),
            "JLinkExe": bool(_segger_jlink()),
            "cmake": bool(shutil.which("cmake")),
            "ninja": bool(shutil.which("ninja")),
        }

    def build_command(self, ctx: dict[str, Any]) -> list[str]:
        project_root = ctx.get("project_root", ".")
        if shutil.which("cmake") and shutil.which("ninja"):
            return ["cmake", "--build", str(project_root)]
        # A bare `arm-none-eabi-gcc --version` probe is not a build.
        return []

    def flash_command(self, ctx: dict[str, Any]) -> list[str]:
        # Prefer probe-rs (cross-vendor, open source); fall back to nrfjprog
        # (Nordic's official tool, available with the nRF Connect SDK).
        elf = ctx.get("elf", "firmware.elf")
        target = self.canonical_chip(str(ctx.get("target", "") or ctx.get("part", "")))
        probe = ctx.get("probe", "")
        if shutil.which("probe-rs"):
            args = ["probe-rs", "download", "--verify", elf]
            if target:
                args.extend(["--chip", target])
            if probe:
                args.extend(["--probe", probe])
            return args
        if shutil.which("nrfjprog"):
            args = ["nrfjprog", "--program", elf, "--sectorerase"]
            if probe:
                args.extend(["--snr", probe])
            return args
        return []

    def observe_command(self, ctx: dict[str, Any]) -> list[str]:
        # RTT over SWD when probe-rs available; UART via pyserial otherwise.
        if shutil.which("probe-rs"):
            target = ctx.get("target", "")
            args = ["probe-rs", "rtt", "attach"]
            if target:
                args.extend(["--chip", target])
            return args
        port = ctx.get("port", "")
        if port:
            return serial_monitor_command(port)
        return []

    def datasheet_queries(self, part: str) -> list[str]:
        return [
            f"{part} product specification pdf",
            f"{part} reference manual",
            f"{part} pinout",
            f"{part} softdevice s140",
        ]

    def platformio_board(self, part: str) -> str:
        p = part.upper()
        if "NRF52832" in p:
            return "nrf52_dk"
        if "NRF52840" in p:
            return "nrf52840_dk"
        if "NRF52833" in p:
            return "nrf52833_dk"
        if "NRF5340" in p:
            return "nrf5340_dk_app"
        return "nrf52_dk"

    def supports_freertos_on_platformio(self) -> bool:
        # Nordic's PlatformIO build vendors CMSIS-RTOS — FreeRTOS codegen
        # works the same as STM32's stm32cube framework path.
        return True

    def _platformio_platform(self) -> str:
        return "nordicnrf52"

    def _platformio_framework(self) -> str:
        return "arduino"


register_adapter(NordicAdapter())
