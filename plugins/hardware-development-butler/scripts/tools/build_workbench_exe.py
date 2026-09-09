"""Build the Hardware Butler CLI and workbench executables with PyInstaller."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
WORK = ROOT / "build" / "pyinstaller"
SPECS = ROOT / "build" / "specs"
ENV_PYINSTALLER = "HW_BUTLER_PYINSTALLER"


def pyinstaller_path() -> str:
    override = os.getenv(ENV_PYINSTALLER)
    if override:
        return override
    found = shutil.which("pyinstaller")
    if found:
        return found
    raise SystemExit(
        "PyInstaller was not found. Install it with pip install pyinstaller or set "
        f"{ENV_PYINSTALLER} to the PyInstaller executable."
    )


def run(command: list[str]) -> None:
    print(">", " ".join(command))
    subprocess.run(command, cwd=ROOT, check=True)


def build_target(
    pyinstaller: str,
    *,
    name: str,
    entry: str,
    windowed: bool,
    include_embeddedskills: bool = False,
    include_qt_material: bool = False,
) -> None:
    command = [
        pyinstaller,
        "--noconfirm",
        "--clean",
        "--onedir",
        "--name",
        name,
        "--distpath",
        str(DIST),
        "--workpath",
        str(WORK),
        "--specpath",
        str(SPECS),
        "--paths",
        str(ROOT / "tools"),
    ]
    if include_embeddedskills:
        command.extend(
            [
                "--paths",
                str(ROOT / "embeddedskills"),
                "--hidden-import",
                "safety_gate",
                "--add-data",
                f"{ROOT / 'embeddedskills'};embeddedskills",
            ]
        )
    if include_qt_material:
        command.extend(["--hidden-import", "qt_material", "--collect-data", "qt_material"])
    command.append("--windowed" if windowed else "--console")
    command.append(str(ROOT / entry))
    run(command)


def main() -> int:
    pyinstaller = pyinstaller_path()
    build_target(
        pyinstaller,
        name="hardware_butler_cli",
        entry="tools/hardware_butler.py",
        windowed=False,
        include_embeddedskills=True,
    )
    build_target(
        pyinstaller,
        name="HardwareButlerWorkbench",
        entry="gui/hardware_agent_ui.py",
        windowed=True,
        include_qt_material=True,
    )

    tutorial = ROOT / "docs" / "WORKBENCH_TUTORIAL.md"
    if tutorial.exists():
        shutil.copy2(tutorial, DIST / "WORKBENCH_TUTORIAL.md")

    print()
    print("Build outputs:")
    print(f"- GUI: {DIST / 'HardwareButlerWorkbench' / 'HardwareButlerWorkbench.exe'}")
    print(f"- CLI: {DIST / 'hardware_butler_cli' / 'hardware_butler_cli.exe'}")
    print("- Keep both folders together so the GUI can find the CLI backend.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
