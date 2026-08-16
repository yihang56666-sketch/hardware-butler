"""Tests: datasheet-collect stage real-fetch branches.

The evidence-file fast path and the host-agent fallback are covered by the
e2e mock tests; these tests pin the in-between branches — chip_dossier
vendor hints, web_fetcher success, and web_fetcher failure/error recording —
which the real-mode workflow actually takes on a headless run.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, "tools")

import workflow_runner as wr  # noqa: E402


def _prepared_state(project: Path) -> dict:
    ctx = wr.WorkflowContext(feature="led-blink", pin="PD12", function="gpio-output")
    state = wr.init_workflow(project, intent="develop-feature", goal="LED blink", context=ctx)
    chip = next(s for s in state["stages"] if s["id"] == "chip-selection")
    chip["status"] = "completed"
    chip["evidence"] = {"selected_part": "STM32F407VGT6"}
    return state


def _project(tmp_path: Path) -> Path:
    project = tmp_path / "proj"
    project.mkdir()
    return project


def test_chip_dossier_vendor_hints_completes_stage(tmp_path: Path) -> None:
    project = _project(tmp_path)
    state = _prepared_state(project)
    with patch("chip_dossier.create_dossier", return_value={"sources": ["vendor-hint"]}):
        result = wr._stage_datasheet_collect(project, state["context"], state)
    assert result.status == "completed"
    assert result.evidence["evidence_source"] == "chip-dossier-vendor-hints"
    assert result.evidence["datasheet_fetched"] is True
    assert result.evidence["dossier_path"].endswith("STM32F407VGT6")


def test_web_fetcher_success_completes_stage_with_queries(tmp_path: Path) -> None:
    project = _project(tmp_path)
    state = _prepared_state(project)
    fetch_result = {
        "saved_count": 1,
        "results": [{"url": "https://example.com/datasheet.pdf", "saved_path": "x.pdf"}],
        "errors": [],
    }
    with patch("chip_dossier.create_dossier", return_value={"sources": []}):
        with patch("web_fetcher.search_and_fetch", return_value=fetch_result) as fetch:
            result = wr._stage_datasheet_collect(project, state["context"], state)
    assert result.status == "completed"
    assert result.evidence["evidence_source"] == "web-fetcher-duckduckgo"
    assert result.evidence["saved_count"] == 1
    # Queries come from the STM32 adapter, not the generic fallback list.
    queries = fetch.call_args.args[0]
    assert any("reference manual" in q for q in queries)
    assert fetch.call_args.args[1] == project / ".hardware-butler" / "datasheets"


def test_web_fetcher_empty_falls_back_to_host_agent_task(tmp_path: Path) -> None:
    project = _project(tmp_path)
    state = _prepared_state(project)
    with patch("chip_dossier.create_dossier", return_value={"sources": []}):
        with patch(
            "web_fetcher.search_and_fetch",
            return_value={"saved_count": 0, "results": [], "errors": [{"query": "q", "reason": "no hits"}]},
        ):
            result = wr._stage_datasheet_collect(project, state["context"], state)
    assert result.status == "blocked-needs-input"
    task_path = project / ".hardware-butler" / "search-tasks.json"
    assert task_path.exists()
    task = json.loads(task_path.read_text(encoding="utf-8"))
    assert task["part"] == "STM32F407VGT6"
    assert task["web_fetcher_errors"] == [{"query": "q", "reason": "no hits"}]
    assert result.evidence["search_task_path"] == str(task_path)


def test_web_fetcher_exception_recorded_in_task(tmp_path: Path) -> None:
    project = _project(tmp_path)
    state = _prepared_state(project)
    with patch("chip_dossier.create_dossier", return_value={"sources": []}):
        with patch("web_fetcher.search_and_fetch", side_effect=RuntimeError("network down")):
            result = wr._stage_datasheet_collect(project, state["context"], state)
    assert result.status == "blocked-needs-input"
    task = json.loads((project / ".hardware-butler" / "search-tasks.json").read_text(encoding="utf-8"))
    assert any("web_fetcher failed" in err.get("reason", "") for err in task["web_fetcher_errors"])


def test_malformed_evidence_file_falls_through_to_fetch(tmp_path: Path) -> None:
    project = _project(tmp_path)
    state = _prepared_state(project)
    evidence_path = project / ".hardware-butler" / "datasheet-evidence.json"
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text("{not valid json", encoding="utf-8")
    with patch("chip_dossier.create_dossier", return_value={"sources": ["vendor-hint"]}):
        result = wr._stage_datasheet_collect(project, state["context"], state)
    # Corrupt evidence must not crash the stage; it continues to the next
    # source instead of trusting the file.
    assert result.status == "completed"
    assert result.evidence["evidence_source"] == "chip-dossier-vendor-hints"


def test_datasheet_collect_requires_chip_selection(tmp_path: Path) -> None:
    project = _project(tmp_path)
    state = _prepared_state(project)
    chip = next(s for s in state["stages"] if s["id"] == "chip-selection")
    chip["status"] = "pending"
    result = wr._stage_datasheet_collect(project, state["context"], state)
    assert result.status == "failed"
    assert "chip-selection" in (result.error or "")
