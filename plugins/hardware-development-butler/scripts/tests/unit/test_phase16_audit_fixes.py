"""Regression tests for Phase 16 real-hardware-day audit fixes.

Covers:
1. _segger_jlink JDK-rejection (HIGH #2)
2. _stage_flash artifact_hash gate (CRITICAL)
3. consume_token TOCTOU atomicity (HIGH)
4. append_event cross-process safety (HIGH)
5. llm_client attempts count for fatal-at-first-try (MEDIUM)
"""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, "tools")


# ---------------------------------------------------------------------------
# Fix 1: _segger_jlink rejects JDK's jlink.exe on case-insensitive Windows
# ---------------------------------------------------------------------------


def test_segger_jlink_rejects_jdk_path(tmp_path: Path) -> None:
    """shutil.which returns a JDK-bundled jlink.exe path; _segger_jlink must
    reject it (return "") to avoid false-positive J-Link detection."""
    import vendor_adapters

    jdk_paths = [
        "C:/Program Files/Eclipse Adoptium/jdk-21/bin/JLink.exe",
        "D:/java/temurin/bin/JLink.exe",
        "/usr/local/zulu/bin/JLink",
        "C:/Users/me/.jdks/corretto/bin/JLink.exe",
        "/opt/adoptium/bin/JLink",
    ]
    for jdk_path in jdk_paths:
        with patch("vendor_adapters.shutil.which", return_value=jdk_path):
            assert vendor_adapters._segger_jlink() == "", (
                f"JDK path {jdk_path} should be rejected"
            )


def test_segger_jlink_accepts_real_segger_path(tmp_path: Path) -> None:
    """A genuine SEGGER install path passes through unchanged."""
    import vendor_adapters

    real_path = "C:/Program Files/SEGGER/JLink_V796b/JLink.exe"
    with patch("vendor_adapters.shutil.which", return_value=real_path):
        assert vendor_adapters._segger_jlink() == real_path


def test_segger_jlink_returns_empty_when_not_found() -> None:
    import vendor_adapters

    with patch("vendor_adapters.shutil.which", return_value=""):
        assert vendor_adapters._segger_jlink() == ""


def test_all_adapters_use_segger_jlink_not_raw_which() -> None:
    """Every adapter that detects JLink.exe must route through _segger_jlink,
    not call shutil.which('JLink.exe') directly. This catches the regression
    where a new adapter forgets the JDK guard."""
    import re

    import vendor_adapters.avr
    import vendor_adapters.c2000
    import vendor_adapters.esp32
    import vendor_adapters.imxrt
    import vendor_adapters.lpc
    import vendor_adapters.max32
    import vendor_adapters.msp430
    import vendor_adapters.nordic
    import vendor_adapters.pic32
    import vendor_adapters.ra
    import vendor_adapters.riscv
    import vendor_adapters.rx
    import vendor_adapters.stm32
    import vendor_adapters.tiva

    adapter_files = [
        "tools/vendor_adapters/avr.py",
        "tools/vendor_adapters/c2000.py",
        "tools/vendor_adapters/esp32.py",
        "tools/vendor_adapters/imxrt.py",
        "tools/vendor_adapters/lpc.py",
        "tools/vendor_adapters/max32.py",
        "tools/vendor_adapters/msp430.py",
        "tools/vendor_adapters/nordic.py",
        "tools/vendor_adapters/pic32.py",
        "tools/vendor_adapters/ra.py",
        "tools/vendor_adapters/riscv.py",
        "tools/vendor_adapters/rx.py",
        "tools/vendor_adapters/stm32.py",
        "tools/vendor_adapters/tiva.py",
    ]
    # Pattern: any line that calls shutil.which with a JLink variant but NOT
    # through _segger_jlink(). Direct calls like shutil.which("JLink.exe")
    # would bypass the JDK guard.
    raw_pattern = re.compile(r'shutil\.which\(\s*["\']JLink(?:Exe|\.exe)?["\']\s*\)')
    for path in adapter_files:
        text = Path(path).read_text(encoding="utf-8")
        # Direct shutil.which("JLink...") calls are forbidden — must use _segger_jlink()
        assert not raw_pattern.search(text), (
            f"{path} calls shutil.which('JLink...') directly — must use _segger_jlink() "
            f"to reject JDK-bundled jlink.exe"
        )


