"""Goal-driven workflow runner that orchestrates existing CLI commands into a state machine.

The runner persists state to .hardware-butler/workflow-state.json and supports resume.
Each stage calls an existing tool module function (no shell-out in-process) and
records evidence. Hardware-touching stages remain behind the existing safety gates;
the runner's job is sequencing, evidence propagation, and failure triage.
"""

from __future__ import annotations

import json
import os
import re as _re
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import backend_detector
import bench_runbook
import build_plan
import cube_detect
import cubemx_config_advisor
import firmware_intent_planner
import llm_client
import llm_config
import runtime_context
import safe_io
import vendor_adapters
import vendor_adapters.esp32
import vendor_adapters.msp430
import vendor_adapters.stm32
from safety_gate import check_goal_token, mint_goal_token

STATE_DIR = ".hardware-butler"
STATE_FILE = "workflow-state.json"
SCHEMA_VERSION = 1
MAX_STAGE_ATTEMPTS = 3

STAGE_ORDER_P0 = [
    "requirement-parse",
    "chip-selection",
    "datasheet-collect",
    "cubemx-config",
]

STAGE_ORDER_P1 = STAGE_ORDER_P0 + [
    "firmware-plan",
    "build",
    "flash",
    "verify-goal",
]

STAGE_ORDER_P2 = STAGE_ORDER_P0 + [
    "firmware-plan",
    "build",
    "flash",
    "debug-observe",
    "verify-goal",
]

STAGE_ORDER = STAGE_ORDER_P2


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _new_workflow_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    rand = secrets.token_hex(3)
    return f"wf-{stamp}-{rand}"


def workflow_state_path(root: Path) -> Path:
    return root.resolve() / STATE_DIR / STATE_FILE


def write_workflow_state(root: Path, state: dict[str, Any]) -> Path:
    path = workflow_state_path(root)
    safe_io.safe_write_text(
        path,
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        allowed_roots=runtime_context.allowed_write_roots(),
    )
    return path


def load_workflow_state(root: Path) -> dict[str, Any] | None:
    path = workflow_state_path(root)
    if not path.exists():
        return None
    loaded: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return loaded


@dataclass(frozen=True)
class WorkflowContext:
    part: str = ""
    feature: str = ""
    pin: str = ""
    function: str = ""
    instance: str = ""
    target: str = ""
    probe: str = ""
    backend: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "part": self.part,
            "feature": self.feature,
            "pin": self.pin,
            "function": self.function,
            "instance": self.instance,
            "target": self.target,
            "probe": self.probe,
            "backend": self.backend,
        }


@dataclass
class StageResult:
    status: str  # completed | blocked-needs-input | failed
    evidence: dict[str, Any] = field(default_factory=dict)
    error: str = ""


def init_workflow(
    root: Path,
    *,
    intent: str,
    goal: str,
    context: WorkflowContext,
) -> dict[str, Any]:
    root = root.resolve()
    wf_id = _new_workflow_id()
    stages = [
        {
            "id": sid,
            "title": _stage_title(sid),
            "status": "pending",
            "attempts": 0,
        }
        for sid in STAGE_ORDER
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "workflow_id": wf_id,
        "intent": intent,
        "goal": goal,
        "root": str(root),
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "status": "running",
        "current_stage": STAGE_ORDER[0],
        "context": context.to_dict(),
        "stages": stages,
    }


def _stage_title(stage_id: str) -> str:
    return {
        "requirement-parse": "需求解析",
        "chip-selection": "芯片/开发板选型与验证",
        "datasheet-collect": "芯片资料收集与解析",
        "cubemx-config": "CubeMX 引脚/外设配置",
        "firmware-plan": "固件实现计划",
        "build": "构建计划生成",
        "flash": "烧录门控计划生成",
        "debug-observe": "调试观测 (sim 模式)",
        "verify-goal": "目标达成验证",
    }.get(stage_id, stage_id)


def _reset_optimize_loop_stages(state: dict[str, Any]) -> None:
    """Reset firmware-plan through verify-goal to pending for optimize-loop retry.

    Preserves attempts counters so MAX_STAGE_ATTEMPTS still bounds total tries.
    Clears evidence so the retry starts fresh (the prior plan may have been wrong).
    """
    optimize_stages = {"firmware-plan", "build", "flash", "debug-observe", "verify-goal"}
    for stage in state["stages"]:
        if stage["id"] in optimize_stages:
            stage["status"] = "pending"
            stage["evidence"] = {}
            stage["error"] = ""
            stage.pop("started_at", None)
            stage.pop("finished_at", None)


