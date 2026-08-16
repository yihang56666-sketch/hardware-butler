"""Regression tests for repository-level pytest configuration."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_pytest_basetemp_uses_accessible_workspace_directory() -> None:
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert "--basetemp=tests/.tmp-pytest-runtime" in pyproject