# ---------------------------------------------------------------------------
# Fix 2: _stage_flash artifact_hash gate
# ---------------------------------------------------------------------------


def test_verify_artifact_hash_blocks_missing_artifact(tmp_path: Path) -> None:
    """If the confirmed artifact is missing, verify_artifact_hash returns
    blocked-artifact-missing — _stage_flash must treat this as a hard block."""
    import hardware_action_executor

    record = {"artifact": "missing.elf", "artifact_hash": "abc123"}
    result = hardware_action_executor.verify_artifact_hash(record, root=tmp_path)
    assert result["status"] == "blocked-artifact-missing"
    assert "missing.elf" in result["message"]


def test_verify_artifact_hash_blocks_hash_mismatch(tmp_path: Path) -> None:
    """If the artifact exists but its sha256 no longer matches the plan,
    verify_artifact_hash returns blocked-artifact-hash-mismatch."""
    import hardware_action_executor

    elf = tmp_path / "fw.elf"
    elf.write_bytes(b"original content")
    record = {"artifact": str(elf), "artifact_hash": "deadbeef" * 8}
    result = hardware_action_executor.verify_artifact_hash(record, root=tmp_path)
    assert result["status"] == "blocked-artifact-hash-mismatch"
    assert result["expected_sha256"] == "deadbeef" * 8
    assert "actual_sha256" in result


def test_verify_artifact_hash_passes_when_match(tmp_path: Path) -> None:
    """Happy path: artifact exists, hash matches — status ok."""
    import hardware_action_plan
    import hardware_action_executor

    elf = tmp_path / "fw.elf"
    elf.write_bytes(b"confirmed firmware")
    real_hash = hardware_action_plan.artifact_sha256(tmp_path, str(elf))
    record = {"artifact": str(elf), "artifact_hash": real_hash}
    result = hardware_action_executor.verify_artifact_hash(record, root=tmp_path)
    assert result["status"] == "ok"
    assert result["sha256"] == real_hash


def test_verify_artifact_hash_skips_when_no_hash_in_plan(tmp_path: Path) -> None:
    """If the plan has no artifact_hash field (legacy plans), skip the check."""
    import hardware_action_executor

    record = {"artifact": "build/fw.elf", "artifact_hash": ""}
    result = hardware_action_executor.verify_artifact_hash(record, root=tmp_path)
    assert result["status"] == "ok"


# ---------------------------------------------------------------------------
# Fix 3: consume_token TOCTOU atomicity
# ---------------------------------------------------------------------------


def test_consume_token_blocks_replay_after_first_consume(tmp_path: Path) -> None:
    """After a token is consumed once, the same token must be rejected on the
    second call — this is the core replay defense."""
    import hardware_action_audit

    plan = {
        "action": "build-flash",
        "confirmation_record": {"plan_id": "p-1"},
        "hardware_side_effect": True,
        "controlled_local_action": False,
    }
    token = "hwc1-deadbeef" * 4
    r1 = hardware_action_audit.consume_token(tmp_path, token=token, plan=plan, backend="probe-rs")
    r2 = hardware_action_audit.consume_token(tmp_path, token=token, plan=plan, backend="probe-rs")
    assert r1["status"] == "ok" and r1["consumed"] is True
    assert r2["status"] == "blocked-token-replay"
    assert r2["consumed"] is False