def _llm_analyze_failure_and_patch(root: Path, state: dict[str, Any], failed_stage: dict[str, Any]) -> dict[str, Any]:
    """Call LLM to analyze a failed stage and apply patch_fields to context.

    Returns the analysis result. If patch_fields are present, mutates
    state["context"] so the next firmware-plan attempt uses the suggested
    pin/function/etc. For claude-code provider this returns pending; the host
    agent must write the response and the runner re-enters verify-goal next pass.
    """
    config = llm_config.load_config(root)
    if not llm_config.is_configured(config):
        return {"status": "no-llm"}
    task_id = f"fix-{state['workflow_id']}-{failed_stage['id']}-{failed_stage.get('attempts', 0)}"
    system, prompt = llm_client.analyze_failure_prompt(
        stage_id=failed_stage["id"],
        error=failed_stage.get("error", ""),
        evidence=failed_stage.get("evidence", {}),
        goal=state.get("goal", ""),
    )
    result = llm_client.call_llm(root, config, task_id=task_id, prompt=prompt, system=system)
    if result.get("status") == "ok":
        parsed = _parse_llm_json(result["text"])
        if parsed and isinstance(parsed.get("patch_fields"), dict):
            for key in ("feature", "function", "pin", "instance", "part"):
                if parsed["patch_fields"].get(key):
                    state["context"][key] = str(parsed["patch_fields"][key]).strip()
        return {"status": "ok", "analysis": parsed}
    return dict(result)


def run_workflow(root: Path, state: dict[str, Any]) -> dict[str, Any]:
    """Execute pending stages until blocked, failed, or all complete.

    Mutates and returns `state`. Persists to workflow-state.json after each stage.

    optimize-loop: when verify-goal fails on unmet signals and attempts <
    MAX_STAGE_ATTEMPTS, reset firmware-plan through verify-goal to pending and
    restart the iteration. Other failures (missing evidence, safety block)
    return immediately as they need user input.
    """
    root = root.resolve()
    while True:
        progress = False
        for stage in state["stages"]:
            if stage["status"] == "completed":
                continue
            if stage["attempts"] >= MAX_STAGE_ATTEMPTS:
                state["status"] = "failed"
                state["updated_at"] = _now_iso()
                write_workflow_state(root, state)
                return state
            stage["attempts"] += 1
            stage["started_at"] = _now_iso()
            state["current_stage"] = stage["id"]
            state["status"] = "running"
            state["updated_at"] = _now_iso()
            write_workflow_state(root, state)
            ctx = WorkflowContext(**{k: state["context"].get(k, "") for k in WorkflowContext().__dict__})
            try:
                result = _dispatch_stage(stage["id"], root, ctx, state)
            except Exception as exc:  # noqa: BLE001 - surface as failed stage
                result = StageResult(status="failed", error=f"{type(exc).__name__}: {exc}")
            stage["finished_at"] = _now_iso()
            stage["status"] = result.status
            stage["error"] = result.error
            stage["evidence"] = result.evidence
            state["updated_at"] = _now_iso()
            write_workflow_state(root, state)
            progress = True
            if result.status != "completed":
                if stage["id"] == "verify-goal" and result.status == "failed" and stage["attempts"] < MAX_STAGE_ATTEMPTS:
                    analysis = _llm_analyze_failure_and_patch(root, state, stage)
                    if analysis.get("status") == "pending":
                        state["status"] = "blocked-needs-input"
                        state["updated_at"] = _now_iso()
                        write_workflow_state(root, state)
                        return state
                    state["status"] = "retrying"
                    state["updated_at"] = _now_iso()
                    state["last_analysis"] = analysis
                    _reset_optimize_loop_stages(state)
                    write_workflow_state(root, state)
                    break
                state["status"] = result.status
                state["updated_at"] = _now_iso()
                write_workflow_state(root, state)
                return state
        else:
            state["status"] = "completed"
            state["current_stage"] = ""
            state["updated_at"] = _now_iso()
            write_workflow_state(root, state)
            return state
        if not progress:
            return state
    return state


def _dispatch_stage(
    stage_id: str,
    root: Path,
    ctx: WorkflowContext,
    state: dict[str, Any],
) -> StageResult:
    if stage_id == "requirement-parse":
        return _stage_requirement_parse(root, ctx, state)
    if stage_id == "chip-selection":
        return _stage_chip_selection(root, ctx, state)
    if stage_id == "datasheet-collect":
        return _stage_datasheet_collect(root, ctx, state)
    if stage_id == "cubemx-config":
        return _stage_cubemx_config(root, ctx, state)
    if stage_id == "firmware-plan":
        return _stage_firmware_plan(root, ctx, state)
    if stage_id == "build":
        return _stage_build(root, ctx, state)
    if stage_id == "flash":
        return _stage_flash(root, ctx, state)
    if stage_id == "debug-observe":
        return _stage_debug_observe(root, ctx, state)
    if stage_id == "verify-goal":
        return _stage_verify_goal(root, ctx, state)
    return StageResult(status="failed", error=f"unknown stage: {stage_id}")


