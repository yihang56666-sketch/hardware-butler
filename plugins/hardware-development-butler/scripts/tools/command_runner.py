"""Run safe commands from a hardware butler build plan.

The runner is intentionally narrow. By default it only runs commands that:
- have no hardware side effect,
- do not require confirmation,
- do not contain placeholders,
- do not declare writes.

This makes it suitable for automatic discovery phases while keeping build,
flash, debug, and bus actions behind separate gates.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, TypedDict, cast

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import build_plan  # noqa: E402
import runtime_context  # noqa: E402
import safe_io  # noqa: E402

REPO_ROOT = runtime_context.PACKAGE_ROOT
TRUSTED_PYTHON = Path(sys.executable).resolve()
MAX_CAPTURE_CHARS = 64 * 1024
SAFE_ENV_KEYS = {"COMSPEC", "PATH", "PATHEXT", "SYSTEMROOT", "TEMP", "TMP", "WINDIR"}


ALLOWED_PYTHON_COMMANDS = {
    "tools/cube_detect.py": {
        "phases": {"inspect"},
        "subcommands": None,
    },
    "tools/hardware_butler_inspect.py": {
        "phases": {"inspect"},
        "subcommands": None,
    },
    "tools/build_log_classifier.py": {
        "phases": {"diagnose"},
        "subcommands": None,
    },
    "embeddedskills/keil/scripts/keil_project.py": {
        "phases": {"build-discovery"},
        "subcommands": {"scan", "targets"},
    },
    "embeddedskills/gcc/scripts/gcc_project.py": {
        "phases": {"build-discovery"},
        "subcommands": {"scan", "presets"},
    },
    "embeddedskills/eide/scripts/eide_project.py": {
        "phases": {"build-discovery"},
        "subcommands": {"scan"},
    },
}


class CommandPolicy(TypedDict):
    phases: set[str]
    subcommands: set[str] | None


ALLOWED_COMMAND_POLICIES = cast(dict[str, CommandPolicy], ALLOWED_PYTHON_COMMANDS)


def configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8", errors="replace")


def run_plan(
    root: Path,
    *,
    phase: str = "",
    allow_writes: bool = False,
    allow_confirmation: bool = False,
    timeout_s: int = 60,
) -> dict[str, Any]:
    plan = build_plan.generate_plan(root)
    results = []
    for item in plan["commands"]:
        if phase and item["phase"] != phase:
            results.append(skipped(item, f"phase mismatch: wanted {phase}"))
            continue
        reason = skip_reason(item, allow_writes=allow_writes, allow_confirmation=allow_confirmation)
        if reason:
            results.append(skipped(item, reason))
            continue
        results.append(run_command(item, timeout_s=timeout_s))

    return {
        "schema_version": 1,
        "root": plan["root"],
        "phase_filter": phase or "all",
        "allow_writes": allow_writes,
        "allow_confirmation": allow_confirmation,
        "safety_policy": {
            "metadata_gates": ["hardware_side_effect", "requires_confirmation", "writes", "placeholders"],
            "hard_allowlist": sorted(ALLOWED_PYTHON_COMMANDS),
            "trusted_python": str(TRUSTED_PYTHON),
        },
        "results": results,
        "summary": summarize(results),
    }


def skip_reason(item: dict[str, Any], *, allow_writes: bool, allow_confirmation: bool) -> str:
    if item.get("hardware_side_effect"):
        return "hardware side effect is not allowed"
    if item.get("requires_confirmation") and not allow_confirmation:
        return "command requires confirmation"
    if item.get("writes") and not allow_writes:
        return "command declares writes"
    if item.get("placeholders"):
        return f"command contains placeholders: {', '.join(item['placeholders'])}"
    allowlist_reason = allowlist_denial_reason(item)
    if allowlist_reason:
        return allowlist_reason
    return ""


def allowlist_denial_reason(item: dict[str, Any]) -> str:
    argv = item.get("argv", [])
    if len(argv) < 2:
        return "command is not a supported Python script invocation"

    if not is_trusted_python(str(argv[0])):
        return "command executable is not the trusted Python interpreter"

    script = allowed_script_key(str(argv[1]))
    policy = ALLOWED_COMMAND_POLICIES.get(script)
    if not policy:
        return f"script is not on the safe allowlist: {script}"

    phases = policy["phases"]
    if item.get("phase") not in phases:
        return f"script is not allowed in phase: {item.get('phase', '')}"

    subcommands = policy["subcommands"]
    if subcommands is not None:
        if len(argv) < 3:
            return f"script requires one of these safe subcommands: {', '.join(sorted(subcommands))}"
        subcommand = str(argv[2])
        if subcommand not in subcommands:
            return f"subcommand is not on the safe allowlist: {subcommand}"

    schema_reason = argv_schema_denial_reason(script, argv)
    if schema_reason:
        return schema_reason

    return ""


def allowed_script_key(value: str) -> str:
    script_path = resolve_script_path(value)
    for key in ALLOWED_PYTHON_COMMANDS:
        allowed_path = allowed_script_path(key)
        if os.path.normcase(str(script_path)) == os.path.normcase(str(allowed_path)):
            return key
    return normalize_script_path(value)


def allowed_script_path(key: str) -> Path:
    path = Path(key)
    if path.parts and path.parts[0] == "embeddedskills":
        return (Path(runtime_context.embeddedskills_root()) / Path(*path.parts[1:])).resolve()
    return (Path(runtime_context.PACKAGE_ROOT) / path).resolve()


def argv_schema_denial_reason(script: str, argv: list[Any]) -> str:
    parts = [str(item) for item in argv[2:]]
    schemas = {
        "tools/cube_detect.py": [["--root", "PATH", "--json"]],
        "tools/hardware_butler_inspect.py": [["--root", "PATH", "--out-dir", "WRITE_PATH", "--json"]],
        "tools/build_log_classifier.py": [["PATH", "--json"]],
        "embeddedskills/keil/scripts/keil_project.py": [
            ["scan", "--root", "PATH", "--json"],
            ["targets", "--project", "PATH", "--json"],
        ],
        "embeddedskills/gcc/scripts/gcc_project.py": [
            ["scan", "--root", "PATH", "--json"],
            ["presets", "--project", "PATH", "--json"],
        ],
        "embeddedskills/eide/scripts/eide_project.py": [["scan", "--root", "PATH", "--json"]],
    }
    for schema in schemas.get(script, []):
        if argv_matches_schema(parts, schema):
            return ""
    return f"argv schema is not on the safe allowlist for {script}"


def argv_matches_schema(parts: list[str], schema: list[str]) -> bool:
    if len(parts) != len(schema):
        return False
    for value, expected in zip(parts, schema):
        if expected == "PATH":
            if not safe_read_path_arg(value):
                return False
        elif expected == "WRITE_PATH":
            if not safe_write_path_arg(value):
                return False
        elif value != expected:
            return False
    return True


def safe_read_path_arg(value: str) -> bool:
    if "<" in value or ">" in value:
        return False
    path = resolve_workspace_path(value)
    return is_within_repo(path) and not path_has_symlink(path)


def safe_write_path_arg(value: str) -> bool:
    if "<" in value or ">" in value:
        return False
    path = resolve_workspace_path(value)
    return is_within_repo(path) and not path_has_symlink(path)


def resolve_workspace_path(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = runtime_context.workspace_root() / path
    return path.resolve()


def is_within_repo(path: Path) -> bool:
    try:
        path.relative_to(runtime_context.workspace_root())
    except ValueError:
        return False
    return True


def path_has_symlink(path: Path) -> bool:
    current = Path(path.anchor) if path.anchor else Path(".")
    parts = path.parts[1:] if path.anchor else path.parts
    for part in parts:
        current = current / part
        if current.exists() and current.is_symlink():
            return True
    return False


def is_trusted_python(value: str) -> bool:
    path = Path(value)
    if not path.is_absolute():
        return False
    try:
        candidate = path.resolve()
    except OSError:
        return False
    return os.path.normcase(str(candidate)) == os.path.normcase(str(TRUSTED_PYTHON))


def canonical_argv(item: dict[str, Any]) -> list[str]:
    argv = list(item["argv"])
    argv[0] = str(TRUSTED_PYTHON)
    argv[1] = str(resolve_script_path(str(argv[1])))
    return argv


def resolve_script_path(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        if path.parts and path.parts[0] == "embeddedskills":
            path = Path(runtime_context.embeddedskills_root()) / Path(*path.parts[1:])
        else:
            path = Path(runtime_context.PACKAGE_ROOT) / path
    return path.resolve()


def normalize_script_path(value: str) -> str:
    script = resolve_script_path(value)
    try:
        path = script.relative_to(runtime_context.PACKAGE_ROOT)
    except ValueError:
        embedded = Path(runtime_context.embeddedskills_root())
        try:
            return (Path("embeddedskills") / script.relative_to(embedded)).as_posix().lower()
        except ValueError:
            path = script
    return path.as_posix().lower()


def skipped(item: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "label": item["label"],
        "phase": item["phase"],
        "status": "skipped",
        "reason": reason,
        "argv": item["argv"],
    }


def run_command(item: dict[str, Any], *, timeout_s: int) -> dict[str, Any]:
    started = time.time()
    env = minimal_env()
    env["PYTHONIOENCODING"] = "utf-8"
    env[runtime_context.ENV_WORKSPACE_ROOT] = str(runtime_context.workspace_root())
    argv = canonical_argv(item)
    process: subprocess.Popen[bytes] | None = None
    try:
        process = subprocess.Popen(
            argv,
            cwd=runtime_context.PACKAGE_ROOT,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stdout_capture = LimitedPipeCapture(process.stdout)
        stderr_capture = LimitedPipeCapture(process.stderr)
        stdout_capture.start()
        stderr_capture.start()
        returncode = process.wait(timeout=timeout_s)
        stdout_capture.join()
        stderr_capture.join()
        _close_process_pipes(process)
        duration_ms = int((time.time() - started) * 1000)
        return {
            "label": item["label"],
            "phase": item["phase"],
            "status": "ok" if returncode == 0 else "error",
            "returncode": returncode,
            "duration_ms": duration_ms,
            "argv": argv,
            "stdout": stdout_capture.text(),
            "stderr": stderr_capture.text(),
            "stdout_truncated": stdout_capture.truncated,
            "stderr_truncated": stderr_capture.truncated,
        }
    except subprocess.TimeoutExpired as exc:
        if process is not None:
            process.kill()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
            _close_process_pipes(process)
        duration_ms = int((time.time() - started) * 1000)
        return {
            "label": item["label"],
            "phase": item["phase"],
            "status": "timeout",
            "returncode": None,
            "duration_ms": duration_ms,
            "argv": argv,
            "stdout": "",
            "stderr": completed_text(exc.stderr),
            "stdout_truncated": False,
            "stderr_truncated": False,
        }


def _close_process_pipes(process: subprocess.Popen[bytes]) -> None:
    for stream in (process.stdout, process.stderr):
        if stream is not None and not stream.closed:
            stream.close()


class LimitedPipeCapture:
    def __init__(self, pipe: Any) -> None:
        self.pipe = pipe
        self.data = bytearray()
        self.truncated = False
        self.thread = threading.Thread(target=self._read, daemon=True)

    def start(self) -> None:
        self.thread.start()

    def join(self) -> None:
        self.thread.join(timeout=5)

    def text(self) -> str:
        suffix = "\n[output truncated]\n" if self.truncated else ""
        return self.data.decode("utf-8", errors="replace") + suffix

    def _read(self) -> None:
        if self.pipe is None:
            return
        while True:
            chunk = self.pipe.read(4096)
            if not chunk:
                break
            remaining = MAX_CAPTURE_CHARS - len(self.data)
            if remaining > 0:
                self.data.extend(chunk[:remaining])
            if len(chunk) > remaining:
                self.truncated = True


def minimal_env() -> dict[str, str]:
    return {key: value for key, value in os.environ.items() if key.upper() in SAFE_ENV_KEYS}


def bounded_text(value: str) -> str:
    if len(value) <= MAX_CAPTURE_CHARS:
        return value
    return value[:MAX_CAPTURE_CHARS] + "\n[output truncated]\n"


def completed_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def summarize(results: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"ok": 0, "error": 0, "timeout": 0, "skipped": 0}
    for item in results:
        status = item.get("status", "error")
        counts[status] = counts.get(status, 0) + 1
    return counts


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Safe Plan Run Report",
        "",
        f"- Root: `{report['root']}`",
        f"- Phase filter: `{report['phase_filter']}`",
        f"- Allow writes: {report['allow_writes']}",
        f"- Allow confirmation: {report['allow_confirmation']}",
        "",
        "## Safety Policy",
        "",
        f"- Metadata gates: {', '.join(report['safety_policy']['metadata_gates'])}",
        f"- Hard allowlist entries: {len(report['safety_policy']['hard_allowlist'])}",
        f"- Trusted Python: `{report['safety_policy']['trusted_python']}`",
        "",
        "## Summary",
        "",
    ]
    for key, value in report["summary"].items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Results", ""])
    for item in report["results"]:
        lines.append(f"### {item['label']}")
        lines.append("")
        lines.append(f"- Phase: `{item['phase']}`")
        lines.append(f"- Status: `{item['status']}`")
        if item.get("reason"):
            lines.append(f"- Reason: {item['reason']}")
        if "returncode" in item:
            lines.append(f"- Return code: {item['returncode']}")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    configure_stdio()
    parser = argparse.ArgumentParser(description="Run safe commands from a build plan")
    parser.add_argument("--root", default=".", help="Project root")
    parser.add_argument("--phase", default="", help="Optional phase filter, e.g. build-discovery")
    parser.add_argument("--allow-writes", action="store_true")
    parser.add_argument("--allow-confirmation", action="store_true")
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    report = run_plan(
        Path(args.root),
        phase=args.phase,
        allow_writes=args.allow_writes,
        allow_confirmation=args.allow_confirmation,
        timeout_s=args.timeout,
    )
    content = json.dumps(report, ensure_ascii=False, indent=2) if args.as_json else render_markdown(report)
    if args.out:
        safe_io.safe_write_text(Path(args.out), content, allowed_roots=runtime_context.allowed_write_roots())
    else:
        print(content)


if __name__ == "__main__":
    main()
