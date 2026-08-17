"""Install a git pre-commit hook that re-syncs the plugin package.

The plugins/hardware-development-butler/scripts/ directory is a packaged
runtime copy of tools/ + embeddedskills/ + nextboard/. Without a hook,
contributors must remember to run `python tools/package_hardware_butler
_plugin.py` after every source change — forgetting it produces silent
drift that the CI's `test_plugin_sync.py` only catches downstream.

This installer drops a small pre-commit hook into .git/hooks/pre-commit
that runs the packaging script. If packaging produces no diff, the hook
exits 0 and the commit proceeds. If it produces a diff (source was
changed but plugin not re-synced), the hook prints a warning, stashes
the diff into the staging area, and the commit proceeds WITH the sync.

Idempotent: re-running reinstalls the hook.
"""

from __future__ import annotations

import stat
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
HOOK_PATH = REPO_ROOT / ".git" / "hooks" / "pre-commit"

HOOK_BODY = """#!/usr/bin/env bash
# Auto-installed by tools/install_plugin_sync_hook.py
# Re-syncs the plugin package so plugins/.../scripts/ never drifts from
# tools/ + embeddedskills/ + nextboard/. If packaging produces a diff,
# the diff is staged into the current commit so the commit ships in sync.
set -e
cd "$(git rev-parse --show-toplevel)"

# Only run if source files are staged (avoid no-op cost on docs-only commits).
if ! git diff --cached --name-only | grep -E '^(tools/|embeddedskills/|nextboard/)' >/dev/null; then
    exit 0
fi

python tools/package_hardware_butler_plugin.py >/dev/null 2>&1 || {
    echo "[pre-commit] WARNING: plugin packaging failed; commit proceeding unsynced" >&2
    exit 0
}

# Stage any changed plugin files so they ship with this commit.
git add plugins/hardware-development-butler/scripts/ || true
exit 0
"""


def install() -> int:
    if not (REPO_ROOT / ".git").is_dir():
        print("not a git repository — skipping hook install", file=sys.stderr)
        return 1
    HOOK_PATH.parent.mkdir(parents=True, exist_ok=True)
    HOOK_PATH.write_text(HOOK_BODY, encoding="utf-8", newline="\n")
    # chmod +x (Windows ignores this, but POSIX needs it)
    try:
        HOOK_PATH.chmod(HOOK_PATH.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    except OSError:
        pass
    print(f"installed pre-commit hook: {HOOK_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(install())