def _parse_llm_json(text: str) -> dict[str, Any] | None:
    """Extract a JSON object from an LLM response that may contain prose."""
    match = _re.search(r"\{[^{}]*\}", text, _re.DOTALL)
    if not match:
        return None
    try:
        parsed: dict[str, Any] = json.loads(match.group(0))
        return parsed
    except ValueError:
        return None


def _stage_requirement_parse(
    root: Path,
    ctx: WorkflowContext,
    state: dict[str, Any],
) -> StageResult:
    """Parse goal + context flags into structured requirements.

    Uses the LLM to parse natural-language goal when context flags are absent.
    If LLM is pending (claude-code provider), returns blocked-needs-input so
    the host agent can execute the LLM task and resume.
    """
    goal = state.get("goal", "")
    requirements: dict[str, Any] = {
        "feature": ctx.feature,
        "function": ctx.function or "gpio-output",
        "pin": ctx.pin.upper(),
        "instance": ctx.instance.upper(),
        "part": ctx.part,
        "goal": goal,
    }

    llm_task_id = f"intent-{state['workflow_id']}-{state.get('updated_at', '')[-8:]}"
    if goal and not ctx.feature:
        config = llm_config.load_config(root)
        if llm_config.is_configured(config):
            system, prompt = llm_client.parse_intent_prompt(goal)
            result = llm_client.call_llm(
                root, config, task_id=llm_task_id, prompt=prompt, system=system
            )
            if result.get("status") == "ok":
                parsed = _parse_llm_json(result["text"])
                if parsed:
                    for key in ("feature", "function", "pin", "instance", "part"):
                        if parsed.get(key):
                            requirements[key] = str(parsed[key]).strip()
            elif result.get("status") == "pending":
                return StageResult(
                    status="blocked-needs-input",
                    evidence={
                        "llm_task_id": llm_task_id,
                        "instruction": "host agent must execute llm-task and write response, then resume",
                    },
                    error="LLM intent parse pending; run workflow-llm-tasks to see pending tasks",
                )

    missing: list[str] = []
    if not requirements["feature"]:
        missing.append("feature")
    if missing:
        return StageResult(
            status="blocked-needs-input",
            evidence={"missing": missing, "parsed_requirements": requirements},
            error="missing required requirement fields: " + ", ".join(missing),
        )
    return StageResult(
        status="completed",
        evidence={"parsed_requirements": requirements},
    )


def _stage_chip_selection(
    root: Path,
    ctx: WorkflowContext,
    state: dict[str, Any],
) -> StageResult:
    """Verify or select chip AND detect host backends. The runner does not
    hardcode STM32/Keil — it probes the project artifacts and host tooling to
    decide which build/flash/observe backends to use."""
    detection = cube_detect.detect(root)
    projects = detection.get("cubemx_projects", []) or []
    primary_mcu = projects[0].get("mcu", {}) if projects else {}
    detected_part = primary_mcu.get("name", "") if isinstance(primary_mcu, dict) else ""
    if not ctx.part and not detected_part:
        return StageResult(
            status="blocked-needs-input",
            evidence={"detected": detection},
            error="no chip specified and CubeMX detection found none",
        )
    selected = ctx.part or detected_part
    backends = backend_detector.detect_backends(root, context_probe=ctx.probe)
    return StageResult(
        status="completed",
        evidence={
            "selected_part": selected,
            "detected_part": detected_part,
            "detection": detection,
            "backends": backends,
        },
    )


