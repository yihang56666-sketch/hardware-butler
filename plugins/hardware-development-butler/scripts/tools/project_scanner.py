"""Scan a hardware firmware workspace and emit a project dossier.

This script is intentionally read-only. It inventories common hardware
development artifacts and produces JSON or Markdown that a butler agent can use
as the first source of truth before build/flash/debug work starts.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import runtime_context
import safe_io

EXCLUDE_DIRS = {
    ".git",
    ".svn",
    ".hg",
    ".vscode",
    ".idea",
    "__pycache__",
    "node_modules",
    "build",
    "cmake-build-debug",
    "cmake-build-release",
    "Debug",
    "Release",
}

EXACT_NAME_MARKERS = {
    "cmakelists.txt", "cmakepresets.json", "eide.yml", "makefile",
}

ARTIFACT_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("cubemx_ioc", (".ioc",)),
    ("keil_project", (".uvprojx", ".uvmpw")),
    ("cmake_project", ("CMakeLists.txt", "CMakePresets.json")),
    ("eide_project", ("eide.yml",)),
    ("makefile", ("Makefile", "makefile")),
    ("linker_script", (".ld", ".sct", ".icf")),
    ("startup_file", ("startup_",)),
    ("schematic", (".sch", ".kicad_sch", ".dsn", "schematic", "circuit", "原理图")),
    ("pcb", (".kicad_pcb", ".brd", ".pcbdoc")),
    ("bom", ("bom", "bill of materials", "bill-of-materials", "物料清单")),
    ("datasheet", ("datasheet", "data sheet", "DataSheet", "DS_", "数据手册")),
    ("manual", ("manual", "user manual", "reference manual", "programming manual", "用户手册")),
    ("build_log", ("build.log", "compile.log", "make.log")),
    ("debug_log", ("debug.log", "serial.log", "rtt.log", "swo.log")),
]


def should_skip(path: Path) -> bool:
    return any(part in EXCLUDE_DIRS for part in path.parts)


def is_project_file(root: Path, path: Path) -> bool:
    try:
        return path.resolve().is_relative_to(root.resolve()) and path.is_file()
    except (OSError, RuntimeError):
        return False


def classify_file(path: Path) -> set[str]:
    name = path.name
    lower_name = name.lower()
    suffix = path.suffix.lower()
    labels: set[str] = set()

    for label, markers in ARTIFACT_RULES:
        for marker in markers:
            marker_lower = marker.lower()
            if marker.startswith("."):
                if suffix == marker_lower:
                    labels.add(label)
            elif marker_lower in EXACT_NAME_MARKERS:
                if lower_name == marker_lower:
                    labels.add(label)
            elif marker_lower in lower_name:
                labels.add(label)
    if path.parent.name == ".eide" and name == "eide.yml":
        labels.add("eide_project")
    if suffix in {".csv", ".xlsx"} and (
        "bom" in lower_name or "bill" in lower_name or "materials" in lower_name or "物料" in name
    ):
        labels.add("bom")
    if suffix == ".pdf":
        classify_pdf_by_name(name, lower_name, labels)
    return labels


def classify_pdf_by_name(name: str, lower_name: str, labels: set[str]) -> None:
    """Avoid treating every PDF as every hardware document type."""
    if any(marker in lower_name for marker in ("schematic", "circuit", "sch")) or "原理图" in name:
        labels.add("schematic")
    if any(marker in lower_name for marker in ("datasheet", "data sheet", "ds_", "spec")) or "数据手册" in name:
        labels.add("datasheet")
    if any(marker in lower_name for marker in ("manual", "user guide", "reference manual", "programming manual")) or "手册" in name:
        labels.add("manual")


def scan(root: Path) -> dict[str, Any]:
    root = root.resolve()
    if not root.is_dir():
        raise ValueError(f"Project root must be an existing directory: {root}")
    artifacts: dict[str, list[dict[str, Any]]] = defaultdict(list)
    extensions: dict[str, int] = defaultdict(int)
    total_files = 0

    for path in root.rglob("*"):
        if should_skip(path.relative_to(root)):
            continue
        if not is_project_file(root, path):
            continue
        total_files += 1
        if path.suffix:
            extensions[path.suffix.lower()] += 1
        labels = classify_file(path)
        for label in labels:
            try:
                size = path.stat().st_size
            except OSError:
                size = 0
            artifacts[label].append(
                {
                    "path": str(path.relative_to(root)),
                    "size_bytes": size,
                }
            )

    toolchains = []
    if artifacts.get("keil_project"):
        toolchains.append("keil")
    if artifacts.get("cmake_project"):
        toolchains.append("cmake-gcc")
    if artifacts.get("eide_project"):
        toolchains.append("eide")
    if artifacts.get("makefile"):
        toolchains.append("make")

    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "root": str(root),
        "summary": {
            "total_files": total_files,
            "toolchains": sorted(set(toolchains)),
            "has_cubemx": bool(artifacts.get("cubemx_ioc")),
            "has_schematic_candidates": bool(artifacts.get("schematic")),
            "has_logs": bool(artifacts.get("build_log") or artifacts.get("debug_log")),
        },
        "artifacts": {key: value for key, value in sorted(artifacts.items())},
        "extension_counts": dict(sorted(extensions.items())),
        "recommended_next_steps": recommend_next_steps(artifacts),
    }


def recommend_next_steps(artifacts: dict[str, list[dict[str, Any]]]) -> list[str]:
    steps = []
    if artifacts.get("cubemx_ioc"):
        steps.append("Run tools/cubemx_ioc_summary.py on the .ioc file.")
    if artifacts.get("keil_project") or artifacts.get("cmake_project") or artifacts.get("eide_project"):
        steps.append("Choose a build backend and run the matching embeddedskills scanner.")
    if artifacts.get("build_log"):
        steps.append("Run tools/build_log_classifier.py on the build log.")
    if artifacts.get("schematic"):
        steps.append("Create or update docs/board-profile.md from schematic/manual evidence.")
    if not steps:
        steps.append("Add schematic, manual, CubeMX .ioc, firmware project, or logs for deeper analysis.")
    return steps


def render_markdown(data: dict[str, Any]) -> str:
    lines = [
        "# Project Dossier",
        "",
        f"- Root: `{data['root']}`",
        f"- Generated: `{data['generated_at']}`",
        f"- Total files scanned: {data['summary']['total_files']}",
        f"- Toolchains: {', '.join(data['summary']['toolchains']) or 'none detected'}",
        f"- CubeMX project: {'yes' if data['summary']['has_cubemx'] else 'no'}",
        f"- Schematic candidates: {'yes' if data['summary']['has_schematic_candidates'] else 'no'}",
        "",
        "## Artifacts",
        "",
    ]
    for label, items in data["artifacts"].items():
        lines.append(f"### {label}")
        lines.append("")
        for item in items[:30]:
            lines.append(f"- `{item['path']}` ({item['size_bytes']} bytes)")
        if len(items) > 30:
            lines.append(f"- ... {len(items) - 30} more")
        lines.append("")
    lines.extend(["## Recommended Next Steps", ""])
    for step in data["recommended_next_steps"]:
        lines.append(f"- {step}")
    lines.append("")
    return "\n".join(lines)


def write_output(path: Path, content: str) -> str:
    written: str = safe_io.safe_write_text(path, content, allowed_roots=runtime_context.allowed_write_roots())
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description="Scan a hardware development project")
    parser.add_argument("--root", default=".", help="Project root to scan")
    parser.add_argument("--json", action="store_true", dest="as_json", help="Emit JSON")
    parser.add_argument("--markdown", action="store_true", help="Emit Markdown")
    parser.add_argument("--out", default="", help="Optional output file")
    args = parser.parse_args()

    data = scan(Path(args.root))
    content = json.dumps(data, ensure_ascii=False, indent=2) if args.as_json and not args.markdown else render_markdown(data)

    if args.out:
        write_output(Path(args.out), content)
    else:
        print(content)


if __name__ == "__main__":
    main()
