"""Install an optional plugin-sync pre-commit check without replacing user hooks.

Packaging can update the working-tree mirror. Any resulting changes stop the
commit so the contributor can review and stage them explicitly.
"""

from __future__ import annotations

import stat
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
HOOK_PATH = REPO_ROOT / ".git" / "hooks" / "pre-commit"
OWNED_MARKER = "# Auto-installed by tools/install_plugin_sync_hook.py"

HOOK_BODY = """#!/usr/bin/env bash
# Auto-installed by tools/install_plugin_sync_hook.py
set -e
cd "$(git rev-parse --show-toplevel)"

python tools/package_hardware_butler_plugin.py || {
    echo "[pre-commit] Plugin packaging failed; commit stopped." >&2
    exit 1
}

if ! git diff --quiet -- plugins/hardware-development-butler/ || \
    git ls-files --others --exclude-standard -- plugins/hardware-development-butler/ | grep -q .; then
    echo "[pre-commit] Review and stage the regenerated plugin before committing." >&2
    exit 1
fi
exit 0
"""


def install() -> int:
    if not (REPO_ROOT / ".git").is_dir():
        print("not a regular git checkout — skipping hook install", file=sys.stderr)
        return 1
    if HOOK_PATH.is_symlink():
        print(f"refusing to replace a linked hook: {HOOK_PATH}", file=sys.stderr)
        return 1
    if HOOK_PATH.exists() and OWNED_MARKER not in HOOK_PATH.read_text(encoding="utf-8", errors="replace"):
        print(f"existing user hook preserved: {HOOK_PATH}", file=sys.stderr)
        return 1
    HOOK_PATH.parent.mkdir(parents=True, exist_ok=True)
    HOOK_PATH.write_text(HOOK_BODY, encoding="utf-8", newline="\n")
    try:
        HOOK_PATH.chmod(HOOK_PATH.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    except OSError as error:
        print(f"hook created but executable permissions could not be set: {error}", file=sys.stderr)
        return 1
    print(f"installed pre-commit hook: {HOOK_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(install())
