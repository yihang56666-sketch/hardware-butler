"""Tests for the LLM client's retry / error-classification layer.

The retry layer wraps every HTTP LLM call. It must:
- Retry transient failures (429, 5xx, URLError, TimeoutError, ConnectionError,
  OSError) up to MAX_ATTEMPTS with exponential backoff.
- NOT retry fatal failures (4xx other than 429, RuntimeError, ValueError).
- Surface structured error_kind ("transient"|"fatal") and attempts count on
  final failure.
- Sleep between retries (verified via patched time.sleep to keep tests fast).

These tests stub out the actual HTTP call (no network) and the sleep function.
"""

from __future__ import annotations

import sys
import urllib.error
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "tools"))

import llm_client  # noqa: E402
import llm_config  # noqa: E402


def _make_config(provider: str = "openai") -> llm_config.LLMConfig:
    return llm_config.LLMConfig(
        provider=provider,
        api_key_env="OPENAI_API_KEY",
        model="gpt-4o-mini",
        base_url="https://example.invalid/v1/chat/completions",
        timeout_s=5,
        max_tokens=100,
        codegen=True,
    )


# --- error classification ---


def test_classify_429_is_transient() -> None:
    exc = urllib.error.HTTPError("u", 429, "Too Many Requests", {}, None)
    assert llm_client._classify_http_error(exc) == "transient"


def test_classify_503_is_transient() -> None:
    exc = urllib.error.HTTPError("u", 503, "Service Unavailable", {}, None)
    assert llm_client._classify_http_error(exc) == "transient"


def test_classify_400_is_fatal() -> None:
    exc = urllib.error.HTTPError("u", 400, "Bad Request", {}, None)
    assert llm_client._classify_http_error(exc) == "fatal"


def test_classify_401_is_fatal() -> None:
    """Auth errors must NOT be retried — they will never succeed."""
    exc = urllib.error.HTTPError("u", 401, "Unauthorized", {}, None)
    assert llm_client._classify_http_error(exc) == "fatal"


def test_classify_urlerror_is_transient() -> None:
    exc = urllib.error.URLError("connection reset")
    assert llm_client._classify_http_error(exc) == "transient"


def test_classify_timeout_is_transient() -> None:
    assert llm_client._classify_http_error(TimeoutError("read timed out")) == "transient"


def test_classify_connection_error_is_transient() -> None:
    assert llm_client._classify_http_error(ConnectionError("broken pipe")) == "transient"


def test_classify_runtime_error_is_fatal() -> None:
    """RuntimeError is used for missing API key — not retryable."""
    assert llm_client._classify_http_error(RuntimeError("no key")) == "fatal"


def test_classify_value_error_is_fatal() -> None:
    assert llm_client._classify_http_error(ValueError("bad json")) == "fatal"


# --- retry behavior ---


def test_retry_succeeds_on_second_attempt(tmp_path: Path, monkeypatch) -> None:
    """A transient failure on attempt 1, success on attempt 2 → ok."""
    monkeypatch.setenv("OPENAI_API_KEY", "fake-key-123")
    monkeypatch.setattr(llm_client.time, "sleep", lambda _: None)
    monkeypatch.setattr(llm_client.random, "uniform", lambda a, b: 0.0)

    calls = {"n": 0}

    def fake_call() -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            raise urllib.error.HTTPError("u", 503, "Service Unavailable", {}, None)
        return "hello world"

    text, meta = llm_client._call_with_retry(fake_call)
    assert text == "hello world"
    assert meta["attempts"] == 2
    assert meta["error_kind"] is None
    assert meta["last_error"] is None


def test_retry_exhausts_on_persistent_transient(tmp_path: Path, monkeypatch) -> None:
    """All 3 attempts fail with 503 → final exception is the last one."""
    monkeypatch.setattr(llm_client.time, "sleep", lambda _: None)
    monkeypatch.setattr(llm_client.random, "uniform", lambda a, b: 0.0)

    def fake_call() -> str:
        raise urllib.error.HTTPError("u", 503, "Service Unavailable", {}, None)

    with pytest.raises(urllib.error.HTTPError) as exc_info:
        llm_client._call_with_retry(fake_call)
    assert exc_info.value.code == 503


def test_fatal_error_not_retried(tmp_path: Path, monkeypatch) -> None:
    """A 401 must NOT trigger a retry — the call returns immediately."""
    monkeypatch.setattr(llm_client.time, "sleep", lambda _: pytest.fail("must not sleep on fatal error"))

    calls = {"n": 0}

    def fake_call() -> str:
        calls["n"] += 1
        raise urllib.error.HTTPError("u", 401, "Unauthorized", {}, None)

    with pytest.raises(urllib.error.HTTPError):
        llm_client._call_with_retry(fake_call)
    assert calls["n"] == 1, "fatal error must not retry"


def test_url_error_is_retried(tmp_path: Path, monkeypatch) -> None:
    """URLError (connection reset) is transient and must be retried."""
    monkeypatch.setattr(llm_client.time, "sleep", lambda _: None)
    monkeypatch.setattr(llm_client.random, "uniform", lambda a, b: 0.0)

    calls = {"n": 0}

    def fake_call() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise urllib.error.URLError("connection reset")
        return "ok"

    text, meta = llm_client._call_with_retry(fake_call)
    assert text == "ok"
    assert meta["attempts"] == 3


