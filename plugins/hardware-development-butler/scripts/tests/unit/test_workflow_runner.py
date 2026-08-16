"""Unit tests for workflow_runner — state machine + vertical slice on cubemx-basic fixture."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.path.insert(0, "tools")

import workflow_runner as wr  # noqa: E402


def _copy_fixture(cubemx_basic_fixture: Path, tmp_path: Path) -> Path:
    """Copy fixture into a repo-local temp dir.

    workflow_runner.safe_io refuses writes outside the repo root, so the
    copy must live inside the repo. Each test gets a unique subdir under
    .tmp-wf-tests/ based on tmp_path name; we clean it first to allow re-runs.
    """
    scratch_root = Path(__file__).resolve().parents[2] / ".tmp-wf-tests"
    project = scratch_root / tmp_path.name / "project"
    if project.exists():
        shutil.rmtree(project, ignore_errors=True)
    project.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(cubemx_basic_fixture, project)
    evidence_path = project / ".hardware-butler" / "datasheet-evidence.json"
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(
        '{"part": "STM32F407VGTx", "sources": [{"url": "stub", "title": "stub", "type": "manual"}], '
        '"parameters": {"vdd": "3.3V"}, "pin_functions": {}}',
        encoding="utf-8",
    )
    return project


def test_init_workflow_creates_pending_stages(cubemx_basic_fixture: Path, tmp_path: Path) -> None:
    project = _copy_fixture(cubemx_basic_fixture, tmp_path)
    ctx = wr.WorkflowContext(feature="led-blink", pin="PD12", function="gpio-output")
    state = wr.init_workflow(project, intent="develop-feature", goal="LED blink", context=ctx)

    assert state["status"] == "running"
    assert state["current_stage"] == "requirement-parse"
    assert len(state["stages"]) == 9
    assert all(s["status"] == "pending" for s in state["stages"])
    assert state["context"]["feature"] == "led-blink"


def test_full_p2_pipeline_completes_on_fixture(cubemx_basic_fixture: Path, tmp_path: Path) -> None:
    project = _copy_fixture(cubemx_basic_fixture, tmp_path)
    ctx = wr.WorkflowContext(feature="led-blink", pin="PD12", function="gpio-output")
    state = wr.init_workflow(project, intent="develop-feature", goal="LED blink on PD12", context=ctx)
    result = wr.run_workflow(project, state)

    assert result["status"] == "completed"
    assert result["current_stage"] == ""
    assert len(result["stages"]) == 9
    assert all(s["status"] == "completed" for s in result["stages"])
    chip_stage = next(s for s in result["stages"] if s["id"] == "chip-selection")
    assert chip_stage["evidence"]["selected_part"] == "STM32F407VGTx"
    fw_stage = next(s for s in result["stages"] if s["id"] == "firmware-plan")
    assert fw_stage["evidence"]["firmware_plan"]["status"].startswith("plan-only")
    build_stage = next(s for s in result["stages"] if s["id"] == "build")
    assert build_stage["evidence"]["build_plan"]["steps"]
    flash_stage = next(s for s in result["stages"] if s["id"] == "flash")
    assert flash_stage["evidence"]["runbook"]["action_plan"]
    assert flash_stage["evidence"]["goal_token"]["status"] == "valid"
    obs_stage = next(s for s in result["stages"] if s["id"] == "debug-observe")
    assert obs_stage["evidence"]["mode"] == "sim"
    assert any(sig["kind"] == "led" for sig in obs_stage["evidence"]["signals"])
    verify_stage = next(s for s in result["stages"] if s["id"] == "verify-goal")
    assert verify_stage["evidence"]["verification_level"] in ("behavior-mock", "behavior-keyword")
    assert "led" in verify_stage["evidence"]["matched"]
    state_path = wr.workflow_state_path(project)
    assert state_path.exists()


def test_resume_picks_up_where_left_off(cubemx_basic_fixture: Path, tmp_path: Path) -> None:
    project = _copy_fixture(cubemx_basic_fixture, tmp_path)
    ctx = wr.WorkflowContext(feature="led-blink", pin="PD12", function="gpio-output")
    state = wr.init_workflow(project, intent="develop-feature", goal="LED blink", context=ctx)
    state["stages"][0]["status"] = "completed"
    state["stages"][0]["attempts"] = 1
    state["stages"][0]["evidence"] = {"parsed_requirements": {"feature": "led-blink", "function": "gpio-output", "pin": "PD12", "instance": "", "part": ""}}
    state["current_stage"] = "chip-selection"
    wr.write_workflow_state(project, state)

    loaded = wr.load_workflow_state(project)
    assert loaded is not None
    result = wr.run_workflow(project, loaded)
    assert result["status"] == "completed"


def test_missing_feature_blocks_at_requirement_parse(cubemx_basic_fixture: Path, tmp_path: Path) -> None:
    project = _copy_fixture(cubemx_basic_fixture, tmp_path)
    ctx = wr.WorkflowContext(feature="", pin="PD12", function="gpio-output")
    state = wr.init_workflow(project, intent="develop-feature", goal="missing feature", context=ctx)
    result = wr.run_workflow(project, state)

    assert result["status"] == "blocked-needs-input"
    assert result["stages"][0]["status"] == "blocked-needs-input"
    assert result["stages"][1]["status"] == "pending"


def test_workflow_summary_returns_compact_view(cubemx_basic_fixture: Path, tmp_path: Path) -> None:
    project = _copy_fixture(cubemx_basic_fixture, tmp_path)
    ctx = wr.WorkflowContext(feature="led-blink", pin="PD12", function="gpio-output")
    state = wr.init_workflow(project, intent="develop-feature", goal="LED blink", context=ctx)
    result = wr.run_workflow(project, state)
    summary = wr.workflow_summary(result)

    assert summary["workflow_id"] == result["workflow_id"]
    assert summary["status"] == "completed"
    assert len(summary["stages"]) == 9
    assert all({"id", "status", "attempts"} <= s.keys() for s in summary["stages"])


def test_flash_stage_does_not_execute_real_flash(cubemx_basic_fixture: Path, tmp_path: Path) -> None:
    """flash stage must produce a runbook, never consume a token or write safety-log."""
    project = _copy_fixture(cubemx_basic_fixture, tmp_path)
    ctx = wr.WorkflowContext(feature="led-blink", pin="PD12", function="gpio-output")
    state = wr.init_workflow(project, intent="develop-feature", goal="LED blink", context=ctx)
    result = wr.run_workflow(project, state)
    flash_stage = next(s for s in result["stages"] if s["id"] == "flash")

    runbook = flash_stage["evidence"]["runbook"]
    assert runbook["executed"] is False
    assert runbook["hardware_side_effect"] is False
    assert runbook["token_consumed"] is False
    assert runbook["safety_log_written"] is False


def test_verify_goal_fails_when_prior_stage_incomplete(cubemx_basic_fixture: Path, tmp_path: Path) -> None:
    """If a prior stage is blocked, verify-goal must not run or must fail."""
    project = _copy_fixture(cubemx_basic_fixture, tmp_path)
    ctx = wr.WorkflowContext(feature="", pin="PD12", function="gpio-output")
    state = wr.init_workflow(project, intent="develop-feature", goal="missing feature", context=ctx)
    result = wr.run_workflow(project, state)

    assert result["status"] == "blocked-needs-input"
    verify_stage = next(s for s in result["stages"] if s["id"] == "verify-goal")
    assert verify_stage["status"] == "pending"


def test_flash_stage_mints_goal_token_on_first_run(cubemx_basic_fixture: Path, tmp_path: Path) -> None:
    """flash stage must mint a goal_token bound to workflow_id on first entry."""
    project = _copy_fixture(cubemx_basic_fixture, tmp_path)
    ctx = wr.WorkflowContext(feature="led-blink", pin="PD12", function="gpio-output")
    state = wr.init_workflow(project, intent="develop-feature", goal="LED blink", context=ctx)
    result = wr.run_workflow(project, state)

    flash_stage = next(s for s in result["stages"] if s["id"] == "flash")
    gt = flash_stage["evidence"]["goal_token"]
    assert gt["workflow_id"] == result["workflow_id"]
    assert gt["status"] == "valid"
    assert gt["max_uses"] == 5
    assert gt["uses"] == 1
    assert "build-flash" in gt["scope"]
    assert "_plaintext" not in gt

    persisted = wr.load_workflow_state(project)
    assert persisted is not None
    assert persisted["goal_token"]["token_hash"] == gt["token_hash"]
    assert "_plaintext" not in persisted["goal_token"]


def test_flash_stage_reissues_ephemeral_goal_token_on_resume(cubemx_basic_fixture: Path, tmp_path: Path) -> None:
    """A persisted workflow has no plaintext token, so resume must reissue one."""
    project = _copy_fixture(cubemx_basic_fixture, tmp_path)
    ctx = wr.WorkflowContext(feature="led-blink", pin="PD12", function="gpio-output")
    state = wr.init_workflow(project, intent="develop-feature", goal="LED blink", context=ctx)
    first = wr.run_workflow(project, state)
    first_hash = first["goal_token"]["token_hash"]

    loaded = wr.load_workflow_state(project)
    assert loaded is not None
    assert "_plaintext" not in loaded["goal_token"]
    flash_stage = next(s for s in loaded["stages"] if s["id"] == "flash")
    flash_stage["status"] = "pending"
    flash_stage["attempts"] = 0
    loaded["stages"][-1]["status"] = "pending"
    loaded["stages"][-1]["attempts"] = 0
    second = wr.run_workflow(project, loaded)
    assert second["goal_token"]["token_hash"] != first_hash
    assert second["goal_token"]["uses"] == 1
    second_flash = next(s for s in second["stages"] if s["id"] == "flash")
    assert second_flash["evidence"]["goal_token"]["reissued_after_resume"] is True
    assert second_flash["evidence"]["goal_token"]["previous_token_hash"] == first_hash


def test_public_workflow_state_redacts_plaintext_without_mutating_internal_state() -> None:
    state = {
        "schema_version": 1,
        "goal_token": {
            "token_hash": "abc123",
            "_plaintext": "hwg1-secret",
        },
        "stages": [],
    }

    public = wr.public_workflow_state(state)

    assert public["goal_token"] == {"token_hash": "abc123"}
    assert state["goal_token"]["_plaintext"] == "hwg1-secret"


def test_load_workflow_state_scrubs_legacy_plaintext_from_disk(tmp_path: Path) -> None:
    project = tmp_path / "legacy-project"
    state_path = wr.workflow_state_path(project)
    state_path.parent.mkdir(parents=True)
    state_path.write_text(
        '{"schema_version": 1, "goal_token": {"token_hash": "abc", "_plaintext": "hwg1-secret"}}',
        encoding="utf-8",
    )

    loaded = wr.load_workflow_state(project)

    assert loaded is not None
    assert "_plaintext" not in loaded["goal_token"]
    assert "_plaintext" not in state_path.read_text(encoding="utf-8")


def test_debug_observe_extracts_led_signal_from_firmware_plan(cubemx_basic_fixture: Path, tmp_path: Path) -> None:
    """debug-observe must extract an LED signal from firmware-plan pin_advice."""
    project = _copy_fixture(cubemx_basic_fixture, tmp_path)
    ctx = wr.WorkflowContext(feature="led-blink", pin="PD12", function="gpio-output")
    state = wr.init_workflow(project, intent="develop-feature", goal="LED blink", context=ctx)
    result = wr.run_workflow(project, state)
    obs_stage = next(s for s in result["stages"] if s["id"] == "debug-observe")

    assert obs_stage["status"] == "completed"
    signals = obs_stage["evidence"]["signals"]
    assert any(sig["kind"] == "led" and sig["pin"] == "PD12" for sig in signals)
    assert obs_stage["evidence"]["mode"] == "sim"
    assert obs_stage["evidence"]["hardware_observed"] is False


def test_verify_goal_behavior_keyword_match(cubemx_basic_fixture: Path, tmp_path: Path) -> None:
    """Goal containing 'led' must match debug-observe led observation.

    P3: sim mode returns verification_level='behavior-mock' (upgraded from
    'behavior-keyword' to indicate the capture is synthetic, not real hardware).
    """
    project = _copy_fixture(cubemx_basic_fixture, tmp_path)
    ctx = wr.WorkflowContext(feature="led-blink", pin="PD12", function="gpio-output")
    state = wr.init_workflow(project, intent="develop-feature", goal="LED blink on PD12", context=ctx)
    result = wr.run_workflow(project, state)
    verify_stage = next(s for s in result["stages"] if s["id"] == "verify-goal")

    assert verify_stage["status"] == "completed"
    assert verify_stage["evidence"]["verification_level"] in ("behavior-mock", "behavior-keyword")
    assert "led" in verify_stage["evidence"]["matched"]
    assert verify_stage["evidence"]["unmet"] == [] if "unmet" in verify_stage["evidence"] else True


def test_optimize_loop_retries_when_verify_goal_fails(cubemx_basic_fixture: Path, tmp_path: Path, monkeypatch) -> None:
    """verify-goal failure must reset firmware-plan..verify-goal and retry."""
    import workflow_runner as wr_mod

    project = _copy_fixture(cubemx_basic_fixture, tmp_path)
    ctx = wr.WorkflowContext(feature="led-blink", pin="PD12", function="gpio-output")
    state = wr.init_workflow(project, intent="develop-feature", goal="LED blink", context=ctx)

    original_verify = wr_mod._stage_verify_goal
    call_count = {"n": 0}

    def flaky_verify(root, ctx_arg, state_arg):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return wr_mod.StageResult(status="failed", evidence={"goal": state_arg.get("goal", "")}, error="unmet signals: led")
        return original_verify(root, ctx_arg, state_arg)

    monkeypatch.setattr(wr_mod, "_stage_verify_goal", flaky_verify)
    monkeypatch.setattr(wr_mod, "_llm_analyze_failure_and_patch", lambda root, state, stage: {"status": "no-llm"})
    result = wr.run_workflow(project, state)

    assert result["status"] == "completed"
    verify_stage = next(s for s in result["stages"] if s["id"] == "verify-goal")
    assert verify_stage["attempts"] == 2
    assert call_count["n"] == 2


def test_optimize_loop_gives_up_after_max_attempts(cubemx_basic_fixture: Path, tmp_path: Path, monkeypatch) -> None:
    """If verify-goal keeps failing, MAX_STAGE_ATTEMPTS bounds the loop."""
    import workflow_runner as wr_mod

    project = _copy_fixture(cubemx_basic_fixture, tmp_path)
    ctx = wr.WorkflowContext(feature="led-blink", pin="PD12", function="gpio-output")
    state = wr.init_workflow(project, intent="develop-feature", goal="LED blink", context=ctx)

    def always_fail(root, ctx_arg, state_arg):
        return wr_mod.StageResult(status="failed", evidence={}, error="unmet signals: led")

    monkeypatch.setattr(wr_mod, "_stage_verify_goal", always_fail)
    monkeypatch.setattr(wr_mod, "_llm_analyze_failure_and_patch", lambda root, state, stage: {"status": "no-llm"})
    result = wr.run_workflow(project, state)

    assert result["status"] == "failed"
    verify_stage = next(s for s in result["stages"] if s["id"] == "verify-goal")
    assert verify_stage["attempts"] == wr_mod.MAX_STAGE_ATTEMPTS
