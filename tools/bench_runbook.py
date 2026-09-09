"""Generate a no-hardware bench runbook for confirmed workflow actions."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import hardware_action_executor  # noqa: E402
import hardware_action_plan  # noqa: E402
import product_doctor  # noqa: E402
import runtime_context  # noqa: E402
import safe_io  # noqa: E402

SENSITIVE_FLAGS = {"--confirm-token", "--child-confirm-token"}


def generate_runbook(
    root: Path,
    *,
    action: str,
    target: str = "",
    probe: str = "",
    voltage: str = "",
    current_limit: str = "",
    erase_scope: str = "",
    recovery: str = "",
    external_loads: str = "",
    artifact: str = "",
    backend: str = "",
) -> dict[str, Any]:
    root = root.resolve()
    action = hardware_action_plan.normalize_action(action)
    readiness = product_doctor.bench_readiness(root)
    selected_backend = backend or backend_from_readiness(readiness, action)
    selected_artifact = artifact or artifact_from_readiness(readiness, action)
    plan = hardware_action_plan.plan_action(
        root,
        action=action,
        target=target,
        probe=probe,
        voltage=voltage,
        current_limit=current_limit,
        erase_scope=erase_scope,
        recovery=recovery,
        external_loads=external_loads,
        artifact=selected_artifact,
        backend=selected_backend,
    )
    preflight = {}
    if plan.get("confirmation_token") and (plan.get("execution_package") or {}).get("workflow_command"):
        preflight = hardware_action_executor.execute_bench_preflight(
            plan,
            token=str(plan.get("confirmation_token") or ""),
            backend="workflow-command-package",
        )

    workflow_command = ((plan.get("execution_package") or {}).get("workflow_command") or {}).get("argv") or []
    dry_run_argv = add_dry_run_flag([str(item) for item in workflow_command])
    workflow_dry_run = execute_workflow_dry_run(root, dry_run_argv, preflight=preflight)
    status = runbook_status(plan, readiness, preflight, workflow_dry_run)
    return {
        "schema_version": 1,
        "status": status,
        "root": str(root),
        "action": action,
        "safe_by_default": True,
        "executed": False,
        "hardware_side_effect": False,
        "token_consumed": False,
        "state_written": False,
        "config_written": False,
        "safety_log_written": False,
        "bench_readiness": readiness,
        "action_plan": sanitize_plan(plan),
        "bench_preflight": sanitize_preflight(preflight),
        "workflow_dry_run": workflow_dry_run,
        "manual_confirmation": manual_confirmation(plan),
        "run_order": run_order(action),
        "remaining_risks": remaining_risks(readiness, preflight),
        "next_actions": next_actions(status),
    }


def backend_from_readiness(readiness: dict[str, Any], action: str) -> str:
    preferences = readiness.get("hardware_preferences") or {}
    if action in {"build-flash", "flash"}:
        return str(preferences.get("flash") or "")
    if action in {"build-debug", "debug"}:
        return str(preferences.get("debug") or "")
    if action == "observe":
        return str(preferences.get("observe") or "")
    return ""


def artifact_from_readiness(readiness: dict[str, Any], action: str) -> str:
    artifacts = readiness.get("artifacts") or {}
    if action in {"build-flash", "flash"}:
        return str(artifacts.get("flash_file") or "")
    if action in {"build-debug", "debug"}:
        return str(artifacts.get("debug_file") or "")
    return ""


def add_dry_run_flag(argv: list[str]) -> list[str]:
    if not argv or "--dry-run" in argv:
        return argv
    if "--json" in argv:
        index = argv.index("--json")
        return [*argv[:index], "--dry-run", *argv[index:]]
    return [*argv, "--dry-run"]


def execute_workflow_dry_run(root: Path, argv: list[str], *, preflight: dict[str, Any] | None = None) -> dict[str, Any]:
    if not argv:
        return {
            "status": "not-available",
            "executed": False,
            "argv_redacted": [],
            "raw_argv_returned": False,
            "token_values_redacted": True,
            "notes": ["No prepared workflow command was available."],
        }
    preflight_status = str((preflight or {}).get("status") or "")
    if preflight_status.startswith("blocked") or preflight_status == "error":
        return {
            "status": "blocked-workflow-dry-run-preflight",
            "executed": False,
            "argv_redacted": redact_argv(argv),
            "raw_argv_returned": False,
            "token_values_redacted": True,
            "parsed_result": {},
            "notes": ["Refused to start workflow dry-run subprocess because bench preflight found blocking errors."],
        }
    if "--dry-run" not in argv or "--json" not in argv:
        return {
            "status": "blocked-workflow-dry-run-unsafe",
            "executed": False,
            "argv_redacted": redact_argv(argv),
            "raw_argv_returned": False,
            "token_values_redacted": True,
            "parsed_result": {},
            "notes": ["Refused to start workflow dry-run subprocess because --dry-run and --json are mandatory."],
        }
    if not argv_uses_trusted_workflow_run(argv):
        return {
            "status": "blocked-workflow-dry-run-untrusted-argv",
            "executed": False,
            "argv_redacted": redact_argv(argv),
            "raw_argv_returned": False,
            "token_values_redacted": True,
            "parsed_result": {},
            "notes": ["Refused to start workflow dry-run subprocess because argv does not point at the trusted workflow_run.py."],
        }
    started = product_doctor.now_iso() if hasattr(product_doctor, "now_iso") else ""
    before = side_effect_snapshot(root)
    try:
        proc = subprocess.run(
            argv,
            cwd=str(runtime_context.PACKAGE_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {
            "status": "timeout",
            "executed": True,
            "returncode": "",
            "argv_redacted": redact_argv(argv),
            "raw_argv_returned": False,
            "token_values_redacted": True,
            "parsed_result": {},
            "side_effect_check": side_effect_check(root, before),
            "notes": ["workflow dry-run timed out; no hardware command should have been executed because --dry-run was present."],
            "started_at": started,
        }
    stdout = proc.stdout or ""
    stderr = proc.stderr or ""
    parsed = parse_json(stdout)
    if parsed is None:
        parsed = parse_json(stderr)
    raw_dry_controls = ((parsed.get("details") or {}).get("dry_run_controls") or {}) if isinstance(parsed, dict) else {}
    dry_controls = sanitize_dry_run_controls(raw_dry_controls)
    no_side_effects = {
        "token_consumed": dry_controls.get("token_consumed") is False,
        "state_written": dry_controls.get("state_written") is False,
        "config_written": dry_controls.get("config_written") is False,
        "safety_log_written": dry_controls.get("safety_log_written") is False,
    }
    side_effects = side_effect_check(root, before)
    parsed_result = parsed if isinstance(parsed, dict) else {}
    parsed_status = str(parsed_result.get("status") or "")
    controls_valid = dry_run_controls_valid(dry_controls)
    status = "ok" if proc.returncode == 0 and parsed_status and parsed_status not in {"error"} and controls_valid else "error"
    if not side_effects["unchanged"]:
        status = "blocked-workflow-dry-run-side-effect"
    return {
        "status": status,
        "executed": True,
        "returncode": proc.returncode,
        "argv_redacted": redact_argv(argv),
        "raw_argv_returned": False,
        "token_values_redacted": True,
        "parsed_result": sanitize_parsed_result(parsed_result),
        "dry_run_controls": dry_controls,
        "no_side_effects_reported": no_side_effects,
        "side_effect_check": side_effects,
        "notes": [
            "This executed workflow_run.py with --dry-run only.",
            "workflow dry-run must not consume tokens, write safety logs, write config/state, or execute backend hardware commands.",
        ],
        "started_at": started,
    }


def argv_uses_trusted_workflow_run(argv: list[str]) -> bool:
    trusted = (runtime_context.embeddedskills_root() / "workflow" / "scripts" / "workflow_run.py").resolve()
    if len(argv) < 2:
        return False
    script = Path(str(argv[1]))
    try:
        interpreter = Path(str(argv[0]))
        return bool(
            interpreter.is_absolute()
            and interpreter.resolve() == Path(sys.executable).resolve()
            and script.resolve() == trusted
        )
    except (OSError, RuntimeError):
        return False


def sanitize_dry_run_controls(controls: dict[str, Any]) -> dict[str, Any]:
    allowed = ("dry_run", "executed", "hardware_side_effect", "token_consumed", "state_written", "config_written", "safety_log_written")
    if not isinstance(controls, dict):
        return {}
    return {key: controls.get(key) for key in allowed if key in controls}


def dry_run_controls_valid(controls: dict[str, Any]) -> bool:
    required_false = ("token_consumed", "state_written", "config_written", "safety_log_written")
    return bool(all(controls.get(key) is False for key in required_false))


def parse_json(text: str) -> dict[str, Any] | None:
    if not text.strip():
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def side_effect_snapshot(root: Path) -> dict[str, dict[str, Any]]:
    embedded = root / ".embeddedskills"
    return {
        "config": file_snapshot(embedded / "config.json"),
        "state": file_snapshot(embedded / "state.json"),
        "safety_log": file_snapshot(embedded / "safety-log.jsonl"),
    }


def file_snapshot(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False, "sha256": "", "size": 0}
    data = path.read_bytes()
    return {"exists": True, "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}


def side_effect_check(root: Path, before: dict[str, dict[str, Any]]) -> dict[str, Any]:
    after = side_effect_snapshot(root)
    changed = [name for name, snapshot in before.items() if after.get(name) != snapshot]
    return {
        "unchanged": not changed,
        "changed": changed,
        "before": before,
        "after": after,
    }


def sanitize_parsed_result(data: dict[str, Any]) -> dict[str, Any]:
    if not data:
        return {}
    redacted = redact_tokens_in_obj(data)
    return redacted if isinstance(redacted, dict) else {}


def redact_tokens_in_obj(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: redact_tokens_in_obj(item)
            for key, item in value.items()
            if not sensitive_result_key(key)
        }
    if isinstance(value, list):
        return [redact_tokens_in_obj(item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    return value


def sensitive_result_key(key: str) -> bool:
    lowered = key.lower()
    token_field_names = {
        "token",
        "tokens",
        "raw_token",
        "raw_tokens",
        "token_value",
        "token_values",
        "confirm_token",
        "confirmation_token",
        "child_confirm_token",
        "child_confirmation_token",
    }
    return (
        lowered == "argv"
        or "stdout" in lowered
        or "stderr" in lowered
        or lowered in token_field_names
        or lowered.endswith("_token")
        or lowered.endswith("-token")
    )


def redact_text(text: str) -> str:
    return re.sub(r"hwc1-[A-Za-z0-9_-]+", "hwc1-<redacted>", text)


def redact_argv(argv: list[str]) -> list[str]:
    redacted = []
    hide_next = False
    for item in argv:
        if hide_next:
            redacted.append("<redacted>")
            hide_next = False
            continue
        redacted.append(str(item))
        if item in SENSITIVE_FLAGS:
            hide_next = True
    return redacted


def token_hash(value: str) -> str:
    if not value:
        return ""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sanitize_plan(plan: dict[str, Any]) -> dict[str, Any]:
    sanitized = {
        key: value
        for key, value in plan.items()
        if key not in {"confirmation_token", "child_safety_tokens", "execution_package"}
    }
    token = str(plan.get("confirmation_token") or "")
    sanitized["confirmation_token"] = "<redacted>" if token else ""
    sanitized["confirmation_token_hash"] = token_hash(token)
    sanitized["child_safety_tokens"] = [
        {
            "action": item.get("action", ""),
            "token": "<redacted>" if item.get("token") else "",
            "token_hash": token_hash(str(item.get("token") or "")),
            "expected_scope": item.get("expected_scope", {}),
            "consume_at": item.get("consume_at", ""),
        }
        for item in plan.get("child_safety_tokens", [])
    ]
    command = ((plan.get("execution_package") or {}).get("workflow_command") or {}).copy()
    if command.get("argv"):
        command["argv_redacted"] = redact_argv([str(item) for item in command["argv"]])
        command.pop("argv", None)
        command["raw_argv_returned"] = False
    sanitized["execution_package"] = {
        "mode": (plan.get("execution_package") or {}).get("mode", ""),
        "workflow_command": command,
        "manual_confirmation": (plan.get("execution_package") or {}).get("manual_confirmation", {}),
        "children_redacted": True,
    }
    return sanitized


def sanitize_preflight(preflight: dict[str, Any]) -> dict[str, Any]:
    if not preflight:
        return {}
    sanitized = dict(preflight)
    command = dict(sanitized.get("workflow_command") or {})
    if command.get("argv"):
        command["argv_redacted"] = redact_argv([str(item) for item in command["argv"]])
        command.pop("argv", None)
        command["raw_argv_returned"] = False
    sanitized["workflow_command"] = command
    sanitized.pop("audit_log", None)
    return sanitized


def manual_confirmation(plan: dict[str, Any]) -> dict[str, Any]:
    record = plan.get("confirmation_record") or {}
    return {
        "target": record.get("target", ""),
        "probe": record.get("probe", ""),
        "voltage": record.get("voltage", ""),
        "current_limit": record.get("current_limit", ""),
        "erase_scope": record.get("erase_scope", ""),
        "recovery": record.get("recovery", ""),
        "external_loads": record.get("external_loads", ""),
        "artifact": record.get("artifact", ""),
        "artifact_hash": record.get("artifact_hash", ""),
        "backend": record.get("backend", ""),
    }


def run_order(action: str) -> list[dict[str, str]]:
    table = {
        "build-flash": [
            ("bench-readiness", "Review config, backend, artifacts, and optional tool checks."),
            ("plan-action", "Generate confirmation-scoped parent and child tokens."),
            ("bench-preflight", "Validate prepared workflow command without consuming tokens."),
            ("workflow-dry-run", "Review redacted build and flash command shape."),
            ("real-run", "Only after physical confirmation, execute a backend-specific flow outside this runbook."),
        ],
        "build-debug": [
            ("bench-readiness", "Review config, backend, artifacts, and optional tool checks."),
            ("plan-action", "Generate confirmation-scoped parent and child tokens."),
            ("bench-preflight", "Validate prepared workflow command without consuming tokens."),
            ("workflow-dry-run", "Review redacted build and debug command shape."),
            ("real-run", "Only after physical confirmation, execute a backend-specific flow outside this runbook."),
        ],
        "observe": [
            ("bench-readiness", "Review backend and bounded observation channel."),
            ("plan-action", "Generate confirmation-scoped observe token."),
            ("bench-preflight", "Validate prepared observe command without consuming tokens."),
            ("workflow-dry-run", "Review redacted observe command shape."),
            ("real-run", "Only after physical confirmation, open the bounded observe channel."),
        ],
    }
    rows = table.get(action, [("plan-action", "Generate a confirmation-scoped plan before hardware action.")])
    return [{"step": step, "purpose": purpose} for step, purpose in rows]


def runbook_status(plan: dict[str, Any], readiness: dict[str, Any], preflight: dict[str, Any], workflow_dry_run: dict[str, Any] | None = None) -> str:
    if str(plan.get("status", "")).startswith("blocked"):
        return str(plan.get("status"))
    if preflight and str(preflight.get("status", "")).startswith("blocked"):
        return str(preflight.get("status"))
    if workflow_dry_run and workflow_dry_run.get("status") in {
        "error",
        "timeout",
        "blocked-workflow-dry-run-unsafe",
        "blocked-workflow-dry-run-untrusted-argv",
        "blocked-workflow-dry-run-preflight",
        "blocked-workflow-dry-run-side-effect",
    }:
        return "blocked-workflow-dry-run-failed"
    summary = readiness.get("summary") or {}
    if summary.get("error", 0):
        return "needs-bench-input"
    if summary.get("warn", 0) or (preflight and preflight.get("status") == "warning"):
        return "ready-with-bench-warnings"
    return "ready-for-manual-confirmation"


def remaining_risks(readiness: dict[str, Any], preflight: dict[str, Any]) -> list[str]:
    risks = []
    for item in readiness.get("checks", []):
        if item.get("status") in {"warn", "error"}:
            risks.append(f"{item.get('name')}: {item.get('message')}")
    for item in preflight.get("checks", []) if preflight else []:
        if item.get("status") in {"warn", "error"}:
            risks.append(f"preflight.{item.get('name')}: {item.get('message')}")
    return risks


def next_actions(status: str) -> list[str]:
    if status.startswith("blocked") or status == "needs-bench-input":
        return ["Fix blocking safety, artifact, backend, or configuration inputs before any hardware run."]
    if status == "ready-with-bench-warnings":
        return ["Review every warning, verify physical bench conditions, then regenerate/confirm the exact action plan."]
    return ["Review the manual confirmation record and physical preflight checklist before any real hardware action."]


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Bench Runbook",
        "",
        f"- Root: `{report['root']}`",
        f"- Action: `{report['action']}`",
        f"- Status: `{report['status']}`",
        f"- Executed: {report['executed']}",
        f"- Hardware side effect: {report['hardware_side_effect']}",
        f"- Token consumed: {report['token_consumed']}",
        "",
        "## Manual Confirmation",
        "",
    ]
    for key, value in report.get("manual_confirmation", {}).items():
        lines.append(f"- {key}: `{value or 'unknown'}`")
    lines.extend(["", "## Run Order", ""])
    for item in report.get("run_order", []):
        lines.append(f"- `{item['step']}`: {item['purpose']}")
    argv = (report.get("workflow_dry_run") or {}).get("argv_redacted") or []
    if argv:
        lines.extend(["", "## Workflow Dry Run Command", "", "```json", json.dumps(argv, ensure_ascii=False, indent=2), "```"])
    lines.extend(["", "## Remaining Risks", ""])
    if report.get("remaining_risks"):
        for item in report["remaining_risks"]:
            lines.append(f"- {item}")
    else:
        lines.append("- none reported by local checks")
    lines.extend(["", "## Next Actions", ""])
    for item in report.get("next_actions", []):
        lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a no-hardware bench runbook")
    parser.add_argument("--root", default=".")
    parser.add_argument("--action", required=True)
    parser.add_argument("--target", default="")
    parser.add_argument("--probe", default="")
    parser.add_argument("--voltage", default="")
    parser.add_argument("--current-limit", default="")
    parser.add_argument("--erase-scope", default="")
    parser.add_argument("--recovery", default="")
    parser.add_argument("--external-loads", default="")
    parser.add_argument("--artifact", default="")
    parser.add_argument("--backend", default="")
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--out", default="")
    args = parser.parse_args()
    report = generate_runbook(
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
    content = json.dumps(report, ensure_ascii=False, indent=2) if args.as_json else render_markdown(report)
    if args.out:
        safe_io.safe_write_text(Path(args.out), content, allowed_roots=runtime_context.allowed_write_roots())
    else:
        print(content)


if __name__ == "__main__":
    main()