def _stage_datasheet_collect(
    root: Path,
    ctx: WorkflowContext,
    state: dict[str, Any],
) -> StageResult:
    """Collect chip datasheet. Calls chip_dossier if host has search APIs
    configured; otherwise generates a search-task bundle for the host agent
    (Claude with web_search) to execute via workflow-search command.

    The search-task bundle is written to .hardware-butler/search-tasks.json.
    The host agent reads it, performs web_search + open_url, writes results to
    .hardware-butler/datasheet-evidence.json, then the runner is resumed.
    """
    chip_stage = next((s for s in state["stages"] if s["id"] == "chip-selection"), None)
    if not chip_stage or chip_stage["status"] != "completed":
        return StageResult(status="failed", error="chip-selection stage did not complete")
    part = chip_stage.get("evidence", {}).get("selected_part", "")
    if not part:
        return StageResult(status="failed", error="no selected_part in chip-selection evidence")

    evidence_path = root / ".hardware-butler" / "datasheet-evidence.json"
    if evidence_path.exists():
        import json as _json
        try:
            evidence = _json.loads(evidence_path.read_text(encoding="utf-8"))
            return StageResult(
                status="completed",
                evidence={
                    "part": part,
                    "datasheet_fetched": True,
                    "evidence_source": "host-agent-web-search",
                    "evidence": evidence,
                },
            )
        except (OSError, ValueError):
            pass

    try:
        import chip_dossier
        part_normalized = chip_dossier.normalize_part(part)
        out_dir = root / "docs" / "chip" / part_normalized
        out_dir.mkdir(parents=True, exist_ok=True)
        dossier = chip_dossier.create_dossier(part_normalized, out_dir, board="", sources=[])
        has_real_sources = bool(dossier.get("sources"))
        if has_real_sources:
            return StageResult(
                status="completed",
                evidence={
                    "part": part_normalized,
                    "datasheet_fetched": True,
                    "evidence_source": "chip-dossier-vendor-hints",
                    "dossier_path": str(out_dir),
                    "dossier": dossier,
                },
            )
    except Exception:  # noqa: BLE001
        pass

    search_task_path = root / ".hardware-butler" / "search-tasks.json"
    search_task_path.parent.mkdir(parents=True, exist_ok=True)
    search_task = {
        "schema_version": 1,
        "workflow_id": state["workflow_id"],
        "part": part,
        "queries": [
            f"{part} datasheet pdf",
            f"{part} reference manual",
            f"{part} development board schematic",
            f"{part} pinout alternate functions",
        ],
        "evidence_output_path": str(evidence_path),
        "instruction": (
            "Use web_search for each query, open_url to fetch the most relevant "
            "datasheet URL, extract key electrical parameters (Vdd, package, "
            "peripherals, pin alternate functions) and write a JSON object to "
            "evidence_output_path with shape: "
            '{"part": "...", "sources": [{"url": "...", "title": "...", "type": "datasheet|manual|board", "extracted": {...}}], '
            '"parameters": {...}, "pin_functions": {...}}. Then resume the workflow.'
        ),
    }
    import json as _json2
    search_task_path.write_text(
        _json2.dumps(search_task, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return StageResult(
        status="blocked-needs-input",
        evidence={
            "part": part,
            "datasheet_fetched": False,
            "search_task_path": str(search_task_path),
            "instruction": "host agent must run workflow-search to fetch datasheet, then resume",
        },
        error="datasheet requires host-agent web search; run: python tools/hardware_butler.py workflow-search --root <project>",
    )


def _stage_cubemx_config(
    root: Path,
    ctx: WorkflowContext,
    state: dict[str, Any],
) -> StageResult:
    """Run advise in-process. patch-ioc stays dry-run by default."""
    req_stage = next((s for s in state["stages"] if s["id"] == "requirement-parse"), None)
    if not req_stage:
        return StageResult(status="failed", error="requirement-parse stage missing")
    reqs = req_stage["evidence"]["parsed_requirements"]
    pin = reqs["pin"]
    function = reqs["function"]
    if not pin or not function:
        return StageResult(
            status="blocked-needs-input",
            error="advise-pin requires --pin and --function",
        )
    try:
        advice = cubemx_config_advisor.advise(root, pin=pin, function=function, pin_evidence="")
    except Exception as exc:  # noqa: BLE001
        return StageResult(status="failed", error=f"advise failed: {exc}")
    status = "completed" if advice.get("status") in {"ok", "needs-configuration"} else "failed"
    return StageResult(
        status=status,
        evidence={"advice": advice},
        error=advice.get("error", "") if status == "failed" else "",
    )


def _requirement_evidence(state: dict[str, Any]) -> dict[str, Any] | None:
    req_stage = next((s for s in state["stages"] if s["id"] == "requirement-parse"), None)
    if not req_stage or req_stage["status"] != "completed":
        return None
    parsed: dict[str, Any] = req_stage["evidence"].get("parsed_requirements") or {}
    return parsed


def _stage_firmware_plan(
    root: Path,
    ctx: WorkflowContext,
    state: dict[str, Any],
) -> StageResult:
    """Generate FreeRTOS firmware implementation plan (plan-only, no code edits)."""
    reqs = _requirement_evidence(state)
    if not reqs:
        return StageResult(status="failed", error="requirement-parse stage did not complete")
    feature = reqs.get("feature", "")
    function = reqs.get("function", "gpio-output")
    pin = reqs.get("pin", "")
    if not feature:
        return StageResult(status="blocked-needs-input", error="firmware-plan requires a feature name")
    try:
        plan = firmware_intent_planner.plan_implementation(
            root, feature=feature, pin=pin, function=function, rtos=True
        )
    except Exception as exc:  # noqa: BLE001
        return StageResult(status="failed", error=f"firmware-plan failed: {exc}")
    status = "completed" if plan.get("status", "").startswith("plan-only") else "failed"
    return StageResult(
        status=status,
        evidence={"firmware_plan": plan},
        error=plan.get("error", "") if status == "failed" else "",
    )


def _get_vendor_adapter(state: dict[str, Any]) -> vendor_adapters.VendorAdapter | None:
    """Resolve the vendor adapter from chip-selection evidence or context part."""
    chip_stage = next((s for s in state["stages"] if s["id"] == "chip-selection"), None)
    if chip_stage and chip_stage["status"] == "completed":
        ev = chip_stage.get("evidence", {})
        adapter_info = ev.get("backends", {}).get("vendor_adapter", {})
        family = adapter_info.get("family", "")
        if family:
            return vendor_adapters.get_adapter(family)
    part = state.get("context", {}).get("part", "")
    if part:
        family = vendor_adapters.detect_family(part)
        if family:
            return vendor_adapters.get_adapter(family)
    return None


def _run_subprocess(cmd: list[str], *, timeout_s: int = 120) -> dict[str, Any]:
    """Run an argv list via subprocess, return structured result."""
    import subprocess
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s, check=False)
        status = "ok" if proc.returncode == 0 else "error"
        return {
            "status": status,
            "returncode": proc.returncode,
            "stdout": proc.stdout[-4000:],
            "stderr": proc.stderr[-4000:],
        }
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "returncode": -1, "stdout": "", "stderr": f"timeout after {timeout_s}s"}
    except FileNotFoundError as exc:
        return {"status": "error", "returncode": -1, "stdout": "", "stderr": f"tool not found: {exc.filename}"}
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "returncode": -1, "stdout": "", "stderr": str(exc)}


