from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "tools"))

import evidence_index
import project_scanner

FIXTURE = REPO_ROOT / "tests" / "fixtures" / "cubemx-basic"
TMP = REPO_ROOT / "tests" / "tmp" / "evidence-index"


def copy_fixture(name: str) -> Path:
    target = TMP / name
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(FIXTURE, target)
    return target


def test_build_evidence_index_writes_machine_readable_local_index() -> None:
    project = copy_fixture("basic")
    # The fixture now ships docs/chip/STM32F407VGTx itself; exist_ok keeps
    # this test working on both the bare and enriched fixture.
    (project / "docs" / "chip" / "STM32F407VGTx").mkdir(parents=True, exist_ok=True)
    (project / "docs" / "chip" / "STM32F407VGTx" / "source-map.md").write_text(
        "# Source Map\n\n- official datasheet: unknown\n",
        encoding="utf-8",
    )
    (project / "docs" / "chip" / "STM32F407VGTx" / "manual-summary.md").write_text(
        "# Manual Summary\n\n- boot mode: unknown\n",
        encoding="utf-8",
    )
    (project / "bom.csv").write_text("designator,part\nU1,STM32F407VGTx\n", encoding="utf-8")

    scan = project_scanner.scan(project)
    index = evidence_index.build_evidence_index(project, scan_data=scan)

    path = evidence_index.evidence_index_path(project)
    saved = json.loads(path.read_text(encoding="utf-8"))
    kinds = {item["kind"] for item in index["items"]}
    assert saved["schema_version"] == 1
    assert saved["summary"]["total_items"] == index["summary"]["total_items"]
    assert {"cubemx_ioc", "bom", "source_map", "manual_summary"} <= kinds
    assert all({"path", "kind", "source_quality", "summary", "citations"} <= set(item) for item in index["items"])
    assert any(item["path"] == "Blinky.ioc" and item["source_quality"] == "local-project" for item in index["items"])
