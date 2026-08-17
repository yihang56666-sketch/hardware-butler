"""Tests for Step D: behavior verification (_verify_signal + _expected_signals upgrade)."""

from __future__ import annotations

import sys

sys.path.insert(0, "tools")

import workflow_runner as wr  # noqa: E402

# --- _expected_signals tests ---

def test_expected_signals_extracts_led_pin_from_pin_advice() -> None:
    plan = {
        "verification": [],
        "pin_advice": {"pin": {"name": "PD12"}},
    }
    signals = wr._expected_signals(plan)
    assert len(signals) == 1
    assert signals[0]["kind"] == "led"
    assert signals[0]["pin"] == "PD12"
    assert signals[0]["frequency_hz"] is None
    assert signals[0]["expected_text"] is None


def test_expected_signals_extracts_frequency_hz() -> None:
    plan = {
        "verification": ["LED on PD12 toggles at 2Hz"],
        "pin_advice": {},
    }
    signals = wr._expected_signals(plan)
    assert len(signals) == 1
    assert signals[0]["kind"] == "led"
    assert signals[0]["frequency_hz"] == 2


def test_expected_signals_extracts_expected_text() -> None:
    plan = {
        "verification": ['UART outputs "Hello World"'],
        "pin_advice": {},
    }
    signals = wr._expected_signals(plan)
    assert len(signals) == 1
    assert signals[0]["kind"] == "uart"
    assert signals[0]["expected_text"] == "Hello World"


def test_expected_signals_handles_rtt_swo() -> None:
    plan = {
        "verification": ["RTT prints 'tick'", "SWO output configured"],
        "pin_advice": {},
    }
    signals = wr._expected_signals(plan)
    assert len(signals) == 2
    kinds = {s["kind"] for s in signals}
    assert kinds == {"rtt", "swo"}


def test_expected_signals_empty_when_no_verification() -> None:
    plan = {"verification": [], "pin_advice": {}}
    assert wr._expected_signals(plan) == []


# --- _verify_signal tests ---

def test_verify_signal_empty_capture_returns_not_matched() -> None:
    result = wr._verify_signal({"kind": "led"}, "")
    assert result["matched"] is False
    assert "empty" in result["reason"]


def test_verify_signal_expected_text_found() -> None:
    capture = "booting...\nUART: Hello World\nready"
    result = wr._verify_signal({"kind": "uart", "expected_text": "Hello World"}, capture)
    assert result["matched"] is True
    assert "Hello World" in result["evidence_snippet"]


def test_verify_signal_expected_text_not_found() -> None:
    capture = "booting...\nUART: Goodbye\nready"
    result = wr._verify_signal({"kind": "uart", "expected_text": "Hello World"}, capture)
    assert result["matched"] is False
    assert "Hello World" in result["reason"]


def test_verify_signal_frequency_marker_found() -> None:
    capture = "LED PD12 toggle at 2Hz"
    result = wr._verify_signal({"kind": "led", "frequency_hz": 2}, capture)
    assert result["matched"] is True


def test_verify_signal_frequency_marker_not_found() -> None:
    capture = "nothing relevant here"
    result = wr._verify_signal({"kind": "led", "frequency_hz": 5}, capture)
    assert result["matched"] is False
    assert "frequency" in result["reason"]


def test_verify_signal_led_toggle_marker_fallback() -> None:
    """A single toggle marker with no timestamps cannot verify a frequency.

    Previous behavior matched on keyword presence alone — that was a false
    positive: 'LED toggle on' says nothing about the rate. The new behavior
    refuses to claim a frequency match without measurable toggle events.
    Use a capture with enough repeated markers (>=4) to actually measure.
    """
    capture = "LED PD12 toggle on"
    result = wr._verify_signal({"kind": "led", "frequency_hz": 10}, capture)
    assert result["matched"] is False
    assert "refusing" in result["reason"] or "not measurable" in result["reason"]


def test_verify_signal_kind_keyword_fallback_match() -> None:
    capture = "LED PD12 on"
    result = wr._verify_signal({"kind": "led"}, capture)
    assert result["matched"] is True
    assert "keyword" in result["reason"]


def test_verify_signal_kind_keyword_fallback_no_match() -> None:
    capture = "nothing relevant"
    result = wr._verify_signal({"kind": "uart"}, capture)
    assert result["matched"] is False
    assert "no uart keywords" in result["reason"]


def test_verify_signal_unknown_kind_returns_not_matched() -> None:
    capture = "anything"
    result = wr._verify_signal({"kind": "unknown"}, capture)
    assert result["matched"] is False
    assert "unknown signal kind" in result["reason"]


def test_sim_capture_from_signals_includes_expected_text() -> None:
    signals = [
        {"kind": "uart", "expected_text": "Hello", "pin": "", "frequency_hz": None},
        {"kind": "led", "pin": "PD12", "expected_text": None, "frequency_hz": 2},
        {"kind": "rtt", "pin": "", "expected_text": None, "frequency_hz": None},
    ]
    capture = wr._sim_capture_from_signals(signals)
    assert "Hello" in capture
    assert "PD12" in capture
    assert "2Hz" in capture
    assert "rtt" in capture