def test_consume_token_atomic_under_concurrent_threads(tmp_path: Path) -> None:
    """20 threads race to consume the same token — exactly 1 must succeed,
    the other 19 must be blocked-token-replay. This catches TOCTOU regressions
    where the check+consume sequence isn't atomic."""
    import hardware_action_audit

    plan = {
        "action": "build-flash",
        "confirmation_record": {"plan_id": "p-race"},
        "hardware_side_effect": True,
        "controlled_local_action": False,
    }
    token = "hwc1-race-token" + "a" * 16
    results: list[dict] = []
    barrier = threading.Barrier(20)

    def worker() -> None:
        barrier.wait()
        r = hardware_action_audit.consume_token(
            tmp_path, token=token, plan=plan, backend="probe-rs"
        )
        results.append(r)

    threads = [threading.Thread(target=worker) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    ok_count = sum(1 for r in results if r["status"] == "ok")
    replay_count = sum(1 for r in results if r["status"] == "blocked-token-replay")
    assert ok_count == 1, f"expected exactly 1 consume, got {ok_count}"
    assert replay_count == 19, f"expected 19 replays blocked, got {replay_count}"


# ---------------------------------------------------------------------------
# Fix 4: append_event cross-process safety
# ---------------------------------------------------------------------------


def test_append_event_uses_true_append_mode(tmp_path: Path) -> None:
    """Source inspection: append_event must use open(path, 'a'), NOT the old
    read-modify-rewrite pattern. This is the cross-process safety fix."""
    import inspect

    import hardware_action_audit

    source = inspect.getsource(hardware_action_audit.append_event)
    # Must contain open(... "a" ...) — true append mode.
    assert '"a"' in source or "'a'" in source, (
        "append_event must use open(path, 'a') for cross-process safety, "
        "not read-modify-rewrite"
    )
    # Must NOT contain safe_io.safe_write_text (the old read-rewrite pattern).
    assert "safe_write_text" not in source, (
        "append_event must not use safe_write_text (read-modify-rewrite loses entries)"
    )


def test_append_event_concurrent_writes_preserve_all_entries(tmp_path: Path) -> None:
    """20 threads append concurrently — all 20 entries must appear in the log.
    Under the old read-rewrite pattern, ~half would be lost."""
    import hardware_action_audit

    barrier = threading.Barrier(20)

    def worker(i: int) -> None:
        barrier.wait()
        hardware_action_audit.append_event(tmp_path, {"event": "test", "worker_id": i})

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    log_path = hardware_action_audit.safety_log_path(tmp_path)
    lines = log_path.read_text(encoding="utf-8").splitlines()
    valid = [json.loads(line) for line in lines if line.strip()]
    worker_ids = {item["worker_id"] for item in valid if item.get("event") == "test"}
    assert len(worker_ids) == 20, (
        f"expected 20 entries preserved, got {len(worker_ids)} — cross-process race lost entries"
    )


# ---------------------------------------------------------------------------
# Fix 5: llm_client attempts count for fatal-at-first-try
# ---------------------------------------------------------------------------


def test_llm_client_401_reports_1_attempt_not_max(tmp_path: Path, monkeypatch) -> None:
    """A fatal 401 error on the first attempt must report attempts=1, NOT
    MAX_ATTEMPTS (which would mislead audit logs into thinking we retried)."""
    import llm_client
    import llm_config
    import urllib.error

    config = llm_config.LLMConfig(
        provider="anthropic",
        api_key_env="ANTHROPIC_API_KEY",
        model="claude-sonnet-4-6",
        max_tokens=1024,
        timeout_s=30,
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")

    def raise_401(*args, **kwargs):
        raise urllib.error.HTTPError(
            url="https://api.anthropic.com/v1/messages",
            code=401,
            msg="Unauthorized",
            hdrs=None,
            fp=None,
        )

    monkeypatch.setattr(llm_client.urllib.request, "urlopen", raise_401)
    result = llm_client.call_llm(
        tmp_path, config, task_id="t-401", prompt="hi"
    )
    assert result["status"] == "error"
    assert result["error_kind"] == "fatal"
    assert result["attempts"] == 1, (
        f"fatal 401 on first attempt must report attempts=1, got {result['attempts']}"
    )


def test_llm_client_persistent_500_reports_max_attempts(tmp_path: Path, monkeypatch) -> None:
    """A persistent 500 (transient but never recovers) must report attempts=MAX_ATTEMPTS."""
    import llm_client
    import llm_config
    import urllib.error

    config = llm_config.LLMConfig(
        provider="anthropic",
        api_key_env="ANTHROPIC_API_KEY",
        model="claude-sonnet-4-6",
        max_tokens=1024,
        timeout_s=30,
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setattr(llm_client, "INITIAL_BACKOFF_S", 0.0)
    monkeypatch.setattr(llm_client, "JITTER_S", 0.0)

    def raise_500(*args, **kwargs):
        raise urllib.error.HTTPError(
            url="https://api.anthropic.com/v1/messages",
            code=500,
            msg="Internal Server Error",
            hdrs=None,
            fp=None,
        )

    monkeypatch.setattr(llm_client.urllib.request, "urlopen", raise_500)
    result = llm_client.call_llm(
        tmp_path, config, task_id="t-500", prompt="hi"
    )
    assert result["status"] == "error"
    assert result["error_kind"] == "transient"
    assert result["attempts"] == llm_client.MAX_ATTEMPTS
