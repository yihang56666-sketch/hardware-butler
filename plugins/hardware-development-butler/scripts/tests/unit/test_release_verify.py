from __future__ import annotations

import sys
from types import SimpleNamespace

from tools import release_verify


def test_python_tools_use_the_running_interpreter_not_unrelated_path_executables() -> None:
    for step in release_verify.STEPS:
        if step.name in {"quick-tests", "lint", "typecheck", "tests"}:
            assert step.command[:2] == (sys.executable, "-m")


def test_missing_command_reports_a_failed_step_without_a_traceback(monkeypatch, capsys) -> None:
    def missing(*args: object, **kwargs: object) -> None:
        raise FileNotFoundError("tool unavailable")

    monkeypatch.setattr(release_verify.subprocess, "run", missing)
    step = release_verify.Step("missing", ("not-installed",), frozenset({"quick"}), "missing executable")
    assert release_verify.run_steps([step]) == 127
    assert "FAILED missing" in capsys.readouterr().err


def test_quick_profile_covers_no_hardware_demo_and_plugin_sync() -> None:
    names = {step.name for step in release_verify.build_steps("quick")}

    assert "package-plugin-runtime" in names
    assert "demo-guide" in names
    assert "demo-doctor" in names
    assert "demo-evidence-ask" in names
    assert "plugin-validation" in names
    assert "quick-tests" in names


def test_full_profile_covers_launch_verification_matrix() -> None:
    names = {step.name for step in release_verify.build_steps("full")}

    assert "lint" in names
    assert "typecheck" in names
    assert "tests" in names
    assert "butler-validation" in names
    assert "editable-install-dry-run" in names
    assert "dev-requirements-dry-run" in names
    assert "all-requirements-dry-run" in names
    assert "diff-check" in names


def test_format_command_keeps_command_readable() -> None:
    step = next(step for step in release_verify.STEPS if step.name == "demo-evidence-ask")

    command = release_verify.format_command(step.command)

    assert "hardware_butler.py" in command
    assert "Mcu.Package" in command


def test_build_env_defaults_python_children_to_utf8(monkeypatch) -> None:
    monkeypatch.delenv("PYTHONUTF8", raising=False)
    monkeypatch.delenv("PYTHONIOENCODING", raising=False)

    env = release_verify.build_env()

    assert env["PYTHONUTF8"] == "1"
    assert env["PYTHONIOENCODING"] == "utf-8"


def test_run_steps_captures_child_output_by_default(monkeypatch, capsys) -> None:
    calls: list[dict[str, object]] = []

    def fake_run(command: tuple[str, ...], **kwargs: object) -> SimpleNamespace:
        calls.append({"command": command, **kwargs})
        return SimpleNamespace(returncode=0, stdout="child stdout\n", stderr="child stderr\n")

    monkeypatch.setattr(release_verify.subprocess, "run", fake_run)
    step = release_verify.Step(
        name="fake-step",
        command=("fake", "command"),
        profiles=frozenset({"quick"}),
        purpose="prove compact output",
    )

    exit_code = release_verify.run_steps([step])

    output = capsys.readouterr()
    assert exit_code == 0
    assert calls[0]["capture_output"] is True
    assert calls[0]["text"] is True
    assert "PASS fake-step" in output.out
    assert "child stdout" not in output.out
    assert "child stderr" not in output.err


def test_run_steps_verbose_streams_child_output(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    def fake_run(command: tuple[str, ...], **kwargs: object) -> SimpleNamespace:
        calls.append({"command": command, **kwargs})
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(release_verify.subprocess, "run", fake_run)
    step = release_verify.Step(
        name="fake-step",
        command=("fake", "command"),
        profiles=frozenset({"quick"}),
        purpose="prove verbose output",
    )

    exit_code = release_verify.run_steps([step], verbose=True)

    assert exit_code == 0
    assert "capture_output" not in calls[0]
    assert "text" not in calls[0]


def test_run_steps_prints_captured_output_on_failure(monkeypatch, capsys) -> None:
    def fake_run(command: tuple[str, ...], **kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(returncode=9, stdout="child stdout\n", stderr="child stderr\n")

    monkeypatch.setattr(release_verify.subprocess, "run", fake_run)
    step = release_verify.Step(
        name="fake-step",
        command=("fake", "command"),
        profiles=frozenset({"quick"}),
        purpose="prove failure output",
    )

    exit_code = release_verify.run_steps([step])

    output = capsys.readouterr()
    assert exit_code == 9
    assert "child stdout" in output.out
    assert "child stderr" in output.err
    assert "FAILED fake-step with exit code 9" in output.err
