"""Tests: real-preflight — one-command readiness check for real-board day.

The preflight answers, without running any workflow: which flash backends are
installed, whether a probe is attached, whether the part's canonical chip
name actually resolves in the installed pyOCD pack database, which COM ports
exist, and the exact command to run once a board is plugged in.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, "tools")

import real_preflight as rp  # noqa: E402


def test_preflight_no_tools_reports_not_ready_with_guidance(tmp_path: Path) -> None:
    with patch("shutil.which", return_value=None):
        with patch("pathlib.Path.exists", return_value=False):
            result = rp.run_preflight(tmp_path, "STM32F407VGT6")
    assert result["status"] == "ok"
    assert result["ready"] is False
    assert result["flash_backend"] == ""
    guidance = " ".join(result["next_commands"])
    assert "pyocd" in guidance
    assert result["part_mapping"]["canonical_chip"] == "STM32F407VGTx"
    assert result["part_mapping"]["platformio_board"] == "disco_f407vg"


def _fake_proc(stdout: str = "", returncode: int = 0) -> object:
    from types import SimpleNamespace

    return SimpleNamespace(stdout=stdout, stderr="", returncode=returncode)


def test_preflight_ready_when_probe_and_target_resolve(tmp_path: Path) -> None:
    pyocd_list_probes = "  PROBE(VENDOR) | SN | FB\n  ---- | ---- | ----\n  STM32 STLink (0104) | 066DFF383333 > ST-Link\n"

    def fake_run(cmd: list[str], **kwargs: object) -> object:  # noqa: ANN003
        if "list" in cmd and "--targets" in cmd:
            name = cmd[cmd.index("-n") + 1]
            if name == "stm32f4":
                return _fake_proc("h\n--\nstm32f407vg row\n")
            if name == "stm32f407vgtx":
                return _fake_proc("h\n--\nstm32f407vgtx row\n")
            return _fake_proc("h\n--\n")
        if "list" in cmd:
            return _fake_proc(pyocd_list_probes)
        return _fake_proc()

    with patch("shutil.which", side_effect=lambda n: f"C:/fake/{n}" if n == "pyocd" else None):
        with patch("subprocess.run", side_effect=fake_run):
            result = rp.run_preflight(tmp_path, "STM32F407VGT6")
    assert result["ready"] is True
    assert result["flash_backend"] == "pyocd"
    assert result["target_status"] == "resolves"
    assert len(result["probes_attached"]) == 1
    assert "ST-Link" in result["probes_attached"][0]
    workflow_cmd = next(c for c in result["next_commands"] if "workflow-run" in c)
    assert "STM32F407VGT6" in workflow_cmd
    assert "HARDWARE_BUTLER_ENABLE_REAL_FLASH" in workflow_cmd


def test_preflight_pack_missing_vs_name_mismatch(tmp_path: Path) -> None:
    def fake_run(cmd: list[str], **kwargs: object) -> object:  # noqa: ANN003
        return _fake_proc("h\n--\n")  # every query: zero rows

    with patch("shutil.which", side_effect=lambda n: f"C:/fake/{n}" if n == "pyocd" else None):
        with patch("subprocess.run", side_effect=fake_run):
            result = rp.run_preflight(tmp_path, "STM32F407VGT6")
    assert result["target_status"] == "pack-missing"
    assert any("pack install" in c for c in result["next_commands"])


def test_preflight_reports_unresolvable_canonical_name(tmp_path: Path) -> None:
    def fake_run(cmd: list[str], **kwargs: object) -> object:  # noqa: ANN003
        if "--targets" in cmd:
            name = cmd[cmd.index("-n") + 1]
            # The F4/F9 family packs are present (7-char family prefix
            # resolves), but the specific chip query does not.
            rows = "h\n--\nrow\n" if name in ("stm32f4", "stm32f9") else "h\n--\n"
            return _fake_proc(rows)
        return _fake_proc("h\n--\n")

    with patch("shutil.which", side_effect=lambda n: f"C:/fake/{n}" if n == "pyocd" else None):
        with patch("subprocess.run", side_effect=fake_run):
            result = rp.run_preflight(tmp_path, "STM32F999VGT6")
    assert result["target_status"] == "not-found"


def test_preflight_ignores_pyocd_no_probes_notice(tmp_path: Path) -> None:
    """pyOCD prints 'No available debug probes are connected' — that must not
    count as an attached probe (ready must stay False)."""
    def fake_run(cmd: list[str], **kwargs: object) -> object:  # noqa: ANN003
        if "--targets" in cmd:
            name = cmd[cmd.index("-n") + 1]
            rows = "h\n--\nrow\n" if name in ("stm32f4", "stm32f407vgtx") else "h\n--\n"
            return _fake_proc(rows)
        return _fake_proc("h\n--\nNo available debug probes are connected\n")

    with patch("shutil.which", side_effect=lambda n: f"C:/fake/{n}" if n == "pyocd" else None):
        with patch("subprocess.run", side_effect=fake_run):
            result = rp.run_preflight(tmp_path, "STM32F407VGT6")
    assert result["probes_attached"] == []
    assert result["ready"] is False
    assert result["target_status"] == "resolves"


def test_preflight_rejects_java_jlink_false_positive(tmp_path: Path) -> None:
    with patch("shutil.which", side_effect=lambda n: (r"C:\Program Files\Eclipse Adoptium\jdk-21\bin\JLink.exe" if n == "JLink.exe" else None)):
        with patch("pathlib.Path.exists", return_value=False):
            result = rp.run_preflight(tmp_path, "STM32F407VGT6")
    assert result["tools"]["flash"]["JLink.exe"] == ""
    assert any("JDK" in w for w in result["warnings"])


def test_preflight_lists_com_ports(tmp_path: Path) -> None:
    from types import SimpleNamespace

    fake_port = SimpleNamespace(device="COM9", description="USB Serial Port (COM9)")

    class _Ports(list):
        pass

    with patch("shutil.which", return_value=None):
        with patch("pathlib.Path.exists", return_value=False):
            with patch("serial.tools.list_ports.comports", return_value=_Ports([fake_port])):
                result = rp.run_preflight(tmp_path, "STM32F407VGT6")
    assert {"device": "COM9", "description": "USB Serial Port (COM9)"} in result["com_ports"]
