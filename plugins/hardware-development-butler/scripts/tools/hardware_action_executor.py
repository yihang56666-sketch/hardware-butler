"""Confirmation-token executor for safe hardware-butler actions.

The executor deliberately starts narrow:
- `fake` backend records what would happen for integration tests and dry runs.
- `build` action delegates to the existing safe discovery runner.
- real flash/debug/bus actions remain blocked here until a backend-specific
  proofed flow is added.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import runtime_context  # noqa: E402

EMBEDDED_DIR = runtime_context.embeddedskills_root()
if str(EMBEDDED_DIR) not in sys.path:
    sys.path.insert(0, str(EMBEDDED_DIR))

import build_log_classifier  # noqa: E402
import command_runner  # noqa: E402
import hardware_action_audit  # noqa: E402
import hardware_action_plan  # noqa: E402
import safe_io  # noqa: E402
import safety_gate  # noqa: E402

EXECUTABLE_ACTIONS = {"build", "fake-flash", "fake-debug", "fake-observe", "fake-reset", "fake-send-can", "fake-send-uart"}
BUILD_BACKENDS = {"workflow-build"}
PREFLIGHT_BACKENDS = {"bench-preflight", "workflow-command-package"}
WORKFLOW_SIM_BACKENDS = {
    "workflow-build-flash-sim": "flash",
    "workflow-build-debug-sim": "debug",
    "workflow-observe-sim": "observe",
}


def load_plan(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("action plan must be a JSON object")
    return data


def execute_plan(plan: dict[str, Any], *, token: str, backend: str = "") -> dict[str, Any]:
    action = hardware_action_plan.normalize_action(str(plan.get("action", "")))
    record = plan.get("confirmation_record") or {}
    recomputed = hardware_action_plan.confirmation_token(action, record)
    plan_token = str(plan.get("confirmation_token") or "")
    if plan_token and plan_token != recomputed:
        return {
            "schema_version": 1,
            "status": "blocked-plan-token-mismatch",
            "action": action,
            "executed": False,
            "error": "plan confirmation token does not match the confirmation record",
        }
    token_ok = hardware_action_plan.verify_confirmation_token(action, record, token)

    requires_confirmation = bool(
        action in hardware_action_plan.HARDWARE_ACTIONS | hardware_action_plan.CONTROLLED_LOCAL_ACTIONS
        or plan.get("hardware_side_effect")
        or plan.get("controlled_local_action")
    )
    if requires_confirmation and not token_ok:
        return {
            "schema_version": 1,
            "status": "blocked-confirmation-required",
            "action": action,
            "executed": False,
            "error": "confirmation token missing or not bound to this plan",
        }
    # Defense in depth: re-run the value-sanity checks here so a hand-crafted
    # plan with physically-impossible safety values is refused at execution
    # time even if it somehow carries a matching token.
    value_safety = safety_gate.evaluate_value_safety(action, record)
    if value_safety["blocks"]:
        return {
            "schema_version": 1,
            "status": "blocked-unsafe-safety-value",
            "action": action,
            "executed": False,
            "error": "unsafe safety-field value(s): " + "; ".join(value_safety["blocks"]),
            "value_safety": value_safety,
        }
    root = Path(plan["root"]).resolve()
    if requires_confirmation and (not record.get("root") or root != Path(record["root"]).resolve()):
        return {
            "schema_version": 1,
            "status": "blocked-plan-root-mismatch",
            "action": action,
            "executed": False,
            "error": "execution root does not match the confirmed workspace",
        }
    artifact_check = verify_artifact_hash(record, root=root)
    if artifact_check["status"] != "ok":
        return {
            "schema_version": 1,
            "status": artifact_check["status"],
            "action": action,
            "executed": False,
            "error": artifact_check["message"],
            "details": artifact_check,
        }

    selected_backend = backend or record.get("backend") or "fake"
    if selected_backend != record.get("backend") and selected_backend not in PREFLIGHT_BACKENDS | {"fake"}:
        return {
            "schema_version": 1,
            "status": "blocked-backend-mismatch",
            "action": action,
            "executed": False,
            "error": "execution backend does not match the confirmed backend",
        }
    if selected_backend in PREFLIGHT_BACKENDS:
        result = execute_bench_preflight(plan, token=token, backend=selected_backend)
        return result

    if requires_confirmation:
        audit = hardware_action_audit.consume_token(root, token=token, plan=plan, backend=selected_backend)
        if audit["status"] != "ok":
            return {
                "schema_version": 1,
                "status": audit["status"],
                "action": action,
                "backend": selected_backend,
                "executed": False,
                "hardware_side_effect": bool(plan.get("hardware_side_effect")),
                "audit": audit,
            }
    if action == "build":
        if selected_backend in BUILD_BACKENDS:
            result = execute_workflow_build(plan)
            result["audit_log"] = hardware_action_audit.record_result(root, token=token, plan=plan, backend=selected_backend, result=result)
            return result
        report = command_runner.run_plan(Path(plan["root"]), phase="build-discovery")
        result = {
            "schema_version": 1,
            "status": "ok" if report["summary"].get("error", 0) == 0 else "error",
            "action": action,
            "backend": "safe-runner",
            "executed": True,
            "hardware_side_effect": False,
            "report": report,
        }
        if requires_confirmation:
            result["audit_log"] = hardware_action_audit.record_result(root, token=token, plan=plan, backend=selected_backend, result=result)
        return result

    if selected_backend in WORKFLOW_SIM_BACKENDS and action in {"build-flash", "build-debug", "flash", "debug", "observe"}:
        result = execute_workflow_hardware_sim(plan, backend=selected_backend)
        result["audit_log"] = hardware_action_audit.record_result(root, token=token, plan=plan, backend=selected_backend, result=result)
        return result

    fake_action = f"fake-{action}"
    if selected_backend == "fake" and fake_action in EXECUTABLE_ACTIONS:
        result = {
            "schema_version": 1,
            "status": "ok",
            "action": action,
            "backend": "fake",
            "executed": True,
            "hardware_side_effect": False,
            "summary": "Fake backend accepted the confirmed action without touching hardware.",
            "confirmation_scope": hardware_action_plan.token_payload(action, record),
        }
        result["audit_log"] = hardware_action_audit.record_result(root, token=token, plan=plan, backend=selected_backend, result=result)
        return result

    result = {
        "schema_version": 1,
        "status": "blocked-real-backend-not-enabled",
        "action": action,
        "backend": selected_backend,
        "executed": False,
        "hardware_side_effect": bool(plan.get("hardware_side_effect")),
        "next_actions": [
            "Use fake backend for integration tests.",
            "Add a backend-specific executor with device ID, artifact hash, voltage/current evidence, and rollback logging before real hardware execution.",
        ],
    }
    if requires_confirmation:
        result["audit_log"] = hardware_action_audit.record_result(root, token=token, plan=plan, backend=selected_backend, result=result)
    return result


def execute_bench_preflight(plan: dict[str, Any], *, token: str, backend: str) -> dict[str, Any]:
    """Validate a prepared workflow command package without consuming tokens or touching hardware."""
    action = hardware_action_plan.normalize_action(str(plan.get("action", "")))
    record = plan.get("confirmation_record") or {}
    package = plan.get("execution_package") or {}
    command = package.get("workflow_command") or {}
    children = plan.get("child_safety_tokens") or []
    checks: list[dict[str, Any]] = []

    checks.append(preflight_check("parent_token_valid", hardware_action_plan.verify_confirmation_token(action, record, token), "Parent token matches confirmation record."))
    checks.append(preflight_check("workflow_command_present", bool(command.get("argv")), "Plan contains a prepared workflow argv."))
    checks.append(preflight_check("child_token_present", bool(children and children[0].get("token")), "Plan contains an action-specific child token."))
    checks.append(preflight_check("artifact_hash_bound", artifact_hash_bound(record, action), "Artifact hash is bound when an artifact is present or flash is requested."))

    argv = command.get("argv") if isinstance(command.get("argv"), list) else []
    if argv:
        checks.extend(validate_workflow_argv(argv, plan=plan, token=token, child=children[0] if children else {}))

    tool = backend_tool_status(record, action)
    checks.append(tool)

    errors = [item for item in checks if item["status"] == "error"]
    warnings = [item for item in checks if item["status"] == "warn"]
    status = "blocked-preflight-failed" if errors else ("warning" if warnings else "ok")
    return {
        "schema_version": 1,
        "status": status,
        "action": action,
        "backend": backend,
        "executed": False,
        "hardware_side_effect": False,
        "token_consumed": False,
        "summary": "Bench preflight validated the prepared command package without touching hardware." if not errors else "Bench preflight found blocking issues.",
        "checks": checks,
        "workflow_command": sanitize_workflow_command(command),
        "next_actions": [
            "Fix blocking preflight checks before any real bench run.",
            "Keep the parent and child confirmation tokens unused until the real execution step.",
        ],
    }


def sanitize_workflow_command(command: dict[str, Any]) -> dict[str, Any]:
    sanitized = {key: value for key, value in command.items() if key != "argv"}
    argv = command.get("argv") if isinstance(command.get("argv"), list) else []
    if argv:
        sanitized["argv_redacted"] = redact_argv([str(item) for item in argv])
    sanitized["raw_argv_returned"] = False
    sanitized["token_values_redacted"] = True
    return sanitized


def redact_argv(argv: list[str]) -> list[str]:
    sensitive_flags = {"--confirm-token", "--child-confirm-token"}
    redacted: list[str] = []
    hide_next = False
    for item in argv:
        if hide_next:
            redacted.append("<redacted>")
            hide_next = False
            continue
        redacted.append(item)
        if item in sensitive_flags:
            hide_next = True
    return redacted


def preflight_check(name: str, ok: bool, message: str, *, warn: bool = False, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "name": name,
        "status": "ok" if ok else ("warn" if warn else "error"),
        "message": message,
        "details": details or {},
    }


def artifact_hash_bound(record: dict[str, Any], action: str) -> bool:
    artifact = str(record.get("artifact") or "")
    artifact_hash = str(record.get("artifact_hash") or "")
    if artifact:
        return bool(artifact_hash)
    return action not in {"flash", "build-flash"}


def validate_workflow_argv(argv: list[Any], *, plan: dict[str, Any], token: str, child: dict[str, Any]) -> list[dict[str, Any]]:
    values = [str(item) for item in argv]
    record = plan.get("confirmation_record") or {}
    child_scope = child.get("expected_scope") or {}
    workflow_token = hardware_action_plan.workflow_parent_token(str(plan.get("action") or ""), record)
    checks = [
        preflight_check("argv_uses_workflow_run", any(item.endswith("workflow_run.py") for item in values), "Prepared argv points at workflow_run.py."),
        preflight_check("argv_action_matches_plan", workflow_action_in_argv(values, plan), "Prepared argv workflow action matches the plan action."),
        preflight_check("argv_backend_matches_plan", workflow_backend_in_argv(values, record, plan), "Prepared argv backend flag matches the confirmation record."),
        preflight_check("argv_has_parent_token", flag_value(values, "--confirm-token") == workflow_token, "Prepared argv includes the embedded workflow parent token."),
        preflight_check("argv_plan_token_separate", workflow_token != token, "Workflow parent token is separate from the butler plan token."),
        preflight_check("argv_has_child_token", flag_value(values, "--child-confirm-token") == str(child.get("token") or ""), "Prepared argv includes the expected child token."),
        preflight_check("argv_workspace_matches_plan", flag_value(values, "--workspace") == str(record.get("root") or plan.get("root") or ""), "Prepared argv workspace matches the plan root."),
        preflight_check("argv_target_matches_plan", flag_value(values, "--target") == str(record.get("target") or ""), "Prepared argv target matches the confirmation record."),
        preflight_check("argv_probe_matches_plan", flag_value(values, "--probe") == str(record.get("probe") or ""), "Prepared argv probe matches the confirmation record."),
        preflight_check("argv_artifact_hash_matches_plan", argv_artifact_hash_ok(values, record, child_scope), "Prepared argv carries the confirmed artifact hash."),
        preflight_check("argv_json_enabled", "--json" in values, "Prepared argv requests machine-readable JSON output."),
        preflight_check("argv_flags_known", argv_flags_known(values), "Prepared argv uses only known workflow safety flags."),
    ]
    return checks


def workflow_action_in_argv(argv: list[str], plan: dict[str, Any]) -> bool:
    expected = {
        "build-flash": "build-flash",
        "build-debug": "build-debug",
        "observe": "observe",
    }.get(hardware_action_plan.normalize_action(str(plan.get("action", ""))), "")
    return bool(expected) and expected in argv


def workflow_backend_in_argv(argv: list[str], record: dict[str, Any], plan: dict[str, Any]) -> bool:
    action = hardware_action_plan.normalize_action(str(plan.get("action", "")))
    flag = {
        "build-flash": "--flash-backend",
        "build-debug": "--debug-backend",
        "observe": "--observe-backend",
    }.get(action, "")
    backend = hardware_action_plan.normalize_action(str(record.get("backend") or ""))
    if not flag:
        return False
    if backend.endswith("-sim"):
        return bool(flag_value(argv, flag) == "")
    return bool(flag_value(argv, flag) == backend)


def flag_value(argv: list[str], flag: str) -> str:
    try:
        index = argv.index(flag)
    except ValueError:
        return ""
    if index + 1 >= len(argv):
        return ""
    return argv[index + 1]


def argv_artifact_hash_ok(argv: list[str], record: dict[str, Any], child_scope: dict[str, Any]) -> bool:
    expected = str(record.get("artifact_hash") or "")
    child_expected = str(child_scope.get("artifact_hash") or "")
    if not expected and not child_expected:
        return True
    return flag_value(argv, "--artifact-hash") == expected and flag_value(argv, "--child-artifact-hash") == (child_expected or expected)


def argv_flags_known(argv: list[str]) -> bool:
    known = {
        "--workspace",
        "--build-backend",
        "--flash-backend",
        "--debug-backend",
        "--observe-backend",
        "--confirm-token",
        "--child-confirm-token",
        "--target",
        "--probe",
        "--voltage",
        "--current-limit",
        "--erase-scope",
        "--recovery",
        "--external-loads",
        "--artifact",
        "--artifact-hash",
        "--child-artifact-hash",
        "--dry-run",
        "--json",
    }
    return all(not item.startswith("--") or item in known for item in argv)


def backend_tool_status(record: dict[str, Any], action: str) -> dict[str, Any]:
    backend = hardware_action_plan.normalize_action(str(record.get("backend") or ""))
    if backend.endswith("-sim"):
        return preflight_check("backend_tool_available", True, "Simulation backend does not require a hardware tool.")
    candidates = {
        "jlink": ["JLink.exe", "JLinkExe"],
        "openocd": ["openocd"],
        "probe-rs": ["probe-rs"],
    }.get(backend, [])
    if not candidates:
        return preflight_check(
            "backend_tool_available",
            False,
            "No known hardware tool mapping for backend.",
            warn=action not in {"flash", "debug", "build-flash", "build-debug", "observe"},
            details={"backend": backend},
        )
    found = first_executable(candidates)
    return preflight_check(
        "backend_tool_available",
        bool(found),
        "Required backend executable is available." if found else "Required backend executable was not found on PATH.",
        warn=True,
        details={"backend": backend, "executables": candidates, "found": found},
    )


def first_executable(names: list[str]) -> str:
    for name in names:
        found = shutil.which(name)
        if found:
            return found
    return ""


def execute_workflow_build(plan: dict[str, Any]) -> dict[str, Any]:
    root = Path(plan["root"]).resolve()
    cmd = [
        sys.executable,
        str(runtime_context.embeddedskills_root() / "workflow" / "scripts" / "workflow_run.py"),
        "build",
        "--workspace",
        str(root),
        "--json",
    ]
    started = time.time()
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(runtime_context.PACKAGE_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "schema_version": 1,
            "status": "timeout",
            "action": "build",
            "backend": "workflow-build",
            "executed": True,
            "hardware_side_effect": False,
            "duration_ms": int((time.time() - started) * 1000),
            "error": "workflow build timed out",
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or "",
        }
    stdout = proc.stdout or ""
    stderr = proc.stderr or ""
    combined = "\n".join(part for part in (stdout, stderr) if part)
    parsed = parse_json_output(stdout) or parse_json_output(stderr)
    classification = build_log_classifier.classify_text(combined) if combined.strip() else build_log_classifier.classify_text("")
    return {
        "schema_version": 1,
        "status": "ok" if proc.returncode == 0 else "error",
        "action": "build",
        "backend": "workflow-build",
        "executed": True,
        "hardware_side_effect": False,
        "duration_ms": int((time.time() - started) * 1000),
        "returncode": proc.returncode,
        "argv": cmd,
        "workflow_result": parsed,
        "log_classification": classification,
        "stdout_tail": stdout[-8000:],
        "stderr_tail": stderr[-8000:],
    }


def execute_workflow_hardware_sim(plan: dict[str, Any], *, backend: str) -> dict[str, Any]:
    """Run build when requested, then consume the child token in a no-hardware simulator."""
    child_action = WORKFLOW_SIM_BACKENDS[backend]
    root = Path(plan["root"]).resolve()
    steps: list[dict[str, Any]] = []
    if plan.get("action") in {"build-flash", "build-debug"}:
        build_result = execute_workflow_build(plan)
        steps.append({"name": "build", "result": build_result})
        if build_result.get("status") != "ok":
            return {
                "schema_version": 1,
                "status": "blocked-build-failed",
                "action": plan.get("action", ""),
                "backend": backend,
                "executed": True,
                "hardware_side_effect": False,
                "steps": steps,
            }
    child = find_child_token(plan, child_action)
    if not child:
        return {
            "schema_version": 1,
            "status": "blocked-missing-child-token",
            "action": plan.get("action", ""),
            "backend": backend,
            "executed": False,
            "hardware_side_effect": False,
            "required_child_action": child_action,
        }
    child_audit = consume_child_token(root, plan=plan, child=child, backend=backend)
    if child_audit["status"] != "ok":
        return {
            "schema_version": 1,
            "status": child_audit["status"],
            "action": plan.get("action", ""),
            "backend": backend,
            "executed": False,
            "hardware_side_effect": False,
            "child_audit": child_audit,
            "steps": steps,
        }
    simulated = {
        "schema_version": 1,
        "status": "ok",
        "action": plan.get("action", ""),
        "backend": backend,
        "executed": True,
        "hardware_side_effect": False,
        "summary": f"Simulated workflow {child_action} consumed the child safety token without touching hardware.",
        "child_action": child_action,
        "child_scope": child.get("expected_scope", {}),
        "child_audit": child_audit,
        "steps": steps,
        "next_actions": [
            "Use this result to validate plan/token/audit wiring.",
            "Real hardware execution remains disabled until backend identity, voltage/current evidence, and recovery logging are verified on a physical bench.",
        ],
    }
    if child_action == "observe":
        samples = simulated_observe_samples(plan)
        simulated["observe_samples"] = samples
        simulated["observe_samples_count"] = len(samples)
        simulated["summary"] = "Simulated bounded observe consumed the child safety token without opening probes, serial ports, CAN adapters, or sockets."
    return simulated


def simulated_observe_samples(plan: dict[str, Any]) -> list[dict[str, Any]]:
    record = plan.get("confirmation_record") or {}
    backend = str(record.get("backend") or "workflow-observe-sim")
    target = str(record.get("target") or "unknown-target")
    return [
        {
            "index": 0,
            "channel": "workflow-observe-sim",
            "level": "info",
            "message": f"observe preflight accepted for {target} via {backend}",
        },
        {
            "index": 1,
            "channel": "workflow-observe-sim",
            "level": "info",
            "message": "bounded no-hardware observation sample",
        },
    ]


def find_child_token(plan: dict[str, Any], action: str) -> dict[str, Any]:
    for child in plan.get("child_safety_tokens", []):
        if isinstance(child, dict) and child.get("action") == action:
            return child
    return {}


def consume_child_token(root: Path, *, plan: dict[str, Any], child: dict[str, Any], backend: str) -> dict[str, Any]:
    token = str(child.get("token") or "")
    if not token:
        return {"status": "blocked-missing-child-token", "consumed": False}
    child_plan = {
        **plan,
        "action": child.get("action", ""),
        "hardware_side_effect": False,
        "controlled_local_action": False,
        "confirmation_record": {
            **(plan.get("confirmation_record") or {}),
            "child_action": child.get("action", ""),
        },
    }
    audit = hardware_action_audit.consume_token(root, token=token, plan=child_plan, backend=backend)
    return dict(audit)


def verify_artifact_hash(record: dict[str, Any], *, root: Path) -> dict[str, Any]:
    expected = str(record.get("artifact_hash") or "")
    artifact = str(record.get("artifact") or "")
    if not expected or not artifact:
        return {"status": "ok", "message": ""}
    path = Path(artifact)
    if not path.is_absolute():
        path = root / path
    if not path.exists():
        return {"status": "blocked-artifact-missing", "message": f"confirmed artifact is missing: {artifact}", "artifact": artifact}
    actual = hardware_action_plan.artifact_sha256(root, str(path))
    if actual != expected:
        return {
            "status": "blocked-artifact-hash-mismatch",
            "message": "firmware artifact hash no longer matches the confirmed plan",
            "artifact": str(path),
            "expected_sha256": expected,
            "actual_sha256": actual,
        }
    return {"status": "ok", "message": "", "artifact": str(path), "sha256": actual}


def parse_json_output(text: str) -> dict[str, Any]:
    text = text.strip()
    if not text:
        return {}
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return dict(data) if isinstance(data, dict) else {}


def render_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# Hardware Action Execution Result",
        "",
        f"- Action: `{result.get('action', '')}`",
        f"- Status: `{result.get('status', '')}`",
        f"- Backend: `{result.get('backend', '')}`",
        f"- Executed: {result.get('executed', False)}",
        f"- Hardware side effect: {result.get('hardware_side_effect', False)}",
    ]
    if result.get("summary"):
        lines.extend(["", result["summary"]])
    if result.get("next_actions"):
        lines.extend(["", "## Next Actions", ""])
        for item in result["next_actions"]:
            lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Execute a confirmation-token hardware action plan")
    parser.add_argument("--plan", required=True, help="JSON plan generated by plan-action --json --out")
    parser.add_argument("--confirm-token", required=True)
    parser.add_argument("--backend", default="")
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    result = execute_plan(load_plan(Path(args.plan)), token=args.confirm_token, backend=args.backend)
    content = json.dumps(result, ensure_ascii=False, indent=2) if args.as_json else render_markdown(result)
    if args.out:
        safe_io.safe_write_text(Path(args.out), content, allowed_roots=runtime_context.allowed_write_roots())
    else:
        print(content)


if __name__ == "__main__":
    main()