def _run_embeddedskills_script(script_rel_path: str, args: list[str], *, timeout_s: int = 120) -> dict[str, Any]:
    """Run an embeddedskills script via subprocess, return structured result.

    Looks up the script under embeddedskills_root(). Returns:
      {"status": "ok"|"error"|"timeout", "returncode": int, "stdout": str, "stderr": str}
    """
    import subprocess
    es_root = runtime_context.embeddedskills_root()
    script_path = es_root / script_rel_path
    if not script_path.exists():
        return {"status": "error", "returncode": -1, "stdout": "", "stderr": f"script not found: {script_path}"}
    cmd = ["python", str(script_path)] + args
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s, check=False)
        status = "ok" if proc.returncode == 0 else "error"
        return {
            "status": status,
            "returncode": proc.returncode,
            "stdout": proc.stdout[-4000:],
            "stderr": proc.stderr[-4000:],
        }
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "returncode": -1, "stdout": "", "stderr": f"timeout after {timeout_s}s"}
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "returncode": -1, "stdout": "", "stderr": str(exc)}


def _stage_build(
    root: Path,
    ctx: WorkflowContext,
    state: dict[str, Any],
) -> StageResult:
    """Generate build plan and execute the real build.

    P3: prefers the vendor adapter's build command (which uses the native
    toolchain for the detected chip family — arm-none-eabi-gcc for STM32,
    idf.py for ESP32, msp430-gcc for MSP430). Falls back to embeddedskills
    scripts if no adapter matches.
    """
    try:
        plan = build_plan.generate_plan(root)
    except Exception as exc:  # noqa: BLE001
        return StageResult(status="failed", error=f"build-plan failed: {exc}")
    if not plan.get("steps"):
        return StageResult(status="failed", error="build plan generated no steps", evidence={"build_plan": plan})

    adapter = _get_vendor_adapter(state)
    if adapter:
        tools = adapter.detect_tools()
        build_tool_available = any(tools.values())
        if not build_tool_available:
            return StageResult(
                status="completed",
                evidence={"build_plan": plan, "build_executed": False, "reason": f"no {adapter.family} build tools on host; plan-only", "adapter": adapter.to_dict()},
            )
        build_ctx = {
            "project_root": str(root),
            "target": state.get("context", {}).get("target", ""),
            "elf": "build/firmware.elf",
        }
        cmd = adapter.build_command(build_ctx)
        result = _run_subprocess(cmd, timeout_s=300)
        build_log = result.get("stdout", "") + "\n" + result.get("stderr", "")
        build_executed = result["status"] == "ok"
        return StageResult(
            status="completed",
            evidence={
                "build_plan": plan,
                "build_executed": build_executed,
                "build_backend": adapter.family,
                "build_command": cmd,
                "build_result": result,
                "build_log": build_log[-4000:],
            },
            error="",
        )

    chip_stage = next((s for s in state["stages"] if s["id"] == "chip-selection"), None)
    backends = (chip_stage or {}).get("evidence", {}).get("backends", {}) if chip_stage else {}
    build_backend = backends.get("backends", {}).get("build", "unknown") if isinstance(backends.get("backends"), dict) else "unknown"
    if build_backend == "unknown":
        return StageResult(
            status="completed",
            evidence={"build_plan": plan, "build_executed": False, "reason": "no build tool on host; plan-only"},
        )

    script_map = {
        "keil": "keil/scripts/keil_build.py",
        "gcc": "gcc/scripts/gcc_build.py",
        "eide": "eide/scripts/eide_build.py",
    }
    script = script_map.get(build_backend)
    if not script:
        return StageResult(
            status="completed",
            evidence={"build_plan": plan, "build_executed": False, "reason": f"no script mapping for {build_backend}"},
        )
    args = ["--workspace", str(root), "--action", "build"]
    result = _run_embeddedskills_script(script, args, timeout_s=180)
    build_log = result.get("stdout", "") + "\n" + result.get("stderr", "")
    build_executed = result["status"] == "ok"
    return StageResult(
        status="completed",
        evidence={
            "build_plan": plan,
            "build_executed": build_executed,
            "build_backend": build_backend,
            "build_result": result,
            "build_log": build_log[-4000:],
        },
        error="",
    )


