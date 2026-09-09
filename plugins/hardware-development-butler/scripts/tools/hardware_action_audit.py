"""Safety log and token consumption for hardware action execution."""

from __future__ import annotations

import hashlib
import json
import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_log_locks: dict[str, threading.Lock] = {}
_log_locks_lock = threading.Lock()


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def safety_log_path(root: Path) -> Path:
    return root.resolve() / ".embeddedskills" / "safety-log.jsonl"


def read_events(root: Path) -> list[dict[str, Any]]:
    path = safety_log_path(root)
    if not path.exists():
        return []
    events = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            events.append(item)
    return events


def is_token_consumed(root: Path, token: str) -> bool:
    hashed = token_hash(token)
    return any(item.get("token_hash") == hashed and item.get("event") == "token-consumed" for item in read_events(root))


def _get_log_lock(log_path: str) -> threading.Lock:
    with _log_locks_lock:
        if log_path not in _log_locks:
            _log_locks[log_path] = threading.Lock()
    return _log_locks[log_path]


@contextmanager
def _locked_log(path: Path) -> Iterator[None]:
    with _get_log_lock(str(path)):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.with_suffix(".lock").open("a+b") as handle:
            if sys.platform == "win32":
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                if sys.platform == "win32":
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def append_event(root: Path, event: dict[str, Any]) -> str:
    """Append a JSONL event under a shared thread and process lock."""
    path = safety_log_path(root)
    payload = {
        "schema_version": 1,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **event,
    }
    line = json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n"
    with _locked_log(path):
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(line)
    return str(path)


def consume_token(root: Path, *, token: str, plan: dict[str, Any], backend: str) -> dict[str, Any]:
    """Atomically check and consume a token across threads and processes."""
    path = safety_log_path(root)
    target_hash = token_hash(token)
    with _locked_log(path):
        # Re-check inside the lock to make check+consume atomic.
        already_consumed = False
        if path.exists():
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                try:
                    item = json.loads(line)
                except ValueError:
                    continue
                if (
                    isinstance(item, dict)
                    and item.get("event") == "token-consumed"
                    and item.get("token_hash") == target_hash
                ):
                    already_consumed = True
                    break
        if already_consumed:
            return {
                "status": "blocked-token-replay",
                "consumed": False,
                "token_hash": target_hash,
                "log_path": str(path),
            }
        # Consume: append the token-consumed event under the same lock.
        payload = {
            "schema_version": 1,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": "token-consumed",
            "token_hash": target_hash,
            "plan_id": (plan.get("confirmation_record") or {}).get("plan_id", ""),
            "action": plan.get("action", ""),
            "backend": backend,
            "hardware_side_effect": bool(plan.get("hardware_side_effect")),
            "controlled_local_action": bool(plan.get("controlled_local_action")),
        }
        line = json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(line)
    return {"status": "ok", "consumed": True, "token_hash": target_hash, "log_path": str(path)}


def record_result(root: Path, *, token: str, plan: dict[str, Any], backend: str, result: dict[str, Any]) -> str:
    record = plan.get("confirmation_record") or {}
    return append_event(
        root,
        {
            "event": "execution-result",
            "token_hash": token_hash(token) if token else "",
            "plan_id": record.get("plan_id", ""),
            "action": plan.get("action", ""),
            "backend": backend,
            "status": result.get("status", ""),
            "executed": bool(result.get("executed")),
            "hardware_side_effect": bool(result.get("hardware_side_effect")),
            "child_action": result.get("child_action", ""),
            "artifact": record.get("artifact", ""),
            "artifact_hash": record.get("artifact_hash", ""),
            "returncode": result.get("returncode", ""),
            "log_classification_status": (result.get("log_classification") or {}).get("status", ""),
            "observe_samples_count": result.get("observe_samples_count", ""),
        },
    )


def audit_report(root: Path) -> dict[str, Any]:
    root = root.resolve()
    events = read_events(root)
    event_counts: dict[str, int] = {}
    action_counts: dict[str, int] = {}
    backend_counts: dict[str, int] = {}
    token_hashes: set[str] = set()
    artifact_hashes: set[str] = set()

    for event in events:
        increment(event_counts, str(event.get("event") or "unknown"))
        increment(action_counts, str(event.get("action") or "unknown"))
        increment(backend_counts, str(event.get("backend") or "unknown"))
        if event.get("token_hash"):
            token_hashes.add(str(event["token_hash"]))
        if event.get("artifact_hash"):
            artifact_hashes.add(str(event["artifact_hash"]))

    latest = sorted(events, key=lambda item: str(item.get("timestamp") or ""))[-10:]
    return {
        "schema_version": 1,
        "status": "ok",
        "root": str(root),
        "log_path": str(safety_log_path(root)),
        "event_count": len(events),
        "event_counts": event_counts,
        "action_counts": action_counts,
        "backend_counts": backend_counts,
        "unique_token_hashes": sorted(token_hashes),
        "artifact_hashes": sorted(artifact_hashes),
        "latest_events": [sanitize_event(item) for item in latest],
        "token_values_returned": False,
        "raw_tokens_returned": False,
    }


def increment(counts: dict[str, int], key: str) -> None:
    counts[key] = counts.get(key, 0) + 1


def sanitize_event(event: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in event.items() if key not in {"token"}}


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Hardware Safety Audit",
        "",
        f"- Status: {report.get('status', '')}",
        f"- Root: `{report.get('root', '')}`",
        f"- Log: `{report.get('log_path', '')}`",
        f"- Events: {report.get('event_count', 0)}",
        f"- Token values returned: {report.get('token_values_returned', False)}",
        "",
        "## Event Counts",
    ]
    for key, value in sorted((report.get("event_counts") or {}).items()):
        lines.append(f"- {key}: {value}")
    lines.append("")
    lines.append("## Backend Counts")
    for key, value in sorted((report.get("backend_counts") or {}).items()):
        lines.append(f"- {key}: {value}")
    lines.append("")
    lines.append("## Latest Events")
    for event in report.get("latest_events", []):
        lines.append(
            f"- {event.get('timestamp', '')}: {event.get('event', '')} "
            f"action={event.get('action', '')} backend={event.get('backend', '')} status={event.get('status', '')}"
        )
    return "\n".join(lines) + "\n"
