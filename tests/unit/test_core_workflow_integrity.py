"""Offline workflow recovery and fail-closed execution regressions."""

from pathlib import Path
from unittest.mock import Mock

import llm_codegen
import pytest
import workflow_runner as workflow


def _state(root):
    context = workflow.WorkflowContext(feature="led-blink", function="gpio-output", pin="PD12", part="STM32F407VGTx")
    state = workflow.init_workflow(root, intent="develop-feature", goal="LED blink", context=context)
    state["stages"][0].update(status="completed", evidence={"parsed_requirements": context.to_dict()})
    return context, state


def test_pending_failure_analysis_does_not_rerun_or_spend_attempt(tmp_path: Path, monkeypatch):
    _, state = _state(tmp_path)
    build = next(stage for stage in state["stages"] if stage["id"] == "build")
    build.update(status="failed", attempts=1, evidence={"llm_fix_pending": True, "llm_fix_task_id": "stable-fix"})
    state["stages"] = [build]
    dispatch = Mock(return_value=workflow.StageResult("failed", error="old error"))
    monkeypatch.setattr(workflow, "_dispatch_stage", dispatch)
    monkeypatch.setattr(workflow.llm_client, "read_response", lambda *args: None)
    monkeypatch.setattr(workflow, "_llm_analyze_failure_and_patch", lambda *args: {"status": "pending"})

    result = workflow.run_workflow(tmp_path, state)

    dispatch.assert_not_called()
    assert result["status"] == "blocked-needs-input"
    assert build["attempts"] == 1
    assert build["evidence"]["llm_fix_task_id"] == "stable-fix"


def test_waiting_for_input_does_not_exhaust_execution_attempts(tmp_path: Path, monkeypatch):
    _, state = _state(tmp_path)
    state["stages"] = [state["stages"][1]]
    dispatch = Mock(return_value=workflow.StageResult("blocked-needs-input", error="waiting"))
    monkeypatch.setattr(workflow, "_dispatch_stage", dispatch)

    for _ in range(workflow.MAX_STAGE_ATTEMPTS + 1):
        assert workflow.run_workflow(tmp_path, state)["status"] == "blocked-needs-input"

    dispatch.return_value = workflow.StageResult("completed")
    assert workflow.run_workflow(tmp_path, state)["status"] == "completed"


def test_failure_patch_updates_requirements_used_by_next_codegen(tmp_path: Path):
    _, state = _state(tmp_path)

    workflow._apply_fix_parsed({"patch_fields": {"pin": "PD13", "feature": "fixed-led"}}, state)

    requirements = workflow._requirement_evidence(state)
    assert requirements["pin"] == state["context"]["pin"] == "PD13"
    assert requirements["feature"] == state["context"]["feature"] == "fixed-led"


def test_firmware_write_failure_cannot_complete_stage(tmp_path: Path, monkeypatch):
    context, state = _state(tmp_path)
    monkeypatch.setattr(workflow, "_get_vendor_adapter", lambda state: None)
    monkeypatch.setattr(workflow.firmware_intent_planner, "plan_implementation", lambda *args, **kwargs: {"status": "plan-only"})
    monkeypatch.setattr(llm_codegen, "generate_app_module", lambda *args, **kwargs: {"status": "not-enabled"})
    monkeypatch.setattr(workflow.firmware_code_patcher, "preview_patch", lambda *args, **kwargs: {"files": [{"path": str(tmp_path / "app.c"), "content": "app"}]})
    monkeypatch.setattr(workflow.safe_io, "safe_write_text", Mock(side_effect=PermissionError("read-only project")))
    import firmware_project_scaffold

    scaffold = Mock(return_value={"status": "ok"})
    monkeypatch.setattr(firmware_project_scaffold, "ensure_compilable", scaffold)

    result = workflow._stage_firmware_plan(tmp_path, context, state)

    assert result.status == "failed"
    assert "read-only project" in str(result.evidence)
    scaffold.assert_not_called()


@pytest.mark.parametrize("backend_status", ["error", "timeout"])
def test_native_build_failure_cannot_complete_stage(tmp_path: Path, monkeypatch, backend_status: str):
    context, state = _state(tmp_path)
    adapter = Mock(family="stm32")
    adapter.build_via_platformio.return_value = []
    adapter.detect_tools.return_value = {"gcc": True}
    adapter.build_command.return_value = ["mock-build"]
    monkeypatch.setattr(workflow, "_get_vendor_adapter", lambda state: adapter)
    monkeypatch.setattr(workflow.build_plan, "generate_plan", lambda root: {"steps": [{"phase": "build"}]})
    monkeypatch.setattr(workflow, "_run_subprocess", lambda *args, **kwargs: {"status": backend_status, "returncode": 1, "stderr": "compile failed"})

    result = workflow._stage_build(tmp_path, context, state)

    assert result.status == "failed"
    assert result.evidence["build_executed"] is False
    assert result.error


def test_environment_opt_in_alone_cannot_dispatch_physical_flash(tmp_path: Path, monkeypatch):
    context, state = _state(tmp_path)
    monkeypatch.setenv("HARDWARE_BUTLER_ENABLE_REAL_FLASH", "1")
    monkeypatch.setattr(workflow.bench_runbook, "generate_runbook", lambda *args, **kwargs: {"action_plan": {"steps": []}})
    adapter = Mock()
    adapter.flash_via_probe_rs.return_value = ["mock-flash"]
    monkeypatch.setattr(workflow, "_get_vendor_adapter", lambda state: adapter)
    run = Mock(return_value={"status": "ok", "stdout": "", "stderr": ""})
    monkeypatch.setattr(workflow, "_run_subprocess", run)
    monkeypatch.setattr(workflow, "_run_embeddedskills_script", run)

    result = workflow._stage_flash(tmp_path, context, state)

    run.assert_not_called()
    assert result.status == "blocked-needs-input"
    assert result.evidence["flash_executed"] is False


def test_environment_opt_in_alone_cannot_dispatch_physical_observe(tmp_path: Path, monkeypatch):
    context = workflow.WorkflowContext(probe="COM7")
    _, state = _state(tmp_path)
    firmware = next(stage for stage in state["stages"] if stage["id"] == "firmware-plan")
    firmware.update(status="completed", evidence={"firmware_plan": {"verification": ["LED blink"]}})
    monkeypatch.setenv("HARDWARE_BUTLER_ENABLE_REAL_FLASH", "1")
    run = Mock(return_value={"status": "ok", "stdout": "LED blink", "stderr": ""})
    monkeypatch.setattr(workflow, "_run_embeddedskills_script", run)

    result = workflow._stage_debug_observe(tmp_path, context, state)

    run.assert_not_called()
    assert result.status == "blocked-needs-input"
    assert result.evidence["hardware_observed"] is False
