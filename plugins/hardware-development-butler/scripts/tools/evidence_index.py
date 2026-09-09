"""Build a local evidence index for a hardware project.

The index is deliberately conservative: it records file-level evidence and
short summaries, but it does not infer electrical facts from filenames.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import project_scanner
import runtime_context
import safe_io

INDEX_DIR = ".hardware-butler"
INDEX_FILE = "evidence-index.json"

INDEXED_ARTIFACTS = {
    "schematic": "schematic",
    "pcb": "pcb",
    "bom": "bom",
    "datasheet": "datasheet",
    "manual": "manual",
    "cubemx_ioc": "cubemx_ioc",
    "build_log": "build_log",
    "debug_log": "debug_log",
}

EXTRA_PATTERNS = {
    "source_map": ("source-map.md",),
    "manual_summary": ("manual-summary.md",),
    "document_coverage": ("document-coverage.json", "document-coverage.md"),
    "chip_dossier": ("chip-dossier.json",),
}

SUMMARY_BY_KIND = {
    "schematic": "Schematic candidate; use it to verify power, reset, boot, debug, and connector wiring.",
    "pcb": "PCB/layout candidate; use it to verify routing, placement, and physical constraints.",
    "bom": "BOM candidate; use it to verify component identity, substitutions, lifecycle, and purchasing risk.",
    "datasheet": "Datasheet candidate; extract electrical limits and package facts before using parameters.",
    "manual": "Manual candidate; extract reference, user, or programming details before using parameters.",
    "cubemx_ioc": "STM32CubeMX IOC file; parse it for MCU identity, pin assignments, clocks, and middleware.",
    "build_log": "Build log; classify it before changing project files or build settings.",
    "debug_log": "Debug/serial/RTT/SWO log; use it as observed runtime evidence.",
    "source_map": "Chip dossier source map; use it to trace downloaded or referenced document provenance.",
    "manual_summary": "Manual summary generated from document evidence; unknown sections should remain explicit.",
    "document_coverage": "Document coverage report; use it to see which required chip documents are missing.",
    "chip_dossier": "Machine-readable chip dossier; use it to inspect source quality, downloads, and coverage.",
}


def evidence_index_path(root: Path) -> Path:
    return root.resolve() / INDEX_DIR / INDEX_FILE


def build_evidence_index(
    root: Path,
    *,
    scan_data: dict[str, Any] | None = None,
    write: bool = True,
) -> dict[str, Any]:
    root = root.resolve()
    scan = scan_data or project_scanner.scan(root)
    items = artifact_items(root, scan)
    items.extend(extra_evidence_items(root))
    items.sort(key=lambda item: (kind_order(str(item["kind"])), str(item["path"]).lower()))

    index = {
        "schema_version": 1,
        "status": "ok",
        "root": str(root),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "index_path": str(evidence_index_path(root)),
        "items": items,
        "summary": summarize_items(items),
    }
    if write:
        safe_io.safe_write_text(
            evidence_index_path(root),
            json.dumps(index, ensure_ascii=False, indent=2) + "\n",
            allowed_roots=runtime_context.allowed_write_roots(root),
        )
    return index


def artifact_items(root: Path, scan_data: dict[str, Any]) -> list[dict[str, Any]]:
    artifacts = scan_data.get("artifacts", {})
    rows: list[dict[str, Any]] = []
    if not isinstance(artifacts, dict):
        return rows
    for artifact_label, kind in INDEXED_ARTIFACTS.items():
        raw_items = artifacts.get(artifact_label, [])
        if not isinstance(raw_items, list):
            continue
        for raw_item in raw_items:
            if not isinstance(raw_item, dict):
                continue
            rel_path = str(raw_item.get("path") or "")
            if not rel_path or not project_scanner.is_project_file(root, root / rel_path):
                continue
            rows.append(evidence_item(root, rel_path, kind, int(raw_item.get("size_bytes", 0) or 0)))
    return rows


def extra_evidence_items(root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in root.rglob("*"):
        if project_scanner.should_skip(path.relative_to(root)) or not project_scanner.is_project_file(root, path):
            continue
        rel_path = path.relative_to(root).as_posix()
        kind = extra_kind(path.name)
        if not kind:
            continue
        rows.append(evidence_item(root, rel_path, kind, safe_size(path)))
    return rows


def evidence_item(root: Path, rel_path: str, kind: str, size_bytes: int) -> dict[str, Any]:
    path = root / rel_path
    return {
        "path": rel_path,
        "kind": kind,
        "source_quality": source_quality(path, kind),
        "summary": SUMMARY_BY_KIND.get(kind, "unknown"),
        "citations": file_citations(rel_path, kind),
        "size_bytes": size_bytes,
    }


def extra_kind(name: str) -> str:
    lower_name = name.lower()
    for kind, markers in EXTRA_PATTERNS.items():
        if lower_name in markers:
            return kind
    return ""


def source_quality(path: Path, kind: str) -> str:
    rel = path.as_posix().lower()
    name = path.name.lower()
    if kind in {"schematic", "pcb", "bom", "cubemx_ioc", "build_log", "debug_log"}:
        return "local-project"
    if "source-map" in name or "chip-dossier" in name or "document-coverage" in name:
        return "generated"
    if any(marker in rel for marker in ("st.com", "stmicroelectronics", "ti.com", "nxp.com", "infineon", "microchip")):
        return "official"
    return "unknown"


def file_citations(rel_path: str, kind: str) -> list[dict[str, Any]]:
    return [
        {
            "path": rel_path,
            "line": "unknown",
            "note": f"file-level {kind} evidence",
        }
    ]


def summarize_items(items: list[dict[str, Any]]) -> dict[str, Any]:
    by_kind: dict[str, int] = {}
    by_quality: dict[str, int] = {}
    for item in items:
        kind = str(item.get("kind", "unknown") or "unknown")
        quality = str(item.get("source_quality", "unknown") or "unknown")
        by_kind[kind] = by_kind.get(kind, 0) + 1
        by_quality[quality] = by_quality.get(quality, 0) + 1
    return {
        "total_items": len(items),
        "by_kind": dict(sorted(by_kind.items())),
        "by_source_quality": dict(sorted(by_quality.items())),
    }


def kind_order(kind: str) -> int:
    order = {
        "schematic": 0,
        "pcb": 1,
        "bom": 2,
        "datasheet": 3,
        "manual": 4,
        "source_map": 5,
        "manual_summary": 6,
        "document_coverage": 7,
        "chip_dossier": 8,
        "cubemx_ioc": 9,
        "build_log": 10,
        "debug_log": 11,
    }
    return order.get(kind, 99)


def safe_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0
