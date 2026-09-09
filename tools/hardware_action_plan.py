"""Create confirmation-gated plans for hardware-changing actions.

The planner never executes build, flash, erase, debug, reset, memory, or bus
actions. It produces a structured confirmation record that a future executor can
verify before touching hardware.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import runtime_context  # noqa: E402

EMBEDDED_DIR = runtime_context.embeddedskills_root()
if str(EMBEDDED_DIR) not in sys.path:
    sys.path.insert(0, str(EMBEDDED_DIR))

import safe_io  # noqa: E402
import safety_gate  # noqa: E402

HARDWARE_ACTIONS = {
    "flash",
    "erase",
    "debug",
    "reset",
    "halt",
    "resume",
    "write-memory",
    "send-can",
    "send-uart",
    "network-scan",
    "build-flash",
    "build-debug",
    "observe",
    "capture-network",
    "can-observe",
    "network-ping",
    "serial-mux",
    "ssh-exec",
    "ssh-transfer",
    "ssh-tunnel",
    "swo",
}

CONTROLLED_LOCAL_ACTIONS = {"build"}
SAFE_ACTIONS = {"build", "classify-log", "inspect", "detect"}
SUPPORTED_ACTIONS = HARDWARE_ACTIONS | SAFE_ACTIONS

COMMON_REQUIRED = ["target", "probe", "voltage", "current_limit", "recovery"]
FLASH_REQUIRED = [*COMMON_REQUIRED, "erase_scope"]
ERASE_REQUIRED = [*COMMON_REQUIRED, "erase_scope"]
DEBUG_REQUIRED = [*COMMON_REQUIRED]
BUS_REQUIRED = ["target", "probe", "voltage", "current_limit", "external_loads", "recovery"]
TOKEN_FIELDS = [
    "action",
    "root",
    "plan_id",
    "created_at",
    "target",
    "probe",
    "voltage",
    "current_limit",
    "erase_scope",
    "recovery",
    "external_loads",
    "artifact",
    "artifact_hash",
    "backend",
]


def normalize_action(action: str) -> str:
    return action.strip().lower().replace("_", "-")


def required_inputs(action: str) -> list[str]:
    action = normalize_action(action)
    if action not in SUPPORTED_ACTIONS:
        return []
    if action in {"flash", "build-flash"}:
        return FLASH_REQUIRED
    if action == "erase":
        return ERASE_REQUIRED
    if action in {"debug", "build-debug", "observe", "reset", "halt", "resume", "write-memory"}:
        return DEBUG_REQUIRED
    if action in {
        "can-observe",
        "capture-network",
        "network-ping",
        "network-scan",
        "send-can",
        "send-uart",
        "serial-mux",
        "ssh-exec",
        "ssh-transfer",
        "ssh-tunnel",
    }:
        return BUS_REQUIRED
    if action in SAFE_ACTIONS:
        return []
    return COMMON_REQUIRED


def plan_action(
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
    action = normalize_action(action)
    root = root.resolve()
    if action not in SUPPORTED_ACTIONS:
        return {
            "schema_version": 1,
            "status": "blocked-unsupported-action",
            "root": str(root),
            "action": action,
            "hardware_side_effect": True,
            "requires_user_confirmation": True,
            "missing_inputs": [],
            "confirmation_record": {},
            "blocked_actions": ["Unsupported action names are blocked by default."],
            "preflight_checks": [],
            "next_actions": ["Use a supported action name or add an explicit policy before planning execution."],
        }
    values = {
        "target": target,
        "probe": probe,
        "voltage": voltage,
        "current_limit": current_limit,
        "erase_scope": erase_scope,
        "recovery": recovery,
        "external_loads": external_loads,
        "artifact": artifact,
        "artifact_hash": artifact_sha256(root, artifact),
        "backend": backend,
    }
    missing = [name for name in required_inputs(action) if not values.get(name)]
    hardware_side_effect = action in HARDWARE_ACTIONS
    controlled_local_action = action in CONTROLLED_LOCAL_ACTIONS
    value_safety = safety_gate.evaluate_value_safety(action, values)
    status = "ready-for-user-confirmation"
    if missing:
        status = "blocked-missing-safety-input"
    elif value_safety["blocks"]:
        status = "blocked-unsafe-safety-value"
    elif not hardware_side_effect and not controlled_local_action:
        status = "ready-safe-action"

    created_at = datetime.now(timezone.utc).isoformat()
    confirmation_record = {
        "plan_id": plan_id(action, root, values, created_at),
        "root": str(root),
        "target": target,
        "probe": probe,
        "voltage": voltage,
        "current_limit": current_limit,
        "erase_scope": erase_scope,
        "recovery": recovery,
        "external_loads": external_loads or "unknown",
        "artifact": artifact,
        "artifact_hash": values["artifact_hash"],
        "backend": backend,
        "created_at": created_at,
    }
    token = ""
    if (hardware_side_effect or controlled_local_action) and not missing and not value_safety["blocks"]:
        token = confirmation_token(action, confirmation_record)

    return {
        "schema_version": 1,
        "status": status,
        "root": str(root),
        "action": action,
        "hardware_side_effect": hardware_side_effect,
        "controlled_local_action": controlled_local_action,
        "requires_user_confirmation": hardware_side_effect or controlled_local_action,
        "missing_inputs": missing,
        "value_safety": value_safety,
        "confirmation_record": confirmation_record,
        "confirmation_token": token,
        "child_safety_tokens": child_safety_tokens(action, confirmation_record) if token else [],
        "token_policy": token_policy(action, hardware_side_effect, controlled_local_action),
        "execution_package": execution_package(action, confirmation_record) if token else {},
        "blocked_actions": blocked_actions(action),
        "preflight_checks": preflight_checks(action),
        "next_actions": next_actions(status, action),
    }


def token_payload(action: str, record: dict[str, Any]) -> dict[str, str]:
    payload = {"action": normalize_action(action)}
    for key in TOKEN_FIELDS:
        if key == "action":
            continue
        payload[key] = str(record.get(key) or "")
    return payload


def plan_id(action: str, root: Path, values: dict[str, str], created_at: str) -> str:
    payload = {
        "action": normalize_action(action),
        "root": str(root),
        "created_at": created_at,
        **{key: str(value or "") for key, value in values.items()},
    }
    raw = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return "hwp-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def confirmation_token(action: str, record: dict[str, Any]) -> str:
    payload = json.dumps(token_payload(action, record), ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return "hwc1-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def artifact_sha256(root: Path, artifact: str) -> str:
    if not artifact:
        return ""
    path = Path(artifact)
    if not path.is_absolute():
        path = root / path
    try:
        resolved = path.resolve()
    except OSError:
        return ""
    if not resolved.is_file():
        return ""
    hasher = hashlib.sha256()
    with resolved.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def child_safety_actions(action: str) -> list[str]:
    action = normalize_action(action)
    table = {
        "build-flash": ["flash"],
        "build-debug": ["debug"],
        "observe": ["observe"],
        "flash": ["flash"],
        "erase": ["erase"],
        "debug": ["debug"],
        "reset": ["reset"],
        "halt": ["halt"],
        "resume": ["go"],
        "write-memory": ["write-memory"],
        "send-can": ["send-can"],
        "send-uart": ["send-uart"],
        "network-scan": ["network-scan"],
        "capture-network": ["capture-network"],
        "can-observe": ["can-observe"],
        "network-ping": ["network-ping"],
        "serial-mux": ["serial-mux"],
        "ssh-exec": ["ssh-exec"],
        "ssh-transfer": ["ssh-transfer"],
        "ssh-tunnel": ["ssh-tunnel"],
        "swo": ["swo"],
    }
    return table.get(action, [])


def safety_record(record: dict[str, Any]) -> dict[str, str]:
    return {
        "target": str(record.get("target") or ""),
        "probe": str(record.get("probe") or ""),
        "voltage": str(record.get("voltage") or ""),
        "current_limit": str(record.get("current_limit") or ""),
        "erase_scope": str(record.get("erase_scope") or ""),
        "recovery": str(record.get("recovery") or ""),
        "external_loads": str(record.get("external_loads") or ""),
        "artifact": str(record.get("artifact") or ""),
        "artifact_hash": str(record.get("artifact_hash") or ""),
        "backend": str(record.get("backend") or ""),
    }


def child_safety_tokens(action: str, record: dict[str, Any]) -> list[dict[str, Any]]:
    children = []
    base_record = safety_record(record)
    for child_action in child_safety_actions(action):
        child_record = {**base_record, "backend": child_backend(child_action, base_record.get("backend", ""))}
        children.append(
            {
                "action": child_action,
                "token": safety_gate.confirmation_token(child_action, child_record),
                "expected_scope": safety_gate.token_payload(child_action, child_record),
                "consume_at": "embeddedskills backend",
            }
        )
    return children


def child_backend(child_action: str, backend: str) -> str:
    backend = normalize_action(backend)
    if child_action == "debug":
        return {
            "jlink": "jlink-gdb",
            "openocd": "openocd-gdb",
            "probe-rs": "probe-rs-gdb",
        }.get(backend, backend)
    if child_action == "observe":
        return {
            "jlink": "jlink-rtt",
            "openocd": "openocd-semihosting",
            "probe-rs": "probe-rs-rtt",
        }.get(backend, backend)
    return backend


def execution_package(action: str, record: dict[str, Any]) -> dict[str, Any]:
    children = child_safety_tokens(action, record)
    if not children:
        return {}
    parent_token = confirmation_token(action, record)
    workflow_token = workflow_parent_token(action, record)
    return {
        "schema_version": 1,
        "mode": "parent-plan-with-child-safety-tokens",
        "rules": [
            "Parent confirmation token authorizes the top-level plan.",
            "Workflow parent token is generated with the embeddedskills safety gate and is separate from the hardware-butler plan token.",
            "Child token is action-specific for embeddedskills and must be consumed by the backend that touches hardware.",
            "Do not reuse parent token for child flash/debug/observe commands.",
            "Review every argv entry before execution; the planner only prepares commands and never runs them.",
        ],
        "plan_token_hash": sha256_text(parent_token),
        "workflow_parent_token_hash": sha256_text(workflow_token),
        "workflow_command": workflow_command(action, record, workflow_token, children[0]),
        "manual_confirmation": manual_confirmation(record),
        "children": children,
    }


def workflow_parent_token(action: str, record: dict[str, Any]) -> str:
    return str(safety_gate.confirmation_token(normalize_action(action), safety_record(record)))


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest() if value else ""


def workflow_command(action: str, record: dict[str, Any], parent_token: str, child: dict[str, Any]) -> dict[str, Any]:
    workflow_action = workflow_action_name(action)
    if not workflow_action:
        return {}
    root = str(record.get("root") or "")
    backend = normalize_action(str(record.get("backend") or ""))
    argv = [
        sys.executable,
        str(runtime_context.embeddedskills_root() / "workflow" / "scripts" / "workflow_run.py"),
        workflow_action,
    ]
    if root:
        argv.extend(["--workspace", root])
    backend_flag = workflow_backend_flag(workflow_action)
    if backend_flag and backend and not backend.endswith("-sim"):
        argv.extend([backend_flag, backend])
    argv.extend(
        [
            "--confirm-token",
            parent_token,
            "--child-confirm-token",
            str(child.get("token") or ""),
            "--target",
            str(record.get("target") or ""),
            "--probe",
            str(record.get("probe") or ""),
            "--voltage",
            str(record.get("voltage") or ""),
            "--current-limit",
            str(record.get("current_limit") or ""),
            "--recovery",
            str(record.get("recovery") or ""),
            "--json",
        ]
    )
    optional_fields = [
        ("erase_scope", "--erase-scope"),
        ("external_loads", "--external-loads"),
        ("artifact", "--artifact"),
        ("artifact_hash", "--artifact-hash"),
    ]
    for key, flag in optional_fields:
        value = str(record.get(key) or "")
        if value:
            argv.extend([flag, value])
    child_hash = str((child.get("expected_scope") or {}).get("artifact_hash") or "")
    if child_hash:
        argv.extend(["--child-artifact-hash", child_hash])
    return {
        "kind": "workflow",
        "status": "prepared-not-executed",
        "argv": argv,
        "uses_parent_token": True,
        "uses_child_token": True,
        "hardware_side_effect_if_executed": True,
        "preconditions": [
            "User has confirmed the exact plan record and command argv.",
            "Target voltage, current limit, recovery path, and probe identity are physically verified.",
            "Firmware artifact path and hash still match the confirmation record.",
        ],
    }


def workflow_action_name(action: str) -> str:
    action = normalize_action(action)
    table = {
        "build-flash": "build-flash",
        "build-debug": "build-debug",
        "observe": "observe",
    }
    return table.get(action, "")


def workflow_backend_flag(workflow_action: str) -> str:
    table = {
        "build-flash": "--flash-backend",
        "build-debug": "--debug-backend",
        "observe": "--observe-backend",
    }
    return table.get(workflow_action, "")


def manual_confirmation(record: dict[str, Any]) -> dict[str, str]:
    return {
        "target": str(record.get("target") or ""),
        "probe": str(record.get("probe") or ""),
        "voltage": str(record.get("voltage") or ""),
        "current_limit": str(record.get("current_limit") or ""),
        "erase_scope": str(record.get("erase_scope") or ""),
        "recovery": str(record.get("recovery") or ""),
        "external_loads": str(record.get("external_loads") or ""),
        "artifact": str(record.get("artifact") or ""),
        "artifact_hash": str(record.get("artifact_hash") or ""),
        "backend": str(record.get("backend") or ""),
    }


def verify_confirmation_token(action: str, record: dict[str, Any], token: str) -> bool:
    return bool(token) and token == confirmation_token(action, record)


def token_policy(action: str, hardware_side_effect: bool, controlled_local_action: bool = False) -> dict[str, Any]:
    if not hardware_side_effect and not controlled_local_action:
        return {"required": False, "accepted_by": ["safe-runner"]}
    if controlled_local_action:
        return {
            "required": True,
            "accepted_by": ["hardware-action-executor"],
            "scope": normalize_action(action),
            "rules": [
                "Token is bound to plan id, creation time, action, target, backend, and optional artifact fields.",
                "Changing build target or backend requires regenerating the plan and obtaining user confirmation again.",
                "The executor records token consumption in `.embeddedskills/safety-log.jsonl`.",
                "Build may run local toolchains and write build outputs but must not touch connected hardware.",
            ],
        }
    return {
        "required": True,
        "accepted_by": ["hardware-action-executor", "embeddedskills safety gate"],
        "scope": normalize_action(action),
            "rules": [
            "Token is bound to plan id, creation time, action, target, probe, voltage, current limit, erase scope, recovery, artifact, and backend.",
            "Changing any bound field requires regenerating the plan and obtaining user confirmation again.",
            "The executor records token consumption in `.embeddedskills/safety-log.jsonl`.",
            "The token is not a substitute for physical preflight checks.",
        ],
    }


def blocked_actions(action: str) -> list[str]:
    if action in SAFE_ACTIONS:
        return []
    blocked = ["Do not execute this action from the safe discovery runner."]
    if action in {"erase", "flash", "build-flash"}:
        blocked.append("Do not mass erase or change option bytes without a separate highest-risk confirmation.")
    if action in {"debug", "build-debug", "observe", "reset", "halt", "resume"}:
        blocked.append("Do not change CPU execution state until target identity and recovery path are confirmed.")
    if action in {"can-observe", "capture-network", "network-ping", "network-scan", "send-can", "send-uart", "serial-mux", "ssh-exec", "ssh-transfer", "ssh-tunnel"}:
        blocked.append("Do not transmit onto a bus connected to external systems without explicit scope confirmation.")
    return blocked


def preflight_checks(action: str) -> list[str]:
    checks = [
        "Exact chip/board identity confirmed.",
        "Target voltage confirmed.",
        "Current limit confirmed.",
        "Recovery path confirmed.",
        "External loads identified or disconnected.",
    ]
    if action in {"flash", "erase", "build-flash"}:
        checks.extend(["Firmware artifact path/hash reviewed.", "Flash/erase scope reviewed."])
    if action in {"debug", "build-debug", "observe", "reset", "halt", "resume", "write-memory"}:
        checks.append("Debug probe identity and target readout reviewed.")
    if action == "observe":
        checks.append("Observation channel is bounded and will not transmit onto external buses.")
    return checks


def next_actions(status: str, action: str) -> list[str]:
    if status == "blocked-missing-safety-input":
        return ["Collect the missing safety inputs and regenerate the action plan."]
    if status == "blocked-unsafe-safety-value":
        return [
            "Fix the out-of-range safety value(s) listed under value_safety.blocks, then regenerate the plan.",
            "No confirmation token is issued while any safety value is physically implausible.",
        ]
    if status == "ready-safe-action":
        return ["Run the safe action through the existing read-only/discovery CLI path."]
    return [
        "Show this plan to the user for explicit confirmation.",
        "After confirmation, use the specific embeddedskills backend manually or through a future confirmation-token executor.",
        "Record the result in the project debug/bring-up log.",
    ]


def render_markdown(plan: dict[str, Any]) -> str:
    lines = [
        "# Hardware Action Plan",
        "",
        f"- Root: `{plan['root']}`",
        f"- Action: `{plan['action']}`",
        f"- Status: `{plan['status']}`",
        f"- Hardware side effect: {plan['hardware_side_effect']}",
        f"- Requires user confirmation: {plan['requires_user_confirmation']}",
        "",
        "## Missing Inputs",
        "",
    ]
    if plan["missing_inputs"]:
        for item in plan["missing_inputs"]:
            lines.append(f"- `{item}`")
    else:
        lines.append("- none")
    value_safety = plan.get("value_safety") or {}
    if value_safety.get("blocks") or value_safety.get("warnings"):
        lines.extend(["", "## Value Safety Checks", ""])
        for item in value_safety.get("blocks", []):
            lines.append(f"- [BLOCK] {item}")
        for item in value_safety.get("warnings", []):
            lines.append(f"- [WARN] {item}")
    lines.extend(["", "## Confirmation Record", ""])
    for key, value in plan["confirmation_record"].items():
        lines.append(f"- {key}: {value or 'unknown'}")
    lines.extend(["", "## Confirmation Token", ""])
    if plan.get("confirmation_token"):
        lines.append(f"- `{plan['confirmation_token']}`")
        lines.append("- Use only after the user confirms the exact action and physical preflight checks.")
    else:
        lines.append("- none")
    if plan.get("child_safety_tokens"):
        lines.extend(["", "## Child Safety Tokens", ""])
        for item in plan["child_safety_tokens"]:
            lines.append(f"- Action `{item['action']}`: `{item['token']}`")
            lines.append("  - Use only with the matching embeddedskills backend command.")
    command = (plan.get("execution_package") or {}).get("workflow_command") or {}
    if command.get("argv"):
        lines.extend(["", "## Prepared Workflow Command", ""])
        lines.append("- Status: prepared, not executed")
        lines.append("- Review the argv array and physical preflight checks before running it.")
        lines.extend(["", "```json", json.dumps(command["argv"], ensure_ascii=False, indent=2), "```"])
    lines.extend(["", "## Preflight Checks", ""])
    for item in plan["preflight_checks"]:
        lines.append(f"- [ ] {item}")
    lines.extend(["", "## Blocked Actions", ""])
    if plan["blocked_actions"]:
        for item in plan["blocked_actions"]:
            lines.append(f"- {item}")
    else:
        lines.append("- none")
    lines.extend(["", "## Next Actions", ""])
    for item in plan["next_actions"]:
        lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a confirmation-gated hardware action plan")
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

    plan = plan_action(
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
    content = json.dumps(plan, ensure_ascii=False, indent=2) if args.as_json else render_markdown(plan)
    if args.out:
        safe_io.safe_write_text(Path(args.out), content, allowed_roots=runtime_context.allowed_write_roots())
    else:
        print(content)


if __name__ == "__main__":
    main()
