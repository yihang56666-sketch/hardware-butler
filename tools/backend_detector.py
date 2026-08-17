"""Backend detection: probe a project to decide which build/flash/debug backends to use.

The runner does NOT hardcode STM32/Keil. It inspects the project artifacts and
declares the actual backend set: build (keil/gcc/eide), flash (jlink/openocd/probe-rs),
observe (serial/jlink-rtt/openocd-itm). Each backend has a probe check so the
runner can skip backends whose host tooling is missing instead of failing hard.

P3: added vendor adapter routing. When the chip family is detected (stm32 /
esp32 / msp430 etc.), the matching vendor adapter provides build/flash/observe
command templates. This makes the workflow support STM32 / ESP32 / TI / AVR /
RISC-V without hardcoding any vendor's toolchain.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cube_detect
import project_scanner

# Vendor adapters register themselves on import.
import vendor_adapters
import vendor_adapters.avr
import vendor_adapters.esp32
import vendor_adapters.msp430
import vendor_adapters.nordic
import vendor_adapters.stm32


@dataclass(frozen=True)
class BackendChoice:
    build: str
    flash: str
    observe: str
    probe_serial: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "build": self.build,
            "flash": self.flash,
            "observe": self.observe,
            "probe_serial": self.probe_serial,
        }


BUILD_TOOL_BINARIES = {
    "keil": "UV4.exe",
    "gcc": "arm-none-eabi-gcc",
    "eide": "code",
}

FLASH_TOOL_BINARIES = {
    "jlink": "JLink.exe",
    "openocd": "openocd",
    "probe-rs": "probe-rs",
}

OBSERVE_TOOL_BINARIES = {
    "serial": "python",
    "jlink-rtt": "JLink.exe",
    "openocd-itm": "openocd",
}


def tool_available(name: str) -> bool:
    """True if the named executable is on PATH."""
    return shutil.which(name) is not None


def available_backends(binaries: dict[str, str]) -> list[str]:
    return [name for name, bin_name in binaries.items() if tool_available(bin_name)]


def detect_build_backend(root: Path) -> str:
    """Pick a build backend based on project artifacts + host tooling.

    Preference order: keil (if .uvprojx + UV4) > eide (if .eide + code) > gcc
    (if CMake/Makefile + arm-none-eabi-gcc). Falls back to first available
    host tool even if project file is ambiguous, so the runner can still
    propose a plan.
    """
    scan = project_scanner.scan(root)
    artifacts = scan.get("artifacts", {})
    host_available = available_backends(BUILD_TOOL_BINARIES)
    if artifacts.get("keil_project") and "keil" in host_available:
        return "keil"
    if artifacts.get("eide_project") and "eide" in host_available:
        return "eide"
    if (artifacts.get("cmake_project") or artifacts.get("makefile")) and "gcc" in host_available:
        return "gcc"
    if host_available:
        return host_available[0]
    if artifacts.get("keil_project"):
        return "keil"
    if artifacts.get("cmake_project") or artifacts.get("makefile"):
        return "gcc"
    return "unknown"


def detect_flash_backend(root: Path, context_probe: str = "") -> str:
    """Pick a flash backend. Prefers probe type from context, else host availability."""
    available = available_backends(FLASH_TOOL_BINARIES)
    if context_probe:
        probe_lower = context_probe.lower()
        if "jlink" in probe_lower and "jlink" in available:
            return "jlink"
        if "stlink" in probe_lower or "cmsis" in probe_lower:
            if "openocd" in available:
                return "openocd"
            if "probe-rs" in available:
                return "probe-rs"
        if "daplink" in probe_lower or "dap" in probe_lower:
            if "probe-rs" in available:
                return "probe-rs"
            if "openocd" in available:
                return "openocd"
    if available:
        return available[0]
    return "unknown"


def detect_observe_backend(root: Path, flash_backend: str) -> str:
    """Pick an observe backend. RTT if jlink, ITM if openocd, serial otherwise."""
    if flash_backend == "jlink" and tool_available("JLink.exe"):
        return "jlink-rtt"
    if flash_backend == "openocd" and tool_available("openocd"):
        return "openocd-itm"
    if tool_available("python"):
        return "serial"
    return "unknown"


def detect_backends(root: Path, context_probe: str = "", context_part: str = "") -> dict[str, Any]:
    """Probe the project + host, return a complete backend choice + diagnostics.

    P3: also runs vendor adapter detection. If the chip family is recognized
    (stm32/esp32/msp430/...), loads the matching vendor adapter and includes
    its tool availability + command templates in the result.
    """
    cube = cube_detect.detect(root)
    build = detect_build_backend(root)
    flash = detect_flash_backend(root, context_probe)
    observe = detect_observe_backend(root, flash)
    choice = BackendChoice(build=build, flash=flash, observe=observe, probe_serial=context_probe)

    part = context_part
    if not part:
        projects = cube.get("cubemx_projects", []) or []
        if projects:
            mcu = projects[0].get("mcu", {})
            if isinstance(mcu, dict):
                part = mcu.get("name", "")
    family = vendor_adapters.detect_family(part) if part else ""
    adapter = vendor_adapters.get_adapter(family) if family else None
    adapter_info: dict[str, Any] = {}
    if adapter:
        adapter_info = {
            "family": family,
            "adapter": adapter.to_dict(),
            "tools_available": adapter.detect_tools(),
        }

    return {
        "schema_version": 1,
        "root": str(root.resolve()),
        "backends": choice.to_dict(),
        "host_availability": {
            "build": available_backends(BUILD_TOOL_BINARIES),
            "flash": available_backends(FLASH_TOOL_BINARIES),
            "observe": available_backends(OBSERVE_TOOL_BINARIES),
        },
        "cube_detection": {
            "has_cubemx": cube.get("has_cubemx", False),
            "mcu": (cube.get("cubemx_projects", [{}])[0].get("mcu", {}).get("name", "") if cube.get("cubemx_projects") else ""),
        },
        "vendor_adapter": adapter_info,
        "notes": _backend_notes(choice),
    }


def _backend_notes(choice: BackendChoice) -> list[str]:
    notes: list[str] = []
    if choice.build == "unknown":
        notes.append("no build tool detected on host; build stage will produce plan-only")
    if choice.flash == "unknown":
        notes.append("no flash tool detected on host; flash stage will produce runbook-only")
    if choice.observe == "unknown":
        notes.append("no observe tool detected; debug-observe will run in sim mode")
    return notes
