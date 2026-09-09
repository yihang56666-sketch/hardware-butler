from pathlib import Path

from tools import install_plugin_sync_hook as installer


def test_install_does_not_replace_a_user_owned_hook(tmp_path: Path, monkeypatch) -> None:
    hook = tmp_path / ".git" / "hooks" / "pre-commit"
    hook.parent.mkdir(parents=True)
    hook.write_text("#!/bin/sh\necho custom-check\n", encoding="utf-8")
    monkeypatch.setattr(installer, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(installer, "HOOK_PATH", hook)
    assert installer.install() == 1
    assert "custom-check" in hook.read_text(encoding="utf-8")


def test_generated_hook_never_silently_stages_unreviewed_working_tree_files() -> None:
    assert "git add " not in installer.HOOK_BODY
    assert "commit proceeding unsynced" not in installer.HOOK_BODY
    assert "exit 1" in installer.HOOK_BODY


def test_reinstall_own_hook_is_idempotent(tmp_path: Path, monkeypatch) -> None:
    hook = tmp_path / ".git" / "hooks" / "pre-commit"
    hook.parent.mkdir(parents=True)
    monkeypatch.setattr(installer, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(installer, "HOOK_PATH", hook)
    assert installer.install() == 0
    first = hook.read_bytes()
    assert installer.install() == 0
    assert hook.read_bytes() == first
