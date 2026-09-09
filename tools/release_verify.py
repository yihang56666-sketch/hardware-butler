"""Run release-readiness checks from one local command."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

REPO_ROOT = Path(__file__).resolve().parents[1]
Profile = Literal["quick", "full"]


@dataclass(frozen=True)
class Step:
    name: str
    command: tuple[str, ...]
    profiles: frozenset[Profile]
    purpose: str


def py(*args: str) -> tuple[str, ...]:
    return (sys.executable, *args)


STEPS: tuple[Step, ...] = (
    Step(
        name="package-plugin-runtime",
        command=py("tools/package_hardware_butler_plugin.py"),
        profiles=frozenset({"quick", "full"}),
        purpose="sync the distributable plugin runtime mirror",
    ),
    Step(
        name="demo-guide",
        command=py("tools/hardware_butler.py", "guide", "--root", "tests/fixtures/cubemx-basic"),
        profiles=frozenset({"quick", "full"}),
        purpose="prove a first-time user can run the no-hardware demo guide",
    ),
    Step(
        name="demo-doctor",
        command=py("tools/hardware_butler.py", "doctor", "--root", "tests/fixtures/cubemx-basic", "--json"),
        profiles=frozenset({"quick", "full"}),
        purpose="prove the no-hardware demo reports no required errors",
    ),
    Step(
        name="demo-evidence-ask",
        command=py(
            "tools/hardware_butler.py",
            "ask",
            "--root",
            "tests/fixtures/cubemx-basic",
            "--question",
            "Mcu.Package",
            "--json",
        ),
        profiles=frozenset({"quick", "full"}),
        purpose="prove local evidence Q&A works on the no-hardware fixture",
    ),
    Step(
        name="plugin-validation",
        command=py("plugins/hardware-development-butler/scripts/validate_package.py"),
        profiles=frozenset({"quick", "full"}),
        purpose="validate plugin manifest, skill metadata, runtime, and source sync",
    ),
    Step(
        name="quick-tests",
        command=py(
            "-m",
            "pytest",
            "tests/unit/test_plugin_sync.py",
            "tests/unit/test_hardware_butler_guide.py",
            "tests/unit/test_github_launch_audit.py",
            "tests/unit/test_github_community_files.py",
            "tests/unit/test_public_docs_readability.py",
            "-q",
            "--no-cov",
            "--basetemp=.tmp-pytest-current",
        ),
        profiles=frozenset({"quick"}),
        purpose="check the launch docs/demo path, GitHub audit, community files, and plugin mirror quickly",
    ),
    Step(
        name="lint",
        command=py("-m", "ruff", "check", "tools/", "tests/"),
        profiles=frozenset({"full"}),
        purpose="lint source and tests",
    ),
    Step(
        name="typecheck",
        command=py("-m", "mypy", "tools/", "--config-file", "mypy.ini"),
        profiles=frozenset({"full"}),
        purpose="typecheck tools",
    ),
    Step(
        name="tests",
        command=py("-m", "pytest", "tests/", "-v", "--basetemp=.tmp-pytest-current"),
        profiles=frozenset({"full"}),
        purpose="run the full local test matrix, excluding opt-in hardware tests",
    ),
    Step(
        name="butler-validation",
        command=py("tests/validate_hardware_butler.py"),
        profiles=frozenset({"full"}),
        purpose="run the standalone integration validator",
    ),
    Step(
        name="editable-install-dry-run",
        command=py("-m", "pip", "install", "-e", ".", "--dry-run"),
        profiles=frozenset({"full"}),
        purpose="verify editable install metadata resolves",
    ),
    Step(
        name="dev-requirements-dry-run",
        command=py("-m", "pip", "install", "-r", "requirements-dev.txt", "--dry-run"),
        profiles=frozenset({"full"}),
        purpose="verify CI/developer dependencies resolve",
    ),
    Step(
        name="all-requirements-dry-run",
        command=py("-m", "pip", "install", "-r", "requirements-all.txt", "--dry-run"),
        profiles=frozenset({"full"}),
        purpose="verify optional integration dependencies resolve",
    ),
    Step(
        name="diff-check",
        command=("git", "diff", "--check"),
        profiles=frozenset({"full"}),
        purpose="detect whitespace errors before commit",
    ),
)


def build_steps(profile: Profile) -> list[Step]:
    return [step for step in STEPS if profile in step.profiles]


def format_command(command: tuple[str, ...]) -> str:
    return subprocess.list2cmdline(command)


def build_env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    return env


def configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")


def _print_captured_output(result: subprocess.CompletedProcess[str]) -> None:
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)


def run_steps(steps: list[Step], *, dry_run: bool = False, verbose: bool = False) -> int:
    env = build_env()
    for index, step in enumerate(steps, start=1):
        print(f"[{index}/{len(steps)}] {step.name}: {step.purpose}")
        print(f"  {format_command(step.command)}")
        if dry_run:
            continue
        try:
            if verbose:
                verbose_result = subprocess.run(step.command, cwd=REPO_ROOT, check=False, env=env)
                returncode = verbose_result.returncode
            else:
                captured_result = subprocess.run(
                    step.command,
                    cwd=REPO_ROOT,
                    check=False,
                    env=env,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                returncode = captured_result.returncode
        except OSError as error:
            print(f"FAILED {step.name}: {error}", file=sys.stderr)
            return 127
        if returncode != 0:
            if not verbose:
                _print_captured_output(captured_result)
            print(f"FAILED {step.name} with exit code {returncode}", file=sys.stderr)
            return returncode
        print(f"  PASS {step.name}")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Hardware Butler release-readiness checks.")
    parser.add_argument(
        "--profile",
        choices=("quick", "full"),
        default="full",
        help="quick checks demo/plugin readiness; full runs the local launch matrix",
    )
    parser.add_argument("--list", action="store_true", help="print selected checks without running them")
    parser.add_argument("--dry-run", action="store_true", help="print selected checks in execution order")
    parser.add_argument("--verbose", action="store_true", help="stream child command output instead of printing a summary")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    configure_stdio()
    args = parse_args(argv)
    steps = build_steps(args.profile)
    if args.list:
        for step in steps:
            print(f"{step.name}: {format_command(step.command)}")
        return 0
    return run_steps(steps, dry_run=args.dry_run, verbose=args.verbose)


if __name__ == "__main__":
    raise SystemExit(main())
