"""Tests for the unified research entrypoint (tools/research.py).

Stubs the network-facing layers (chip_dossier.create_dossier,
manual_summarizer.summarize_documents, evidence_qa.answer_question) so the
test runs offline. Verifies the orchestration contract:
- part normalization (empty -> error)
- per-stage status reporting
- overall status: ok / partial / error
- question propagation
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, "tools")

import research  # noqa: E402


def test_research_empty_part_returns_error(tmp_path: Path) -> None:
    result = research.run_research(tmp_path, part="")
    assert result["status"] == "error"
    assert "part is required" in result["error"]


def test_research_partial_when_no_pdfs(tmp_path: Path) -> None:
    """Without downloaded PDFs, summarize stage is skipped -> overall partial."""
    fake_dossier = {"schema_version": 1, "status": "ok", "part": "STM32F407VGTx", "documents": []}
    with patch("research.chip_dossier.create_dossier", return_value=fake_dossier):
        result = research.run_research(tmp_path, part="STM32F407VGTx")
    assert result["status"] == "partial"
    assert result["pdf_count"] == 0
    stages = {s["stage"]: s["status"] for s in result["stages"]}
    assert stages["dossier"] == "ok"
    assert stages["summarize"] == "skipped"


def test_research_ok_with_pdfs_and_question(tmp_path: Path) -> None:
    """Happy path: dossier downloads PDFs, summarize succeeds, question answered."""
    fake_dossier = {"schema_version": 1, "status": "ok", "part": "STM32F407VGTx", "documents": []}
    fake_summary = {"status": "ok", "part": "STM32F407VGTx", "sections": {}}
    fake_answer = {"status": "ok", "answer": "PD12 is on GPIOD", "citations": []}

    # Pre-create a fake PDF so the rglob finds it.
    docs_dir = tmp_path / ".hardware-butler" / "research" / "STM32F407VGTx"
    docs_dir.mkdir(parents=True, exist_ok=True)
    (docs_dir / "fake.pdf").write_bytes(b"%PDF-1.4 fake")

    with patch("research.chip_dossier.create_dossier", return_value=fake_dossier), \
         patch("research.manual_summarizer.summarize_documents", return_value=fake_summary), \
         patch("research.evidence_qa.answer_question", return_value=fake_answer):
        result = research.run_research(tmp_path, part="STM32F407VGTx", question="Where is PD12?")

    assert result["status"] == "ok"
    assert result["pdf_count"] == 1
    stages = {s["stage"]: s["status"] for s in result["stages"]}
    assert stages == {"dossier": "ok", "summarize": "ok", "answer": "ok"}
    assert result["answer"] == fake_answer


def test_research_reports_stage_errors(tmp_path: Path) -> None:
    """A stage exception is captured, not propagated; overall status reflects it."""
    def boom(*args, **kwargs):
        raise RuntimeError("network down")
    with patch("research.chip_dossier.create_dossier", side_effect=boom):
        result = research.run_research(tmp_path, part="STM32F407VGTx")
    assert result["status"] == "error"
    stages = {s["stage"]: s["status"] for s in result["stages"]}
    assert stages["dossier"] == "error"
    assert "network down" in result["dossier"]["error"]


def test_research_render_markdown_roundtrip(tmp_path: Path) -> None:
    fake_dossier = {"status": "ok", "part": "STM32F407VGTx"}
    with patch("research.chip_dossier.create_dossier", return_value=fake_dossier):
        result = research.run_research(tmp_path, part="STM32F407VGTx")
    md = research.render_research_markdown(result)
    assert "Research: STM32F407VGTx" in md
    assert "Status: partial" in md
