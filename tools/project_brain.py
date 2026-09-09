"""Project brain model for the hardware development copilot."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cubemx_ioc_summary
import evidence_index
import hardware_risk
import project_scanner
import runtime_context
import safe_io

BRAIN_DIR = ".hardware-butler"
BRAIN_FILE = "project-brain.json"

HEALTH_CATEGORIES = [
    ("schematic", "Schematic", "Board connections, power tree, reset, boot, debug, and interfaces", True),
    ("pcb", "PCB", "Layout and routing evidence", False),
    ("bom", "BOM", "Component identity, substitutions, lifecycle, and purchasing risk", True),
    ("datasheet", "Datasheet", "Chip and component electrical limits", True),
    ("manual", "Reference/User Manual", "Peripheral, board, boot, and programming behavior", True),
    ("cubemx_ioc", "CubeMX IOC", "MCU, clocks, pinmux, middleware, and firmware package settings", False),
    ("firmware", "Firmware Project", "Build entry, startup file, linker script, and app source evidence", True),
    ("logs", "Logs", "Build/debug/serial/RTT observations", False),
]


def project_brain_path(root: Path) -> Path:
    return root.resolve() / BRAIN_DIR / BRAIN_FILE


def build_project_brain(root: Path, *, write: bool = True) -> dict[str, Any]:
    root = root.resolve()
    scan = project_scanner.scan(root)
    ioc_summaries = summarize_iocs(root, scan)
    index = evidence_index.build_evidence_index(root, scan_data=scan, write=write)
    risks = hardware_risk.analyze_risks(root, scan_data=scan, evidence_index=index)
    health = build_evidence_health(scan, index)
    missing = missing_evidence(health)
    brain = {
        "schema_version": 1,
        "app": "hardware-project-brain",
        "status": brain_status(missing, risks),
        "root": str(root),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "identity": build_identity(root, scan, ioc_summaries),
        "evidence_health": health,
        "missing_evidence": missing,
        "risk_snapshot": risks,
        "recommended_tasks": recommended_tasks(root, missing, risks, ioc_summaries),
        "evidence_index": {
            "path": index["index_path"],
            "item_count": index["summary"]["total_items"],
            "summary": index["summary"],
            "items": index["items"],
        },
        "written": {
            "project_brain": str(project_brain_path(root)) if write else "",
            "evidence_index": index["index_path"] if write else "",
        },
    }
    if write:
        safe_io.safe_write_text(
            project_brain_path(root),
            json.dumps(brain, ensure_ascii=False, indent=2) + "\n",
            allowed_roots=runtime_context.allowed_write_roots(root),
        )
    return brain


def summarize_iocs(root: Path, scan_data: dict[str, Any]) -> list[dict[str, Any]]:
    summaries = []
    for item in scan_data.get("artifacts", {}).get("cubemx_ioc", []):
        if not isinstance(item, dict):
            continue
        rel_path = str(item.get("path") or "")
        if not rel_path or not project_scanner.is_project_file(root, root / rel_path):
            continue
        try:
            summaries.append(cubemx_ioc_summary.summarize(root / rel_path))
        except OSError as exc:
            summaries.append({"ioc_file": str(root / rel_path), "error": str(exc)})
    return summaries


def build_identity(root: Path, scan_data: dict[str, Any], ioc_summaries: list[dict[str, Any]]) -> dict[str, Any]:
    artifacts = scan_data.get("artifacts", {}) if isinstance(scan_data.get("artifacts"), dict) else {}
    primary_ioc = ioc_summaries[0] if ioc_summaries else {}
    mcu = primary_ioc.get("mcu", {}) if isinstance(primary_ioc.get("mcu"), dict) else {}
    project = primary_ioc.get("project", {}) if isinstance(primary_ioc.get("project"), dict) else {}
    return {
        "project_name": project.get("name") or root.name,
        "root": str(root),
        "mcu": {
            "name": mcu.get("name") or "unknown",
            "family": mcu.get("family") or "unknown",
            "package": mcu.get("package") or "unknown",
            "line": mcu.get("line") or "unknown",
        },
        "cubemx_projects": [str(item.get("path", "")) for item in artifacts.get("cubemx_ioc", []) if isinstance(item, dict)],
        "project_files": {
            "keil": [str(item.get("path", "")) for item in artifacts.get("keil_project", []) if isinstance(item, dict)],
            "cmake": [str(item.get("path", "")) for item in artifacts.get("cmake_project", []) if isinstance(item, dict)],
            "eide": [str(item.get("path", "")) for item in artifacts.get("eide_project", []) if isinstance(item, dict)],
            "make": [str(item.get("path", "")) for item in artifacts.get("makefile", []) if isinstance(item, dict)],
        },
        "toolchains": scan_data.get("summary", {}).get("toolchains", []),
    }


def build_evidence_health(scan_data: dict[str, Any], index: dict[str, Any]) -> dict[str, Any]:
    artifacts = scan_data.get("artifacts", {}) if isinstance(scan_data.get("artifacts"), dict) else {}
    by_kind = index.get("summary", {}).get("by_kind", {}) if isinstance(index.get("summary"), dict) else {}
    categories = []
    for category_id, title, role, required in HEALTH_CATEGORIES:
        count = evidence_count(category_id, artifacts, by_kind)
        categories.append(
            {
                "id": category_id,
                "title": title,
                "role": role,
                "required": required,
                "count": count,
                "status": "present" if count else ("missing" if required else "optional-missing"),
                "source": "project_scanner+evidence_index",
            }
        )
    required_items = [item for item in categories if item["required"]]
    present_required = [item for item in required_items if item["status"] == "present"]
    return {
        "summary": {
            "required_present": len(present_required),
            "required_total": len(required_items),
            "coverage_percent": round((len(present_required) / len(required_items)) * 100, 1) if required_items else 100.0,
            "indexed_items": index.get("summary", {}).get("total_items", 0),
        },
        "categories": categories,
    }


def evidence_count(category_id: str, artifacts: dict[str, Any], by_kind: dict[str, Any]) -> int:
    if category_id == "firmware":
        labels = ("keil_project", "cmake_project", "eide_project", "makefile", "startup_file", "linker_script")
        return sum(len(artifacts.get(label, [])) for label in labels)
    if category_id == "logs":
        return len(artifacts.get("build_log", [])) + len(artifacts.get("debug_log", []))
    if category_id == "datasheet":
        return int(by_kind.get("datasheet", 0) or len(artifacts.get("datasheet", [])))
    if category_id == "manual":
        return int(by_kind.get("manual", 0) or len(artifacts.get("manual", []))) + int(by_kind.get("manual_summary", 0) or 0)
    return int(by_kind.get(category_id, 0) or len(artifacts.get(category_id, [])))


def missing_evidence(health: dict[str, Any]) -> list[dict[str, Any]]:
    missing = []
    for category in health.get("categories", []):
        if not isinstance(category, dict) or not category.get("required") or category.get("status") != "missing":
            continue
        missing.append(
            {
                "id": category.get("id", "unknown"),
                "title": category.get("title", "unknown"),
                "reason": f"{category.get('title', 'Evidence')} is required for reliable hardware bring-up but was not found.",
                "next_safe_action": missing_next_action(str(category.get("id", ""))),
                "citations": [{"path": "unknown", "line": "unknown", "note": "required evidence is missing"}],
            }
        )
    return missing


def missing_next_action(category_id: str) -> str:
    actions = {
        "schematic": "Add the schematic or create docs/board-profile.md from verified board evidence.",
        "bom": "Add a BOM export or key-component list with part numbers and voltage/domain notes.",
        "datasheet": "Run chip-dossier for the detected MCU or add official datasheet PDFs.",
        "manual": "Add the reference manual, programming manual, board manual, or generated manual summary.",
        "firmware": "Add or locate the firmware build entry, startup file, and linker script.",
    }
    return actions.get(category_id, "Add verified local evidence and rerun project brain.")


def brain_status(missing: list[dict[str, Any]], risks: dict[str, Any]) -> str:
    high_risk = any(item.get("severity") in {"critical", "high"} for item in risks.get("risks", []))
    if high_risk:
        return "needs-risk-review"
    if missing:
        return "needs-evidence"
    if risks.get("risks"):
        return "ready-with-warnings"
    return "ready-for-task-planning"


def recommended_tasks(
    root: Path,
    missing: list[dict[str, Any]],
    risks: dict[str, Any],
    ioc_summaries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    del root
    tasks = []
    missing_ids = {str(item.get("id", "")) for item in missing}
    primary_part = detected_part(ioc_summaries)
    if {"schematic", "bom"} & missing_ids:
        tasks.append(
            task(
                "collect-board-evidence",
                "Collect board evidence",
                "Schematic or BOM evidence is missing, so board-level claims must stay unverified.",
                ["Add schematic/BOM files, then run python tools/hardware_butler.py brain --root <project> --json"],
            )
        )
    if {"datasheet", "manual"} & missing_ids:
        command = (
            f"python tools/hardware_butler.py chip-dossier --part {primary_part} --api-search --download --json"
            if primary_part
            else "python tools/hardware_butler.py chip-dossier --part <chip> --api-search --download --json"
        )
        tasks.append(
            task(
                "collect-chip-documents",
                "Collect chip documents",
                "Datasheet or reference manual evidence is missing.",
                [command],
            )
        )
    if risks.get("summary", {}).get("total", 0):
        tasks.append(
            task(
                "review-risk-snapshot",
                "Review risk snapshot",
                "Resolve high and medium risks before changing pins or touching hardware.",
                ["python tools/hardware_butler.py brain --root <project> --json"],
            )
        )
    tasks.append(
        task(
            "prepare-bringup-checklist",
            "Prepare bring-up checklist",
            "Use the current evidence map to plan safe bench steps before build/flash/debug.",
            ["python tools/hardware_butler.py bench-runbook --root <project> --action build-flash --json"],
        )
    )
    return tasks


def task(task_id: str, title: str, reason: str, commands: list[str]) -> dict[str, Any]:
    return {
        "id": task_id,
        "title": title,
        "reason": reason,
        "commands": commands,
        "safe_by_default": True,
        "touches_hardware": False,
    }


def detected_part(ioc_summaries: list[dict[str, Any]]) -> str:
    if not ioc_summaries:
        return ""
    mcu = ioc_summaries[0].get("mcu", {})
    if not isinstance(mcu, dict):
        return ""
    part = str(mcu.get("name") or "")
    return "" if part == "unknown" else part


def render_markdown(brain: dict[str, Any]) -> str:
    identity = brain.get("identity", {}) if isinstance(brain.get("identity"), dict) else {}
    mcu = identity.get("mcu", {}) if isinstance(identity.get("mcu"), dict) else {}
    health = brain.get("evidence_health", {}) if isinstance(brain.get("evidence_health"), dict) else {}
    health_summary = health.get("summary", {}) if isinstance(health.get("summary"), dict) else {}
    risks = brain.get("risk_snapshot", {}) if isinstance(brain.get("risk_snapshot"), dict) else {}
    lines = [
        "# Project Brain",
        "",
        f"- Root: `{brain.get('root', '')}`",
        f"- Status: `{brain.get('status', 'unknown')}`",
        f"- Project: {identity.get('project_name', 'unknown')}",
        f"- MCU: {mcu.get('name', 'unknown')} / {mcu.get('package', 'unknown')}",
        f"- Evidence coverage: {health_summary.get('required_present', 0)}/{health_summary.get('required_total', 0)} required ({health_summary.get('coverage_percent', 0)}%)",
        f"- Indexed evidence: {health_summary.get('indexed_items', 0)} items",
        f"- Risks: {risks.get('summary', {}).get('total', 0)}",
        "",
        "## Missing Evidence",
        "",
    ]
    missing = brain.get("missing_evidence", [])
    if missing:
        for item in missing:
            lines.append(f"- `{item.get('id', 'unknown')}`: {item.get('next_safe_action', '')}")
    else:
        lines.append("- none")
    lines.extend(["", "## Risk Snapshot", ""])
    risk_items = risks.get("risks", []) if isinstance(risks.get("risks"), list) else []
    if risk_items:
        for item in risk_items:
            lines.append(f"- [{item.get('severity', 'unknown')}] {item.get('category', 'unknown')}: {item.get('message', '')}")
    else:
        lines.append("- no deterministic risks")
    lines.extend(["", "## Recommended Tasks", ""])
    for item in brain.get("recommended_tasks", []):
        lines.append(f"- `{item.get('id', 'unknown')}`: {item.get('reason', '')}")
    lines.append("")
    return "\n".join(lines)
