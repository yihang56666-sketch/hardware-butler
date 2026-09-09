from __future__ import annotations

import json
from pathlib import Path

import evidence_index
import evidence_qa
import hardware_butler
import hardware_butler_inspect
import hardware_risk
import project_brain
import project_scanner
import pytest


@pytest.fixture(autouse=True)
def isolated_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HW_BUTLER_ROOT", str(tmp_path))
    monkeypatch.setattr(hardware_butler, "configure_stdio", lambda: None)


@pytest.mark.parametrize("raw", [b"{", b"[]", b"null", b'{"workflow": []}', b"\xff"])
def test_risk_reports_invalid_config_instead_of_treating_it_as_missing(tmp_path: Path, raw: bytes) -> None:
    config = tmp_path / ".embeddedskills/config.json"
    config.parent.mkdir()
    config.write_bytes(raw)
    result = hardware_risk.analyze_risks(tmp_path)
    invalid = [item for item in result["risks"] if item["id"] == "project_config_invalid"]
    assert len(invalid) == 1
    assert invalid[0]["severity"] == "high"
    assert invalid[0]["evidence"][0]["path"] == ".embeddedskills/config.json"


def test_risk_reports_unreadable_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = tmp_path / ".embeddedskills/config.json"
    config.parent.mkdir()
    config.write_text("{}", encoding="utf-8")
    real_read = Path.read_text

    def denied(path: Path, *args, **kwargs):
        if path == config:
            raise PermissionError("fixture: config cannot be read")
        return real_read(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", denied)
    result = hardware_risk.analyze_risks(tmp_path)
    assert any(item["id"] == "project_config_invalid" for item in result["risks"])


@pytest.mark.parametrize(
    "filename, label",
    [
        ("board.ioc.bak", "cubemx_ioc"),
        ("memory.ld.old", "linker_script"),
        ("board.uvprojx.disabled", "keil_project"),
        ("board.sch.bak", "schematic"),
        ("Makefile.backup", "makefile"),
        ("CMakeLists.txt.bak", "cmake_project"),
    ],
)
def test_scanner_does_not_treat_backup_names_as_active_artifacts(filename: str, label: str) -> None:
    assert label not in project_scanner.classify_file(Path(filename))


def test_scanner_rejects_a_missing_project_root(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="directory"):
        project_scanner.scan(tmp_path / "missing-project")


@pytest.mark.parametrize("absolute", [False, True])
def test_qa_text_search_rejects_outside_index_paths(tmp_path: Path, absolute: bool) -> None:
    root = tmp_path / "project"
    root.mkdir()
    outside = tmp_path / "outside-manual.txt"
    outside.write_text("needle: must not be read through project evidence\n", encoding="utf-8")
    reference = str(outside) if absolute else "../outside-manual.txt"
    index = {"items": [{"kind": "manual", "path": reference}]}
    assert evidence_qa.search_indexed_text(root, index, "needle") == []


@pytest.mark.parametrize("consumer", ["qa", "brain"])
def test_ioc_summary_rejects_outside_index_paths(tmp_path: Path, consumer: str) -> None:
    root = tmp_path / "project"
    root.mkdir()
    outside = tmp_path / "outside.ioc"
    outside.write_text("Mcu.Name=OUTSIDE_FIXTURE\n", encoding="utf-8")
    index = {"items": [{"kind": "cubemx_ioc", "path": "../outside.ioc"}]}
    if consumer == "qa":
        assert evidence_qa.ioc_summaries(root, index) == []
    else:
        assert project_brain.summarize_iocs(root, {"artifacts": {"cubemx_ioc": index["items"]}}) == []


def test_qa_ioc_citations_reject_an_outside_summary_path(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    outside = tmp_path / "outside.ioc"
    outside.write_text("PA1.GPIO_Label=OUTSIDE_FIXTURE\n", encoding="utf-8")
    assert evidence_qa.ioc_line_citations(root, {"ioc_file": str(outside)}, ["PA1."]) == []


def test_index_drops_outside_artifacts_in_supplied_scan(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    (tmp_path / "outside-manual.txt").write_text("outside fixture\n", encoding="utf-8")
    scan = {"artifacts": {"manual": [{"path": "../outside-manual.txt", "size_bytes": 16}]}}
    index = evidence_index.build_evidence_index(root, scan_data=scan, write=False)
    assert index["items"] == []


def test_ask_does_not_read_external_symlink_evidence(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("needle: external local fixture\n", encoding="utf-8")
    alias = root / "manual.txt"
    try:
        alias.symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"symlink unavailable: {exc}")
    scan = project_scanner.scan(root)
    assert not scan["artifacts"].get("manual")
    answer = evidence_qa.answer_question(root, "needle", refresh=False)
    assert answer["status"] == "no-answer"
    assert answer["citations"] == []


def test_inspection_records_ioc_failure_without_rendering_a_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "project"
    root.mkdir()
    (root / "board.ioc").write_text("Mcu.Name=STM32F407VGTx\n", encoding="utf-8")
    out_dir = tmp_path / "inspection"
    out_dir.mkdir()
    summary_path = out_dir / "cubemx-ioc-summary.md"
    summary_path.write_text("stale success\n", encoding="utf-8")

    def fail_summary(path: Path):
        raise PermissionError("fixture: IOC is not readable")

    monkeypatch.setattr(hardware_butler_inspect.cubemx_ioc_summary, "summarize", fail_summary)
    result = hardware_butler_inspect.inspect_project(root, out_dir)
    assert result["status"] == "partial"
    assert result["errors"][0]["error"] == "fixture: IOC is not readable"
    assert "stale success" not in summary_path.read_text(encoding="utf-8")
    assert "fixture: IOC is not readable" in summary_path.read_text(encoding="utf-8")


@pytest.mark.parametrize("status", ["error", "timeout", "blocked-real-backend-not-enabled", "blocked-plan-token-mismatch"])
def test_execute_action_cli_has_nonzero_exit_for_unsuccessful_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], status: str
) -> None:
    monkeypatch.setattr(hardware_butler.hardware_action_executor, "load_plan", lambda path: {})
    monkeypatch.setattr(
        hardware_butler.hardware_action_executor, "execute_plan", lambda *args, **kwargs: {"status": status}
    )
    monkeypatch.setattr(hardware_butler.hardware_action_executor, "render_markdown", lambda data: "")
    try:
        exit_code = hardware_butler.cli_entry(
            ["execute-action", "--plan", str(tmp_path / "fixture.json"), "--confirm-token", "fixture-only", "--json"]
        )
    except SystemExit as exc:
        exit_code = exc.code
    assert exit_code == 2
    assert json.loads(capsys.readouterr().out)["status"] == status


@pytest.mark.parametrize("failure", ["error", "timeout"])
def test_run_plan_cli_has_nonzero_exit_for_command_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    monkeypatch.setattr(hardware_butler.command_runner, "run_plan", lambda *args, **kwargs: {"summary": {failure: 1}})
    monkeypatch.setattr(hardware_butler.command_runner, "render_markdown", lambda data: "")
    try:
        exit_code = hardware_butler.cli_entry(["run-plan", "--root", str(tmp_path), "--json"])
    except SystemExit as exc:
        exit_code = exc.code
    assert exit_code == 2
