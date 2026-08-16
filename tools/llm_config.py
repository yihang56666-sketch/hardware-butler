"""LLM configuration for the workflow runner.

Users configure their own LLM provider via .hardware-butler/llm-config.json:
  {
    "provider": "anthropic" | "openai" | "local" | "claude-code",
    "api_key_env": "ANTHROPIC_API_KEY",  # env var name, not the key itself
    "model": "claude-sonnet-4-6",
    "base_url": "",  # optional, for local/self-hosted
    "timeout_s": 30
  }

The "claude-code" provider is a special case: it signals that the workflow is
being driven by Claude Code itself, and LLM calls are handled by the host
agent (no HTTP call needed). This is the default when no config exists.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CONFIG_DIR = ".hardware-butler"
CONFIG_FILE = "llm-config.json"


@dataclass(frozen=True)
class LLMConfig:
    provider: str = "claude-code"
    api_key_env: str = ""
    model: str = ""
    base_url: str = ""
    timeout_s: int = 30
    max_tokens: int = 1024
    # Opt-in: allow the workflow to ask the LLM to WRITE firmware code
    # (app modules / drivers), not just parse intent. Default off so the
    # template generator stays the deterministic baseline.
    codegen: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "api_key_env": self.api_key_env,
            "model": self.model,
            "base_url": self.base_url,
            "timeout_s": self.timeout_s,
            "max_tokens": self.max_tokens,
            "codegen": self.codegen,
        }


def config_path(root: Path) -> Path:
    return root.resolve() / CONFIG_DIR / CONFIG_FILE


def load_config(root: Path) -> LLMConfig:
    path = config_path(root)
    if not path.exists():
        return LLMConfig()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return LLMConfig()
    provider = str(data.get("provider", "claude-code"))
    # "codex"/"host-agent" are aliases for the host-agent task-file mode
    # (the workflow is driven from inside Codex/Claude Code/Cursor, which
    # executes llm-tasks itself instead of HTTP calls).
    if provider in ("codex", "host-agent"):
        provider = "claude-code"
    return LLMConfig(
        provider=provider,
        api_key_env=data.get("api_key_env", ""),
        model=data.get("model", ""),
        base_url=data.get("base_url", ""),
        timeout_s=int(data.get("timeout_s", 30)),
        max_tokens=int(data.get("max_tokens", 1024)),
        codegen=bool(data.get("codegen", False)),
    )


def save_config(root: Path, config: LLMConfig) -> Path:
    path = config_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(config.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def api_key(config: LLMConfig) -> str:
    """Resolve the API key from the configured env var name. Never logs."""
    if not config.api_key_env:
        return ""
    return os.environ.get(config.api_key_env, "")


def is_configured(config: LLMConfig) -> bool:
    """True if the config has enough to actually call an LLM provider."""
    if config.provider == "claude-code":
        return True
    if config.provider == "local":
        return bool(config.base_url)
    return bool(config.api_key_env and api_key(config))
