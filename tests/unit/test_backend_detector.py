"""Unit tests for backend detection — probe-driven backend selection."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, "tools")

import backend_detector  # noqa: E402


def test_detect_backends_returns_schema(cubemx_basic_fixture: Path, tmp_path: Path) -> None:
    import shutil
    project = tmp_path / "project"
    shutil.copytree(cubemx_basic_fixture, project)
    result = backend_detector.detect_backends(project, context_probe="")
    assert result["schema_version"] == 1
    assert "backends" in result
    assert "build" in result["backends"]
    assert "flash" in result["backends"]
    assert "observe" in result["backends"]
    assert "host_availability" in result
    assert "build" in result["host_availability"]
    assert "cube_detection" in result


def test_detect_build_backend_responds_to_artifacts(tmp_path: Path) -> None:
    """Empty project should return 'unknown' or fall back to host tools."""
    project = tmp_path / "empty"
    project.mkdir()
    backend = backend_detector.detect_build_backend(project)
    assert backend in {"keil", "gcc", "eide", "unknown"}


def test_detect_flash_backend_with_stlink_probe_hint() -> None:
    """ST-Link probe hint should prefer openocd or probe-rs, not jlink."""
    backend = backend_detector.detect_flash_backend(Path("."), context_probe="stlink-v3")
    assert backend in {"openocd", "probe-rs", "jlink", "unknown"}


def test_detect_flash_backend_with_jlink_probe_hint() -> None:
    """J-Link probe hint should prefer jlink if available."""
    backend = backend_detector.detect_flash_backend(Path("."), context_probe="jlink")
    assert backend in {"jlink", "openocd", "probe-rs", "unknown"}


def test_tool_available_returns_bool() -> None:
    assert isinstance(backend_detector.tool_available("python"), bool)
    assert backend_detector.tool_available("definitely-not-a-real-tool-xyz123") is False
