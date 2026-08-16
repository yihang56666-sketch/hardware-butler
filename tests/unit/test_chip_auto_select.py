"""Tests for P3: --auto-select chip candidate + host-agent provider aliases."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "tools"))

import llm_config  # noqa: E402
import workflow_runner as wr  # noqa: E402

FIXTURE = REPO_ROOT / "tests" / "fixtures" / "cubemx-basic"


def _no_ioc_copy(name: str) -> Path:
    """Copy the fixture WITHOUT the .ioc so chip-selection cannot detect a part."""
    scratch = REPO_ROOT / ".tmp-wf-tests" / name / "project"
    if scratch.exists():
        shutil.rmtree(scratch, ignore_errors=True)
    scratch.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(FIXTURE, scratch)
    (scratch / "Blinky.ioc").unlink()
    return scratch


CANDIDATES = [
    {"part": "STM32F103RBT6", "vendor": "STMicroelectronics", "family": "stm32", "rationale": "cheap"},
    {"part": "ESP32-WROOM-32", "vendor": "Espressif", "family": "esp32", "rationale": "wifi"},
]


def test_chip_selection_blocks_without_auto_select() -> None:
    project = _no_ioc_copy("auto-select-off")
    state = wr.init_workflow(project, intent="develop-feature", goal="blink", context=wr.WorkflowContext(feature="led-blink"))
    with patch("workflow_runner._llm_chip_candidates", return_value=list(CANDIDATES)):
        result = wr._stage_chip_selection(project, wr.WorkflowContext(feature="led-blink"), state)
    assert result.status == "blocked-needs-input"
    assert result.evidence["candidates"] == CANDIDATES
    assert result.evidence["auto_select"] is False


def test_chip_selection_auto_selects_first_candidate() -> None:
    project = _no_ioc_copy("auto-select-on")
    state = wr.init_workflow(project, intent="develop-feature", goal="blink", context=wr.WorkflowContext(feature="led-blink"))
    state["context"]["auto_select"] = True
    with patch("workflow_runner._llm_chip_candidates", return_value=list(CANDIDATES)):
        result = wr._stage_chip_selection(project, wr.WorkflowContext(feature="led-blink"), state)
    assert result.status == "completed"
    assert result.evidence["selected_part"] == "STM32F103RBT6"
    assert result.evidence["selection_mode"] == "llm-auto-select-first"
    assert state["context"]["part"] == "STM32F103RBT6"


def test_chip_selection_auto_select_with_no_candidates_still_blocks() -> None:
    project = _no_ioc_copy("auto-select-empty")
    state = wr.init_workflow(project, intent="develop-feature", goal="blink", context=wr.WorkflowContext(feature="led-blink"))
    state["context"]["auto_select"] = True
    with patch("workflow_runner._llm_chip_candidates", return_value=[]):
        result = wr._stage_chip_selection(project, wr.WorkflowContext(feature="led-blink"), state)
    assert result.status == "blocked-needs-input"
    assert result.evidence["auto_select"] is True


def test_provider_aliases_normalize_to_claude_code(tmp_path: Path) -> None:
    cfg_dir = tmp_path / ".hardware-butler"
    cfg_dir.mkdir()
    (cfg_dir / "llm-config.json").write_text('{"provider": "codex", "codegen": true}', encoding="utf-8")
    config = llm_config.load_config(tmp_path)
    assert config.provider == "claude-code"
    assert config.codegen is True

    (cfg_dir / "llm-config.json").write_text('{"provider": "host-agent"}', encoding="utf-8")
    assert llm_config.load_config(tmp_path).provider == "claude-code"
