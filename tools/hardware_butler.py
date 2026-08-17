"""Unified CLI facade for the hardware development butler.

The facade keeps early project operations discoverable while preserving safety:
it delegates to read-only tooling by default and does not run build, flash,
debug, or bus actions.
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

import bench_runbook  # noqa: E402
import build_log_classifier  # noqa: E402
import build_plan  # noqa: E402
import chip_dossier  # noqa: E402
import command_runner  # noqa: E402
import config_proposal  # noqa: E402
import cube_detect  # noqa: E402
import cubemx_config_advisor  # noqa: E402
import document_search_api  # noqa: E402
import evidence_qa  # noqa: E402
import firmware_code_patcher  # noqa: E402
import firmware_intent_planner  # noqa: E402
import hardware_action_audit  # noqa: E402
import hardware_action_executor  # noqa: E402
import hardware_action_plan  # noqa: E402
import hardware_butler_inspect  # noqa: E402
import manual_summarizer  # noqa: E402
import product_doctor  # noqa: E402
import project_brain  # noqa: E402
import project_workflow  # noqa: E402
import runtime_context  # noqa: E402
import safe_io  # noqa: E402
import task_workflows  # noqa: E402
import workflow_runner  # noqa: E402
from logger import get_logger  # noqa: E402

# Setup logging
logger = get_logger(__name__)


REPO_ROOT = runtime_context.PACKAGE_ROOT


def configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8", errors="replace")


def output(data: dict[str, Any], *, as_json: bool, markdown: str = "", out: str = "") -> None:
    content = json.dumps(data, ensure_ascii=False, indent=2) if as_json or not markdown else markdown
    if out:
        safe_io.safe_write_text(Path(out), content, allowed_roots=runtime_context.allowed_write_roots())
    else:
        print(content)


def json_requested(argv: list[str]) -> bool:
    return "--json" in argv


def classify_cli_error(exc: BaseException) -> str:
    message = str(exc)
    if isinstance(exc, json.JSONDecodeError):
        return "json-decode-error"
    if "Refusing to write outside allowed roots" in message:
        return "safe-write-denied"
    if "Refusing to write through symlink path" in message:
        return "safe-write-denied"
    if isinstance(exc, OSError):
        return "io-error"
    return "validation-error"


def cli_error_payload(exc: BaseException) -> dict[str, Any]:
    code = classify_cli_error(exc)
    payload: dict[str, Any] = {
        "schema_version": 1,
        "status": "error",
        "error": {
            "code": code,
            "message": str(exc),
        },
    }
    if code == "safe-write-denied":
        payload["error"]["hint"] = (
            "Write outputs under the active workspace root, or set HW_BUTLER_ROOT "
            "to the workspace you want this CLI invocation to manage."
        )
    return payload


def format_cli_error(exc: BaseException, *, as_json: bool) -> str:
    payload = cli_error_payload(exc)
    if as_json:
        return json.dumps(payload, ensure_ascii=False, indent=2)
    error = payload["error"]
    hint = error.get("hint")
    lines = [f"ERROR [{error['code']}]: {error['message']}"]
    if hint:
        lines.append(f"Hint: {hint}")
    return "\n".join(lines)


def write_markdown(path: Path, content: str) -> str:
    return str(safe_io.safe_write_text(path, content, allowed_roots=runtime_context.allowed_write_roots()))


def quickstart_guide(root: Path) -> dict[str, Any]:
    root = root.resolve()
    inspection_dir = runtime_context.default_inspection_dir(root)
    root_text = str(root)

    return {
        "schema_version": 1,
        "status": "ok",
        "root": root_text,
        "inspection_dir": str(inspection_dir),
        "first_day_commands": [
            guide_command(
                "doctor",
                "Check local readiness",
                ["python", "tools\\hardware_butler.py", "doctor", "--root", root_text, "--json"],
                "Verify Python, required files, optional tools, backend hints, and bench readiness.",
            ),
            guide_command(
                "auto",
                "Run the safe first pass",
                [
                    "python",
                    "tools\\hardware_butler.py",
                    "auto",
                    "--root",
                    root_text,
                    "--out-dir",
                    str(inspection_dir),
                    "--json",
                ],
                "Generate reports and project-state.json without build, flash, debug, bus, or network actions.",
            ),
            guide_command(
                "next-step",
                "Ask for one safe recommendation",
                ["python", "tools\\hardware_butler.py", "next-step", "--root", root_text, "--json"],
                "Read the current project state and return the next safe command.",
            ),
            guide_command(
                "workbench",
                "Open the desktop workbench",
                ["python", "gui\\hardware_agent_ui.py"],
                "Use the GUI when you want a guided project selector and action list.",
            ),
        ],
        "expected_outputs": [
            {
                "path": ".hardware-butler\\project-state.json",
                "purpose": "workflow state and next recommended action",
            },
            {
                "path": str(inspection_dir / "project-dossier.md"),
                "purpose": "project overview",
            },
            {
                "path": str(inspection_dir / "board-profile.md"),
                "purpose": "board and MCU clues",
            },
            {
                "path": str(inspection_dir / "firmware-profile.md"),
                "purpose": "firmware structure clues",
            },
            {
                "path": str(inspection_dir / "build-plan.md"),
                "purpose": "safe build discovery plan",
            },
        ],
        "safety_boundary": {
            "safe_first_day_actions": [
                "inspect files",
                "generate reports",
                "write local project state",
                "recommend safe commands",
            ],
            "not_performed": [
                "flash",
                "erase",
                "reset",
                "debug control",
                "bus transmit",
                "network scan",
                "hardware confirmation bypass",
            ],
        },
        "docs": [
            {"path": "docs/START_HERE.md", "purpose": "first-day GUI and CLI path"},
            {"path": "docs/COMMANDS.md", "purpose": "command cookbook by workflow stage"},
            {"path": "docs/README.md", "purpose": "documentation map"},
            {"path": "docs/WORKBENCH_TUTORIAL.md", "purpose": "daily GUI tutorial"},
            {"path": "README.md", "purpose": "workspace overview"},
        ],
        "next_success_state": [
            "doctor returns without required errors",
            "auto writes an inspection directory",
            "next-step returns exactly one safe recommended action",
            "you know whether the next action touches hardware",
        ],
    }


def guide_command(command_id: str, title: str, argv: list[str], purpose: str) -> dict[str, Any]:
    return {
        "id": command_id,
        "title": title,
        "argv": argv,
        "command": command_text(argv),
        "purpose": purpose,
        "safe_by_default": True,
        "touches_hardware": False,
    }


def command_text(argv: list[str]) -> str:
    return " ".join(quote_command_arg(item) for item in argv)


def quote_command_arg(value: str) -> str:
    if not value:
        return '""'
    if any(char.isspace() for char in value):
        escaped = value.replace('"', '\\"')
        return f'"{escaped}"'
    return value


def render_guide_markdown(data: dict[str, Any]) -> str:
    lines = [
        "# Hardware Butler Start Guide",
        "",
        f"- Root: `{data['root']}`",
        f"- Inspection directory: `{data['inspection_dir']}`",
        "",
        "## First Day Path",
        "",
        "| Step | Command | Why |",
        "| --- | --- | --- |",
    ]
    for item in data["first_day_commands"]:
        lines.append(f"| {item['title']} | `{item['command']}` | {item['purpose']} |")

    lines.extend(["", "## Expected Outputs", "", "| Path | Purpose |", "| --- | --- |"])
    for item in data["expected_outputs"]:
        lines.append(f"| `{item['path']}` | {item['purpose']} |")

    boundary = data["safety_boundary"]
    lines.extend(["", "## Safety Boundary", ""])
    lines.append("These first-day commands may:")
    for item in boundary["safe_first_day_actions"]:
        lines.append(f"- {item}")
    lines.extend(["", "They do not:"])
    for item in boundary["not_performed"]:
        lines.append(f"- {item}")

    lines.extend(["", "## Docs", "", "| Path | Purpose |", "| --- | --- |"])
    for item in data["docs"]:
        lines.append(f"| `{item['path']}` | {item['purpose']} |")

    lines.extend(["", "## Good First Success", ""])
    for item in data["next_success_state"]:
        lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def onboard_project(root: Path, *, out_dir: Path, target: str = "", preset: str = "", config_name: str = "") -> dict[str, Any]:
    root = root.resolve()
    out_dir = out_dir.resolve()

    inspection = hardware_butler_inspect.inspect_project(root, out_dir)
    detection = cube_detect.detect(root)
    plan = build_plan.generate_plan(root)
    discovery = command_runner.run_plan(root, phase="build-discovery")
    config = config_proposal.propose_config(root, target=target, preset=preset, config_name=config_name)
    primary_part = primary_mcu_part(inspection)
    chip = None
    if primary_part:
        chip = chip_dossier.create_dossier(
            primary_part,
            runtime_context.workspace_root() / "docs" / "chip" / chip_dossier.normalize_part(primary_part),
        )
    action_plan = hardware_action_plan.plan_action(
        root,
        action="flash",
        target=primary_part,
    )

    written = {
        "inspection_dir": str(out_dir),
        "build_plan": write_markdown(out_dir / "build-plan.md", build_plan.render_markdown(plan)),
        "discovery_run": write_markdown(out_dir / "discovery-run.md", command_runner.render_markdown(discovery)),
        "config_proposal": write_markdown(out_dir / "config-proposal.md", config_proposal.render_markdown(config)),
        "flash_action_plan": write_markdown(out_dir / "flash-action-plan.md", hardware_action_plan.render_markdown(action_plan)),
    }
    if chip:
        written["chip_dossier"] = chip["written"]["dossier_json"]
    manifest = {
        "schema_version": 1,
        "root": str(root),
        "out_dir": str(out_dir),
        "detection": {
            "selected_backend": detection.get("selected_backend"),
            "backend_candidates": detection.get("backend_candidates", []),
            "cubemx_project_count": len(detection.get("cubemx_projects", [])),
        },
        "build_plan": {
            "status": plan["status"],
            "command_count": len(plan.get("commands", [])),
        },
        "discovery": {
            "summary": discovery["summary"],
            "phase_filter": discovery["phase_filter"],
            "allow_writes": discovery["allow_writes"],
            "allow_confirmation": discovery["allow_confirmation"],
        },
        "config": {
            "status": config["status"],
            "required_inputs": config.get("required_inputs", []),
            "config_path": config.get("config_path", ""),
        },
        "chip": {
            "part": primary_part,
            "dossier": chip["out_dir"] if chip else "",
        },
        "hardware_actions": {
            "flash_plan_status": action_plan["status"],
            "missing_inputs": action_plan["missing_inputs"],
        },
    }
    written["manifest"] = safe_io.safe_write_text(
        out_dir / "onboarding-manifest.json",
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        allowed_roots=runtime_context.allowed_write_roots(),
    )

    return {
        "schema_version": 1,
        "status": onboard_status(detection, discovery, config),
        "root": str(root),
        "out_dir": str(out_dir),
        "inspection": inspection,
        "detection": detection,
        "build_plan": {
            "status": plan["status"],
            "selected_backend": plan.get("selected_backend"),
            "command_count": len(plan.get("commands", [])),
        },
        "discovery": {
            "summary": discovery["summary"],
            "safety_policy": discovery["safety_policy"],
        },
        "config": {
            "status": config["status"],
            "required_inputs": config.get("required_inputs", []),
            "config_path": config.get("config_path", ""),
        },
        "chip": {
            "part": primary_part,
            "dossier": chip["out_dir"] if chip else "",
        },
        "hardware_actions": {
            "flash_plan_status": action_plan["status"],
            "missing_inputs": action_plan["missing_inputs"],
        },
        "written": written,
        "next_actions": onboard_next_actions(config),
    }


def primary_mcu_part(inspection: dict[str, Any]) -> str:
    board_profile = inspection.get("board_profile")
    if not isinstance(board_profile, dict):
        return ""
    mcu = board_profile.get("mcu")
    if not isinstance(mcu, dict):
        return ""
    return str(mcu.get("name") or "")


def onboard_status(detection: dict[str, Any], discovery: dict[str, Any], config: dict[str, Any]) -> str:
    if detection.get("selected_backend") is None:
        return "needs-build-backend"
    if discovery["summary"].get("error", 0) or discovery["summary"].get("timeout", 0):
        return "discovery-has-errors"
    if config.get("required_inputs"):
        return "needs-input"
    return "ready-for-config-review"


def onboard_next_actions(config: dict[str, Any]) -> list[str]:
    if config.get("required_inputs"):
        return [
            f"Provide required inputs: {', '.join(config['required_inputs'])}.",
            "Run propose-config again with the missing target, preset, or config name.",
        ]
    return [
        "Review the generated dossier, build plan, discovery run, and config proposal.",
        "Write .embeddedskills/config.json only with propose-config --write --confirm-write.",
        "Run real build/flash/debug actions only after explicit confirmation.",
    ]


def main(argv: list[str] | None = None) -> None:
    configure_stdio()
    parser = argparse.ArgumentParser(description="Hardware development butler CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    guide_p = sub.add_parser("guide", help="Show the first-day start guide")
    guide_p.add_argument("--root", default=".")
    guide_p.add_argument("--json", action="store_true", dest="as_json")
    guide_p.add_argument("--out", default="")

    inspect_p = sub.add_parser("inspect", help="Generate project dossier, board profile, and firmware profile")
    inspect_p.add_argument("--root", default=".")
    inspect_p.add_argument("--out-dir", default="")
    inspect_p.add_argument("--json", action="store_true", dest="as_json")

    detect_p = sub.add_parser("detect", help="Detect CubeMX metadata and backend candidates")
    detect_p.add_argument("--root", default=".")
    detect_p.add_argument("--json", action="store_true", dest="as_json")
    detect_p.add_argument("--out", default="")

    plan_p = sub.add_parser("plan-build", help="Generate safe build plan without executing it")
    plan_p.add_argument("--root", default=".")
    plan_p.add_argument("--json", action="store_true", dest="as_json")
    plan_p.add_argument("--out", default="")

    config_p = sub.add_parser("propose-config", help="Generate or write .embeddedskills/config.json proposal")
    config_p.add_argument("--root", default=".")
    config_p.add_argument("--target", default="")
    config_p.add_argument("--preset", default="")
    config_p.add_argument("--config-name", default="")
    config_p.add_argument("--write", action="store_true")
    config_p.add_argument("--confirm-write", action="store_true")
    config_p.add_argument("--json", action="store_true", dest="as_json")
    config_p.add_argument("--out", default="")

    run_p = sub.add_parser("run-plan", help="Run safe non-hardware commands from a generated plan")
    run_p.add_argument("--root", default=".")
    run_p.add_argument("--phase", default="")
    run_p.add_argument("--allow-writes", action="store_true")
    run_p.add_argument("--allow-confirmation", action="store_true")
    run_p.add_argument("--timeout", type=int, default=60)
    run_p.add_argument("--json", action="store_true", dest="as_json")
    run_p.add_argument("--out", default="")

    onboard_p = sub.add_parser("onboard", help="Run safe first-pass onboarding and write project reports")
    onboard_p.add_argument("--root", default=".")
    onboard_p.add_argument("--out-dir", default="")
    onboard_p.add_argument("--target", default="")
    onboard_p.add_argument("--preset", default="")
    onboard_p.add_argument("--config-name", default="")
    onboard_p.add_argument("--json", action="store_true", dest="as_json")
    onboard_p.add_argument("--out", default="")

    auto_p = sub.add_parser("auto", help="Run safe automation and write project-state.json")
    auto_p.add_argument("--root", default=".")
    auto_p.add_argument("--out-dir", default="")
    auto_p.add_argument("--target", default="")
    auto_p.add_argument("--preset", default="")
    auto_p.add_argument("--config-name", default="")
    auto_p.add_argument("--json", action="store_true", dest="as_json")
    auto_p.add_argument("--out", default="")

    next_p = sub.add_parser("next-step", help="Show the next safe recommended action")
    next_p.add_argument("--root", default=".")
    next_p.add_argument("--json", action="store_true", dest="as_json")
    next_p.add_argument("--out", default="")

    workbench_p = sub.add_parser("workbench", help="Show the connected project workbench model for CLI and UI")
    workbench_p.add_argument("--root", default=".")
    workbench_p.add_argument("--out-dir", default="")
    workbench_p.add_argument("--json", action="store_true", dest="as_json")
    workbench_p.add_argument("--out", default="")

    brain_p = sub.add_parser("brain", help="Build the hardware project brain with evidence health and risks")
    brain_p.add_argument("--root", default=".")
    brain_p.add_argument("--json", action="store_true", dest="as_json")
    brain_p.add_argument("--out", default="")
    brain_p.add_argument("--no-write", action="store_true")

    ask_p = sub.add_parser("ask", help="Answer a project question from local indexed evidence")
    ask_p.add_argument("--root", default=".")
    ask_p.add_argument("--question", required=True)
    ask_p.add_argument("--json", action="store_true", dest="as_json")
    ask_p.add_argument("--out", default="")
    ask_p.add_argument("--no-refresh", action="store_true")

    task_p = sub.add_parser("task", help="Expand an intent into safe hardware-copilot workflow commands")
    task_p.add_argument("--root", default=".")
    task_p.add_argument("--intent", required=True, choices=sorted(task_workflows.INTENTS))
    task_p.add_argument("--part", default="")
    task_p.add_argument("--pin", default="")
    task_p.add_argument("--function", default="")
    task_p.add_argument("--instance", default="")
    task_p.add_argument("--log", default="")
    task_p.add_argument("--question", default="")
    task_p.add_argument("--json", action="store_true", dest="as_json")
    task_p.add_argument("--out", default="")

    wf_run_p = sub.add_parser("workflow-run", help="Run a goal-driven workflow through staged plan/config/build/flash")
    wf_run_p.add_argument("--root", default=".")
    wf_run_p.add_argument("--intent", default="develop-feature")
    wf_run_p.add_argument("--goal", default="")
    wf_run_p.add_argument("--feature", default="")
    wf_run_p.add_argument("--pin", default="")
    wf_run_p.add_argument("--function", default="")
    wf_run_p.add_argument("--instance", default="")
    wf_run_p.add_argument("--part", default="")
    wf_run_p.add_argument("--target", default="")
    wf_run_p.add_argument("--probe", default="")
    wf_run_p.add_argument("--backend", default="")
    wf_run_p.add_argument("--auto-select", action="store_true", help="Auto-select the first LLM chip candidate when no --part and no CubeMX detection")
    wf_run_p.add_argument("--resume", action="store_true")
    wf_run_p.add_argument("--json", action="store_true", dest="as_json")
    wf_run_p.add_argument("--out", default="")

    wf_status_p = sub.add_parser("workflow-status", help="Show current workflow state and stage progress")
    wf_status_p.add_argument("--root", default=".")
    wf_status_p.add_argument("--json", action="store_true", dest="as_json")
    wf_status_p.add_argument("--out", default="")

    wf_search_p = sub.add_parser("workflow-search", help="Print the pending datasheet search task for host-agent execution")
    wf_search_p.add_argument("--root", default=".")
    wf_search_p.add_argument("--json", action="store_true", dest="as_json")
    wf_search_p.add_argument("--out", default="")

    wf_llm_tasks_p = sub.add_parser("workflow-llm-tasks", help="Print pending LLM tasks for host-agent execution")
    wf_llm_tasks_p.add_argument("--root", default=".")
    wf_llm_tasks_p.add_argument("--json", action="store_true", dest="as_json")
    wf_llm_tasks_p.add_argument("--out", default="")

    wf_llm_config_p = sub.add_parser("workflow-llm-config", help="Show or set LLM config")
    wf_llm_config_p.add_argument("--root", default=".")
    wf_llm_config_p.add_argument("--provider", default="")
    wf_llm_config_p.add_argument("--api-key-env", default="")
    wf_llm_config_p.add_argument("--model", default="")
    wf_llm_config_p.add_argument("--base-url", default="")
    wf_llm_config_p.add_argument("--timeout", type=int, default=0)
    wf_llm_config_p.add_argument("--max-tokens", type=int, default=0)
    wf_llm_config_p.add_argument("--codegen", choices=["on", "off"], default="")
    wf_llm_config_p.add_argument("--json", action="store_true", dest="as_json")
    wf_llm_config_p.add_argument("--out", default="")

    cap_p = sub.add_parser("capabilities", help="Show product capability matrix")
    cap_p.add_argument("--json", action="store_true", dest="as_json")
    cap_p.add_argument("--out", default="")

    doctor_p = sub.add_parser("doctor", help="Check local environment and product readiness")
    doctor_p.add_argument("--root", default=".")
    doctor_p.add_argument("--json", action="store_true", dest="as_json")
    doctor_p.add_argument("--out", default="")

    preflight_p = sub.add_parser(
        "real-preflight", help="Real-board-day readiness: tools, probes, chip-name resolution, run command"
    )
    preflight_p.add_argument("--root", default=".")
    preflight_p.add_argument("--part", required=True)
    preflight_p.add_argument("--probe", default="")
    preflight_p.add_argument("--json", action="store_true", dest="as_json")

    status_p = sub.add_parser("status", help="Show project onboarding and readiness status")
    status_p.add_argument("--root", default=".")
    status_p.add_argument("--json", action="store_true", dest="as_json")
    status_p.add_argument("--out", default="")

    log_p = sub.add_parser("classify-log", help="Classify build log")
    log_p.add_argument("log")
    log_p.add_argument("--json", action="store_true", dest="as_json")
    log_p.add_argument("--out", default="")

    chip_p = sub.add_parser("chip-dossier", help="Create chip document dossier and summary skeleton")
    chip_p.add_argument("--part", required=True)
    chip_p.add_argument("--board", default="")
    chip_p.add_argument("--source", action="append", default=[])
    chip_p.add_argument("--search", action="store_true")
    chip_p.add_argument("--search-source", action="append", default=[], help="Omit with --search to use built-in vendor hints")
    chip_p.add_argument("--api-search", action="store_true", help="Use configured search APIs such as Exa or DOC_SEARCH_API_URL")
    chip_p.add_argument("--api-provider", action="append", default=[], choices=["exa", "generic"])
    chip_p.add_argument("--api-preset", default=document_search_api.DEFAULT_PRESET, choices=sorted(document_search_api.SEARCH_PRESETS))
    chip_p.add_argument("--api-query", default="")
    chip_p.add_argument("--api-max-results", type=int, default=8)
    chip_p.add_argument("--download", action="store_true")
    chip_p.add_argument("--no-extract", action="store_true")
    chip_p.add_argument("--out-dir", default="")
    chip_p.add_argument("--json", action="store_true", dest="as_json")
    chip_p.add_argument("--out", default="")

    pin_p = sub.add_parser("advise-pin", help="Advise CubeMX pin/peripheral configuration")
    pin_p.add_argument("--root", default=".")
    pin_p.add_argument("--pin", required=True)
    pin_p.add_argument("--function", required=True)
    pin_p.add_argument("--pin-evidence", default="")
    pin_p.add_argument("--json", action="store_true", dest="as_json")
    pin_p.add_argument("--out", default="")

    patch_ioc_p = sub.add_parser("patch-ioc", help="Preview or write safe STM32CubeMX .ioc pin/peripheral changes")
    patch_ioc_p.add_argument("--root", default=".")
    patch_ioc_p.add_argument("--function", required=True)
    patch_ioc_p.add_argument("--pin", default="")
    patch_ioc_p.add_argument("--label", default="")
    patch_ioc_p.add_argument("--instance", default="")
    patch_ioc_p.add_argument("--scl", default="")
    patch_ioc_p.add_argument("--sda", default="")
    patch_ioc_p.add_argument("--timing", default="")
    patch_ioc_p.add_argument("--write", action="store_true")
    patch_ioc_p.add_argument("--confirm-write", action="store_true")
    patch_ioc_p.add_argument("--json", action="store_true", dest="as_json")
    patch_ioc_p.add_argument("--out", default="")

    action_p = sub.add_parser("plan-action", help="Create confirmation-gated hardware action plan")
    action_p.add_argument("--root", default=".")
    action_p.add_argument("--action", required=True)
    action_p.add_argument("--target", default="")
    action_p.add_argument("--probe", default="")
    action_p.add_argument("--voltage", default="")
    action_p.add_argument("--current-limit", default="")
    action_p.add_argument("--erase-scope", default="")
    action_p.add_argument("--recovery", default="")
    action_p.add_argument("--external-loads", default="")
    action_p.add_argument("--artifact", default="")
    action_p.add_argument("--backend", default="")
    action_p.add_argument("--json", action="store_true", dest="as_json")
    action_p.add_argument("--out", default="")

    exec_p = sub.add_parser("execute-action", help="Execute a confirmation-token action plan through safe/fake backends")
    exec_p.add_argument("--plan", required=True)
    exec_p.add_argument("--confirm-token", required=True)
    exec_p.add_argument("--backend", default="")
    exec_p.add_argument("--json", action="store_true", dest="as_json")
    exec_p.add_argument("--out", default="")

    audit_p = sub.add_parser("safety-audit", help="Summarize hardware action safety/audit log without exposing tokens")
    audit_p.add_argument("--root", default=".")
    audit_p.add_argument("--json", action="store_true", dest="as_json")
    audit_p.add_argument("--out", default="")

    runbook_p = sub.add_parser("bench-runbook", help="Generate a no-hardware bench runbook for build/flash/debug/observe")
    runbook_p.add_argument("--root", default=".")
    runbook_p.add_argument("--action", required=True)
    runbook_p.add_argument("--target", default="")
    runbook_p.add_argument("--probe", default="")
    runbook_p.add_argument("--voltage", default="")
    runbook_p.add_argument("--current-limit", default="")
    runbook_p.add_argument("--erase-scope", default="")
    runbook_p.add_argument("--recovery", default="")
    runbook_p.add_argument("--external-loads", default="")
    runbook_p.add_argument("--artifact", default="")
    runbook_p.add_argument("--backend", default="")
    runbook_p.add_argument("--json", action="store_true", dest="as_json")
    runbook_p.add_argument("--out", default="")

    firmware_p = sub.add_parser("firmware-plan", help="Plan CubeMX/HAL/FreeRTOS implementation without editing code")
    firmware_p.add_argument("--root", default=".")
    firmware_p.add_argument("--feature", required=True)
    firmware_p.add_argument("--pin", default="")
    firmware_p.add_argument("--function", default="")
    firmware_p.add_argument("--no-rtos", action="store_true")
    firmware_p.add_argument("--json", action="store_true", dest="as_json")
    firmware_p.add_argument("--out", default="")

    patch_p = sub.add_parser("firmware-patch", help="Generate or write safe app-layer firmware patch files")
    patch_p.add_argument("--root", default=".")
    patch_p.add_argument("--feature", required=True)
    patch_p.add_argument("--pin", default="")
    patch_p.add_argument("--function", default="")
    patch_p.add_argument("--no-rtos", action="store_true")
    patch_p.add_argument("--write", action="store_true")
    patch_p.add_argument("--confirm-write", action="store_true")
    patch_p.add_argument("--json", action="store_true", dest="as_json")
    patch_p.add_argument("--out", default="")

    integrate_p = sub.add_parser("firmware-integrate", help="Preview or write CubeMX USER CODE integration hooks for an app module")
    integrate_p.add_argument("--root", default=".")
    integrate_p.add_argument("--feature", required=True)
    integrate_p.add_argument("--pin", default="")
    integrate_p.add_argument("--function", default="")
    integrate_p.add_argument("--no-rtos", action="store_true")
    integrate_p.add_argument("--write", action="store_true")
    integrate_p.add_argument("--confirm-write", action="store_true")
    integrate_p.add_argument("--json", action="store_true", dest="as_json")
    integrate_p.add_argument("--out", default="")

    summary_p = sub.add_parser("summarize-manual", help="Summarize extracted chip manual text with evidence lines")
    summary_p.add_argument("--part", required=True)
    summary_p.add_argument("--document", action="append", required=True)
    summary_p.add_argument("--json", action="store_true", dest="as_json")
    summary_p.add_argument("--out", default="")

    research_p = sub.add_parser(
        "research",
        help="One-command auxiliary research: datasheet download + manual summary + optional Q&A",
    )
    research_p.add_argument("--root", default=".")
    research_p.add_argument("--part", required=True)
    research_p.add_argument("--out-dir", default="")
    research_p.add_argument("--question", default="", help="Optional free-form question answered against the downloaded evidence")
    research_p.add_argument("--timeout", type=int, default=20)
    research_p.add_argument("--json", action="store_true", dest="as_json")
    research_p.add_argument("--out", default="")

    args = parser.parse_args(argv)

    if args.command == "guide":
        data = quickstart_guide(Path(args.root))
        output(data, as_json=args.as_json, markdown=render_guide_markdown(data), out=args.out)
    elif args.command == "inspect":
        root = Path(args.root)
        out_dir = Path(args.out_dir) if args.out_dir else root / "docs"
        safe_io.validate_write_path(out_dir, allowed_roots=runtime_context.allowed_write_roots())
        data = hardware_butler_inspect.inspect_project(root, out_dir)
        output(data, as_json=args.as_json)
    elif args.command == "detect":
        data = cube_detect.detect(Path(args.root))
        output(data, as_json=args.as_json, markdown=cube_detect.render_markdown(data), out=args.out)
    elif args.command == "plan-build":
        data = build_plan.generate_plan(Path(args.root))
        output(data, as_json=args.as_json, markdown=build_plan.render_markdown(data), out=args.out)
    elif args.command == "propose-config":
        data = config_proposal.propose_config(
            Path(args.root),
            target=args.target,
            preset=args.preset,
            config_name=args.config_name,
        )
        if args.write:
            try:
                data["write_result"] = config_proposal.write_config(data, confirm_write=args.confirm_write)
            except (ValueError, json.JSONDecodeError) as exc:
                output({"status": "error", "error": str(exc), "proposal": data}, as_json=True)
                sys.exit(2)
        output(data, as_json=args.as_json, markdown=config_proposal.render_markdown(data), out=args.out)
    elif args.command == "run-plan":
        data = command_runner.run_plan(
            Path(args.root),
            phase=args.phase,
            allow_writes=args.allow_writes,
            allow_confirmation=args.allow_confirmation,
            timeout_s=args.timeout,
        )
        output(data, as_json=args.as_json, markdown=command_runner.render_markdown(data), out=args.out)
    elif args.command == "onboard":
        root = Path(args.root)
        out_dir = Path(args.out_dir) if args.out_dir else runtime_context.default_inspection_dir(root)
        safe_io.validate_write_path(out_dir, allowed_roots=runtime_context.allowed_write_roots())
        data = onboard_project(
            root,
            out_dir=out_dir,
            target=args.target,
            preset=args.preset,
            config_name=args.config_name,
        )
        output(data, as_json=args.as_json, out=args.out)
    elif args.command == "auto":
        root = Path(args.root)
        auto_out_dir = Path(args.out_dir) if args.out_dir else None

        def runner(project_root: Path, reports_dir: Path) -> dict[str, Any]:
            safe_io.validate_write_path(reports_dir, allowed_roots=runtime_context.allowed_write_roots())
            return onboard_project(
                project_root,
                out_dir=reports_dir,
                target=args.target,
                preset=args.preset,
                config_name=args.config_name,
            )

        data = project_workflow.run_auto(root, out_dir=auto_out_dir, onboard_runner=runner)
        output(data, as_json=args.as_json, out=args.out)
    elif args.command == "next-step":
        root = Path(args.root)
        state = project_workflow.collect_project_state(root)
        state_path = project_workflow.write_project_state(root, state)
        data = {
            "schema_version": 1,
            "status": state["status"],
            "root": state["root"],
            "state_path": str(state_path),
            "state": state,
            "next_step": state["next_step"],
            "phases": state["phases"],
        }
        output(data, as_json=args.as_json, out=args.out)
    elif args.command == "workbench":
        root = Path(args.root)
        reports_dir = Path(args.out_dir) if args.out_dir else None
        data = project_workflow.build_workbench(root, reports_dir=reports_dir)
        state_path = project_workflow.write_project_state(root, data["state"])
        data["state_path"] = str(state_path)
        output(data, as_json=args.as_json, out=args.out)
    elif args.command == "brain":
        data = project_brain.build_project_brain(Path(args.root), write=not args.no_write)
        output(data, as_json=args.as_json, markdown=project_brain.render_markdown(data), out=args.out)
    elif args.command == "ask":
        data = evidence_qa.answer_question(Path(args.root), args.question, refresh=not args.no_refresh)
        output(data, as_json=args.as_json, markdown=evidence_qa.render_markdown(data), out=args.out)
    elif args.command == "task":
        data = task_workflows.build_task_plan(
            Path(args.root),
            args.intent,
            part=args.part,
            pin=args.pin,
            function=args.function,
            instance=args.instance,
            log=args.log,
            question=args.question,
        )
        output(data, as_json=args.as_json, markdown=task_workflows.render_markdown(data), out=args.out)
    elif args.command == "workflow-run":
        root = Path(args.root)
        if args.resume:
            state = workflow_runner.load_workflow_state(root)
            if state is None:
                output({"schema_version": 1, "status": "error", "error": "no workflow-state.json to resume"}, as_json=True)
                sys.exit(2)
        else:
            ctx = workflow_runner.WorkflowContext(
                part=args.part,
                feature=args.feature,
                pin=args.pin,
                function=args.function,
                instance=args.instance,
                target=args.target,
                probe=args.probe,
                backend=args.backend,
            )
            state = workflow_runner.init_workflow(
                root, intent=args.intent, goal=args.goal, context=ctx
            )
            if args.auto_select:
                state["context"]["auto_select"] = True
        state = workflow_runner.run_workflow(root, state)
        public_state = workflow_runner.public_workflow_state(state)
        data = {"schema_version": 1, "state": public_state, "summary": workflow_runner.workflow_summary(public_state)}
        output(data, as_json=args.as_json, out=args.out)
    elif args.command == "workflow-status":
        root = Path(args.root)
        state = workflow_runner.load_workflow_state(root)
        if state is None:
            output({"schema_version": 1, "status": "no-workflow", "root": str(root)}, as_json=args.as_json)
        else:
            public_state = workflow_runner.public_workflow_state(state)
            output({"schema_version": 1, "state": public_state, "summary": workflow_runner.workflow_summary(public_state)}, as_json=args.as_json, out=args.out)
    elif args.command == "workflow-search":
        root = Path(args.root)
        task_path = root / ".hardware-butler" / "search-tasks.json"
        if not task_path.exists():
            output({"schema_version": 1, "status": "no-search-task", "root": str(root)}, as_json=True)
        else:
            import json as _json
            task = _json.loads(task_path.read_text(encoding="utf-8"))
            output({"schema_version": 1, "status": "pending-search", "task": task}, as_json=args.as_json, out=args.out)
    elif args.command == "workflow-llm-tasks":
        root = Path(args.root)
        tasks_path = root / ".hardware-butler" / "llm-tasks.jsonl"
        responses_path = root / ".hardware-butler" / "llm-responses.jsonl"
        import json as _json
        pending: list[dict[str, Any]] = []
        if tasks_path.exists():
            responded_ids: set[str] = set()
            if responses_path.exists():
                for line in responses_path.read_text(encoding="utf-8", errors="replace").splitlines():
                    try:
                        r = _json.loads(line)
                        if isinstance(r, dict) and r.get("task_id"):
                            responded_ids.add(r["task_id"])
                    except ValueError:
                        continue
            for line in tasks_path.read_text(encoding="utf-8", errors="replace").splitlines():
                try:
                    t = _json.loads(line)
                except ValueError:
                    continue
                if isinstance(t, dict) and t.get("task_id") and t["task_id"] not in responded_ids:
                    pending.append(t)
        output({"schema_version": 1, "status": "ok", "pending": pending, "count": len(pending)}, as_json=args.as_json, out=args.out)
    elif args.command == "workflow-llm-config":
        root = Path(args.root)
        import llm_config as _llm_cfg
        if args.provider or args.api_key_env or args.model or args.base_url or args.timeout or args.max_tokens or args.codegen:
            current = _llm_cfg.load_config(root)
            new_config = _llm_cfg.LLMConfig(
                provider=args.provider or current.provider,
                api_key_env=args.api_key_env or current.api_key_env,
                model=args.model or current.model,
                base_url=args.base_url or current.base_url,
                timeout_s=args.timeout if args.timeout else current.timeout_s,
                max_tokens=args.max_tokens if args.max_tokens else current.max_tokens,
                codegen=(args.codegen == "on") if args.codegen else current.codegen,
            )
            path = _llm_cfg.save_config(root, new_config)
            output({"schema_version": 1, "status": "saved", "config": new_config.to_dict(), "path": str(path)}, as_json=args.as_json, out=args.out)
        else:
            current = _llm_cfg.load_config(root)
            output({"schema_version": 1, "status": "ok", "config": current.to_dict(), "configured": _llm_cfg.is_configured(current)}, as_json=args.as_json, out=args.out)
    elif args.command == "capabilities":
        data = product_doctor.capabilities()
        output(data, as_json=args.as_json, markdown=product_doctor.render_capabilities_markdown(data), out=args.out)
    elif args.command == "doctor":
        data = product_doctor.doctor(Path(args.root))
        output(data, as_json=args.as_json, markdown=product_doctor.render_doctor_markdown(data), out=args.out)
    elif args.command == "real-preflight":
        import real_preflight  # noqa: E402

        data = real_preflight.run_preflight(Path(args.root), args.part, probe=args.probe)
        output(data, as_json=args.as_json)
    elif args.command == "status":
        data = product_doctor.project_status(Path(args.root))
        output(data, as_json=args.as_json, markdown=product_doctor.render_status_markdown(data), out=args.out)
    elif args.command == "classify-log":
        try:
            text = build_log_classifier.read_log(Path(args.log))
        except (OSError, ValueError) as exc:
            output({"schema_version": 1, "status": "error", "error": str(exc)}, as_json=True)
            sys.exit(2)
        data = build_log_classifier.classify_text(text)
        output(data, as_json=args.as_json, markdown=build_log_classifier.render_markdown(data), out=args.out)
    elif args.command == "chip-dossier":
        part = chip_dossier.normalize_part(args.part)
        out_dir = Path(args.out_dir) if args.out_dir else runtime_context.workspace_root() / "docs" / "chip" / part
        if args.search or args.api_search:
            data = chip_dossier.search_and_download_documents(
                part,
                out_dir,
                board=args.board,
                search_sources=args.search_source or args.source,
                api_search=args.api_search,
                api_providers=args.api_provider,
                api_preset=args.api_preset,
                api_query=args.api_query,
                api_max_results=args.api_max_results,
            )
        elif args.download:
            data = chip_dossier.download_documents(
                part,
                out_dir,
                board=args.board,
                sources=args.source,
                extract_text=not args.no_extract,
            )
        else:
            data = chip_dossier.create_dossier(part, out_dir, board=args.board, sources=args.source)
        output(data, as_json=args.as_json, markdown=chip_dossier.render_source_map(data), out=args.out)
    elif args.command == "advise-pin":
        data = cubemx_config_advisor.advise(Path(args.root), pin=args.pin, function=args.function, pin_evidence=args.pin_evidence)
        output(data, as_json=args.as_json, markdown=cubemx_config_advisor.render_markdown(data), out=args.out)
    elif args.command == "patch-ioc":
        try:
            patch = cubemx_config_advisor.propose_ioc_patch(
                Path(args.root),
                function=args.function,
                pin=args.pin,
                label=args.label,
                instance=args.instance,
                scl_pin=args.scl,
                sda_pin=args.sda,
                timing=args.timing,
            )
            data = cubemx_config_advisor.write_ioc_patch(patch, confirm_write=args.confirm_write) if args.write else patch
        except (OSError, ValueError) as exc:
            output({"schema_version": 1, "status": "error", "error": str(exc)}, as_json=True)
            sys.exit(2)
        output(data, as_json=args.as_json, markdown=cubemx_config_advisor.render_ioc_patch_markdown(data), out=args.out)
    elif args.command == "plan-action":
        data = hardware_action_plan.plan_action(
            Path(args.root),
            action=args.action,
            target=args.target,
            probe=args.probe,
            voltage=args.voltage,
            current_limit=args.current_limit,
            erase_scope=args.erase_scope,
            recovery=args.recovery,
            external_loads=args.external_loads,
            artifact=args.artifact,
            backend=args.backend,
        )
        output(data, as_json=args.as_json, markdown=hardware_action_plan.render_markdown(data), out=args.out)
    elif args.command == "execute-action":
        try:
            plan = hardware_action_executor.load_plan(Path(args.plan))
            data = hardware_action_executor.execute_plan(plan, token=args.confirm_token, backend=args.backend)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            output({"schema_version": 1, "status": "error", "error": str(exc)}, as_json=True)
            sys.exit(2)
        output(data, as_json=args.as_json, markdown=hardware_action_executor.render_markdown(data), out=args.out)
    elif args.command == "safety-audit":
        data = hardware_action_audit.audit_report(Path(args.root))
        output(data, as_json=args.as_json, markdown=hardware_action_audit.render_markdown(data), out=args.out)
    elif args.command == "bench-runbook":
        data = bench_runbook.generate_runbook(
            Path(args.root),
            action=args.action,
            target=args.target,
            probe=args.probe,
            voltage=args.voltage,
            current_limit=args.current_limit,
            erase_scope=args.erase_scope,
            recovery=args.recovery,
            external_loads=args.external_loads,
            artifact=args.artifact,
            backend=args.backend,
        )
        output(data, as_json=args.as_json, markdown=bench_runbook.render_markdown(data), out=args.out)
    elif args.command == "firmware-plan":
        data = firmware_intent_planner.plan_implementation(
            Path(args.root),
            feature=args.feature,
            pin=args.pin,
            function=args.function,
            rtos=not args.no_rtos,
        )
        output(data, as_json=args.as_json, markdown=firmware_intent_planner.render_markdown(data), out=args.out)
    elif args.command == "firmware-patch":
        try:
            preview = firmware_code_patcher.preview_patch(
                Path(args.root),
                feature=args.feature,
                pin=args.pin,
                function=args.function,
                rtos=not args.no_rtos,
            )
            data = firmware_code_patcher.write_patch(preview, confirm_write=args.confirm_write) if args.write else preview
        except (OSError, ValueError) as exc:
            output({"schema_version": 1, "status": "error", "error": str(exc)}, as_json=True)
            sys.exit(2)
        output(data, as_json=args.as_json, markdown=firmware_code_patcher.render_markdown(data), out=args.out)
    elif args.command == "firmware-integrate":
        try:
            preview = firmware_code_patcher.preview_integration_patch(
                Path(args.root),
                feature=args.feature,
                pin=args.pin,
                function=args.function,
                rtos=not args.no_rtos,
            )
            data = firmware_code_patcher.write_integration_patch(preview, confirm_write=args.confirm_write) if args.write else preview
        except (OSError, ValueError) as exc:
            output({"schema_version": 1, "status": "error", "error": str(exc)}, as_json=True)
            sys.exit(2)
        output(data, as_json=args.as_json, markdown=firmware_code_patcher.render_integration_markdown(data), out=args.out)
    elif args.command == "summarize-manual":
        data = manual_summarizer.summarize_documents(args.part, [Path(item) for item in args.document])
        output(data, as_json=args.as_json, markdown=manual_summarizer.render_markdown(data), out=args.out)
    elif args.command == "research":
        import research  # noqa: E402
        root = Path(args.root)
        research_out_dir: Path | None = Path(args.out_dir) if args.out_dir else None
        data = research.run_research(
            root, part=args.part, out_dir=research_out_dir, question=args.question, timeout_s=args.timeout
        )
        output(data, as_json=args.as_json, markdown=research.render_research_markdown(data), out=args.out)

def cli_entry(argv: list[str] | None = None) -> int:
    configure_stdio()
    effective_argv = sys.argv[1:] if argv is None else argv
    try:
        main(effective_argv)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(format_cli_error(exc, as_json=json_requested(effective_argv)), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(cli_entry())
