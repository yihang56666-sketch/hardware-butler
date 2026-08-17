"""One-command readiness check for real-board day (no hardware required to run).

Answers, before any workflow is started:
- which flash backends are installed (probe-rs, pyOCD, openocd, STM32 CLI, JLink)
- whether a debug probe is currently attached (`pyocd list` / `probe-rs list`)
- whether the part's canonical chip name resolves against the locally
  installed pyOCD pack database (catches name/pack mismatches BEFORE flashing)
- which COM ports exist for serial observe
- the exact environment + command to run the 9-stage workflow once a board
  is plugged in

Never performs any hardware write: only `list`-style read-only queries with
fixed argv lists (shell never involved).
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import vendor_adapters  # noqa: E402
import vendor_adapters.c2000  # noqa: E402,F401 — registers the c2000 adapter
import vendor_adapters.esp32  # noqa: E402,F401 — registers the esp32 adapter
import vendor_adapters.lpc  # noqa: E402,F401 — registers the lpc adapter
import vendor_adapters.msp430  # noqa: E402,F401 — registers the msp430 adapter
import vendor_adapters.nordic  # noqa: E402,F401 — registers the nordic adapter
import vendor_adapters.pic32  # noqa: E402,F401 — registers the pic32 adapter
import vendor_adapters.ra  # noqa: E402,F401 — registers the ra adapter
import vendor_adapters.riscv  # noqa: E402,F401 — registers the riscv adapter
import vendor_adapters.stm32  # noqa: E402,F401 — registers the stm32 adapter
import vendor_adapters.tiva  # noqa: E402,F401 — registers the ti-tiva adapter

_TIMEOUT_S = 120


def _find_exe(name: str, root: Path) -> str:
    """Locate an executable on PATH or in a project-local .venv (walking up)."""
    found = shutil.which(name)
    if found:
        return found
    suffix = "Scripts" if sys.platform == "win32" else "bin"
    for base in [root, *root.parents]:
        candidate = base / ".venv" / suffix / (name + (".exe" if sys.platform == "win32" else ""))
        if candidate.exists():
            return str(candidate)
    return ""


def _run_readonly(argv: list[str]) -> tuple[bool, list[str]]:
    """Run a read-only list command (fixed argv, no shell). Returns
    (ok, non-empty output lines)."""
    try:
        proc = subprocess.run(
            [str(token) for token in argv],
            shell=False,
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_S,
        )
    except (OSError, subprocess.SubprocessError):
        return False, []
    lines = [line for line in (proc.stdout + proc.stderr).splitlines() if line.strip()]
    return proc.returncode == 0, lines


def _table_rows(lines: list[str]) -> list[str]:
    """Drop a `Name Vendor ...` header and dashed separator, keep rows."""
    if len(lines) >= 2 and set(lines[1].strip()) <= {"-", " ", "+", "|"}:
        return lines[2:]
    return lines


def _pyocd_target_rows(pyocd: str, name: str) -> int:
    ok, lines = _run_readonly([pyocd, "list", "--targets", "-n", name])
    if not ok:
        return -1
    return len(_table_rows(lines))


_NO_PROBE_PHRASES = ("no available debug probes", "no probes", "no debug probes")


def _probe_rows(lines: list[str]) -> list[str]:
    """Table rows minus headers/separators and 'no probes connected' notes."""
    return [
        line
        for line in _table_rows(lines)
        if not any(phrase in line.lower() for phrase in _NO_PROBE_PHRASES)
    ]


def _looks_like_java_jlink(path: str) -> bool:
    """shutil.which('JLink.exe') hits the JDK's jlink (case-insensitive FS);
    Segger's tool never lives under a Java runtime directory."""
    lowered = path.lower().replace("\\", "/")
    return any(marker in lowered for marker in ("/jdk", "/java", "adoptium", "temurin", "/zulu", "corretto", "amazon-corretto"))


def _family_probe_query(canonical: str) -> str:
    """Short prefix used to test whether ANY pack for the family is present
    (e.g. stm32f4 for STM32F407VGTx)."""
    lowered = canonical.lower()
    if lowered.startswith("stm32") and len(lowered) >= 7:
        return lowered[:7]  # "stm32f4"
    return lowered[:6]


