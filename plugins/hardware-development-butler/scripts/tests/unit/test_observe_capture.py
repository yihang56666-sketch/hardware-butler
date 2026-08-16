"""Tests for P4: bounded real-observation window + JSON-Lines capture flattening."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "tools"))

import workflow_runner as wr  # noqa: E402


def test_extract_stream_text_flattens_json_lines() -> None:
    stdout = "\n".join([
        '{"type": "data", "data": "LED toggle on"}',
        "plain log line without json",
        '{"status": "ok", "summary": "read 3 lines"}',
        '{"record": {"line": "tick 2Hz"}}',
        "",
    ])
    text = wr._extract_stream_text(stdout)
    assert "LED toggle on" in text
    assert "plain log line without json" in text
    assert "tick 2Hz" in text


def test_extract_stream_text_empty() -> None:
    assert wr._extract_stream_text("") == ""
    assert wr._extract_stream_text("\n\n") == ""


def test_observe_window_defaults_and_clamps(monkeypatch: pytest.MonkeyPatch) -> None:

    assert wr._observe_window_s() == 8.0
    monkeypatch.setenv("HARDWARE_BUTLER_OBSERVE_WINDOW_S", "5")
    assert wr._observe_window_s() == 5.0
    monkeypatch.setenv("HARDWARE_BUTLER_OBSERVE_WINDOW_S", "0.2")
    assert wr._observe_window_s() == 1.0
    monkeypatch.setenv("HARDWARE_BUTLER_OBSERVE_WINDOW_S", "999")
    assert wr._observe_window_s() == 30.0
    monkeypatch.setenv("HARDWARE_BUTLER_OBSERVE_WINDOW_S", "not-a-number")
    assert wr._observe_window_s() == 8.0


def test_probe_rs_flash_command_includes_verify() -> None:
    import vendor_adapters
    adapter = vendor_adapters.get_adapter("stm32")
    assert adapter is not None
    with patch("shutil.which", return_value="/fake/probe-rs"):
        cmd = adapter.flash_via_probe_rs({"elf": "build/firmware.elf", "target": "STM32F407VGTx"})
    assert cmd[0:3] == ["probe-rs", "download", "--verify"]
    assert "--chip" in cmd and "STM32F407VGTx" in cmd
