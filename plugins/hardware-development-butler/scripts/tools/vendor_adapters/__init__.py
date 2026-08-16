"""Vendor adapter base class.

Each MCU vendor gets one adapter that declares how to build / flash / observe
for that vendor's chips. The workflow runner does NOT hardcode any vendor —
it routes to the right adapter based on chip family detection.

Adapters expose command templates, not commands themselves. The runner fills
in {port}, {target}, {elf}, {part} from workflow context. This keeps each
adapter a thin declaration layer; the actual execution goes through the
existing embeddedskills backend scripts or direct subprocess calls.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class VendorAdapter:
    """Base class for all vendor adapters.

    Subclasses set vendor_id + family + the command templates. The runner
    uses detect_tools() to probe the host, build_command() / flash_command()
    / observe_command() to get argv lists, datasheet_queries() for the
    datasheet-collect stage.
    """

    vendor_id: str = ""
    family: str = ""  # e.g. "stm32", "esp32", "msp430"
    display_name: str = ""
    build_tool: str = ""
    flash_tool: str = ""
    observe_tool: str = ""
    datasheet_term: str = "datasheet"

    def detect_tools(self) -> dict[str, bool]:
        """Probe the host for this vendor's tools. Returns {tool_name: available}."""
        import shutil
        return {
            "build": bool(shutil.which(self.build_tool)),
            "flash": bool(shutil.which(self.flash_tool)),
            "observe": bool(shutil.which(self.observe_tool)),
        }

    def build_command(self, ctx: dict[str, Any]) -> list[str]:
        """Return argv to build the firmware. ctx carries project_root, target, elf, etc."""
        raise NotImplementedError

    def flash_command(self, ctx: dict[str, Any]) -> list[str]:
        """Return argv to flash the firmware. ctx carries port, target, elf, etc."""
        raise NotImplementedError

    def observe_command(self, ctx: dict[str, Any]) -> list[str]:
        """Return argv to observe (serial/RTT/ITM). ctx carries port, baud."""
        raise NotImplementedError

    def platformio_board(self, part: str) -> str:
        """Map a chip part number to a PlatformIO board id. Override per vendor."""
        return ""

    def find_pio(self, project_root: Path) -> str:
        """Locate a usable pio binary without side effects.

        Checks PATH first, then a project-local .venv (searching up the
        directory tree). Returns "" when PlatformIO is disabled via env or
        not findable. Used both by build_via_platformio and by callers that
        need to know whether the PlatformIO backend will be used (e.g. to
        pick RTOS vs bare-metal codegen) without triggering a build.
        """
        import os
        import shutil
        if os.environ.get("HARDWARE_BUTLER_DISABLE_PLATFORMIO") == "1":
            return ""
        pio_bin = shutil.which("pio")
        if pio_bin:
            return pio_bin
        root = Path(project_root).resolve()
        search_dirs = [root]
        search_dirs.extend(root.parents)
        for base in search_dirs:
            for candidate in (
                base / ".venv" / "Scripts" / "pio.exe",
                base / ".venv" / "bin" / "pio",
            ):
                if candidate.exists():
                    return str(candidate)
        return ""

    def build_via_platformio(self, ctx: dict[str, Any]) -> list[str]:
        """Return argv to build via PlatformIO. Base impl generates `pio run -d
        <build_root>` if pio is on PATH.

        build_root may be an ASCII staging copy of the project when the real
        project path contains non-ASCII characters (GNU ld cannot write its
        map file under such paths on Windows). If no platformio.ini exists,
        one is generated using platformio_board() mapping and the CubeMX
        Core/Src layout when present. Returns empty list if pio is not
        findable (runner falls back to adapter.build_command).
        """
        import shutil
        pio_bin = self.find_pio(Path(str(ctx.get("project_root", "."))))
        if not pio_bin:
            return []
        project_root = Path(str(ctx.get("project_root", "."))).resolve()
        build_root = self._pio_build_root(project_root)
        if build_root != project_root:
            self._stage_ascii_build_copy(project_root, build_root)
        ini_path = build_root / "platformio.ini"
        if not ini_path.exists():
            board = self.platformio_board(ctx.get("part", ""))
            if board:
                ini_path.write_text(self._render_platformio_ini(build_root, board), encoding="utf-8")
        return [pio_bin, "run", "-d", str(build_root)]

    def pio_build_root(self, ctx: dict[str, Any]) -> Path:
        """Resolve the directory pio should build in (staging copy if needed)."""
        project_root = Path(str(ctx.get("project_root", "."))).resolve()
        return self._pio_build_root(project_root)

    def _pio_build_root(self, project_root: Path) -> Path:
        """GNU ld cannot create its map file under non-ASCII paths (Windows).
        Stage the build into an ASCII path under the temp dir when needed."""
        raw = str(project_root)
        if all(ord(ch) < 128 for ch in raw):
            return project_root
        import hashlib
        import tempfile
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
        return Path(tempfile.gettempdir()) / "hw-butler-pio" / digest

    def _stage_ascii_build_copy(self, project_root: Path, build_root: Path) -> None:
        """Mirror the project into build_root (excluding build/noise dirs).

        .pio is intentionally NOT excluded from being preserved: we never
        delete build_root, so previous build caches survive and rebuilds
        stay incremental. copytree(dirs_exist_ok=True) only adds/overwrites
        source files.
        """
        import shutil
        ignore = shutil.ignore_patterns(
            ".pio", ".git", "__pycache__", ".hardware-butler", ".embeddedskills",
            "docs", "build", "*.pyc",
        )
        shutil.copytree(project_root, build_root, ignore=ignore, dirs_exist_ok=True)

    def _render_platformio_ini(self, build_root: Path, board: str) -> str:
        """Render platformio.ini matching the generated HAL code layout.

        The firmware templates are STM32 HAL code living in Core/Src +
        Core/Inc (CubeMX layout). framework=stm32cube vendors the HAL
        package, and src_dir/build_flags point the build at that layout.
        """
        lines = [
            "; Auto-generated by hardware_butler workflow",
            f"[env:{board}]",
            f"platform = {self._platformio_platform()}",
            f"board = {board}",
            f"framework = {self._platformio_framework()}",
        ]
        if (build_root / "Core" / "Src").exists():
            lines.append("build_flags = -ICore/Inc")
            lines.append("")
            lines.append("[platformio]")
            lines.append("src_dir = Core/Src")
        return "\n".join(lines) + "\n"

    def _platformio_platform(self) -> str:
        """PlatformIO platform name. Override per vendor."""
        return ""

    def _platformio_framework(self) -> str:
        """PlatformIO framework name. Override per vendor."""
        return "arduino"

    def flash_via_probe_rs(self, ctx: dict[str, Any]) -> list[str]:
        """Return argv to flash via probe-rs download (with post-flash verify).

        Returns empty list if probe-rs is not on PATH.
        """
        import shutil
        if not shutil.which("probe-rs"):
            return []
        elf = ctx.get("elf", "build/firmware.elf")
        target = ctx.get("target", "")
        probe = ctx.get("probe", "")
        args = ["probe-rs", "download", "--verify", elf]
        if target:
            args.extend(["--chip", target])
        if probe:
            args.extend(["--probe", probe])
        return args

    def observe_via_probe_rs(self, ctx: dict[str, Any]) -> list[str]:
        """Return argv to observe RTT via probe-rs. Returns [] if probe-rs absent."""
        import shutil
        if not shutil.which("probe-rs"):
            return []
        target = ctx.get("target", "")
        args = ["probe-rs", "rtt", "attach"]
        if target:
            args.extend(["--chip", target])
        return args

    def observe_via_pyserial(self, ctx: dict[str, Any]) -> list[str]:
        """Return argv to observe UART via pyserial miniterm."""
        port = ctx.get("port", "")
        baud = ctx.get("baud", "115200")
        if not port:
            return []
        return ["python", "-m", "serial.tools.miniterm", port, baud]

    def datasheet_queries(self, part: str) -> list[str]:
        """Return search queries for the datasheet-collect stage."""
        return [
            f"{part} {self.datasheet_term} pdf",
            f"{part} reference manual",
            f"{part} pinout",
            f"{part} programming guide",
        ]

    def to_dict(self) -> dict[str, Any]:
        return {
            "vendor_id": self.vendor_id,
            "family": self.family,
            "display_name": self.display_name,
            "build_tool": self.build_tool,
            "flash_tool": self.flash_tool,
            "observe_tool": self.observe_tool,
            "datasheet_term": self.datasheet_term,
        }


