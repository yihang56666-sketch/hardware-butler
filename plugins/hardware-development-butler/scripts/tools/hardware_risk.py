"""Deterministic hardware project risk checks.

These checks flag missing or unsafe evidence states. They do not claim that a
board is electrically safe; they point to the next evidence needed to verify it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import project_scanner

RISK_CATEGORIES = ("power", "clock", "reset", "boot", "debug", "pinmux", "build", "documentation")
SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


def analyze_risks(
    root: Path,
    *,
    scan_data: dict[str, Any] | None = None,
    evidence_index: dict[str, Any] | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    scan = scan_data or project_scanner.scan(root)
    artifacts = scan.get("artifacts", {}) if isinstance(scan.get("artifacts"), dict) else {}
    index_summary = (evidence_index or {}).get("summary", {}) if isinstance(evidence_index, dict) else {}
    by_kind = index_summary.get("by_kind", {}) if isinstance(index_summary.get("by_kind"), dict) else {}
    risks: list[dict[str, Any]] = []

    if not artifacts.get("schematic"):
        risks.extend(
            [
                risk(
                    "schematic_missing_power",
                    "high",
                    "power",
                    "No schematic candidate was found, so the power tree and voltage domains are unverified.",
                    "Add the board schematic or a board-profile with power-tree evidence before enabling outputs or powering external loads.",
                    evidence_refs(artifacts, "schematic"),
                ),
                risk(
                    "schematic_missing_reset_boot_debug",
                    "medium",
                    "reset",
                    "No schematic candidate was found, so reset, BOOT, and debug wiring remain unverified.",
                    "Collect schematic evidence for NRST, BOOT pins, SWD/JTAG, pull-ups, and connector pinout.",
                    evidence_refs(artifacts, "schematic"),
                ),
            ]
        )

    if not artifacts.get("bom"):
        risks.append(
            risk(
                "bom_missing",
                "medium",
                "documentation",
                "No BOM candidate was found, so component identity, substitutions, and lifecycle risks are unknown.",
                "Add a BOM export or key-component list before making replacement or purchasing decisions.",
                evidence_refs(artifacts, "bom"),
            )
        )

    has_chip_doc = bool(
        artifacts.get("datasheet")
        or artifacts.get("manual")
        or by_kind.get("datasheet")
        or by_kind.get("manual")
        or by_kind.get("manual_summary")
    )
    if not has_chip_doc:
        risks.append(
            risk(
                "chip_documents_missing",
                "medium",
                "documentation",
                "No datasheet or reference manual candidate was found, so MCU electrical limits and peripheral details are unknown.",
                "Run chip-dossier with official sources or add datasheet/reference manual PDFs under docs/chip/<part>/documents.",
                evidence_refs(artifacts, "datasheet") + evidence_refs(artifacts, "manual"),
            )
        )

    has_ioc = bool(artifacts.get("cubemx_ioc"))
    has_board_evidence = bool(artifacts.get("schematic") or artifacts.get("bom") or artifacts.get("manual"))
    if has_ioc and not has_board_evidence:
        risks.append(
            risk(
                "cubemx_without_board_evidence",
                "medium",
                "pinmux",
                "CubeMX configuration exists, but no board-level schematic/BOM/manual evidence was found.",
                "Before changing pins, verify the pin against schematic connections, voltage domain, pull-ups, and external loads.",
                evidence_refs(artifacts, "cubemx_ioc"),
            )
        )

    try:
        config = read_project_config(root)
    except (OSError, ValueError) as exc:
        config = {}
        risks.append(
            risk(
                "project_config_invalid",
                "high",
                "debug",
                f"Project configuration could not be validated: {exc}",
                "Repair .embeddedskills/config.json and rerun the risk review before hardware-facing actions.",
                [{"path": ".embeddedskills/config.json", "line": "unknown", "note": "invalid or unreadable configuration"}],
            )
        )
    auto_preferences = auto_hardware_preferences(config)
    if auto_preferences:
        risks.append(
            risk(
                "auto_hardware_backend_preferences",
                "high",
                "debug",
                f"Hardware backend preferences are set to auto: {', '.join(auto_preferences)}.",
                "Set explicit flash/debug/observe backends and generate a bench-runbook before any hardware-facing action.",
                [{"path": ".embeddedskills/config.json", "line": "unknown", "note": "workflow hardware backend preference"}],
            )
        )

    selected_toolchains = scan.get("summary", {}).get("toolchains", [])
    if has_ioc and not selected_toolchains:
        risks.append(
            risk(
                "build_backend_missing",
                "medium",
                "build",
                "CubeMX project exists, but no Keil, CMake/GCC, EIDE, or Makefile build entry was detected.",
                "Add or locate the build project before attempting firmware changes that need compilation evidence.",
                evidence_refs(artifacts, "cubemx_ioc"),
            )
        )

    risks.sort(key=lambda item: (SEVERITY_ORDER.get(str(item["severity"]), 99), str(item["id"])))
    return {
        "schema_version": 1,
        "status": "ok" if not risks else "risks-found",
        "root": str(root),
        "categories": list(RISK_CATEGORIES),
        "summary": summarize_risks(risks),
        "risks": risks,
    }


def risk(
    risk_id: str,
    severity: str,
    category: str,
    message: str,
    next_check: str,
    evidence: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "id": risk_id,
        "severity": severity,
        "category": category,
        "message": message,
        "next_safe_check": next_check,
        "evidence": evidence or [{"path": "unknown", "line": "unknown", "note": "required evidence is missing"}],
    }


def evidence_refs(artifacts: dict[str, Any], label: str) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    items = artifacts.get(label, []) if isinstance(artifacts, dict) else []
    if not isinstance(items, list):
        return refs
    for item in items[:5]:
        if not isinstance(item, dict):
            continue
        refs.append({"path": str(item.get("path") or "unknown"), "line": "unknown", "note": f"{label} candidate"})
    return refs


def summarize_risks(risks: list[dict[str, Any]]) -> dict[str, Any]:
    by_severity: dict[str, int] = {}
    by_category: dict[str, int] = {category: 0 for category in RISK_CATEGORIES}
    for item in risks:
        severity = str(item.get("severity", "unknown") or "unknown")
        category = str(item.get("category", "documentation") or "documentation")
        by_severity[severity] = by_severity.get(severity, 0) + 1
        by_category[category] = by_category.get(category, 0) + 1
    return {
        "total": len(risks),
        "by_severity": dict(sorted(by_severity.items())),
        "by_category": by_category,
    }


def read_project_config(root: Path) -> dict[str, Any]:
    path = root / ".embeddedskills" / "config.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("project configuration must be a JSON object")
    if "workflow" in data and not isinstance(data["workflow"], dict):
        raise ValueError("project configuration workflow must be a JSON object")
    return data


def auto_hardware_preferences(config: dict[str, Any]) -> list[str]:
    workflow = config.get("workflow", {}) if isinstance(config.get("workflow"), dict) else {}
    result = []
    for key in ("preferred_flash", "preferred_debug", "preferred_observe"):
        if workflow.get(key) == "auto":
            result.append(key)
    return result
