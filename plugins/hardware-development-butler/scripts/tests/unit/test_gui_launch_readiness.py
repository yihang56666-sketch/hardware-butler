"""Offline entrypoint, process lifecycle, and design-contract regressions."""

from __future__ import annotations

import importlib
import importlib.util
import json
import os
import runpy
import shutil
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
NEXTBOARD = REPO_ROOT / "nextboard"


@pytest.fixture
def offline_env(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("HARDWARE_BUTLER_ENABLE_REAL_FLASH", "0")
    monkeypatch.setenv("PYTHONIOENCODING", "utf-8")
    monkeypatch.delenv("PYTHONPATH", raising=False)
    return dict(os.environ)


@pytest.fixture
def gui(offline_env):
    pytest.importorskip("PyQt6.QtWidgets")
    return importlib.import_module("gui.hardware_agent_ui")


@pytest.fixture
def qt_app(gui):
    app = gui.QApplication.instance() or gui.QApplication([])
    yield app
    app.processEvents()


@pytest.fixture
def window(gui, qt_app, tmp_path):
    instance = gui.HardwareButlerWindow()
    instance.project_input.setText(str(tmp_path))
    yield instance
    worker = instance.worker
    if worker is not None and worker.isRunning():
        worker.cancel()
        assert worker.wait(5000), "test child failed to stop"
    qt_app.processEvents()
    instance.close()
    qt_app.processEvents()


@pytest.fixture
def validator():
    spec = importlib.util.spec_from_file_location("nextboard_validator_readiness", NEXTBOARD / "tests" / "validate.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def wait_until(predicate, app, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        time.sleep(0.01)
    pytest.fail("offline operation did not finish within its bounded wait")


def test_launcher_uses_sibling_gui_from_foreign_cwd(monkeypatch, tmp_path):
    captured = []
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", [str(REPO_ROOT / "launch_gui.py")])

    def record_child(argv, **kwargs):
        captured.append((argv, kwargs))
        return SimpleNamespace(returncode=23)

    monkeypatch.setattr(subprocess, "run", record_child)
    with pytest.raises(SystemExit) as exit_info:
        runpy.run_path(str(REPO_ROOT / "launch_gui.py"), run_name="__main__")
    assert exit_info.value.code == 23
    assert captured[0][0] == [sys.executable, str(REPO_ROOT / "gui" / "hardware_agent_ui.py")]
    assert Path.cwd() == tmp_path


def test_gui_constructs_from_foreign_cwd_without_editable_install(gui, tmp_path, offline_env):
    script = (
        "import json, runpy; "
        f"module = runpy.run_path({str(REPO_ROOT / 'gui' / 'hardware_agent_ui.py')!r}); "
        "app = module['QApplication']([]); window = module['HardwareButlerWindow'](); "
        "print(json.dumps({'tabs': window.tabs.count(), 'root': str(module['APP_ROOT'])})); window.close()"
    )
    result = subprocess.run(
        [sys.executable, "-I", "-c", script], cwd=tmp_path, env=offline_env,
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"tabs": 13, "root": str(REPO_ROOT)}


def test_gui_cli_is_importable_from_foreign_cwd(window, tmp_path, offline_env):
    result = subprocess.run(
        window.cli("capabilities", "--json"), cwd=tmp_path, env=offline_env,
        capture_output=True, text=True, encoding="utf-8", timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert isinstance(json.loads(result.stdout), dict)


def test_missing_qt_dependency_has_actionable_source_install_hint(tmp_path, offline_env):
    result = subprocess.run(
        [sys.executable, "-S", str(REPO_ROOT / "gui" / "hardware_agent_ui.py")],
        cwd=tmp_path, env=offline_env, capture_output=True, text=True, encoding="utf-8", timeout=15,
    )
    assert result.returncode != 0
    assert "[ui]" in result.stderr
    assert "pip install" in result.stderr
    assert "Traceback" not in result.stderr


def test_frozen_cli_locator_skips_directory_named_like_executable(gui, monkeypatch, tmp_path):
    monkeypatch.setattr(gui, "APP_ROOT", tmp_path)
    (tmp_path / gui.CLI_EXE_NAME).mkdir()
    executable = tmp_path / "hardware_butler_cli" / gui.CLI_EXE_NAME
    executable.parent.mkdir()
    executable.touch()
    assert gui.find_frozen_cli() == executable


def test_gui_never_inherits_real_hardware_opt_in(window, monkeypatch):
    monkeypatch.setenv("HARDWARE_BUTLER_ENABLE_REAL_FLASH", "1")
    assert window.command_env()["HARDWARE_BUTLER_ENABLE_REAL_FLASH"] == "0"
    assert os.environ["HARDWARE_BUTLER_ENABLE_REAL_FLASH"] == "1"


def test_relative_project_path_has_same_meaning_for_every_command(window, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    window.project_input.setText("relative project")
    assert window.project_root() == str(tmp_path / "relative project")


def test_llm_config_read_uses_async_command_boundary(window, monkeypatch):
    commands = []
    monkeypatch.setattr(window, "run_command", commands.append)

    def no_blocking_call(*args, **kwargs):
        pytest.fail("configuration read blocked the GUI thread")

    monkeypatch.setattr(subprocess, "run", no_blocking_call)
    window.load_workflow_llm_config()
    assert commands == [window.cli("workflow-llm-config", "--root", window.project_root(), "--json")]


def test_async_llm_config_result_populates_form(window):
    data = {"configured": True, "config": {"provider": "local", "model": "offline-test", "codegen": False}}
    window.command_finished(window.cli("workflow-llm-config", "--json"), 0, json.dumps(data), "")
    assert window.wf_llm_provider.currentText() == "local"
    assert window.wf_llm_model.text() == "offline-test"
    assert not window.wf_llm_codegen.isChecked()


@pytest.mark.parametrize("metadata", [{}, {"safe_by_default": False}, {"safe_by_default": "true"}, {"safe_by_default": True, "touches_hardware": "false"}])
def test_report_actions_require_explicit_safe_metadata(window, monkeypatch, metadata):
    commands = []
    monkeypatch.setattr(window, "run_command", commands.append)
    window.run_action({"argv": ["python", "tools/hardware_butler.py", "doctor"], **metadata})
    assert commands == []


@pytest.mark.parametrize("argv", [
    ["python", "-c", "raise RuntimeError('not a CLI command')"],
    ["powershell", "-Command", "Write-Output not-a-cli"],
    ["python", "tools/hardware_butler.py", "execute-action", "--json"],
    ["python", "other/tools/hardware_butler.py", "doctor"],
])
def test_report_actions_cannot_supply_arbitrary_executables_or_hardware_commands(window, monkeypatch, argv):
    commands = []
    monkeypatch.setattr(window, "run_command", commands.append)
    window.run_action({"argv": argv, "safe_by_default": True, "touches_hardware": False})
    assert commands == []


def test_safe_local_report_action_still_dispatches(window, monkeypatch):
    commands = []
    monkeypatch.setattr(window, "run_command", commands.append)
    argv = ["python", "tools/hardware_butler.py", "doctor", "--root", window.project_root(), "--json"]
    window.run_action({"argv": argv, "safe_by_default": True, "touches_hardware": False})
    assert commands == [window.cli(*argv[2:])]


@pytest.mark.parametrize("command", ["status", "inspect", "plan-build"])
def test_existing_safe_core_recommendations_remain_runnable(window, monkeypatch, command):
    commands = []
    monkeypatch.setattr(window, "run_command", commands.append)
    argv = ["python", "tools/hardware_butler.py", command, "--root", window.project_root(), "--json"]
    window.run_action({"argv": argv, "safe_by_default": True, "touches_hardware": False})
    assert commands == [window.cli(*argv[2:])]


def test_classify_log_button_matches_real_cli_contract(window, monkeypatch, tmp_path, offline_env):
    log = tmp_path / "build.log"
    log.write_text("fatal error: missing-header.h: No such file or directory\n", encoding="utf-8")
    window.tools_log_path.setText(str(log))
    commands = []
    monkeypatch.setattr(window, "run_command", commands.append)
    window.run_classify_log()
    result = subprocess.run(
        commands[0], cwd=tmp_path, env=offline_env, capture_output=True, text=True, encoding="utf-8", timeout=15,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert isinstance(json.loads(result.stdout), dict)


def test_switching_project_invalidates_recommended_and_task_actions(window, tmp_path):
    action = {"argv": ["python", "tools/hardware_butler.py", "auto"], "safe_by_default": True, "touches_hardware": False}
    window.apply_report({"app": "hardware-butler-workbench", "primary_action": action, "actions": [action]})
    window.set_task_plan({"steps": [action]})
    window.project_input.setText(str(tmp_path / "another project"))
    assert window.current_workbench == {}
    assert window.current_actions == []
    assert window.current_task_steps == []
    assert window.action_table.rowCount() == 0


@pytest.mark.parametrize("part", [".", "..", " ... ", "///"])
def test_part_download_folder_is_not_a_dot_directory(gui, part):
    assert gui.safe_part_name(part) == "unknown-part"


def test_failed_json_status_is_not_presented_as_success(window):
    window.command_finished(window.cli("doctor", "--json"), 0, '{"status":"error","error":"offline failure"}', "")
    assert "失败" in window.run_status.text()
    assert "offline failure" in window.output.toPlainText()


def test_malformed_report_does_not_escape_qt_result_handler(window):
    window.command_finished(window.cli("workbench", "--json"), 0, '{"phases":[null]}', "")
    assert window.phase_table.rowCount() == 0


def test_non_string_status_cannot_crash_result_handler(window):
    window.command_finished(window.cli("doctor", "--json"), 0, '{"status":{"bad":"shape"}}', "")
    assert "失败" in window.run_status.text()


@pytest.mark.parametrize("stdout", ["not-json", "[]", "null", ""])
def test_invalid_json_response_is_not_reported_as_completed(window, stdout):
    window.command_finished(window.cli("doctor", "--json"), 0, stdout, "")
    assert "失败" in window.run_status.text()
    assert "JSON" in window.output.toPlainText()


def test_all_tabs_fit_an_860_pixel_window(window, qt_app, gui):
    if gui.apply_stylesheet is not None:
        gui.apply_stylesheet(qt_app, theme="light_blue.xml")
    qt_app.setStyleSheet(qt_app.styleSheet() + gui.STYLE)
    window.show()
    qt_app.processEvents()
    for tab_index in range(window.tabs.count()):
        window.tabs.setCurrentIndex(tab_index)
        qt_app.processEvents()
        assert window.minimumSizeHint().height() <= 860, window.tabs.tabText(tab_index)
        assert window.height() <= 860, window.tabs.tabText(tab_index)


def test_mock_workflow_evidence_is_visible_and_not_hardware_verification(window):
    window.apply_workflow_state({"status": "completed", "stages": [
        {"id": "verify-goal", "status": "completed", "evidence": {"verification_level": "behavior-mock"}},
    ]})
    assert "behavior-mock" in window.wf_status_label.text()
    assert "非实机" in window.wf_status_label.text()


@pytest.mark.parametrize("handler", ["run_workflow", "run_workflow_resume", "run_document_search", "run_research"])
def test_network_or_llm_paths_require_explicit_gui_opt_in(window, monkeypatch, handler):
    window.wf_goal_input.setText("offline regression only")
    window.part_input.setText("unverified-test-part")
    commands = []
    monkeypatch.setattr(window, "run_command", commands.append)
    getattr(window, handler)()
    assert commands == []


def test_command_timeout_retains_partial_output(gui, qt_app, tmp_path, offline_env):
    from PyQt6.QtTest import QSignalSpy

    worker = gui.CommandWorker(
        [sys.executable, "-u", "-c", "import sys,time; print('partial-out'); print('partial-err',file=sys.stderr); time.sleep(5)"],
        cwd=tmp_path, env=offline_env, timeout_s=0.3,
    )
    results = QSignalSpy(getattr(worker, "result_ready", worker.finished))
    worker.run()
    assert len(results) == 1
    assert results[0][1] == 124
    assert "partial-out" in results[0][2]
    assert "partial-err" in results[0][3]


def test_command_worker_cancel_stops_its_child(gui, qt_app, tmp_path, offline_env):
    from PyQt6.QtTest import QSignalSpy

    marker = tmp_path / "child-started.txt"
    worker = gui.CommandWorker(
        [sys.executable, "-u", "-c", f"from pathlib import Path; import time; print('before-cancel'); Path({str(marker)!r}).touch(); time.sleep(30)"],
        cwd=tmp_path, env=offline_env,
    )
    assert callable(getattr(worker, "cancel", None)), "worker has no cancellation API"
    results = QSignalSpy(worker.result_ready)
    finished = QSignalSpy(worker.finished)
    worker.start()
    try:
        wait_until(marker.exists, qt_app)
        worker.cancel()
        wait_until(lambda: not worker.isRunning(), qt_app)
    finally:
        worker.cancel()
        assert worker.wait(5000)
    qt_app.processEvents()
    assert len(results) == len(finished) == 1
    assert results[0][1] == 130
    assert "before-cancel" in results[0][2]


def test_close_defers_until_worker_stops(window):
    from PyQt6.QtGui import QCloseEvent

    cancelled = []
    window.worker = SimpleNamespace(isRunning=lambda: True, cancel=lambda: cancelled.append(True))
    event = QCloseEvent()
    try:
        window.closeEvent(event)
        assert not event.isAccepted()
        assert cancelled == [True]
    finally:
        window.worker = None


def test_worker_spawn_failure_is_reported(gui, qt_app, tmp_path, offline_env):
    from PyQt6.QtTest import QSignalSpy

    worker = gui.CommandWorker([str(tmp_path / "missing-cli")], cwd=tmp_path, env=offline_env)
    results = QSignalSpy(getattr(worker, "result_ready", worker.finished))
    worker.run()
    assert len(results) == 1
    assert results[0][1] != 0
    assert results[0][3]


def test_window_releases_finished_worker_before_next_command(window, qt_app):
    argv = [sys.executable, "-c", "print('{\"status\":\"ok\"}')"]
    window.run_command(argv)
    assert not window.project_input.isEnabled()
    wait_until(lambda: window.worker is None, qt_app)
    assert window.project_input.isEnabled()
    assert not window.cancel_button.isEnabled()
    window.run_command(argv)
    wait_until(lambda: window.worker is None, qt_app)
    assert window.run_status.text() == "完成"


def test_closing_a_running_window_reaps_worker(window, qt_app):
    window.show()
    window.run_command([sys.executable, "-c", "import time; time.sleep(30)"])
    window.close()
    wait_until(lambda: window.worker is None, qt_app)
    assert not window.isVisible()
    assert window.run_status.text() == "已取消"


@pytest.mark.parametrize("platform", ["claude", "codex"])
def test_nextboard_clean_install_into_isolated_home(validator, tmp_path, offline_env, platform):
    bash = validator._find_windows_bash() if os.name == "nt" else shutil.which("bash")
    if not bash:
        pytest.skip("bash unavailable")
    home = (tmp_path / "isolated home").resolve()
    home.mkdir()
    assert home.is_relative_to(tmp_path.resolve())
    env = {**offline_env, "HOME": str(home)}
    result = subprocess.run(
        [bash, str(NEXTBOARD / "scripts" / "install.sh"), "--global", "--platform", platform],
        cwd=tmp_path, env=env, capture_output=True, text=True, encoding="utf-8", timeout=15,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    skill = home / f".{platform}" / "skills" / "hardware-solution"
    assert (skill / "scripts" / "md_to_pdf.py").is_file()
    assert (home / f".{platform}" / "agents" / "hardware-reviewer.md").is_file()
    validation = subprocess.run(
        [sys.executable, str(NEXTBOARD / "tests" / "validate.py"), str(skill), "--installed"],
        cwd=tmp_path, env=env, capture_output=True, text=True, encoding="utf-8", timeout=15,
    )
    assert validation.returncode == 0, validation.stdout + validation.stderr


def test_nextboard_checks_links_in_references(validator, tmp_path):
    skill = tmp_path / "skills" / "hardware-solution"
    references = skill / "references"
    references.mkdir(parents=True)
    (skill / "SKILL.md").write_text("[workflow](references/design-workflow.md)\n", encoding="utf-8")
    (references / "design-workflow.md").write_text("[broken](missing.md)\n", encoding="utf-8")
    validator.check_cross_references(skill)
    assert validator.fail_count == 1


def test_nextboard_accepts_external_and_fragment_links(validator, tmp_path):
    (tmp_path / "SKILL.md").write_text("# Title\n[local](#title) [external](https://example.invalid/doc)\n", encoding="utf-8")
    validator.check_cross_references(tmp_path)
    assert validator.fail_count == 0


def test_nextboard_installed_skill_requires_pdf_entrypoint(validator, tmp_path):
    skill = tmp_path / "hardware-solution"
    shutil.copytree(NEXTBOARD / "skills" / "hardware-solution", skill)
    (skill / "scripts" / "md_to_pdf.py").unlink()
    validator.check_structure(skill, installed=True)
    assert validator.fail_count > 0


def test_nextboard_template_requires_decisions_and_evidence(validator, tmp_path):
    references = tmp_path / "references"
    references.mkdir()
    (references / "output-template.md").write_text("系统框图 接口 电源树 PCB 验证计划 风险清单 原理图", encoding="utf-8")
    validator.check_output_template_sections(tmp_path)
    assert validator.fail_count > 0


def test_nextboard_source_authority_policy_is_consistent():
    for relative in ["SKILL.md", "references/design-workflow.md", "references/verification-gates.md"]:
        text = (NEXTBOARD / "skills" / "hardware-solution" / relative).read_text(encoding="utf-8")
        assert "原厂官网 > 授权分销商 > 元器件平台 > 聚合站" in text, relative
        assert "AllDatasheet > 立创" not in text, relative


def test_nextboard_installed_copy_can_be_validated_without_using_real_home(validator, tmp_path, offline_env):
    skill = tmp_path / ".codex" / "skills" / "hardware-solution"
    shutil.copytree(NEXTBOARD / "skills" / "hardware-solution", skill)
    reviewer = tmp_path / ".codex" / "agents" / "hardware-reviewer.md"
    reviewer.parent.mkdir(parents=True)
    shutil.copyfile(NEXTBOARD / "agents" / "hardware-reviewer.md", reviewer)
    result = subprocess.run(
        [sys.executable, str(NEXTBOARD / "tests" / "validate.py"), str(skill), "--installed", "--platform", "codex"],
        cwd=tmp_path, env=offline_env, capture_output=True, text=True, encoding="utf-8", timeout=15,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert str(skill) in result.stdout


def test_nextboard_uninstall_preserves_unowned_project_files(validator, tmp_path, offline_env):
    bash = validator._find_windows_bash() if os.name == "nt" else shutil.which("bash")
    if not bash:
        pytest.skip("bash unavailable")
    project = (tmp_path / "isolated project").resolve()
    project.mkdir()
    unowned = [project / name / "keep.txt" for name in ["skills", "agents", "hooks", ".claude-plugin", ".nextboard"]]
    unowned.append(project / ".gitignore")
    for path in unowned:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("user-owned\nskills/\nagents/\nhooks/\n", encoding="utf-8")
    managed_skill = project / ".codex" / "skills" / "hardware-solution"
    managed_skill.mkdir(parents=True)
    (managed_skill / "SKILL.md").write_text("isolated test installation", encoding="utf-8")
    assert project.is_relative_to(tmp_path.resolve())
    assert all(path.resolve().is_relative_to(project) for path in [*unowned, managed_skill])
    result = subprocess.run(
        [bash, str(NEXTBOARD / "scripts" / "install.sh"), "--uninstall-project", str(project)],
        cwd=tmp_path, env=offline_env, capture_output=True, text=True, encoding="utf-8", timeout=15,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert all(path.is_file() for path in unowned), "uninstaller deleted unrelated project directories"
    assert unowned[-1].read_text(encoding="utf-8") == "user-owned\nskills/\nagents/\nhooks/\n"
    assert not managed_skill.exists()
