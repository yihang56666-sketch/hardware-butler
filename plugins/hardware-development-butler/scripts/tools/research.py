"""Unified research entrypoint.

Single command for the auxiliary "资料搜集/分析" workflow:

1. Download datasheets + reference manuals for a chip part
   (chip_dossier.search_and_download_documents).
2. Summarize the downloaded PDFs into a structured evidence index
   (manual_summarizer.summarize_documents).
3. Optionally answer a free-form question against the resulting evidence
   (evidence_qa.answer_question).

This is the entrypoint the GUI surfaces under "资料中心 / 研究". The
workflow_runner's `datasheet-collect` stage calls the same underlying modules
in-process; this command is for the user-facing ad-hoc path.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import chip_dossier
import evidence_qa
import manual_summarizer


def run_research(
    root: Path,
    *,
    part: str,
    out_dir: Path | None = None,
    question: str = "",
    timeout_s: int = 20,
) -> dict[str, Any]:
    """Download datasheets, summarize them, and optionally answer a question.

    Returns a dict with: part, documents_dir, dossier, summary, answer (if
    question non-empty), status. Network failures do not abort the whole run:
    each stage reports its own status, and the overall status reflects the
    worst-case ("partial" if some stages succeeded but others failed).
    """
    part_raw = part.strip()
    if not part_raw:
        return {"status": "error", "error": "part is required"}
    part = chip_dossier.normalize_part(part_raw)

    docs_dir = out_dir or (root / ".hardware-butler" / "research" / part)
    docs_dir.mkdir(parents=True, exist_ok=True)

    dossier: dict[str, Any] = {}
    summary: dict[str, Any] = {}
    answer: dict[str, Any] = {}
    stages: list[dict[str, Any]] = []

    try:
        dossier = chip_dossier.create_dossier(part, docs_dir, sources=chip_dossier.vendor_search_hints(part))
        stages.append({"stage": "dossier", "status": "ok"})
    except Exception as exc:  # noqa: BLE001
        dossier = {"error": str(exc)}
        stages.append({"stage": "dossier", "status": "error", "error": str(exc)})

    pdfs = sorted(p for p in docs_dir.rglob("*.pdf"))
    if pdfs:
        try:
            summary = manual_summarizer.summarize_documents(part, pdfs)
            stages.append({"stage": "summarize", "status": "ok", "pdf_count": len(pdfs)})
        except Exception as exc:  # noqa: BLE001
            summary = {"error": str(exc)}
            stages.append({"stage": "summarize", "status": "error", "error": str(exc)})
    else:
        stages.append({"stage": "summarize", "status": "skipped", "reason": "no PDFs downloaded"})

    if question:
        try:
            answer = evidence_qa.answer_question(root, question)
            stages.append({"stage": "answer", "status": "ok"})
        except Exception as exc:  # noqa: BLE001
            answer = {"error": str(exc)}
            stages.append({"stage": "answer", "status": "error", "error": str(exc)})

    statuses = [s["status"] for s in stages]
    if all(s == "ok" for s in statuses):
        overall = "ok"
    elif any(s == "ok" for s in statuses):
        overall = "partial"
    else:
        overall = "error"

    return {
        "status": overall,
        "part": part,
        "documents_dir": str(docs_dir),
        "pdf_count": len(pdfs),
        "dossier": dossier,
        "summary": summary,
        "answer": answer if question else None,
        "stages": stages,
    }


def render_research_markdown(data: dict[str, Any]) -> str:
    """Render research result as markdown for human-facing output."""
    lines: list[str] = []
    lines.append(f"# Research: {data.get('part', '')}")
    lines.append(f"Status: {data.get('status', '')}")
    lines.append(f"Documents dir: {data.get('documents_dir', '')}")
    lines.append(f"PDFs: {data.get('pdf_count', 0)}")
    lines.append("")
    for stage in data.get("stages", []):
        lines.append(f"- {stage['stage']}: {stage['status']}")
    answer = data.get("answer")
    if isinstance(answer, dict) and answer:
        lines.append("")
        lines.append("## Answer")
        lines.append(json.dumps(answer, ensure_ascii=False, indent=2))
    return "\n".join(lines)