def _stage_flash(
    root: Path,
    ctx: WorkflowContext,
    state: dict[str, Any],
) -> StageResult:
    """Generate a no-hardware bench runbook + confirmation-gated action plan.

    Does NOT execute real flashing. The runbook aggregates readiness, action
    plan, preflight, and a workflow_run.py --dry-run subprocess. Real flash
    stays behind HARDWARE_BUTLER_ENABLE_REAL_FLASH + confirmation token.

    On first entry to this stage for a workflow, mints a goal_token that
    authorises repeated build-flash/flash-debug within the same workflow_id,
    subject to max_uses and expires_at caps. Each stage entry consumes one
    use, modelling the "flash -> observe -> reflash" loop without real
    hardware. Token plaintext stays in workflow-state.json for this slice
    (acceptable for P1; P2 will move plaintext to a session-kept secret).
    """
    chip_stage = next((s for s in state["stages"] if s["id"] == "chip-selection"), None)
    target = ""
    if chip_stage and chip_stage["status"] == "completed":
        target = chip_stage["evidence"].get("selected_part", "")
    try:
        runbook = bench_runbook.generate_runbook(
            root,
            action="build-flash",
            target=target,
            probe=ctx.probe,
            backend=ctx.backend,
        )
    except Exception as exc:  # noqa: BLE001
        return StageResult(status="failed", error=f"bench-runbook failed: {exc}")

    goal_token_record = state.get("goal_token")
    if not goal_token_record:
        minted = mint_goal_token(
            workflow_id=state["workflow_id"],
            scope="build-flash,flash-debug",
            max_uses=5,
            ttl_seconds=3600,
        )
        goal_token_record = {
            "token_hash": minted["token_hash"],
            "workflow_id": minted["workflow_id"],
            "scope": minted["scope"],
            "max_uses": minted["max_uses"],
            "expires_at": minted["expires_at"],
            "uses": 0,
            "_plaintext": minted["token"],
        }
        state["goal_token"] = goal_token_record

    check = check_goal_token(
        root,
        workflow_id=state["workflow_id"],
        token=goal_token_record["_plaintext"],
        record=goal_token_record,
        action="build-flash",
        consume=True,
    )
    if check.get("allowed"):
        goal_token_record["uses"] = check.get("uses", 0) + 1
    token_status = "valid" if check.get("allowed") else f"blocked:{check.get('error_code', 'unknown')}"

    status = "completed"
    if not runbook.get("action_plan"):
        status = "blocked-needs-input"
    if not check.get("allowed"):
        status = "failed"

    flash_executed = False
    flash_result: dict[str, Any] = {}
    if status == "completed" and os.environ.get("HARDWARE_BUTLER_ENABLE_REAL_FLASH") == "1":
        adapter = _get_vendor_adapter(state)
        if adapter:
            flash_ctx = {
                "target": target,
                "port": state.get("context", {}).get("probe", ""),
                "elf": "build/firmware.elf",
                "probe": ctx.probe,
            }
            cmd = adapter.flash_command(flash_ctx)
            if cmd:
                flash_result = _run_subprocess(cmd, timeout_s=120)
                flash_executed = flash_result["status"] == "ok"
                if not flash_executed:
                    status = "failed"
        if not flash_result:
            chip_stage = next((s for s in state["stages"] if s["id"] == "chip-selection"), None)
            backends = (chip_stage or {}).get("evidence", {}).get("backends", {}) if chip_stage else {}
            flash_backend = backends.get("backends", {}).get("flash", "unknown") if isinstance(backends.get("backends"), dict) else "unknown"
            script_map = {
                "openocd": "openocd/scripts/openocd_run.py",
                "jlink": "jlink/scripts/jlink_exec.py",
                "probe-rs": "probe-rs/scripts/probe_rs_exec.py",
            }
            script = script_map.get(flash_backend)
            if script:
                flash_args = ["--workspace", str(root), "--action", "flash"]
                if target:
                    flash_args.extend(["--target", target])
                if ctx.probe:
                    flash_args.extend(["--probe", ctx.probe])
                flash_result = _run_embeddedskills_script(script, flash_args, timeout_s=120)
                flash_executed = flash_result["status"] == "ok"
                if not flash_executed:
                    status = "failed"

    return StageResult(
        status=status,
        evidence={
            "runbook": runbook,
            "goal_token": {
                "token_hash": goal_token_record["token_hash"],
                "workflow_id": goal_token_record["workflow_id"],
                "scope": goal_token_record["scope"],
                "max_uses": goal_token_record["max_uses"],
                "expires_at": goal_token_record["expires_at"],
                "uses": goal_token_record["uses"],
                "status": token_status,
            },
            "flash_executed": flash_executed,
            "flash_result": flash_result,
        },
        error="" if status == "completed" else f"goal_token check failed: {check.get('reason', '')}",
    )


