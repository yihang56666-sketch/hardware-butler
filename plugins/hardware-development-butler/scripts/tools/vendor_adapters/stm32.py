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

    def platformio_board(self, part: str) -> str:
        """Map STM32 part number to PlatformIO board id (ststm32 platform)."""
        p = part.upper()
        if "F103" in p and "RB" in p:
            return "nucleo_f103rb"
        if "F401" in p:
            return "nucleo_f401re"
        if "F411" in p:
            return "nucleo_f411re"
        if "F407" in p:
            return "disco_f407vg"
        if "F429" in p:
            return "nucleo_f429zi"
        if "F446" in p:
            return "nucleo_f446re"
        if "L432" in p:
            return "nucleo_l432kc"
        if "L476" in p:
            return "nucleo_l476rg"
        return "nucleo_f401re"

    def _platformio_platform(self) -> str:
        return "ststm32"

    def _platformio_framework(self) -> str:
        # The workflow generates STM32 HAL code (Core/Src + Core/Inc), so the
        # PlatformIO build must use the stm32cube framework that vendors HAL
        # + CMSIS + startup/linker, not the Arduino core.
        return "stm32cube"

    def supports_freertos_on_platformio(self) -> bool:
        # The stm32cube framework package vendors FreeRTOS + CMSIS-RTOS v1
        # middleware; the generated pio_freertos.py script compiles it.
        return True

    def platformio_freertos_script(self) -> str:
        # Pre-script: the stock stm32cube builder compiles HAL/BSP/Utilities/
        # USB middleware but skips Third_Party/FreeRTOS entirely, so add the
        # kernel + CMSIS_RTOS (v1) + heap_4 + the core-matching GCC port via
        # the official extra_scripts hook (env.BuildSources must run before
        # the main program is constructed, hence pre:).
        return """\\
# Auto-generated by hardware_butler: compile the STM32Cube framework's bundled
# FreeRTOS (CMSIS-RTOS v1) into this PlatformIO stm32cube build.
Import("env")

import os

mcu = env.BoardConfig().get("build.mcu", "")
framework_dir = env.PioPlatform().get_package_dir("framework-stm32cube%s" % mcu[5:7])
freertos_src = os.path.join(
    framework_dir, "Middlewares", "Third_Party", "FreeRTOS", "Source"
)
assert os.path.isdir(freertos_src), (
    "FreeRTOS middleware missing from framework package: %s" % freertos_src
)

cpu = env.BoardConfig().get("build.cpu", "")
port_map = {
    "cortex-m0": "ARM_CM0",
    "cortex-m0plus": "ARM_CM0",
    "cortex-m23": "ARM_CM23",
    "cortex-m3": "ARM_CM3",
    "cortex-m33": "ARM_CM33",
    "cortex-m4": "ARM_CM4F",
    "cortex-m7": "ARM_CM7",
}
port = port_map.get(cpu)
assert port, "no FreeRTOS GCC port mapping for cpu=%r" % cpu

# The ARM_CM4F/ARM_CM7 ports save FPU context with explicit FPU instructions,
# but stm32cube board definitions declare plain cortex-m4/m7 without FPU
# flags, which makes gas reject those instructions. Add the FPU flags for the
# cores whose FreeRTOS port requires them (later flags override -mcpu only);
# they must reach compilation AND linking or the link fails with
# "uses VFP register arguments" ABI mismatches.
if cpu in ("cortex-m4", "cortex-m7"):
    fpu = "fpv4-sp-d16" if cpu == "cortex-m4" else "fpv5-sp-d16"
    fpu_flags = ["-mfpu=%s" % fpu, "-mfloat-abi=hard"]
    env.Append(CCFLAGS=fpu_flags, ASFLAGS=fpu_flags, LINKFLAGS=fpu_flags)

env.Append(
    CPPPATH=[
        os.path.join(freertos_src, "include"),
        os.path.join(freertos_src, "CMSIS_RTOS"),
        os.path.join(freertos_src, "portable", "GCC", port),
    ]
)

env.BuildSources(
    "$BUILD_DIR/freertos",
    freertos_src,
    "+<*.c> +<CMSIS_RTOS> +<portable/GCC/%s> +<portable/MemMang/heap_4.c>" % port,
)
"""


register_adapter(STM32Adapter())
