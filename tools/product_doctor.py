"""Product-grade capability, doctor, and project status reports.

This module is intentionally read-only. It checks local files, Python runtime,
optional tool executables, project metadata, and safety policy state without
running build, flash, debug, bus, or network actions.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import command_runner  # noqa: E402
import cube_detect  # noqa: E402
import runtime_context  # noqa: E402

REPO_ROOT = runtime_context.PACKAGE_ROOT


CORE_FILES = [
    "tools/hardware_butler.py",
    "tools/runtime_context.py",
    "tools/product_doctor.py",
    "tools/project_workflow.py",
    "tools/project_brain.py",
    "tools/evidence_index.py",
    "tools/evidence_qa.py",
    "tools/hardware_risk.py",
    "tools/task_workflows.py",
    "tools/hardware_butler_inspect.py",
    "tools/cube_detect.py",
    "tools/build_plan.py",
    "tools/command_runner.py",
    "tools/config_proposal.py",
    "tools/build_log_classifier.py",
    "tools/bench_runbook.py",
    "tools/chip_dossier.py",
    "tools/document_search_api.py",
    "tools/document_providers.py",
    "tools/pin_capabilities.py",
    "tools/cubemx_config_advisor.py",
    "tools/firmware_intent_planner.py",
    "tools/firmware_code_patcher.py",
    "tools/hardware_action_plan.py",
    "tools/hardware_action_executor.py",
    "tools/hardware_action_audit.py",
    "tools/manual_summarizer.py",
    "tests/validate_hardware_butler.py",
]

EMBEDDEDSKILLS_FILES = [
    "embeddedskills/keil/scripts/keil_project.py",
    "embeddedskills/gcc/scripts/gcc_project.py",
    "embeddedskills/eide/scripts/eide_project.py",
    "embeddedskills/workflow/scripts/workflow_run.py",
    "embeddedskills/safety_gate.py",
    "embeddedskills/safety_cli.py",
    "embeddedskills/jlink/scripts/jlink_exec.py",
    "embeddedskills/openocd/scripts/openocd_run.py",
    "embeddedskills/probe-rs/scripts/probe_rs_exec.py",
    "embeddedskills/serial/scripts/serial_scan.py",
    "embeddedskills/can/scripts/can_scan.py",
    "embeddedskills/net/scripts/net_iface.py",
]

AGENT_FILES = [
    ".codex/config.toml",
    ".codex/agents/hardware-development-butler.toml",
    ".codex/agents/nextboard-hardware-architect.toml",
    ".codex/agents/embeddedskills-lab-operator.toml",
    "agents/hardware-development-butler.md",
    "agents/nextboard-hardware-architect.md",
    "agents/embeddedskills-lab-operator.md",
]

OPTIONAL_EXECUTABLES = [
    {"name": "Keil uVision", "executables": ["UV4.exe", "UV4"], "capability": "keil-build"},
    {"name": "CMake", "executables": ["cmake"], "capability": "cmake-gcc-build"},
    {"name": "Ninja", "executables": ["ninja"], "capability": "cmake-gcc-build"},
    {"name": "Arm GCC", "executables": ["arm-none-eabi-gcc"], "capability": "cmake-gcc-build"},
    {"name": "J-Link", "executables": ["JLink.exe", "JLinkExe"], "capability": "flash-debug"},
    {"name": "OpenOCD", "executables": ["openocd"], "capability": "flash-debug"},
    {"name": "probe-rs", "executables": ["probe-rs"], "capability": "flash-debug"},
]


def capabilities() -> dict[str, Any]:
    items = [
        cap("guide", "first-day-start-guide", "available", True, "python tools\\hardware_butler.py guide --root <project>", "prints the safe GUI/CLI first-day path without touching project files or hardware"),
        cap("onboard", "safe-onboarding", "available", True, "python tools\\hardware_butler.py onboard --root <project> --json", "writes reports and runs allowlisted discovery only"),
        cap("auto", "one-command-safe-workflow", "available", True, "python tools\\hardware_butler.py auto --root <project> --json", "runs safe onboarding when needed, writes .hardware-butler/project-state.json, and returns the next recommended action"),
        cap("next-step", "next-action-recommendation", "available", True, "python tools\\hardware_butler.py next-step --root <project> --json", "read-only project analysis plus project-state.json update; never touches hardware"),
        cap("workbench", "connected-ui-workbench", "available", True, "python tools\\hardware_butler.py workbench --root <project> --json", "one connected model for project status, safe actions, reports, next step, and UI state"),
        cap("brain", "project-brain", "available", True, "python tools\\hardware_butler.py brain --root <project> --json", "indexes local evidence, reports missing documents, and runs deterministic hardware risk checks without touching hardware"),
        cap("ask", "local-evidence-qa", "available", True, "python tools\\hardware_butler.py ask --root <project> --question \"PD12 接了什么\" --json", "answers only from local indexed evidence, CubeMX IOC, and project-brain risks; unknowns stay explicit"),
        cap("task", "intent-workflow-planner", "available", True, "python tools\\hardware_butler.py task --root <project> --intent prepare-bringup --json", "expands common hardware development intents into safe local commands without executing hardware actions"),
        cap("inspect", "project-dossier", "available", True, "python tools\\hardware_butler.py inspect --root <project>", "writes dossier reports"),
        cap("detect", "cubemx-backend-detection", "available", True, "python tools\\hardware_butler.py detect --root <project> --json", "read-only"),
        cap("plan-build", "build-plan-generation", "available", True, "python tools\\hardware_butler.py plan-build --root <project>", "no execution"),
        cap("run-plan", "safe-discovery-execution", "available", True, "python tools\\hardware_butler.py run-plan --root <project> --phase build-discovery --json", "hard allowlist only"),
        cap("propose-config", "embeddedskills-config-proposal", "available", True, "python tools\\hardware_butler.py propose-config --root <project> --target <target>", "dry-run by default"),
        cap("classify-log", "build-log-diagnosis", "available", True, "python tools\\hardware_butler.py classify-log <log> --json", "read-only"),
        cap("chip-dossier", "chip-document-dossier", "available-limited", True, "python tools\\hardware_butler.py chip-dossier --part <chip> --api-search --download", "uses configured search APIs, built-in vendor hints, or supplied sources, validates PDFs, extracts text, and writes evidence summaries; arbitrary vendor portals remain best-effort"),
        cap("advise-pin", "cubemx-pin-configuration-advice", "available", True, "python tools\\hardware_butler.py advise-pin --root <project> --pin PD12 --function gpio-output --pin-evidence <pin-capabilities.json>", "read-only against firmware project; optional package pin evidence labels support as verified, contradicted, inferred, or unknown"),
        cap("patch-ioc", "cubemx-ioc-safe-patch", "available-limited", True, "python tools\\hardware_butler.py patch-ioc --root <project> --function i2c --instance I2C1 --scl PB6 --sda PB7", "dry-run by default; writes .ioc and backup only with --write --confirm-write; blocks debug/clock/occupied pins"),
        cap("firmware-plan", "freertos-firmware-implementation-plan", "available", True, "python tools\\hardware_butler.py firmware-plan --root <project> --feature sensor-read --pin PB7 --function i2c", "plan-only, no code edits"),
        cap("firmware-patch", "safe-app-layer-firmware-patch", "available-limited", True, "python tools\\hardware_butler.py firmware-patch --root <project> --feature led-blink --pin PD12 --function gpio-output", "dry-run by default; writes only app files and integration notes with --write --confirm-write"),
        cap("firmware-integrate", "cubemx-user-code-integration-patch", "available-limited", True, "python tools\\hardware_butler.py firmware-integrate --root <project> --feature led-blink --pin PD12 --function gpio-output", "dry-run by default; writes only CubeMX USER CODE blocks with --write --confirm-write after app module files exist"),
        cap("plan-action", "hardware-action-confirmation-plan", "available", True, "python tools\\hardware_butler.py plan-action --root <project> --action build-flash --target <chip>", "plan-only; emits parent/child tokens, artifact hash binding, and prepared workflow argv without executing hardware action"),
        cap("execute-action", "confirmation-token-action-executor", "available-limited", True, "python tools\\hardware_butler.py execute-action --plan action.json --confirm-token <token> --backend fake", "fake backend and safe build only; real hardware backends blocked"),
        cap("safety-audit", "hardware-action-audit-report", "available", True, "python tools\\hardware_butler.py safety-audit --root <project> --json", "read-only summary of safety log events, token hashes, backend counts, execution results, and artifact hash evidence without exposing token values"),
        cap("bench-runbook", "no-hardware-bench-runbook", "available-limited", True, "python tools\\hardware_butler.py bench-runbook --root <project> --action build-flash --target <chip> --probe <probe> --backend openocd --json", "aggregates bench readiness, action plan, preflight checks, artifact hash, and an actual workflow_run.py --dry-run subprocess; it does not execute hardware actions, consume tokens, or write safety log/state/config"),
        cap("bench-preflight", "confirmed-bench-command-preflight", "available-limited", True, "execute-action --backend bench-preflight", "validates prepared workflow argv, parent/child tokens, artifact hash, backend scope, and tool availability without consuming tokens or touching hardware"),
        cap("workflow-dry-run", "workflow-command-dry-run", "available-limited", True, "python embeddedskills\\workflow\\scripts\\workflow_run.py build-flash --workspace <project> --dry-run --json", "prepares redacted build/flash/debug/observe commands without subprocess execution, token consumption, state writes, config writes, or safety-log writes"),
        cap("summarize-manual", "chip-manual-evidence-summary", "available-limited", True, "python tools\\hardware_butler.py summarize-manual --part <chip> --document <manual.pdf>", "summarizes PDF or extracted source text with evidence lines; missing sections remain unknown"),
        cap("research", "auxiliary-research-entrypoint", "available-limited", True, "python tools\\hardware_butler.py research --part <chip> --question '...' --json", "one-command auxiliary research: chip-dossier download + manual_summarizer + evidence_qa; network failures are reported per-stage, not fatal"),
        cap("capabilities", "product-capability-matrix", "available", True, "python tools\\hardware_butler.py capabilities --json", "read-only"),
        cap("doctor", "environment-doctor", "available", True, "python tools\\hardware_butler.py doctor --root <project> --json", "read-only"),
        cap("status", "project-status", "available", True, "python tools\\hardware_butler.py status --root <project> --json", "read-only"),
        cap("build", "confirmed-build", "available-limited", True, "hardware_butler execute-action for action=build", "delegates to safe discovery runner; full build remains backend-gated"),
        cap("build-flash-sim", "confirmed-build-flash-simulation", "available-limited", True, "execute-action --backend workflow-build-flash-sim", "runs controlled build, consumes child flash token, writes audit log, and touches no hardware"),
        cap("build-debug-sim", "confirmed-build-debug-simulation", "available-limited", True, "execute-action --backend workflow-build-debug-sim", "runs controlled build, consumes child debug token, writes audit log, and touches no hardware"),
        cap("observe-sim", "confirmed-observe-simulation", "available-limited", True, "execute-action --backend workflow-observe-sim", "consumes child observe token, writes bounded sample audit data, and touches no hardware"),
        cap("flash-debug", "confirmed-hardware-actions", "planned-gated", False, "J-Link/OpenOCD/probe-rs flows", "real hardware remains blocked until bench verification is added"),
        cap("observe", "confirmed-observe-actions", "planned-gated", False, "serial/RTT/SWO/CAN/network flows", "long-running or external-system actions stay gated"),
    ]
    return {
        "schema_version": 1,
        "product": "hardware-development-butler",
        "status": "available-safe-mvp",
        "capabilities": items,
        "summary": {
            "available": sum(1 for item in items if item["status"] in {"available", "available-limited"}),
            "planned_gated": sum(1 for item in items if item["status"] == "planned-gated"),
        },
        "safety_model": {
            "default": "safe local discovery and report generation",
            "blocked_in_safe_runner": ["build", "flash", "erase", "debug-control", "bus-transmit", "network-scan"],
            "hard_allowlist": sorted(command_runner.ALLOWED_PYTHON_COMMANDS),
            "trusted_python": str(command_runner.TRUSTED_PYTHON),
        },
    }


def cap(command: str, name: str, status: str, safe_by_default: bool, example: str, notes: str) -> dict[str, Any]:
    return {
        "command": command,
        "name": name,
        "status": status,
        "safe_by_default": safe_by_default,
        "example": example,
        "notes": notes,
    }


def doctor(root: Path) -> dict[str, Any]:
    root = root.resolve()
    checks: list[dict[str, Any]] = []
    checks.append(check("python.version", "ok" if sys.version_info >= (3, 10) else "error", f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"))
    checks.append(check("python.trusted_interpreter", "ok", str(command_runner.TRUSTED_PYTHON)))
    embedded_status = runtime_context.embeddedskills_status()
    checks.append(
        check(
            "embeddedskills.runtime",
            "ok" if embedded_status["available"] else "error",
            str(embedded_status["path"]),
            embedded_status,
        )
    )
    checks.extend(path_checks("core.file", CORE_FILES, required=True))
    checks.extend(path_checks("embeddedskills.file", EMBEDDEDSKILLS_FILES, required=True))
    checks.extend(path_checks("agent.file", AGENT_FILES, required=True))
    checks.append(check("project.root", "ok" if root.exists() and root.is_dir() else "error", str(root)))
    checks.append(report_dir_check(root))
    checks.extend(optional_tool_checks())

    if root.exists() and root.is_dir():
        detection = cube_detect.detect(root)
        selected = detection.get("selected_backend") or {}
        backend = selected.get("backend", "")
        checks.append(check("project.backend", "ok" if backend else "warn", backend or "No supported backend detected."))
        checks.append(config_check(root))
        bench = bench_readiness(root)
        for item in bench.get("checks", []):
            checks.append(check(f"bench.{item['name']}", item["status"], item["message"], item.get("details", {})))
    else:
        detection = {"schema_version": 1, "root": str(root), "selected_backend": None, "backend_candidates": [], "warnings": []}
        bench = {"status": "needs-project-root", "checks": [], "next_actions": ["Provide an existing project root."]}

    checks.append(
        check(
            "safe_runner.allowlist",
            "ok",
            f"{len(command_runner.ALLOWED_PYTHON_COMMANDS)} allowlisted script entries",
            {"entries": sorted(command_runner.ALLOWED_PYTHON_COMMANDS)},
        )
    )

    return {
        "schema_version": 1,
        "status": status_from_checks(checks),
        "root": str(root),
        "summary": summarize_checks(checks),
        "checks": checks,
        "selected_backend": detection.get("selected_backend"),
        "bench_readiness": bench,
        "next_actions": doctor_next_actions(checks),
    }


def project_status(root: Path) -> dict[str, Any]:
    root = root.resolve()
    detection = cube_detect.detect(root) if root.exists() else {"selected_backend": None, "cubemx_projects": [], "backend_candidates": []}
    selected = detection.get("selected_backend") or {}
    config = read_config_status(root)
    report_dir = runtime_context.workspace_root() / "docs" / "inspections" / root.name
    reports = {
        "manifest": file_state(report_dir / "onboarding-manifest.json"),
        "project_dossier": file_state(report_dir / "project-dossier.md"),
        "board_profile": file_state(report_dir / "board-profile.md"),
        "firmware_profile": file_state(report_dir / "firmware-profile.md"),
        "build_plan": file_state(report_dir / "build-plan.md"),
        "discovery_run": file_state(report_dir / "discovery-run.md"),
        "config_proposal": file_state(report_dir / "config-proposal.md"),
    }
    manifest = read_manifest(report_dir / "onboarding-manifest.json")
    discovery_state = discovery_status(root, manifest)
    discovery_ready = bool(selected.get("backend") in {"keil", "cmake-gcc", "eide"})

    return {
        "schema_version": 1,
        "status": project_state(selected, config, reports, discovery_state),
        "root": str(root),
        "backend": selected,
        "cubemx_project_count": len(detection.get("cubemx_projects", [])),
        "backend_candidates": detection.get("backend_candidates", []),
        "config": config,
        "reports_dir": str(report_dir),
        "reports": reports,
        "manifest": manifest,
        "discovery": discovery_state,
        "bench_readiness": bench_readiness(root),
        "safe_discovery_ready": discovery_ready,
        "safe_runner": {
            "hard_allowlist": sorted(command_runner.ALLOWED_PYTHON_COMMANDS),
            "trusted_python": str(command_runner.TRUSTED_PYTHON),
        },
        "next_actions": status_next_actions(selected, config, reports, discovery_ready, discovery_state),
    }


def bench_readiness(root: Path) -> dict[str, Any]:
    root = root.resolve()
    config_path = root / ".embeddedskills" / "config.json"
    state_path = root / ".embeddedskills" / "state.json"
    safety_log = root / ".embeddedskills" / "safety-log.jsonl"
    checks: list[dict[str, Any]] = []

    config = read_json_object(config_path)
    state = read_json_object(state_path)
    workflow = config.get("workflow", {}) if isinstance(config, dict) else {}
    last_build = state.get("last_build", {}) if isinstance(state, dict) else {}
    artifacts = last_build.get("artifacts", {}) if isinstance(last_build, dict) else {}
    flash_file = str(last_build.get("flash_file") or artifacts.get("flash_file") or "")
    debug_file = str(last_build.get("debug_file") or artifacts.get("debug_file") or last_build.get("elf_file") or artifacts.get("elf_file") or "")

    checks.append(bench_check("config_present", config_path.exists(), f"Config path: {config_path}"))
    checks.append(bench_check("config_valid_json", isinstance(config, dict), "Project config is valid JSON." if isinstance(config, dict) else "Project config is missing or invalid JSON."))
    checks.append(bench_check("state_present", state_path.exists(), f"State path: {state_path}", warn=True))
    checks.append(bench_check("safe_log_directory", (root / ".embeddedskills").exists() or os.access(root, os.W_OK), f"Safety log path: {safety_log}", warn=True, details={"path": str(safety_log)}))

    hardware_preferences = {
        "flash": workflow.get("preferred_flash", ""),
        "debug": workflow.get("preferred_debug", ""),
        "observe": workflow.get("preferred_observe", ""),
    }
    configured = {name: value for name, value in hardware_preferences.items() if value and value not in {"disabled", "manual"}}
    auto = [name for name, value in hardware_preferences.items() if value == "auto"]
    checks.append(bench_check("hardware_backend_selected", bool(configured), "At least one hardware backend preference is selected.", details={"preferences": hardware_preferences}))
    checks.append(bench_check("hardware_backend_not_auto", not auto, "Hardware backend preferences are explicit.", warn=True, details={"auto": auto}))

    backend_details = hardware_backend_details(config, hardware_preferences)
    checks.extend(backend_details["checks"])

    checks.append(bench_check("flash_artifact_known", bool(flash_file), "last_build exposes a flash artifact.", warn=True, details={"flash_file": flash_file}))
    checks.append(bench_check("debug_artifact_known", bool(debug_file), "last_build exposes a debug artifact.", warn=True, details={"debug_file": debug_file}))
    checks.append(bench_check("flash_artifact_exists", artifact_exists(root, flash_file), "Flash artifact exists on disk.", warn=True, details={"flash_file": flash_file}))
    checks.append(bench_check("debug_artifact_exists", artifact_exists(root, debug_file), "Debug artifact exists on disk.", warn=True, details={"debug_file": debug_file}))

    errors = [item for item in checks if item["status"] == "error"]
    warnings = [item for item in checks if item["status"] == "warn"]
    status = "ready-for-bench-preflight"
    if errors:
        status = "needs-bench-input"
    elif warnings:
        status = "ready-with-bench-warnings"
    return {
        "schema_version": 1,
        "status": status,
        "root": str(root),
        "config_path": str(config_path),
        "state_path": str(state_path),
        "safety_log_path": str(safety_log),
        "hardware_preferences": hardware_preferences,
        "backend_details": backend_details["details"],
        "artifacts": {
            "flash_file": flash_file,
            "flash_exists": artifact_exists(root, flash_file),
            "debug_file": debug_file,
            "debug_exists": artifact_exists(root, debug_file),
        },
        "summary": summarize_checks(checks),
        "checks": checks,
        "next_actions": bench_next_actions(status, checks),
    }


def bench_check(name: str, ok: bool, message: str, *, warn: bool = False, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "name": name,
        "status": "ok" if ok else ("warn" if warn else "error"),
        "message": message,
        "details": details or {},
    }


def read_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def hardware_backend_details(config: dict[str, Any], preferences: dict[str, str]) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    details: dict[str, Any] = {}
    backends = sorted({value for value in preferences.values() if value and value not in {"auto", "disabled", "manual"}})
    for backend in backends:
        if backend == "jlink":
            cfg = config.get("jlink", {}) if isinstance(config.get("jlink"), dict) else {}
            ready = bool(cfg.get("device"))
            tool = first_executable(["JLink.exe", "JLinkExe"])
            details[backend] = {"configured": ready, "tool": tool, "required_config": ["jlink.device"]}
            checks.append(bench_check("jlink_config", ready, "J-Link device is configured.", details={"required": "jlink.device"}))
            checks.append(bench_check("jlink_tool", bool(tool), "J-Link executable is available.", warn=True, details={"found": tool}))
        elif backend == "openocd":
            cfg = config.get("openocd", {}) if isinstance(config.get("openocd"), dict) else {}
            ready = bool(cfg.get("board") or (cfg.get("interface") and cfg.get("target")))
            tool = first_executable(["openocd"])
            details[backend] = {"configured": ready, "tool": tool, "required_config": ["openocd.board or openocd.interface+openocd.target"]}
            checks.append(bench_check("openocd_config", ready, "OpenOCD board or interface/target is configured.", details={"required": "openocd.board or openocd.interface+openocd.target"}))
            checks.append(bench_check("openocd_tool", bool(tool), "OpenOCD executable is available.", warn=True, details={"found": tool}))
        elif backend == "probe-rs":
            cfg = config.get("probe-rs", {}) if isinstance(config.get("probe-rs"), dict) else {}
            ready = bool(cfg.get("chip"))
            tool = first_executable(["probe-rs"])
            details[backend] = {"configured": ready, "tool": tool, "required_config": ["probe-rs.chip"]}
            checks.append(bench_check("probe_rs_config", ready, "probe-rs chip is configured.", details={"required": "probe-rs.chip"}))
            checks.append(bench_check("probe_rs_tool", bool(tool), "probe-rs executable is available.", warn=True, details={"found": tool}))
        else:
            details[backend] = {"configured": False, "tool": "", "required_config": []}
            checks.append(bench_check(f"{backend}_config", False, "Unknown hardware backend preference.", details={"backend": backend}))
    return {"checks": checks, "details": details}


def artifact_exists(root: Path, value: str) -> bool:
    if not value:
        return False
    path = Path(value)
    if not path.is_absolute():
        path = root / path
    return path.exists()


def bench_next_actions(status: str, checks: list[dict[str, Any]]) -> list[str]:
    if status == "ready-for-bench-preflight":
        return ["Generate a plan-action command package, then run execute-action --backend bench-preflight. Real hardware execution remains planned-gated until backend-specific bench validation is added."]
    errors = [item for item in checks if item["status"] == "error"]
    if errors:
        return [f"Fix bench readiness check: {item['name']}" for item in errors[:5]]
    warnings = [item for item in checks if item["status"] == "warn"]
    return [f"Review bench readiness warning: {item['name']}" for item in warnings[:5]]


def check(name: str, status: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "name": name,
        "status": status,
        "message": message,
        "details": details or {},
    }


def path_checks(prefix: str, paths: list[str], *, required: bool) -> list[dict[str, Any]]:
    results = []
    for value in paths:
        path = repo_file(value)
        exists = path.exists()
        status = "ok" if exists else ("error" if required else "warn")
        results.append(check(f"{prefix}:{value}", status, str(path)))
    return results


def repo_file(value: str) -> Path:
    path = Path(value)
    if path.parts and path.parts[0] == "embeddedskills":
        return Path(runtime_context.embeddedskills_root()) / Path(*path.parts[1:])
    return Path(REPO_ROOT) / path


def report_dir_check(root: Path) -> dict[str, Any]:
    report_parent = runtime_context.workspace_root() / "docs" / "inspections"
    writable = report_parent.exists() and os.access(report_parent, os.W_OK)
    if writable:
        return check("reports.output", "ok", str(report_parent / root.name))
    if report_parent.parent.exists() and os.access(report_parent.parent, os.W_OK):
        return check("reports.output", "warn", f"{report_parent} does not exist yet but parent is writable.")
    workspace = runtime_context.workspace_root()
    if workspace.exists() and os.access(workspace, os.W_OK):
        return check("reports.output", "warn", f"{report_parent} does not exist yet but workspace is writable.")
    return check("reports.output", "error", f"{report_parent} is not writable.")


def optional_tool_checks() -> list[dict[str, Any]]:
    results = []
    for item in OPTIONAL_EXECUTABLES:
        found = first_executable(list(item["executables"]))
        status = "ok" if found else "info"
        message = found or f"Optional executable not found: {'/'.join(item['executables'])}"
        results.append(check(f"optional_tool:{item['capability']}:{item['name']}", status, message))
    return results


def first_executable(names: list[str]) -> str:
    for name in names:
        found = shutil.which(name)
        if found:
            return found
    return ""


def config_check(root: Path) -> dict[str, Any]:
    state = read_config_status(root)
    if state["exists"] and state["valid_json"]:
        workflow = state.get("workflow", {})
        auto_hardware = [
            key
            for key in ("preferred_flash", "preferred_debug", "preferred_observe")
            if workflow.get(key) == "auto"
        ]
        if auto_hardware:
            return check("project.config", "warn", f"Hardware action preferences set to auto: {', '.join(auto_hardware)}")
        return check("project.config", "ok", state["path"])
    if state["exists"] and not state["valid_json"]:
        return check("project.config", "error", state["error"])
    return check("project.config", "warn", "No .embeddedskills/config.json yet.")


def read_config_status(root: Path) -> dict[str, Any]:
    path = root / ".embeddedskills" / "config.json"
    if not path.exists():
        return {"exists": False, "valid_json": False, "path": str(path), "sections": [], "error": ""}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {"exists": True, "valid_json": False, "path": str(path), "sections": [], "error": str(exc)}
    return {
        "exists": True,
        "valid_json": True,
        "path": str(path),
        "sections": sorted(data.keys()),
        "workflow": data.get("workflow", {}),
        "auto_hardware_preferences": [
            key
            for key in ("preferred_flash", "preferred_debug", "preferred_observe")
            if data.get("workflow", {}).get(key) == "auto"
        ],
    }


def file_state(path: Path) -> dict[str, Any]:
    return {
        "path": str(path),
        "exists": path.exists(),
        "size_bytes": path.stat().st_size if path.exists() else 0,
    }


def read_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False, "valid_json": False, "path": str(path), "error": ""}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {"exists": True, "valid_json": False, "path": str(path), "error": str(exc)}
    if not isinstance(data, dict):
        return {"exists": True, "valid_json": False, "path": str(path), "error": "manifest JSON must be an object"}
    manifest: dict[str, Any] = data
    manifest["exists"] = True
    manifest["valid_json"] = True
    manifest["path"] = str(path)
    return manifest


def discovery_status(root: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    if not manifest.get("exists"):
        return {"status": "missing", "summary": {}, "message": "No onboarding manifest found."}
    if not manifest.get("valid_json"):
        return {"status": "invalid", "summary": {}, "message": manifest.get("error", "Invalid manifest JSON.")}
    if Path(manifest.get("root", "")).resolve() != root.resolve():
        return {"status": "stale", "summary": {}, "message": "Manifest root does not match requested project root."}
    summary = manifest.get("discovery", {}).get("summary", {})
    if summary.get("error", 0) or summary.get("timeout", 0):
        return {"status": "failed", "summary": summary, "message": "Safe discovery had errors or timeouts."}
    if summary.get("ok", 0) <= 0:
        return {"status": "not-run", "summary": summary, "message": "Safe discovery did not execute any commands."}
    return {"status": "ok", "summary": summary, "message": "Safe discovery completed successfully."}


def status_from_checks(checks: list[dict[str, Any]]) -> str:
    if any(item["status"] == "error" for item in checks):
        return "error"
    if any(item["status"] == "warn" for item in checks):
        return "warning"
    return "ok"


def summarize_checks(checks: list[dict[str, Any]]) -> dict[str, int]:
    summary = {"ok": 0, "warn": 0, "error": 0, "info": 0}
    for item in checks:
        summary[item["status"]] = summary.get(item["status"], 0) + 1
    return summary


def doctor_next_actions(checks: list[dict[str, Any]]) -> list[str]:
    errors = [item for item in checks if item["status"] == "error"]
    warnings = [item for item in checks if item["status"] == "warn"]
    if errors:
        return [f"Fix required check: {item['name']}" for item in errors[:5]]
    if warnings:
        return [f"Review warning: {item['name']}" for item in warnings[:5]]
    return ["Run onboard for a project folder, then review generated reports before any confirmed build or hardware action."]


def project_state(
    selected: dict[str, Any],
    config: dict[str, Any],
    reports: dict[str, dict[str, Any]],
    discovery: dict[str, Any],
) -> str:
    if not selected.get("backend"):
        return "needs-backend"
    if not config["exists"]:
        return "needs-config"
    if not config["valid_json"]:
        return "config-invalid"
    if not reports["discovery_run"]["exists"] or discovery.get("status") != "ok":
        return "needs-safe-discovery"
    if config.get("auto_hardware_preferences"):
        return "ready-with-config-warning"
    return "ready-for-confirmed-next-step"


def status_next_actions(
    selected: dict[str, Any],
    config: dict[str, Any],
    reports: dict[str, dict[str, Any]],
    discovery_ready: bool,
    discovery: dict[str, Any],
) -> list[str]:
    if not selected.get("backend"):
        return ["Run onboard or detect to identify a supported Keil, CMake/GCC, or EIDE backend."]
    if not discovery_ready:
        return ["Resolve backend selection before running safe discovery."]
    if not config["exists"]:
        return ["Run propose-config and write only after reviewing with --write --confirm-write."]
    if not config["valid_json"]:
        return ["Fix .embeddedskills/config.json JSON syntax before continuing."]
    if not reports["discovery_run"]["exists"] or discovery.get("status") != "ok":
        return [f"Run onboard or run-plan --phase build-discovery again: {discovery.get('message', 'safe discovery missing')}"]
    if config.get("auto_hardware_preferences"):
        return [
            f"Review hardware action preferences before continuing: {', '.join(config['auto_hardware_preferences'])}.",
            "Project can proceed only through an explicit user-confirmed build or hardware action path.",
        ]
    return ["Project is ready for a user-confirmed build path; real flash/debug/observe remains planned-gated until backend-specific bench validation is added."]


def render_capabilities_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Hardware Butler Capabilities",
        "",
        f"- Status: `{report['status']}`",
        f"- Available: {report['summary']['available']}",
        f"- Planned gated: {report['summary']['planned_gated']}",
        "",
        "| Command | Status | Safe By Default | Notes |",
        "| --- | --- | --- | --- |",
    ]
    for item in report["capabilities"]:
        safe = "yes" if item["safe_by_default"] else "no"
        lines.append(f"| `{item['command']}` | `{item['status']}` | {safe} | {item['notes']} |")
    return "\n".join(lines) + "\n"


def render_doctor_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Hardware Butler Doctor",
        "",
        f"- Root: `{report['root']}`",
        f"- Status: `{report['status']}`",
        "",
        "## Summary",
        "",
    ]
    for key, value in report["summary"].items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Checks", ""])
    for item in report["checks"]:
        lines.append(f"- `{item['status']}` {item['name']}: {item['message']}")
    bench = report.get("bench_readiness") or {}
    if bench:
        lines.extend(["", "## Bench Readiness", ""])
        lines.append(f"- Status: `{bench.get('status', '')}`")
        for item in bench.get("checks", []):
            lines.append(f"- `{item['status']}` {item['name']}: {item['message']}")
    lines.extend(["", "## Next Actions", ""])
    for action in report["next_actions"]:
        lines.append(f"- {action}")
    return "\n".join(lines) + "\n"


def render_status_markdown(report: dict[str, Any]) -> str:
    backend = report.get("backend") or {}
    lines = [
        "# Hardware Butler Project Status",
        "",
        f"- Root: `{report['root']}`",
        f"- Status: `{report['status']}`",
        f"- Backend: `{backend.get('backend', 'none')}`",
        f"- CubeMX projects: {report['cubemx_project_count']}",
        f"- Config exists: {report['config']['exists']}",
        f"- Safe discovery: `{report['discovery']['status']}`",
        f"- Bench readiness: `{report.get('bench_readiness', {}).get('status', 'unknown')}`",
        "",
        "## Reports",
        "",
    ]
    for name, item in report["reports"].items():
        state = "present" if item["exists"] else "missing"
        lines.append(f"- `{name}`: {state}")
    lines.extend(["", "## Next Actions", ""])
    for action in report["next_actions"]:
        lines.append(f"- {action}")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Hardware butler product diagnostics")
    sub = parser.add_subparsers(dest="command", required=True)

    cap_p = sub.add_parser("capabilities")
    cap_p.add_argument("--json", action="store_true", dest="as_json")

    doctor_p = sub.add_parser("doctor")
    doctor_p.add_argument("--root", default=".")
    doctor_p.add_argument("--json", action="store_true", dest="as_json")

    status_p = sub.add_parser("status")
    status_p.add_argument("--root", default=".")
    status_p.add_argument("--json", action="store_true", dest="as_json")

    args = parser.parse_args()
    if args.command == "capabilities":
        data = capabilities()
        content = json.dumps(data, ensure_ascii=False, indent=2) if args.as_json else render_capabilities_markdown(data)
    elif args.command == "doctor":
        data = doctor(Path(args.root))
        content = json.dumps(data, ensure_ascii=False, indent=2) if args.as_json else render_doctor_markdown(data)
    else:
        data = project_status(Path(args.root))
        content = json.dumps(data, ensure_ascii=False, indent=2) if args.as_json else render_status_markdown(data)
    print(content)


if __name__ == "__main__":
    main()
