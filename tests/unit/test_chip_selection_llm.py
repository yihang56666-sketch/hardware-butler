"""Tests for Step E: LLM chip selection when context.part is empty."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, "tools")

import workflow_runner as wr  # noqa: E402


def _copy_fixture(src: Path, dst: Path) -> Path:
    if dst.exists():
        shutil.rmtree(dst, ignore_errors=True)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst)
    return dst


def test_parse_llm_json_array_extracts_list() -> None:
    text = 'Sure! Here are some candidates:\n[{"part": "STM32F407", "vendor": "ST"}, {"part": "ESP32", "vendor": "Espressif"}]\nLet me know.'
    result = wr._parse_llm_json_array(text)
    assert isinstance(result, list)
    assert len(result) == 2
    assert result[0]["part"] == "STM32F407"


def test_parse_llm_json_array_returns_none_on_invalid() -> None:
    assert wr._parse_llm_json_array("not json") is None
    assert wr._parse_llm_json_array("{}") is None


def test_llm_chip_candidates_parses_valid_response(tmp_path: Path) -> None:
    """When LLM returns valid JSON array, candidates are parsed correctly."""
    fake_response = {
        "status": "ok",
        "text": '[{"part": "STM32F407VGT6", "vendor": "STMicroelectronics", "family": "stm32", "rationale": "abundant peripherals"}, {"part": "ESP32-WROOM-32", "vendor": "Espressif", "family": "esp32", "rationale": "WiFi + BLE"}]',
    }
    state = {"workflow_id": "wf-test", "goal": "low-power BLE MCU"}
    with patch("llm_config.load_config", return_value={"provider": "claude-code", "model": "x"}):
        with patch("llm_config.is_configured", return_value=True):
            with patch("llm_client.call_llm", return_value=fake_response):
                candidates = wr._llm_chip_candidates(tmp_path, state)
    assert len(candidates) == 2
    assert candidates[0]["part"] == "STM32F407VGT6"
    assert candidates[0]["vendor"] == "STMicroelectronics"
    assert candidates[0]["family"] == "stm32"
    assert candidates[1]["part"] == "ESP32-WROOM-32"


def test_llm_chip_candidates_returns_empty_when_llm_not_configured(tmp_path: Path) -> None:
    state = {"workflow_id": "wf-test", "goal": "low-power BLE MCU"}
    with patch("llm_config.load_config", return_value={}):
        with patch("llm_config.is_configured", return_value=False):
            candidates = wr._llm_chip_candidates(tmp_path, state)
    assert candidates == []


def test_llm_chip_candidates_returns_empty_when_goal_empty(tmp_path: Path) -> None:
    state = {"workflow_id": "wf-test", "goal": ""}
    candidates = wr._llm_chip_candidates(tmp_path, state)
    assert candidates == []


def test_llm_chip_candidates_returns_empty_on_llm_failure(tmp_path: Path) -> None:
    state = {"workflow_id": "wf-test", "goal": "low-power BLE MCU"}
    with patch("llm_config.load_config", return_value={"provider": "claude-code", "model": "x"}):
        with patch("llm_config.is_configured", return_value=True):
            with patch("llm_client.call_llm", return_value={"status": "error", "text": ""}):
                candidates = wr._llm_chip_candidates(tmp_path, state)
    assert candidates == []


def test_llm_chip_candidates_skips_items_without_part(tmp_path: Path) -> None:
    fake_response = {
        "status": "ok",
        "text": '[{"part": "", "vendor": "X"}, {"part": "ESP32", "vendor": "Espressif"}]',
    }
    state = {"workflow_id": "wf-test", "goal": "wifi MCU"}
    with patch("llm_config.load_config", return_value={"provider": "claude-code", "model": "x"}):
        with patch("llm_config.is_configured", return_value=True):
            with patch("llm_client.call_llm", return_value=fake_response):
                candidates = wr._llm_chip_candidates(tmp_path, state)
    assert len(candidates) == 1
    assert candidates[0]["part"] == "ESP32"


def test_llm_chip_candidates_caps_at_five(tmp_path: Path) -> None:
    fake_response = {
        "status": "ok",
        "text": json.dumps([{"part": f"CHIP{i}", "vendor": "X"} for i in range(10)]),
    }
    state = {"workflow_id": "wf-test", "goal": "any MCU"}
    with patch("llm_config.load_config", return_value={"provider": "claude-code", "model": "x"}):
        with patch("llm_config.is_configured", return_value=True):
            with patch("llm_client.call_llm", return_value=fake_response):
                candidates = wr._llm_chip_candidates(tmp_path, state)
    assert len(candidates) == 5


import json  # noqa: E402  (used in test_llm_chip_candidates_caps_at_five)
