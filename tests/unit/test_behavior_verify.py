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


# --- extended signal-kind coverage (i2c/spi/adc/pwm/can) ---


def test_verify_signal_i2c_kind_matches_ack_keyword() -> None:
    """i2c traffic prints 'ack'/'nack'/'wrote <addr>' patterns. The fallback
    keyword path must recognize these so the optimize-loop can succeed on
    i2c-based features without a frequency or expected_text override."""
    capture = "i2c1: wrote 0x42, ack received"
    result = wr._verify_signal({"kind": "i2c"}, capture)
    assert result["matched"] is True
    assert "i2c" in result["reason"] or "ack" in result["reason"]


def test_verify_signal_i2c_kind_matches_nack_keyword() -> None:
    capture = "i2c1: nack from 0x42"
    result = wr._verify_signal({"kind": "i2c"}, capture)
    assert result["matched"] is True


def test_verify_signal_i2c_kind_no_match_when_capture_lacks_keywords() -> None:
    capture = "system idle, nothing to report"
    result = wr._verify_signal({"kind": "i2c"}, capture)
    assert result["matched"] is False
    assert "i2c" in result["reason"]


def test_verify_signal_spi_kind_matches_xfer_keyword() -> None:
    capture = "spi1: xfer 0xFF -> 0x00 (cs=low)"
    result = wr._verify_signal({"kind": "spi"}, capture)
    assert result["matched"] is True


def test_verify_signal_spi_kind_matches_mosi_miso() -> None:
    capture = "spi: mosi=0xAA miso=0x55"
    result = wr._verify_signal({"kind": "spi"}, capture)
    assert result["matched"] is True


def test_verify_signal_adc_kind_matches_sample_keyword() -> None:
    capture = "adc1 ch3: sample=2048 raw=2048 mv=1650"
    result = wr._verify_signal({"kind": "adc"}, capture)
    assert result["matched"] is True


def test_verify_signal_adc_kind_matches_mv_keyword() -> None:
    capture = "vin: 3300 mv"
    result = wr._verify_signal({"kind": "adc"}, capture)
    assert result["matched"] is True


def test_verify_signal_pwm_kind_matches_duty_keyword() -> None:
    capture = "pwm ch1: duty=50% freq=1000hz"
    result = wr._verify_signal({"kind": "pwm"}, capture)
    assert result["matched"] is True


def test_verify_signal_pwm_kind_matches_channel_keyword() -> None:
    capture = "pwm channel 2 enabled"
    result = wr._verify_signal({"kind": "pwm"}, capture)
    assert result["matched"] is True


def test_verify_signal_can_kind_matches_frame_keyword() -> None:
    capture = "can1: frame id=0x123 ext=0 dl=8"
    result = wr._verify_signal({"kind": "can"}, capture)
    assert result["matched"] is True


def test_verify_signal_can_kind_matches_id_keyword() -> None:
    capture = "rx can id=0x456 std"
    result = wr._verify_signal({"kind": "can"}, capture)
    assert result["matched"] is True


def test_verify_signal_extended_kinds_no_match_on_empty_capture() -> None:
    """All extended kinds must fail-closed on an empty capture rather than
    spuriously matching."""
    for kind in ("i2c", "spi", "adc", "pwm", "can"):
        result = wr._verify_signal({"kind": kind}, "system idle no traffic")
        assert result["matched"] is False, kind