def _firmware_plan_evidence(state: dict[str, Any]) -> dict[str, Any] | None:
    stage = next((s for s in state["stages"] if s["id"] == "firmware-plan"), None)
    if not stage or stage["status"] != "completed":
        return None
    evidence: dict[str, Any] = stage["evidence"].get("firmware_plan") or {}
    return evidence


def _expected_signals(firmware_plan: dict[str, Any]) -> list[dict[str, str]]:
    """Extract expected observable signals from firmware-plan verification field.

    Each signal: {"kind": "led"|"uart"|"rtt"|"swo", "pin": "...", "description": "..."}
    """
    signals: list[dict[str, str]] = []
    for entry in firmware_plan.get("verification", []) or []:
        text = str(entry)
        lowered = text.lower()
        if "led" in lowered:
            signals.append({"kind": "led", "pin": "", "description": text})
        elif "uart" in lowered:
            signals.append({"kind": "uart", "pin": "", "description": text})
        elif "rtt" in lowered:
            signals.append({"kind": "rtt", "pin": "", "description": text})
        elif "swo" in lowered:
            signals.append({"kind": "swo", "pin": "", "description": text})
    pin_advice = firmware_plan.get("pin_advice") or {}
    if pin_advice.get("pin", {}).get("name"):
        name = pin_advice["pin"]["name"]
        signals.insert(0, {"kind": "led", "pin": name, "description": f"{name} toggles on firmware main loop"})
    return signals


def _stage_debug_observe(
    root: Path,
    ctx: WorkflowContext,
    state: dict[str, Any],
) -> StageResult:
    """Observe hardware signals. Uses real serial/RTT backend when a probe is
    available; falls back to sim mode otherwise.

    Real observation: if the host has a serial port configured (ctx.probe
    starts with "COM" or "/dev/tty") OR HARDWARE_BUTLER_ENABLE_REAL_FLASH=1
    with a jlink/openocd probe, runs the embeddedskills serial/jlink_rtt
    script for a short capture window and matches expected signals in the
    output. Otherwise sim mode.
    """
    plan = _firmware_plan_evidence(state)
    if plan is None:
        return StageResult(status="failed", error="firmware-plan stage did not complete")
    signals = _expected_signals(plan)
    if not signals:
        return StageResult(
            status="completed",
            evidence={
                "mode": "sim",
                "signals": [],
                "observations": [],
                "note": "firmware-plan declared no observable signals; verify-goal will fall back to evidence-completeness",
            },
        )

    real_capture = ""
    observe_mode = "sim"
    chip_stage = next((s for s in state["stages"] if s["id"] == "chip-selection"), None)
    backends = (chip_stage or {}).get("evidence", {}).get("backends", {}) if chip_stage else {}
    observe_backend = backends.get("backends", {}).get("observe", "unknown") if isinstance(backends.get("backends"), dict) else "unknown"
    enable_real = os.environ.get("HARDWARE_BUTLER_ENABLE_REAL_FLASH") == "1"
    if enable_real:
        adapter = _get_vendor_adapter(state)
        if adapter:
            observe_ctx = {
                "port": state.get("context", {}).get("probe", ""),
                "baud": "115200",
            }
            cmd = adapter.observe_command(observe_ctx)
            if cmd:
                observe_result = _run_subprocess(cmd, timeout_s=10)
                if observe_result["status"] == "ok":
                    real_capture = observe_result.get("stdout", "")
                    observe_mode = adapter.family
        elif observe_backend == "serial":
            serial_args = ["--workspace", str(root), "--action", "scan"]
            serial_result = _run_embeddedskills_script("serial/scripts/serial_scan.py", serial_args, timeout_s=20)
            if serial_result["status"] == "ok":
                real_capture = serial_result.get("stdout", "")
                observe_mode = "serial"
        elif observe_backend == "jlink-rtt":
            rtt_args = ["--workspace", str(root), "--action", "rtt-read"]
            rtt_result = _run_embeddedskills_script("jlink/scripts/jlink_rtt.py", rtt_args, timeout_s=20)
            if rtt_result["status"] == "ok":
                real_capture = rtt_result.get("stdout", "")
                observe_mode = "rtt"

    observations = []
    for sig in signals:
        if observe_mode != "sim" and real_capture:
            lowered = real_capture.lower()
            matched = sig.get("kind", "") in lowered or sig.get("pin", "").lower() in lowered
        else:
            matched = True
        observations.append({
            "signal": sig,
            "mode": observe_mode,
            "matched": matched,
            "sample": (real_capture[:500] if real_capture else f"simulated {sig['kind']} output for {sig.get('pin', 'n/a')}"),
        })
    return StageResult(
        status="completed",
        evidence={
            "mode": observe_mode,
            "signals": signals,
            "observations": observations,
            "hardware_observed": observe_mode != "sim",
            "capture": real_capture[:2000] if real_capture else "",
            "note": f"{observe_mode} mode observation",
        },
    )


