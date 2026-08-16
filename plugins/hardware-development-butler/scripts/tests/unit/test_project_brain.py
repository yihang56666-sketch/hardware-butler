from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "tools"))

import project_brain

FIXTURE = REPO_ROOT / "tests" / "fixtures" / "cubemx-basic"
TMP = REPO_ROOT / "tests" / "tmp" / "project-brain"


def copy_fixture(name: str) -> Path:
    target = TMP / name
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(FIXTURE, target)
    # The fixture ships pre-built chip documents (docs/chip/...); the first
    # test below verifies the missing-evidence path, so strip them.
    chip_docs = target / "docs" / "chip"
    if chip_docs.exists():
        shutil.rmtree(chip_docs)
    return target


def test_build_project_brain_detects_identity_evidence_gaps_and_risks() -> None:
    project = copy_fixture("basic")

    brain = project_brain.build_project_brain(project)

    assert brain["schema_version"] == 1
    assert brain["app"] == "hardware-project-brain"
    assert brain["identity"]["project_name"] == "Blinky"
    assert brain["identity"]["mcu"]["name"] == "STM32F407VGTx"
    assert brain["identity"]["project_files"]["keil"] == ["Blinky.uvprojx"]
    health = {item["id"]: item for item in brain["evidence_health"]["categories"]}
    assert health["cubemx_ioc"]["count"] == 1
    assert health["firmware"]["status"] == "present"
    missing_ids = {item["id"] for item in brain["missing_evidence"]}
    assert {"schematic", "bom", "datasheet", "manual"} <= missing_ids
    risk_ids = {item["id"] for item in brain["risk_snapshot"]["risks"]}
    assert "cubemx_without_board_evidence" in risk_ids
    assert "auto_hardware_backend_preferences" in risk_ids
    assert any(task["id"] == "collect-chip-documents" for task in brain["recommended_tasks"])
    assert Path(brain["written"]["project_brain"]).exists()
    assert Path(brain["written"]["evidence_index"]).exists()


def test_brain_cli_emits_json_and_writes_index() -> None:
    project = copy_fixture("cli")

    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "tools" / "hardware_butler.py"),
            "brain",
            "--root",
            str(project),
            "--json",
        ],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    data = json.loads(result.stdout)

    assert data["app"] == "hardware-project-brain"
    assert data["identity"]["mcu"]["name"] == "STM32F407VGTx"
    assert Path(data["written"]["evidence_index"]).exists()