# Registry of available adapters, keyed by family. Populated by each adapter
# module on import. The runner looks up adapters via get_adapter(family).
_ADAPTERS: dict[str, VendorAdapter] = {}


def register_adapter(adapter: VendorAdapter) -> None:
    _ADAPTERS[adapter.family] = adapter


def get_adapter(family: str) -> VendorAdapter | None:
    return _ADAPTERS.get(family)


def list_adapters() -> list[VendorAdapter]:
    return list(_ADAPTERS.values())


def detect_family(part: str) -> str:
    """Heuristic: map a chip part number to its vendor family.

    STM32xx → stm32, ESP32-xx → esp32, MSP430-xx → msp430, LM4F/TM4C → ti-tiva,
    TMS320 → c2000, ATmega/ATtiny → avr, CH32/GD32 → riscv (if RISC-V core)
    or stm32-compatible (if Cortex-M). Conservative: unknown → "".
    """
    p = part.upper()
    if p.startswith("STM32"):
        return "stm32"
    if p.startswith("ESP32") or p.startswith("ESP8266"):
        return "esp32"
    if p.startswith("MSP430"):
        return "msp430"
    if p.startswith(("TM4C", "LM4F", "CC2538", "CC2650", "CC2640")):
        return "ti-tiva"
    if p.startswith(("TMS320", "F280")):
        return "c2000"
    if p.startswith(("ATMEGA", "ATTINY", "ATXMEGA")):
        return "avr"
    if p.startswith("GD32") or p.startswith("CH32"):
        # GD32/CH32 Cortex-M variants act like STM32; RISC-V variants differ
        # but detection by part number alone is unreliable. Default to stm32.
        return "stm32"
    if p.startswith("NRF5"):
        return "nordic"
    return ""
