"""Regression tests for repository-level pytest configuration."""

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
VENV_PYTHON = REPO_ROOT / ".venv" / "Scripts" / "python.exe"


def test_pytest_basetemp_is_per_process_and_workspace_local(monkeypatch) -> None:
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert "--basetemp=" not in pyproject
    assert "PYTEST_TEMP_PARENT = REPO_ROOT / \"tests\" / \".tmp-pytest-isolated\"" in (REPO_ROOT / "conftest.py").read_text(
        encoding="utf-8"
    )


def test_parallel_pytest_processes_receive_private_basetemp_directories(tmp_path: Path) -> None:
    if not VENV_PYTHON.exists():
        return

    probe = tmp_path / "probe.py"
    marker_root = tmp_path / "markers"
    marker_root.mkdir()
    probe.write_text(
        "\n".join(
            [
                "import os",
                "from pathlib import Path",
                "import pytest",
                "",
                "def test_report_basetemp(request):",
                "    basetemp = Path(request.config.option.basetemp)",
                "    assert Path(request.config.option.basetemp).is_relative_to(Path.cwd() / 'tests' / '.tmp-pytest-isolated')",
                f"    marker = Path(r'{marker_root}') / f'pid-{{os.getpid()}}.txt'",
                "    marker.write_text(basetemp.as_posix(), encoding='utf-8')",
            ]
        ),
        encoding="utf-8",
    )
    commands = [
        [
            str(VENV_PYTHON),
            "-m",
            "pytest",
            "-q",
            "--no-cov",
            str(probe),
        ]
        for _ in range(2)
    ]
    processes = [subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True) for command in commands]
    outputs = [process.communicate()[0] for process in processes]
    basetemps = {
        path.read_text(encoding="utf-8") for path in marker_root.glob("pid-*.txt")
    }

    assert all(process.returncode == 0 for process in processes), outputs
    assert len(basetemps) == 2, outputs
