"""Local evidence Q&A for hardware projects.

This first version is intentionally deterministic. It answers only from local
indexed files, CubeMX IOC summaries, and the project brain risk snapshot.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import cubemx_ioc_summary
import evidence_index
import project_brain
import project_scanner

PIN_RE = re.compile(r"\bP[A-K](?:[0-9]|1[0-5])\b", re.IGNORECASE)
PERIPHERAL_RE = re.compile(r"\b(?:I2C|SPI|USART|UART|CAN|ADC|TIM)\d+\b", re.IGNORECASE)
TEXT_SUFFIXES = {".c", ".h", ".ioc", ".json", ".log", ".md", ".s", ".txt", ".xml", ".yml", ".yaml", ".csv"}
MAX_TEXT_BYTES = 512 * 1024
STOP_WORDS = {
    "this",
    "that",
    "what",
    "which",
    "where",
    "怎么",
    "什么",
    "这个",
    "那个",
    "多少",
    "为什么",
}
RISK_TERMS = ("risk", "risks", "missing", "缺", "缺失", "风险", "资料", "证据", "危险")
CONNECTION_TERMS = ("connect", "connected", "connection", "接", "连接", "连到", "接到")
POWER_TERMS = ("power", "supply", "voltage", "vdd", "vcc", "供电", "电压", "电源")


def answer_question(root: Path, question: str, *, refresh: bool = True) -> dict[str, Any]:
    root = root.resolve()
    question = question.strip()
    if not question:
        return unknown_response(root, question, ["question is empty"], ["Enter a concrete project question."])

    index = evidence_index.build_evidence_index(root, write=refresh)
    pins = normalized_pins(question)
    if pins:
        return answer_pin_question(root, question, pins, index)

    peripherals = normalized_peripherals(question)
    if peripherals:
        return answer_peripheral_question(root, question, peripherals, index)

    if asks_for_risk_or_missing(question):
        return answer_risk_question(root, question, refresh=refresh)

    matches = search_indexed_text(root, index, question)
    if matches:
        return {
            "schema_version": 1,
            "status": "ok",
            "root": str(root),
            "question": question,
            "answer": "Found local evidence lines that may be relevant. Treat this as a keyword match, not a confirmed hardware conclusion.",
            "confidence": "medium",
            "citations": matches,
            "unknowns": [],
            "next_checks": ["Open the cited files and verify the surrounding context before using the result."],
            "evidence_used": {"mode": "text-search", "indexed_items": index.get("summary", {}).get("total_items", 0)},
        }

    return unknown_response(
        root,
        question,
        ["No indexed local evidence directly answers the question."],
        [
            "Add or refresh schematic/BOM/manual/log evidence, then run ask again.",
            "For chip facts, run chip-dossier and summarize-manual first.",
        ],
        indexed_items=index.get("summary", {}).get("total_items", 0),
    )


def answer_pin_question(root: Path, question: str, pins: list[str], index: dict[str, Any]) -> dict[str, Any]:
    iocs = ioc_summaries(root, index)
    answer_parts = []
    citations: list[dict[str, Any]] = []
    unknowns = []
    connection_question = asks_for_connection(question)

    for pin in pins:
        pin_found = False
        for summary in iocs:
            normalized = summary.get("normalized_pins", {}) if isinstance(summary.get("normalized_pins"), dict) else {}
            info = normalized.get(pin)
            if not isinstance(info, dict):
                continue
            pin_found = True
            signal = str(info.get("signal") or "unknown")
            label = str(info.get("label") or "")
            owner = str(info.get("owner") or "unknown")
            mode = str(info.get("mode") or "")
            details = [f"signal={signal}", f"owner={owner}"]
            if mode:
                details.append(f"mode={mode}")
            if label:
                details.append(f"label={label}")
            answer_parts.append(f"{pin}: CubeMX IOC configures {', '.join(details)}.")
            citations.extend(ioc_line_citations(root, summary, [f"{pin}.", f"{pin}="]))
        if not pin_found:
            unknowns.append(f"No indexed CubeMX assignment was found for {pin}.")
        elif connection_question:
            unknowns.append(f"{pin} board-level connection is unknown without schematic or board-profile evidence.")

    confidence = "medium" if connection_question or unknowns else "high"
    status = "ok" if answer_parts else "no-answer"
    return {
        "schema_version": 1,
        "status": status,
        "root": str(root),
        "question": question,
        "answer": " ".join(answer_parts) if answer_parts else "unknown",
        "confidence": confidence if answer_parts else "unknown",
        "citations": dedupe_citations(citations),
        "unknowns": unknowns,
        "next_checks": pin_next_checks(connection_question, bool(unknowns)),
        "evidence_used": {"mode": "cubemx-pin", "ioc_count": len(iocs)},
    }


def answer_peripheral_question(root: Path, question: str, peripherals: list[str], index: dict[str, Any]) -> dict[str, Any]:
    iocs = ioc_summaries(root, index)
    answer_parts = []
    citations: list[dict[str, Any]] = []
    unknowns = []

    for peripheral in peripherals:
        found = False
        for summary in iocs:
            details = summary.get("peripheral_details", {}) if isinstance(summary.get("peripheral_details"), dict) else {}
            item = details.get(peripheral)
            if not isinstance(item, dict):
                continue
            found = True
            mode = str(item.get("mode") or "unknown")
            pins = item.get("pins") if isinstance(item.get("pins"), list) else []
            pin_text = ", ".join(str(pin) for pin in pins) if pins else "no pins found in IOC"
            answer_parts.append(f"{peripheral}: CubeMX IOC lists type={item.get('type', 'unknown')}, mode={mode}, pins={pin_text}.")
            citations.extend(ioc_line_citations(root, summary, [f"{peripheral}."]))
            if not pins:
                unknowns.append(f"{peripheral} has no indexed pin assignments in the IOC summary.")
        if not found:
            unknowns.append(f"No indexed CubeMX peripheral block was found for {peripheral}.")

    return {
        "schema_version": 1,
        "status": "ok" if answer_parts else "no-answer",
        "root": str(root),
        "question": question,
        "answer": " ".join(answer_parts) if answer_parts else "unknown",
        "confidence": "medium" if answer_parts else "unknown",
        "citations": dedupe_citations(citations),
        "unknowns": unknowns,
        "next_checks": [
            "Verify peripheral pins against schematic and package pin evidence before changing firmware.",
            "Use advise-pin or patch-ioc for configuration changes.",
        ],
        "evidence_used": {"mode": "cubemx-peripheral", "ioc_count": len(iocs)},
    }


def answer_risk_question(root: Path, question: str, *, refresh: bool) -> dict[str, Any]:
    brain = project_brain.build_project_brain(root, write=refresh)
    risks = brain.get("risk_snapshot", {}).get("risks", [])
    missing = brain.get("missing_evidence", [])
    citations: list[dict[str, Any]] = []
    unknowns = []
    lines = []
    if isinstance(missing, list) and missing:
        lines.append("Missing evidence: " + "; ".join(str(item.get("id", "unknown")) for item in missing[:5] if isinstance(item, dict)) + ".")
    if isinstance(risks, list) and risks:
        lines.append(
            "Top risks: "
            + "; ".join(
                f"{item.get('severity', 'unknown')} {item.get('category', 'unknown')} - {item.get('message', '')}"
                for item in risks[:3]
                if isinstance(item, dict)
            )
        )
        for item in risks[:5]:
            if isinstance(item, dict):
                raw_evidence = item.get("evidence")
                evidence = raw_evidence if isinstance(raw_evidence, list) else []
                citations.extend(citation for citation in evidence if isinstance(citation, dict))
    if not lines:
        lines.append("No deterministic project-brain risks are currently reported.")
    if any(term in question.lower() for term in POWER_TERMS):
        unknowns.append("Specific board power or voltage values are unknown without schematic/BOM/board manual evidence.")
    return {
        "schema_version": 1,
        "status": "ok",
        "root": str(root),
        "question": question,
        "answer": " ".join(lines),
        "confidence": "high",
        "citations": dedupe_citations(citations),
        "unknowns": unknowns,
        "next_checks": risk_next_checks(missing, bool(unknowns)),
        "evidence_used": {"mode": "project-brain", "brain_status": brain.get("status", "unknown")},
    }


def ioc_summaries(root: Path, index: dict[str, Any]) -> list[dict[str, Any]]:
    summaries = []
    for item in index.get("items", []):
        if not isinstance(item, dict) or item.get("kind") != "cubemx_ioc":
            continue
        path = root / str(item.get("path", ""))
        if not project_scanner.is_project_file(root, path):
            continue
        try:
            summaries.append(cubemx_ioc_summary.summarize(path))
        except OSError:
            continue
    return summaries


def ioc_line_citations(root: Path, summary: dict[str, Any], prefixes: list[str]) -> list[dict[str, Any]]:
    path = Path(str(summary.get("ioc_file", "")))
    if not path.is_absolute():
        path = root / path
    if not project_scanner.is_project_file(root, path):
        return []
    rel_path = path.resolve().relative_to(root.resolve()).as_posix()
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return [{"path": rel_path, "line": "unknown", "note": "CubeMX IOC evidence"}]
    citations = []
    for line_no, line in enumerate(lines, start=1):
        stripped = line.strip()
        if any(stripped.startswith(prefix) for prefix in prefixes):
            citations.append({"path": rel_path, "line": line_no, "note": "CubeMX IOC evidence", "text": stripped})
    return citations or [{"path": rel_path, "line": "unknown", "note": "CubeMX IOC evidence"}]


def search_indexed_text(root: Path, index: dict[str, Any], question: str) -> list[dict[str, Any]]:
    root = root.resolve()
    tokens = query_tokens(question)
    if not tokens:
        return []
    matches = []
    for item in index.get("items", []):
        if not isinstance(item, dict):
            continue
        path = root / str(item.get("path", ""))
        if (
            path.suffix.lower() not in TEXT_SUFFIXES
            or not project_scanner.is_project_file(root, path)
            or safe_size(path) > MAX_TEXT_BYTES
        ):
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line_no, line in enumerate(lines, start=1):
            lower = line.lower()
            score = sum(1 for token in tokens if token in lower)
            if score <= 0:
                continue
            matches.append(
                {
                    "path": path.resolve().relative_to(root).as_posix(),
                    "line": line_no,
                    "note": f"keyword match score={score}",
                    "text": line.strip()[:240],
                }
            )
            if len(matches) >= 8:
                return matches
    return matches


def normalized_pins(question: str) -> list[str]:
    pins = []
    for match in PIN_RE.findall(question):
        pin = match.upper()
        if pin not in pins:
            pins.append(pin)
    return pins


def normalized_peripherals(question: str) -> list[str]:
    peripherals = []
    for match in PERIPHERAL_RE.findall(question):
        peripheral = match.upper()
        if peripheral not in peripherals:
            peripherals.append(peripheral)
    return peripherals


def asks_for_connection(question: str) -> bool:
    lower = question.lower()
    return any(term in lower for term in CONNECTION_TERMS)


def asks_for_risk_or_missing(question: str) -> bool:
    lower = question.lower()
    return any(term in lower for term in RISK_TERMS) or any(term in lower for term in POWER_TERMS)


def query_tokens(question: str) -> list[str]:
    raw_tokens = re.findall(r"[a-z0-9_+\-.]{2,}|[\u4e00-\u9fff]{2,}", question.lower())
    tokens = []
    for token in raw_tokens:
        if token in STOP_WORDS or token in tokens:
            continue
        tokens.append(token)
    return tokens


def pin_next_checks(connection_question: bool, has_unknowns: bool) -> list[str]:
    checks = ["Verify the cited CubeMX IOC lines before editing firmware."]
    if connection_question or has_unknowns:
        checks.append("Add schematic or board-profile evidence to confirm board-level connection, voltage domain, pull-ups, and loads.")
    checks.append("Use advise-pin with package pin evidence before changing pinmux.")
    return checks


def risk_next_checks(missing: Any, has_unknowns: bool) -> list[str]:
    checks = [str(item.get("next_safe_action", "")) for item in missing[:5] if isinstance(item, dict)] if isinstance(missing, list) else []
    if has_unknowns:
        checks.append("Add schematic/BOM/board manual evidence before using any power or voltage value.")
    return [item for item in checks if item]


def unknown_response(
    root: Path,
    question: str,
    unknowns: list[str],
    next_checks: list[str],
    *,
    indexed_items: int = 0,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "no-answer",
        "root": str(root),
        "question": question,
        "answer": "unknown",
        "confidence": "unknown",
        "citations": [],
        "unknowns": unknowns,
        "next_checks": next_checks,
        "evidence_used": {"mode": "none", "indexed_items": indexed_items},
    }


def dedupe_citations(citations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    seen: set[tuple[str, str]] = set()
    for item in citations:
        key = (str(item.get("path", "")), str(item.get("line", "")))
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def safe_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return MAX_TEXT_BYTES + 1


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Evidence Answer",
        "",
        f"- Root: `{report.get('root', '')}`",
        f"- Question: {report.get('question', '')}",
        f"- Status: `{report.get('status', 'unknown')}`",
        f"- Confidence: `{report.get('confidence', 'unknown')}`",
        "",
        "## Answer",
        "",
        str(report.get("answer", "unknown")),
        "",
        "## Citations",
        "",
    ]
    citations = report.get("citations", [])
    if citations:
        for item in citations:
            text = f" - {item.get('text', '')}" if item.get("text") else ""
            lines.append(f"- `{item.get('path', 'unknown')}` line {item.get('line', 'unknown')}: {item.get('note', '')}{text}")
    else:
        lines.append("- none")
    lines.extend(["", "## Unknowns", ""])
    unknowns = report.get("unknowns", [])
    if unknowns:
        for item in unknowns:
            lines.append(f"- {item}")
    else:
        lines.append("- none")
    lines.extend(["", "## Next Checks", ""])
    for item in report.get("next_checks", []):
        lines.append(f"- {item}")
    lines.append("")
    return "\n".join(lines)
