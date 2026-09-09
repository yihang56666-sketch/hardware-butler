from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PRIVATE_PATH_PATTERN = re.compile(rb"D:[\\/]|C:[\\/]Users|35182")
TEXT_SUFFIXES = {
    ".cmd",
    ".config",
    ".css",
    ".example",
    ".htm",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".md",
    ".ps1",
    ".py",
    ".sh",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}


def test_repository_text_files_do_not_expose_machine_specific_paths() -> None:
    tracked_files = [
        Path(path)
        for path in _tracked_files()
        if Path(path).suffix.lower() in TEXT_SUFFIXES
        and Path(path).name != "test_repository_privacy_boundaries.py"
    ]
    assert tracked_files

    leaks = [
        path.as_posix()
        for path in tracked_files
        if (REPO_ROOT / path).is_file() and PRIVATE_PATH_PATTERN.search((REPO_ROOT / path).read_bytes())
    ]

    assert leaks == []


def test_local_agent_allowlist_is_not_tracked() -> None:
    tracked = set(_tracked_files())
    assert "reasonix.toml" not in tracked


def _tracked_files() -> list[str]:
    completed = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
    )
    return [entry for entry in completed.stdout.decode("utf-8").split("\0") if entry]
