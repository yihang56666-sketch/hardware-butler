"""Tests for frequency-measurement behavioral verification in workflow_runner.

Verifies that `_verify_signal` actually MEASURES the toggle frequency from
captures with timestamps, instead of falling back to "2hz" string matching.
This is the regression net for HANDOFF §8.3 / §19 — frequency/time-level
real behavioral evidence, not keyword match.
"""

from __future__ import annotations

import sys

sys.path.insert(0, "tools")

import workflow_runner as wr  # noqa: E402


def test_verify_signal_measures_frequency_from_timestamps() -> None:
    """Timestamped toggles at 2Hz must measure ~2Hz, not just match '2hz' string."""
    # 2Hz = 0.5s period = 0.25s between successive on-events (half-period).
    # 5 on-events at 0.25s spacing -> 4 gaps of 0.25s -> avg 0.25 -> 1/(2*0.25)=2.0Hz.
    capture = "\n".join(
        f"[{t:.3f}] app_led_blink: on" for t in (0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75)
    )
    result = wr._verify_signal(
        {"kind": "led", "frequency_hz": 2, "expected_text": None},
        capture,
    )
    assert result["matched"] is True, result
    assert "measured" in result["reason"]
    assert 1.5 <= result["measured_frequency_hz"] <= 2.5


def test_verify_signal_rejects_wrong_frequency_from_timestamps() -> None:
    """Timestamped toggles at 10Hz must NOT match an expected 2Hz."""
    # 10Hz = 0.05s between on-events.
    capture = "\n".join(
        f"[{t:.3f}] app_led_blink: on" for t in (0.0, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35)
    )
    result = wr._verify_signal(
        {"kind": "led", "frequency_hz": 2, "expected_text": None},
        capture,
    )
    assert result["matched"] is False, result
    assert "outside" in result["reason"]
    assert result["measured_frequency_hz"] > 5.0


def test_verify_signal_falls_back_to_marker_count_without_timestamps(monkeypatch) -> None:
    """When no timestamps, count markers + use observe-window as denominator."""
    # 8 markers in 8s -> 4 cycles / 8s = 0.5Hz. Expected 0.5Hz must match.
    monkeypatch.setenv("HARDWARE_BUTLER_OBSERVE_WINDOW_S", "8")
    capture = "\n".join(["app_led_blink: on"] * 8)
    result = wr._verify_signal(
        {"kind": "led", "frequency_hz": 1, "expected_text": None},  # 0.5Hz within [0.5, 2.0]
        capture,
    )
    assert result["matched"] is True, result
    assert "measured" in result["reason"]


def test_verify_signal_no_toggle_events_returns_unmatched() -> None:
    """Capture with no toggle events must not claim a frequency match."""
    capture = "booting firmware...\nLED init done\nsystem ready\n"
    result = wr._verify_signal(
        {"kind": "led", "frequency_hz": 2, "expected_text": None},
        capture,
    )
    assert result["matched"] is False
    assert "not measurable" in result["reason"] or "refusing" in result["reason"]


def test_measure_toggle_frequency_returns_none_for_empty_capture() -> None:
    assert wr._measure_toggle_frequency("", kind="led") is None


def test_measure_toggle_frequency_returns_none_for_one_event() -> None:
    """A single timestamped event has no period — cannot measure frequency."""
    assert wr._measure_toggle_frequency("[0.0] app_led_blink: on", kind="led") is None


def test_measure_toggle_frequency_two_events() -> None:
    """Two events at 0.5s apart -> 1/(2*0.5) = 1Hz."""
    capture = "[0.000] app_led_blink: on\n[0.500] app_led_blink: on"
    measured = wr._measure_toggle_frequency(capture, kind="led")
    assert measured is not None
    assert 0.9 <= measured <= 1.1


def test_measure_toggle_frequency_rejects_on_substring_false_positives() -> None:
    """Bare substring 'on' in communication/configuration must not count as LED toggles."""
    capture = "\n".join(
        [
            "communication channel ready",
            "configuration loaded",
            "monitor session started",
            "button debounce window",
            "action queue empty",
            "only debug output enabled",
            "session token refreshed",
            "system power state unknown",
        ]
    )
    assert wr._measure_toggle_frequency(capture, kind="led") is None
