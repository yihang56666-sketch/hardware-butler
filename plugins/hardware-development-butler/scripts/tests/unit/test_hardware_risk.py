from __future__ import annotations

import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "tools"))

import evidence_index
import hardware_risk
import project_scanner

FIXTURE = REPO_ROOT / "tests" / "fixtures" / "cubemx-basic"
TMP = REPO_ROOT / "tests" / "tmp" / "hardware-risk"


def copy_fixture(name: str) -> Path:
    target = TMP / name
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(FIXTURE, target)
    # The fixture ships pre-built chip documents (docs/chip/...); this test
    # verifies the missing-documents risk path, so strip them after copying.
    chip_docs = target / "docs" / "chip"
    if chip_docs.exists():
        shutil.rmtree(chip_docs)
    # Strip runtime scratch state too: ad-hoc CLI invocations against the
    # fixture (e.g. `research --root tests/fixtures/cubemx-basic`) drop
    # generated evidence under .hardware-butler/, which would then be picked
    # up by the scanner and mask the "missing chip documents" risk.
    scratch = target / ".hardware-butler"
    if scratch.exists():
        shutil.rmtree(scratch)
    return target


def test_analyze_risks_flags_missing_evidence_and_auto_hardware_preferences() -> None:
    project = copy_fixture("basic")
    scan = project_scanner.scan(project)
    index = evidence_index.build_evidence_index(project, scan_data=scan)

    report = hardware_risk.analyze_risks(project, scan_data=scan, evidence_index=index)

    risk_ids = {item["id"] for item in report["risks"]}
    assert report["status"] == "risks-found"
    assert "schematic_missing_power" in risk_ids
    assert "bom_missing" in risk_ids
    assert "chip_documents_missing" in risk_ids
    assert "cubemx_without_board_evidence" in risk_ids
    assert "auto_hardware_backend_preferences" in risk_ids
    assert report["summary"]["by_category"]["power"] >= 1
    assert report["summary"]["by_category"]["debug"] >= 1
    assert all("next_safe_check" in item for item in report["risks"])
