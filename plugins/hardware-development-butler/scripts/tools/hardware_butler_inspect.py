"""Run the first-phase hardware butler inspection loop.

The loop is read-only against the inspected project. It writes dossier outputs
to an output directory so later build/flash/debug actions can start from stable
evidence instead of rediscovering the project every session.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import cubemx_ioc_summary  # noqa: E402
import project_scanner  # noqa: E402
import runtime_context  # noqa: E402
import safe_io  # noqa: E402

REPO_ROOT = runtime_context.PACKAGE_ROOT


def inspect_project(root: Path, out_dir: Path) -> dict[str, Any]:
    root = root.resolve()
    out_dir = out_dir.resolve()
    safe_io.validate_write_path(out_dir, allowed_roots=runtime_context.allowed_write_roots())
    profiles_dir = out_dir / "profiles"

    scan_data = project_scanner.scan(root)
    write_text(out_dir / "project-dossier.md", project_scanner.render_markdown(scan_data))
    write_json(profiles_dir / "project-dossier.json", scan_data)

    ioc_summaries = []
    for item in scan_data.get("artifacts", {}).get("cubemx_ioc", []):
        ioc_path = root / item["path"]
        try:
            summary = cubemx_ioc_summary.summarize(ioc_path)
        except (OSError, ValueError) as exc:
            summary = {
                "ioc_file": str(ioc_path),
                "error": str(exc),
            }
        ioc_summaries.append(summary)

    firmware_profile = build_firmware_profile(scan_data, ioc_summaries)
    board_profile = build_board_profile(scan_data, ioc_summaries)

    write_text(out_dir / "firmware-profile.md", render_firmware_profile(firmware_profile))
    write_text(out_dir / "board-profile.md", render_board_profile(board_profile))
    write_json(profiles_dir / "firmware-profile.json", firmware_profile)
    write_json(profiles_dir / "board-profile.json", board_profile)

    if ioc_summaries:
        primary_summary = ioc_summaries[0]
        summary_markdown = (
            f"# CubeMX IOC Summary\n\nInspection error: {primary_summary['error']}\n"
            if primary_summary.get("error") else cubemx_ioc_summary.render_markdown(primary_summary)
        )
        write_text(out_dir / "cubemx-ioc-summary.md", summary_markdown)
        write_json(profiles_dir / "cubemx-ioc-summary.json", primary_summary)

    ensure_log_files(out_dir)
    errors = [summary for summary in ioc_summaries if summary.get("error")]

    return {
        "status": "partial" if errors else "ok",
        "errors": errors,
        "root": str(root),
        "out_dir": str(out_dir),
        "generated": [
            str(out_dir / "project-dossier.md"),
            str(out_dir / "board-profile.md"),
            str(out_dir / "firmware-profile.md"),
            str(out_dir / "issues.md"),
            str(out_dir / "debug-logbook.md"),
        ],
        "summary": {
            "toolchains": scan_data["summary"]["toolchains"],
            "cubemx_projects": len(ioc_summaries),
            "schematic_candidates": len(scan_data.get("artifacts", {}).get("schematic", [])),
            "build_logs": len(scan_data.get("artifacts", {}).get("build_log", [])),
        },
        "board_profile": board_profile,
        "firmware_profile": firmware_profile,
        "next_actions": scan_data["recommended_next_steps"],
    }


def build_firmware_profile(scan_data: dict[str, Any], ioc_summaries: list[dict[str, Any]]) -> dict[str, Any]:
    primary_ioc = ioc_summaries[0] if ioc_summaries else {}
    artifacts = scan_data.get("artifacts", {})
    return {
        "schema_version": 1,
        "source": "hardware_butler_inspect",
        "project_type": "CubeMX" if ioc_summaries else "unknown",
        "mcu": primary_ioc.get("mcu", {}),
        "cubemx_project": primary_ioc.get("project", {}),
        "toolchains": scan_data["summary"]["toolchains"],
        "build_entries": {
            "keil": artifacts.get("keil_project", []),
            "cmake_gcc": artifacts.get("cmake_project", []),
            "eide": artifacts.get("eide_project", []),
            "make": artifacts.get("makefile", []),
        },
        "startup_files": artifacts.get("startup_file", []),
        "linker_scripts": artifacts.get("linker_script", []),
        "peripherals": primary_ioc.get("peripherals", []),
        "middleware": primary_ioc.get("middleware", []),
        "diagnostics": firmware_diagnostics(scan_data, primary_ioc),
    }


def build_board_profile(scan_data: dict[str, Any], ioc_summaries: list[dict[str, Any]]) -> dict[str, Any]:
    primary_ioc = ioc_summaries[0] if ioc_summaries else {}
    artifacts = scan_data.get("artifacts", {})
    return {
        "schema_version": 1,
        "source": "hardware_butler_inspect",
        "mcu": primary_ioc.get("mcu", {}),
        "evidence": {
            "schematics": artifacts.get("schematic", []),
            "pcb": artifacts.get("pcb", []),
            "bom": artifacts.get("bom", []),
            "datasheets": artifacts.get("datasheet", []),
            "manuals": artifacts.get("manual", []),
            "cubemx_ioc": artifacts.get("cubemx_ioc", []),
        },
        "interfaces_from_ioc": primary_ioc.get("peripherals", []),
        "pins_from_ioc": primary_ioc.get("pins", {}),
        "risks": board_risks(scan_data, primary_ioc),
    }


def firmware_diagnostics(scan_data: dict[str, Any], ioc: dict[str, Any]) -> list[dict[str, str]]:
    diagnostics = []
    toolchains = scan_data["summary"]["toolchains"]
    declared_toolchain = ioc.get("project", {}).get("toolchain", "")
    if ioc and not toolchains:
        diagnostics.append(
            {
                "level": "warning",
                "code": "no_build_backend",
                "message": "CubeMX .ioc was found, but no Keil, CMake/GCC, EIDE, or Makefile build entry was detected.",
            }
        )
    if declared_toolchain and toolchains:
        diagnostics.append(
            {
                "level": "info",
                "code": "declared_toolchain",
                "message": f"CubeMX declares toolchain '{declared_toolchain}', detected backends: {', '.join(toolchains)}.",
            }
        )
    return diagnostics


def board_risks(scan_data: dict[str, Any], ioc: dict[str, Any]) -> list[dict[str, str]]:
    artifacts = scan_data.get("artifacts", {})
    risks = []
    if not artifacts.get("schematic"):
        risks.append(
            {
                "level": "medium",
                "code": "schematic_missing",
                "message": "No schematic candidate was detected; hardware pin and power assumptions must remain unverified.",
            }
        )
    if ioc and not ioc.get("mcu", {}).get("name"):
        risks.append(
            {
                "level": "medium",
                "code": "mcu_not_identified",
                "message": "A CubeMX .ioc exists, but the MCU name was not parsed.",
            }
        )
    return risks


def render_firmware_profile(profile: dict[str, Any]) -> str:
    mcu = profile.get("mcu", {})
    project = profile.get("cubemx_project", {})
    lines = [
        "# Firmware Profile",
        "",
        f"- Project type: {profile['project_type']}",
        f"- MCU: {mcu.get('name') or 'unknown'}",
        f"- Family: {mcu.get('family') or 'unknown'}",
        f"- CubeMX project: {project.get('name') or 'unknown'}",
        f"- CubeMX toolchain: {project.get('toolchain') or 'unknown'}",
        f"- Detected toolchains: {', '.join(profile['toolchains']) or 'none'}",
        "",
        "## Build Entries",
        "",
    ]
    for backend, entries in profile["build_entries"].items():
        lines.append(f"### {backend}")
        lines.append("")
        if entries:
            for entry in entries:
                lines.append(f"- `{entry['path']}`")
        else:
            lines.append("- none detected")
        lines.append("")
    lines.extend(["## Diagnostics", ""])
    if profile["diagnostics"]:
        for item in profile["diagnostics"]:
            lines.append(f"- [{item['level']}] {item['code']}: {item['message']}")
    else:
        lines.append("- no firmware diagnostics")
    lines.append("")
    return "\n".join(lines)


def render_board_profile(profile: dict[str, Any]) -> str:
    mcu = profile.get("mcu", {})
    lines = [
        "# Board Profile",
        "",
        f"- MCU: {mcu.get('name') or 'unknown'}",
        f"- Family: {mcu.get('family') or 'unknown'}",
        f"- Package: {mcu.get('package') or 'unknown'}",
        "",
        "## Evidence",
        "",
    ]
    for label, items in profile["evidence"].items():
        lines.append(f"### {label}")
        lines.append("")
        if items:
            for item in items[:20]:
                lines.append(f"- `{item['path']}`")
        else:
            lines.append("- none detected")
        lines.append("")
    lines.extend(["## Risks", ""])
    if profile["risks"]:
        for item in profile["risks"]:
            lines.append(f"- [{item['level']}] {item['code']}: {item['message']}")
    else:
        lines.append("- no initial board risks")
    lines.append("")
    return "\n".join(lines)


def ensure_log_files(out_dir: Path) -> None:
    issues = out_dir / "issues.md"
    if not issues.exists():
        write_text(issues, "# Issues\n\nNo issues recorded yet.\n")
    logbook = out_dir / "debug-logbook.md"
    if not logbook.exists():
        write_text(logbook, "# Debug Logbook\n\nNo debug attempts recorded yet.\n")


def write_json(path: Path, data: dict[str, Any]) -> None:
    safe_io.safe_write_text(
        path,
        json.dumps(data, ensure_ascii=False, indent=2),
        allowed_roots=runtime_context.allowed_write_roots(),
    )


def write_text(path: Path, content: str) -> None:
    safe_io.safe_write_text(path, content, allowed_roots=runtime_context.allowed_write_roots())


def main() -> None:
    parser = argparse.ArgumentParser(description="Run hardware butler project inspection")
    parser.add_argument("--root", default=".", help="Project root to inspect")
    parser.add_argument("--out-dir", default="", help="Output docs directory; default is <root>/docs")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()

    root = Path(args.root)
    out_dir = Path(args.out_dir) if args.out_dir else root / "docs"
    result = inspect_project(root, out_dir)
    if args.as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Inspection written to {result['out_dir']}")
        print(f"CubeMX projects: {result['summary']['cubemx_projects']}")
        print(f"Toolchains: {', '.join(result['summary']['toolchains']) or 'none'}")
        print("Next actions:")
        for action in result["next_actions"]:
            print(f"- {action}")


if __name__ == "__main__":
    main()