def test_backoff_grows_exponentially(tmp_path: Path, monkeypatch) -> None:
    """Verify the sleep durations grow: 0.5, 1.0, 2.0 (with jitter=0)."""
    sleeps: list[float] = []
    monkeypatch.setattr(llm_client.time, "sleep", lambda s: sleeps.append(s))
    monkeypatch.setattr(llm_client.random, "uniform", lambda a, b: 0.0)

    def fake_call() -> str:
        raise urllib.error.HTTPError("u", 429, "Too Many Requests", {}, None)

    with pytest.raises(urllib.error.HTTPError):
        llm_client._call_with_retry(fake_call)
    # MAX_ATTEMPTS=3 means 2 sleeps between 3 attempts.
    assert len(sleeps) == 2
    assert sleeps[0] == pytest.approx(0.5)
    assert sleeps[1] == pytest.approx(1.0)


# --- call_llm end-to-end with stubbed HTTP ---


def test_call_llm_returns_error_kind_transient_on_persistent_503(tmp_path: Path, monkeypatch) -> None:
    """The user-facing call_llm must surface error_kind + attempts on failure."""
    config = _make_config()
    monkeypatch.setenv("OPENAI_API_KEY", "fake-key-123")
    monkeypatch.setattr(llm_client.time, "sleep", lambda _: None)
    monkeypatch.setattr(llm_client.random, "uniform", lambda a, b: 0.0)

    def fake_call(*args, **kwargs):  # noqa: ANN002, ANN003
        raise urllib.error.HTTPError("u", 503, "Service Unavailable", {}, None)

    with patch.object(llm_client, "_http_call_openai", side_effect=fake_call):
        result = llm_client.call_llm(
            tmp_path, config, task_id="t1", prompt="p", system="s", max_tokens=10,
        )
    assert result["status"] == "error"
    assert result["error_kind"] == "transient"
    assert result["attempts"] == 3
    assert "503" in result["error"]


def test_call_llm_surfaces_attempts_on_retry_success(tmp_path: Path, monkeypatch) -> None:
    """When retries eventually succeed, the attempts count is surfaced."""
    config = _make_config()
    monkeypatch.setenv("OPENAI_API_KEY", "fake-key-123")
    monkeypatch.setattr(llm_client.time, "sleep", lambda _: None)
    monkeypatch.setattr(llm_client.random, "uniform", lambda a, b: 0.0)

    calls = {"n": 0}

    def fake_call(*args, **kwargs):  # noqa: ANN002, ANN003
        calls["n"] += 1
        if calls["n"] == 1:
            raise urllib.error.HTTPError("u", 429, "Too Many Requests", {}, None)
        return "ok"

    with patch.object(llm_client, "_http_call_openai", side_effect=fake_call):
        result = llm_client.call_llm(
            tmp_path, config, task_id="t1", prompt="p", system="s", max_tokens=10,
        )
    assert result["status"] == "ok"
    assert result["text"] == "ok"
    assert result["attempts"] == 2


def test_call_llm_401_returns_fatal_without_retry(tmp_path: Path, monkeypatch) -> None:
    """Auth errors must be classified 'fatal' and not retried."""
    config = _make_config()
    monkeypatch.setenv("OPENAI_API_KEY", "fake-key-123")

    calls = {"n": 0}

    def fake_call(*args, **kwargs):  # noqa: ANN002, ANN003
        calls["n"] += 1
        raise urllib.error.HTTPError("u", 401, "Unauthorized", {}, None)

    # If the retry layer triggered on a 401, time.sleep would be called and
    # this lambda would fail the test.
    monkeypatch.setattr(llm_client.time, "sleep", lambda _: pytest.fail("must not sleep on 401"))

    with patch.object(llm_client, "_http_call_openai", side_effect=fake_call):
        result = llm_client.call_llm(
            tmp_path, config, task_id="t1", prompt="p", system="s", max_tokens=10,
        )
    assert result["status"] == "error"
    assert result["error_kind"] == "fatal"
    assert calls["n"] == 1
    # Bug fix (Phase 16): attempts must reflect the actual number of HTTP
    # calls made, NOT the MAX_ATTEMPTS ceiling. A 401 fails on attempt 1, so
    # attempts=1. (Previously this was hardcoded to MAX_ATTEMPTS=3, which
    # misreported fatal-at-first-try errors as having exhausted all retries.)
    assert result["attempts"] == 1


def test_call_llm_unknown_provider_returns_error_without_http(tmp_path: Path, monkeypatch) -> None:
    """An unknown provider string must short-circuit before any HTTP call."""
    config = _make_config(provider="bogus")
    monkeypatch.setenv("OPENAI_API_KEY", "fake-key-123")

    def fake_call() -> str:
        pytest.fail("must not call HTTP for unknown provider")

    with patch.object(llm_client, "_http_call_openai", side_effect=fake_call):
        result = llm_client.call_llm(
            tmp_path, config, task_id="t1", prompt="p", system="s", max_tokens=10,
        )
    assert result["status"] == "error"
    assert "unknown provider" in result["error"]
    assert "error_kind" not in result  # short-circuited before classification
