"""Unit tests for safe_io module."""

import os
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
import safe_io


def test_safe_write_text_creates_file(tmp_path: Path):
    """safe_write_text should create file with content."""
    target = tmp_path / "test.txt"
    content = "Hello, World!"

    result = safe_io.safe_write_text(target, content, allowed_roots=[tmp_path])

    assert target.exists()
    assert target.read_text(encoding="utf-8") == content
    assert result == str(target)


def test_safe_write_text_creates_parent_dirs(tmp_path: Path):
    """safe_write_text should create parent directories."""
    target = tmp_path / "nested" / "dir" / "test.txt"
    content = "test"

    safe_io.safe_write_text(target, content, allowed_roots=[tmp_path])

    assert target.exists()
    assert target.read_text(encoding="utf-8") == content


def test_safe_write_text_rejects_outside_roots(tmp_path: Path):
    """safe_write_text should reject writes outside allowed roots."""
    target = tmp_path / "test.txt"
    other_root = tmp_path / "other"
    other_root.mkdir()

    with pytest.raises(ValueError, match="Refusing to write outside allowed roots"):
        safe_io.safe_write_text(target, "test", allowed_roots=[other_root])


def test_safe_write_text_with_backup(tmp_path: Path):
    """safe_write_text should create backup if file exists."""
    target = tmp_path / "test.txt"
    target.write_text("original", encoding="utf-8")

    safe_io.safe_write_text(target, "updated", allowed_roots=[tmp_path], backup_existing=True)

    backup = target.with_suffix(target.suffix + ".bak")
    assert backup.exists()
    assert backup.read_text(encoding="utf-8") == "original"
    assert target.read_text(encoding="utf-8") == "updated"


def test_safe_write_bytes_creates_file(tmp_path: Path):
    """safe_write_bytes should create file with binary content."""
    target = tmp_path / "test.bin"
    content = b"\x00\x01\x02\xFF"

    result = safe_io.safe_write_bytes(target, content, allowed_roots=[tmp_path])

    assert target.exists()
    assert target.read_bytes() == content
    assert result == str(target)


def test_reject_symlink_path_allows_normal_paths(tmp_path: Path):
    """reject_symlink_path should allow normal paths."""
    target = tmp_path / "test.txt"
    target.write_text("test")

    # Should not raise
    safe_io.reject_symlink_path(target)


@pytest.mark.skipif(os.name == "nt", reason="Symlinks require admin on Windows")
def test_reject_symlink_path_rejects_symlinks(tmp_path: Path):
    """reject_symlink_path should reject symlinks."""
    real_file = tmp_path / "real.txt"
    real_file.write_text("test")

    symlink = tmp_path / "link.txt"
    symlink.symlink_to(real_file)

    with pytest.raises(ValueError, match="Refusing to write through symlink"):
        safe_io.reject_symlink_path(symlink)


def test_validate_write_path_resolves_relative_paths(tmp_path: Path):
    """validate_write_path should resolve relative paths."""
    os.chdir(tmp_path)
    relative = Path("test.txt")

    result = safe_io.validate_write_path(relative, allowed_roots=[tmp_path])

    assert result.is_absolute()
    assert result == (tmp_path / "test.txt").resolve()


def test_is_relative_to_returns_true_for_child(tmp_path: Path):
    """is_relative_to should return True for child paths."""
    parent = tmp_path
    child = tmp_path / "subdir" / "file.txt"

    assert safe_io.is_relative_to(child, parent)


def test_is_relative_to_returns_false_for_sibling(tmp_path: Path):
    """is_relative_to should return False for sibling paths."""
    path1 = tmp_path / "dir1" / "file.txt"
    path2 = tmp_path / "dir2"

    assert not safe_io.is_relative_to(path1, path2)


@pytest.mark.parametrize("binary", [False, True])
def test_safe_write_preserves_preexisting_temp_hardlink(tmp_path: Path, binary: bool):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    target = allowed / "state.json"
    unrelated = tmp_path / "unrelated.txt"
    unrelated.write_bytes(b"must stay unchanged")
    os.link(unrelated, target.with_name(f".{target.name}.tmp"))

    if binary:
        safe_io.safe_write_bytes(target, b"new state", allowed_roots=[allowed])
    else:
        safe_io.safe_write_text(target, "new state", allowed_roots=[allowed])

    assert target.read_bytes() == b"new state"
    assert unrelated.read_bytes() == b"must stay unchanged"


@pytest.mark.parametrize("binary", [False, True])
def test_concurrent_safe_writes_have_independent_temporary_files(tmp_path: Path, monkeypatch, binary: bool):
    target = tmp_path / "state.json"
    barrier = threading.Barrier(2)
    replace = os.replace
    temporary_paths = []
    rename_lock = threading.Lock()

    def synchronized_replace(source, destination):
        temporary_paths.append(Path(source))
        barrier.wait(timeout=5)
        with rename_lock:
            return replace(source, destination)

    monkeypatch.setattr(safe_io.os, "replace", synchronized_replace)

    def write_state(content):
        if binary:
            return safe_io.safe_write_bytes(target, content.encode(), allowed_roots=[tmp_path])
        return safe_io.safe_write_text(target, content, allowed_roots=[tmp_path])

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(write_state, content) for content in ("first", "second")]
        results = [future.result() for future in futures]

    assert results == [str(target), str(target)]
    assert len(set(temporary_paths)) == 2
    assert target.read_text(encoding="utf-8") in {"first", "second"}
    assert list(tmp_path.iterdir()) == [target]
