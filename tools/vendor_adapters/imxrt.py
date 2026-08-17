"""NXP i.MX RT vendor adapter (RT1010/1020/1050/1060/1160/1170 Cortex-M7).

Covers NXP's i.MX RT crossover MCUs — Cortex-M7 (and M4F on RT1170) running
at 500-1000 MHz, targeting high-performance applications that need MCU-class
real-time behavior with SoC-class throughput. Toolchain:
  - Build: arm-none-eabi-gcc + make or cmake/ninja; MCUXpresso IDE
    (proprietary, GCC-based); the MCUXpresso SDK provides HAL drivers
  - Flash: probe-rs (Cortex-M7, supports RT); J-Link (NXP official for RT);
    pyOCD; openocd; the on-board mfg-tool (uf2 bootloader) for USB mass
    storage flashing on RT1010 evk
  - Observe: SWO/RTT over SWD (probe-rs/J-Link); UART via LPUART peripheral

i.MX RT uses standard ARM SWD. The on-board LinkServer probe (CMSIS-DAP)
works with pyOCD and openocd. RT1170 is dual-core (M7+M4) — the workflow
treats it as single-core for simplicity; the user is responsible for cross-
core coordination when that matters.
"""

from __future__ import annotations

import shutil
from typing import Any

from vendor_adapters import VendorAdapter, _segger_jlink, register_adapter


class IMXRTAdapter(VendorAdapter):
    def __init__(self) -> None:
        super().__init__(
            vendor_id="nxp",
            family="imxrt",
            display_name="NXP i.MX RT (Cortex-M7 crossover)",
            build_tool="arm-none-eabi-gcc",
            flash_tool="probe-rs",
            observe_tool="probe-rs",
            datasheet_term="reference manual",
        )

    def detect_tools(self) -> dict[str, bool]:
        return {
            "arm-none-eabi-gcc": bool(shutil.which("arm-none-eabi-gcc")),
            "cmake": bool(shutil.which("cmake")),
            "ninja": bool(shutil.which("ninja")),
            "make": bool(shutil.which("make")),
            "probe-rs": bool(shutil.which("probe-rs")),
            "pyocd": bool(shutil.which("pyocd")),
            "openocd": bool(shutil.which("openocd")),
            "JLinkExe": bool(_segger_jlink()),
            "JLink.exe": bool(_segger_jlink()),
        }

    def _pick_flash_tool(self) -> str:
        """Prefer probe-rs (Cortex-M7); J-Link is NXP's recommended debugger
        but probe-rs is cross-vendor open source. Fall back to pyOCD, openocd,
        then J-Link."""
        for tool in ("probe-rs", "pyocd", "_jlink", "openocd"):
            if tool == "_jlink":
                if _segger_jlink():
                    return "JLink.exe"
            elif shutil.which(tool):
                return tool
        return ""

    def build_command(self, ctx: dict[str, Any]) -> list[str]:
        project_root = ctx.get("project_root", ".")
        # i.MX RT projects typically use cmake/ninja; fall back to make,
        # then to a bare gcc version check.
        if shutil.which("cmake") and shutil.which("ninja"):
            return ["cmake", "--build", str(project_root)]
        if shutil.which("make"):
            return ["make", "-C", str(project_root)]
        return ["arm-none-eabi-gcc", "--version"]

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
            args = ["pyocd", "flash", "-t", target or "mimxrt1052"]
            if probe:
                args.extend(["--probe", probe])
            args.append(elf)
            return args
        if tool in ("JLinkExe", "JLink.exe"):
            args = [tool, "-autoconnect", "1", "-commanderscript", "flash.jlink"]
            if target:
                args.extend(["-device", target])
            return args
        if tool == "openocd":
            cfg = ctx.get("openocd_cfg", "imxrt.cfg")
            return ["openocd", "-f", cfg, "-c", f"program {elf} verify reset exit"]
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
            return ["python", "-m", "serial.tools.miniterm", port, "115200"]
        return []

    def datasheet_queries(self, part: str) -> list[str]:
        return [
            f"{part} reference manual pdf",
            f"{part} datasheet pdf",
            f"{part} MCUXpresso",
            f"{part} boot configuration",
            f"{part} flexspi",
        ]

    def platformio_board(self, part: str) -> str:
        """Map i.MX RT part to PlatformIO board id (nxpimxrt platform)."""
        p = part.upper()
        if "RT1010" in p or "RT1011" in p:
            return "imxrt1010_evk"
        if "RT1020" in p or "RT1021" in p:
            return "imxrt1020_evk"
        if "RT1050" in p or "RT1051" in p or "RT1052" in p:
            return "imxrt1050_evk"
        if "RT1060" in p or "RT1061" in p or "RT1062" in p or "RT1064" in p:
            return "imxrt1060_evk"
        if "RT1160" in p or "RT1161" in p:
            return "imxrt1160_evk_cm7"
        if "RT1170" in p or "RT1171" in p or "RT1176" in p:
            return "imxrt1170_evk_cm7"
        return "imxrt1060_evk"

    def _platformio_platform(self) -> str:
        return "nxpimxrt"

    def _platformio_framework(self) -> str:
        return "mbed"

    def supports_freertos_on_platformio(self) -> bool:
        # i.MX RT mbed framework vendors FreeRTOS via the rtos subdirectory;
        # RT has plenty of RAM for FreeRTOS heaps.
        return True

    def canonical_chip(self, part: str) -> str:
        """i.MX RT part numbers pass through to probe-rs target names."""
        return part


register_adapter(IMXRTAdapter())
