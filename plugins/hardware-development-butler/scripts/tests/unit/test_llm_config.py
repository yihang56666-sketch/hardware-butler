"""Unit tests for LLM config + client."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, "tools")

import llm_client  # noqa: E402
import llm_config  # noqa: E402


def test_default_config_is_claude_code(tmp_path: Path) -> None:
    config = llm_config.load_config(tmp_path)
    assert config.provider == "claude-code"
    assert llm_config.is_configured(config) is True


def test_save_and_load_config_roundtrip(tmp_path: Path) -> None:
    config = llm_config.LLMConfig(
        provider="anthropic",
        api_key_env="ANTHROPIC_API_KEY",
        model="claude-sonnet-4-6",
    )
    llm_config.save_config(tmp_path, config)
    loaded = llm_config.load_config(tmp_path)
    assert loaded.provider == "anthropic"
    assert loaded.api_key_env == "ANTHROPIC_API_KEY"
    assert loaded.model == "claude-sonnet-4-6"


def test_is_configured_requires_api_key_for_anthropic(tmp_path: Path, monkeypatch) -> None:
    config = llm_config.LLMConfig(provider="anthropic", api_key_env="ANTHROPIC_API_KEY", model="m")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert llm_config.is_configured(config) is False
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    assert llm_config.is_configured(config) is True


def test_parse_intent_prompt_returns_system_and_user() -> None:
    system, prompt = llm_client.parse_intent_prompt("LED blink on PD12")
    assert "intent parser" in system.lower()
    assert "LED blink on PD12" in prompt
    assert "feature" in prompt
    assert "pin" in prompt


def test_analyze_failure_prompt_includes_error() -> None:
    system, prompt = llm_client.analyze_failure_prompt(
        stage_id="verify-goal",
        error="unmet signals: led",
        evidence={"goal": "LED blink"},
        goal="LED blink",
    )
    assert "verify-goal" in prompt
    assert "unmet signals: led" in prompt
    assert "patch_fields" in prompt


def test_call_llm_claude_code_writes_task_and_returns_pending(tmp_path: Path) -> None:
    config = llm_config.LLMConfig(provider="claude-code")
    result = llm_client.call_llm(
        tmp_path,
        config,
        task_id="test-task-1",
        prompt="test prompt",
        system="test system",
    )
    assert result["status"] == "pending"
    tasks_path = tmp_path / ".hardware-butler" / "llm-tasks.jsonl"
    assert tasks_path.exists()
    import json
    task = json.loads(tasks_path.read_text(encoding="utf-8").splitlines()[0])
    assert task["task_id"] == "test-task-1"
    assert task["prompt"] == "test prompt"


def test_read_response_returns_none_when_absent(tmp_path: Path) -> None:
    assert llm_client.read_response(tmp_path, "no-such-task") is None


def test_call_llm_returns_cached_response_when_present(tmp_path: Path) -> None:
    import json
    responses_path = tmp_path / ".hardware-butler" / "llm-responses.jsonl"
    responses_path.parent.mkdir(parents=True, exist_ok=True)
    responses_path.write_text(
        json.dumps({"task_id": "cached-task", "text": '{"feature":"led-blink"}'}) + "\n",
        encoding="utf-8",
    )
    config = llm_config.LLMConfig(provider="claude-code")
    result = llm_client.call_llm(tmp_path, config, task_id="cached-task", prompt="x", system="")
    assert result["status"] == "ok"
    assert "led-blink" in result["text"]
