"""Regression tests for command runner subprocess cleanup."""

from __future__ import annotations

from typing import Any

import command_runner


class FakePipe:
    def __init__(self) -> None:
        self.closed = False

    def read(self, size: int = -1) -> bytes:
        return b""

    def close(self) -> None:
        self.closed = True


class FakeProcess:
    def __init__(self, timeout: bool) -> None:
        self.stdout = FakePipe()
        self.stderr = FakePipe()
        self.killed = False
        self.timeout = timeout

    def wait(self, timeout: float | None = None) -> int:
        if timeout is None or not self.timeout:
            return 0
        raise command_runner.subprocess.TimeoutExpired("timeout", timeout=timeout)

    def kill(self) -> None:
        self.killed = True


def test_timeout_closes_process_output_pipes(monkeypatch: Any) -> None:
    process = FakeProcess(timeout=True)
    monkeypatch.setattr(command_runner.subprocess, "Popen", lambda *args, **kwargs: process)

    result = command_runner.run_command(
        {"argv": [str(command_runner.TRUSTED_PYTHON), "tool.py"], "label": "fixture", "phase": "inspect"},
        timeout_s=1,
    )

    assert result["status"] == "timeout"
    assert process.killed is True
    assert process.stdout.closed is True
    assert process.stderr.closed is True


def test_completed_process_closes_output_pipes(monkeypatch: Any) -> None:
    process = FakeProcess(timeout=False)
    monkeypatch.setattr(command_runner.subprocess, "Popen", lambda *args, **kwargs: process)

    result = command_runner.run_command(
        {"argv": [str(command_runner.TRUSTED_PYTHON), "tool.py"], "label": "fixture", "phase": "inspect"},
        timeout_s=1,
    )

    assert result["status"] == "ok"
    assert process.killed is False
    assert process.stdout.closed is True
    assert process.stderr.closed is True