def run_preflight(root: Path, part: str, *, probe: str = "") -> dict[str, Any]:
    root = root.resolve()
    result: dict[str, Any] = {
        "schema_version": 1,
        "status": "ok",
        "action": "real-preflight",
        "root": str(root),
        "part": part,
        "summary": "",
    }

    family = vendor_adapters.detect_family(part)
    adapter = vendor_adapters.get_adapter(family) if family else None
    canonical = adapter.canonical_chip(part) if adapter else part
    board = adapter.platformio_board(part) if adapter else ""
    result["part_mapping"] = {
        "family": family or "unknown",
        "canonical_chip": canonical,
        "platformio_board": board,
    }

    tools: dict[str, str] = {}
    warnings: list[str] = []
    for name in ("probe-rs", "openocd", "STM32_Programmer_CLI", "JLink.exe"):
        tools[name] = shutil.which(name) or ""
    if tools["JLink.exe"] and _looks_like_java_jlink(tools["JLink.exe"]):
        warnings.append(
            "JLink.exe resolved to the JDK's jlink (Java), not Segger J-Link; excluded"
        )
        tools["JLink.exe"] = ""
    tools["pyocd"] = _find_exe("pyocd", root)
    pio = adapter.find_pio(root) if adapter else ""
    result["tools"] = {"flash": tools, "platformio": pio}

    # Attached probes (read-only list queries only).
    probes_attached: list[str] = []
    if tools["pyocd"]:
        ok, lines = _run_readonly([tools["pyocd"], "list"])
        if ok:
            probes_attached = _probe_rows(lines)
    if not probes_attached and tools["probe-rs"]:
        ok, lines = _run_readonly([tools["probe-rs"], "list"])
        if ok:
            probes_attached = _probe_rows(lines)
    result["probes_attached"] = probes_attached

    # pyOCD target-name resolution against the installed pack database.
    target_status = "unchecked"
    if tools["pyocd"] and family:
        rows = _pyocd_target_rows(tools["pyocd"], canonical.lower())
        if rows == 0:
            family_rows = _pyocd_target_rows(tools["pyocd"], _family_probe_query(canonical))
            target_status = "pack-missing" if family_rows == 0 else "not-found"
        elif rows > 0:
            target_status = "resolves"
    result["target_status"] = target_status

    # COM ports for serial observe.
    com_ports: list[dict[str, str]] = []
    try:
        import serial.tools.list_ports  # type: ignore[import-not-found]

        com_ports = [
            {"device": p.device, "description": p.description}
            for p in serial.tools.list_ports.comports()
        ]
    except Exception:  # noqa: BLE001 — pyserial optional
        pass
    result["com_ports"] = com_ports

    flash_backend = next((name for name in ("probe-rs", "pyocd") if tools[name]), "")
    result["flash_backend"] = flash_backend
    checks = {
        "flash_tool_installed": bool(flash_backend),
        "target_resolves": target_status in ("resolves", "unchecked"),
        "probe_attached": bool(probes_attached),
        "part_mapping_known": family is not None and family != "",
    }
    result["checks"] = checks
    result["ready"] = all(checks.values())
    result["warnings"] = warnings

    next_commands: list[str] = []
    if not flash_backend:
        next_commands.append(
            "install one flash backend: pip install pyocd  (or: cargo install probe-rs)"
        )
    if target_status == "pack-missing":
        next_commands.append(f"install the CMSIS pack: pyocd pack install {canonical.lower()}")
    elif target_status == "not-found":
        next_commands.append(
            f"chip {canonical} does not resolve in the installed pyOCD packs; "
            "check the part number or install its pack"
        )
    if not probes_attached:
        next_commands.append(
            "no debug probe attached: plug in the board (ST-Link Nucleo/Discovery), then re-run real-preflight"
        )
    probe_arg = probe or "stlink"
    goal_cmd = (
        "HARDWARE_BUTLER_ENABLE_REAL_FLASH=1 "
        f"python tools/hardware_butler.py workflow-run --root \"{root}\" "
        "--intent develop-feature --goal \"LED blink\" --feature led-blink "
        f"--pin PD12 --function gpio-output --part {part} --probe {probe_arg} --json"
    )
    next_commands.append(goal_cmd)
    next_commands.append("(PowerShell: set HARDWARE_BUTLER_ENABLE_REAL_FLASH=1 in a separate step)")
    result["next_commands"] = next_commands

    result["summary"] = (
        f"ready={result['ready']} backend={flash_backend or 'none'} "
        f"target={target_status} probes={len(probes_attached)} com_ports={len(com_ports)}"
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Real-board-day readiness preflight (read-only)")
    parser.add_argument("--root", default=".")
    parser.add_argument("--part", required=True)
    parser.add_argument("--probe", default="")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()
    result = run_preflight(Path(args.root), args.part, probe=args.probe)
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.as_json else json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