def _stage_verify_goal(
    root: Path,
    ctx: WorkflowContext,
    state: dict[str, Any],
) -> StageResult:
    """Verify goal achievement by cross-checking goal text + firmware-plan
    verification signals + debug-observe observations.

    P2 verification: behavior-aware, not just evidence-complete. If goal text
    mentions "led" / "blink", requires debug-observe to have a matching led
    signal observation. On failure, returns status="failed" which triggers the
    optimize-loop retry (handled in run_workflow).
    """
    required = STAGE_ORDER[:-1]
    completed_stages = {s["id"]: s for s in state["stages"] if s["status"] == "completed"}
    missing = [sid for sid in required if sid not in completed_stages]
    if missing:
        return StageResult(
            status="failed",
            error=f"cannot verify goal; stages incomplete: {', '.join(missing)}",
        )

    goal = state.get("goal", "").lower()
    observe_stage = completed_stages.get("debug-observe", {})
    observe_ev = observe_stage.get("evidence", {}) if observe_stage else {}
    observations = observe_ev.get("observations", []) if isinstance(observe_ev, dict) else []
    signals = observe_ev.get("signals", []) if isinstance(observe_ev, dict) else []

    observed_kinds = {obs.get("signal", {}).get("kind", "") for obs in observations}

    goal_keywords: list[str] = []
    if "led" in goal or "blink" in goal:
        goal_keywords.append("led")
    if "uart" in goal:
        goal_keywords.append("uart")
    if "rtt" in goal:
        goal_keywords.append("rtt")
    if "swo" in goal:
        goal_keywords.append("swo")

    matched: list[str] = []
    unmet: list[str] = []
    if goal_keywords:
        for kw in goal_keywords:
            if kw in observed_kinds:
                matched.append(kw)
            else:
                unmet.append(kw)
    elif signals:
        verification_level = "signals-present"
    else:
        verification_level = "evidence-completeness"

    if unmet:
        return StageResult(
            status="failed",
            evidence={
                "goal": state.get("goal", ""),
                "goal_keywords": goal_keywords,
                "matched": matched,
                "unmet": unmet,
                "signals": signals,
                "observations": observations,
                "verification_level": "behavior-keyword",
                "note": "goal keywords not satisfied by observations; optimize-loop will retry",
            },
            error=f"unmet goal signals: {', '.join(unmet)}",
        )

    verification_level = "behavior-keyword" if goal_keywords else ("signals-present" if signals else "evidence-completeness")
    return StageResult(
        status="completed",
        evidence={
            "goal": state.get("goal", ""),
            "goal_keywords": goal_keywords,
            "matched": matched,
            "signals": signals,
            "observations": observations,
            "verification_level": verification_level,
            "evidence_chain": {sid: bool(completed_stages[sid].get("evidence")) for sid in required},
        },
    )


def workflow_summary(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "workflow_id": state["workflow_id"],
        "intent": state["intent"],
        "goal": state["goal"],
        "status": state["status"],
        "current_stage": state["current_stage"],
        "stages": [
            {"id": s["id"], "status": s["status"], "attempts": s["attempts"]}
            for s in state["stages"]
        ],
        "updated_at": state["updated_at"],
    }
