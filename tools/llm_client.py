"""LLM client for the workflow runner.

Two execution modes:

1. claude-code provider: the workflow is driven by Claude Code itself. LLM
   calls cannot be made from Python code, so this module writes an "llm-task"
   bundle to .hardware-butler/llm-tasks.jsonl and the host agent (Claude)
   executes it, writing the result to .hardware-butler/llm-responses.jsonl.

2. anthropic/openai/local providers: real HTTP calls via urllib. Requires the
   user to configure api_key_env + model in llm-config.json.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import llm_config

TASKS_FILE = "llm-tasks.jsonl"
RESPONSES_FILE = "llm-responses.jsonl"


def _tasks_path(root: Path) -> Path:
    return root.resolve() / ".hardware-butler" / TASKS_FILE


def _responses_path(root: Path) -> Path:
    return root.resolve() / ".hardware-butler" / RESPONSES_FILE


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def _read_response(root: Path, task_id: str, *, max_wait_s: int = 0) -> dict[str, Any] | None:
    path = _responses_path(root)
    if not path.exists():
        return None
    deadline = time.time() + max_wait_s
    while True:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                item = json.loads(line)
            except ValueError:
                continue
            if isinstance(item, dict) and item.get("task_id") == task_id:
                return item
        if time.time() >= deadline or max_wait_s <= 0:
            return None
        time.sleep(0.2)


def _http_call_anthropic(config: llm_config.LLMConfig, prompt: str, system: str = "") -> str:
    api_key = llm_config.api_key(config)
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    payload = {
        "model": config.model or "claude-sonnet-4-6",
        "max_tokens": 1024,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        payload["system"] = system
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        config.base_url or "https://api.anthropic.com/v1/messages",
        data=body,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=config.timeout_s) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    contents = data.get("content", [])
    if contents and isinstance(contents[0], dict):
        return str(contents[0].get("text", ""))
    return ""


def _http_call_openai(config: llm_config.LLMConfig, prompt: str, system: str = "") -> str:
    api_key = llm_config.api_key(config)
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set")
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    payload = {
        "model": config.model or "gpt-4o-mini",
        "messages": messages,
        "max_tokens": 1024,
    }
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        config.base_url or "https://api.openai.com/v1/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "content-type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=config.timeout_s) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    choices = data.get("choices", [])
    if choices:
        return str(choices[0].get("message", {}).get("content", ""))
    return ""


def call_llm(
    root: Path,
    config: llm_config.LLMConfig,
    *,
    task_id: str,
    prompt: str,
    system: str = "",
) -> dict[str, Any]:
    """Call the configured LLM. Returns {"status": "ok"|"pending"|"error", "text": "..."}.

    For claude-code provider: writes an llm-task and returns pending. The host
    agent must execute it and write the response, then the caller can poll
    via read_response or re-run the stage.
    """
    if config.provider == "claude-code":
        task = {
            "schema_version": 1,
            "task_id": task_id,
            "prompt": prompt,
            "system": system,
            "model_hint": "claude",
            "timestamp": time.time(),
        }
        _append_jsonl(_tasks_path(root), task)
        cached = _read_response(root, task_id)
        if cached:
            return {"status": "ok", "text": str(cached.get("text", ""))}
        return {"status": "pending", "text": ""}
    try:
        if config.provider == "anthropic":
            text = _http_call_anthropic(config, prompt, system)
        elif config.provider == "openai":
            text = _http_call_openai(config, prompt, system)
        elif config.provider == "local":
            text = _http_call_openai(config, prompt, system)
        else:
            return {"status": "error", "text": "", "error": f"unknown provider: {config.provider}"}
        return {"status": "ok", "text": text}
    except (urllib.error.URLError, RuntimeError, ValueError) as exc:
        return {"status": "error", "text": "", "error": str(exc)}


def read_response(root: Path, task_id: str) -> dict[str, Any] | None:
    return _read_response(root, task_id)


def parse_intent_prompt(goal: str) -> tuple[str, str]:
    system = (
        "You are a hardware development intent parser. Given a user's natural-language "
        "goal, extract structured fields for an embedded firmware workflow. "
        "Respond ONLY with a JSON object, no prose."
    )
    prompt = (
        f"User goal: {goal}\n\n"
        "Extract these fields as JSON:\n"
        '- "feature": short kebab-case name for the firmware feature (e.g. "led-blink", "sensor-read")\n'
        '- "function": peripheral function class, one of: gpio-output, gpio-input, i2c, spi, uart, can, adc, pwm, timer-exti\n'
        '- "pin": MCU pin name if mentioned (e.g. "PD12", "PB7"), empty string if not\n'
        '- "instance": peripheral instance if mentioned (e.g. "I2C1", "USART2"), empty string if not\n'
        '- "part": MCU part number if mentioned (e.g. "STM32F407VGT6"), empty string if not\n'
        "If a field cannot be inferred, use empty string. Output JSON only."
    )
    return system, prompt


def analyze_failure_prompt(stage_id: str, error: str, evidence: dict[str, Any], goal: str) -> tuple[str, str]:
    system = (
        "You are a firmware debugging assistant. Given a workflow stage failure, "
        "analyze the cause and suggest a concrete fix. Respond ONLY with a JSON object."
    )
    prompt = (
        f"Goal: {goal}\n"
        f"Failed stage: {stage_id}\n"
        f"Error: {error}\n"
        f"Evidence: {json.dumps(evidence, ensure_ascii=False, default=str)[:2000]}\n\n"
        "Respond with JSON:\n"
        '- "root_cause": one-sentence explanation\n'
        '- "fix_action": concrete action to take (e.g. "change pin from PD12 to PD13", "add pull-up resistor config")\n'
        '- "patch_fields": object with fields to override in the next firmware-plan attempt '
        '(feature, pin, function, instance, part — only include fields that should change)\n'
        "Output JSON only."
    )
    return system, prompt
