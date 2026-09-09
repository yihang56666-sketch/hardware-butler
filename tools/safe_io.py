"""Safe file IO helpers for product-facing commands."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def safe_write_text(
    path: Path,
    content: str,
    *,
    allowed_roots: list[Path],
    encoding: str = "utf-8",
    backup_existing: bool = False,
) -> str:
    target = validate_write_path(path, allowed_roots=allowed_roots)
    reject_symlink_path(target)
    target.parent.mkdir(parents=True, exist_ok=True)

    if backup_existing and target.exists():
        backup = target.with_suffix(target.suffix + ".bak")
        validate_write_path(backup, allowed_roots=allowed_roots)
        reject_symlink_path(backup)
        backup.write_text(target.read_text(encoding=encoding), encoding=encoding)

    tmp: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding=encoding, dir=target.parent,
            prefix=f".{target.name}.", suffix=".tmp", delete=False,
        ) as handle:
            tmp = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, target)
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)
    return str(target)


def safe_write_bytes(
    path: Path,
    content: bytes,
    *,
    allowed_roots: list[Path],
    backup_existing: bool = False,
) -> str:
    target = validate_write_path(path, allowed_roots=allowed_roots)
    reject_symlink_path(target)
    target.parent.mkdir(parents=True, exist_ok=True)

    if backup_existing and target.exists():
        backup = target.with_suffix(target.suffix + ".bak")
        validate_write_path(backup, allowed_roots=allowed_roots)
        reject_symlink_path(backup)
        backup.write_bytes(target.read_bytes())

    tmp: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=target.parent, prefix=f".{target.name}.",
            suffix=".tmp", delete=False,
        ) as handle:
            tmp = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, target)
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)
    return str(target)


def validate_write_path(path: Path, *, allowed_roots: list[Path]) -> Path:
    original = path if path.is_absolute() else Path.cwd() / path
    target = original.resolve()
    reject_symlink_path(target)
    roots = [root.resolve() for root in allowed_roots]
    if not any(is_relative_to(target, root) for root in roots):
        allowed = ", ".join(str(root) for root in roots)
        raise ValueError(f"Refusing to write outside allowed roots: {target}; allowed roots: {allowed}")
    return target


def reject_symlink_path(path: Path) -> None:
    current = Path(path.anchor) if path.anchor else Path(".")
    parts = path.parts[1:] if path.anchor else path.parts

    for part in parts:
        current = current / part
        if current.exists() and current.is_symlink():
            raise ValueError(f"Refusing to write through symlink path: {current}")


def is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True
