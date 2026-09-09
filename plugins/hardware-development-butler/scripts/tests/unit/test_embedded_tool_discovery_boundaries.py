import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_runtime_module(relative_path: str, module_name: str):
    path = REPO_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def test_wireshark_discovery_uses_program_files_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = _load_runtime_module(
        "embeddedskills/net/scripts/net_runtime.py", "boundary_net_runtime"
    )
    install_root = tmp_path / "Wireshark"
    install_root.mkdir()
    (install_root / "tshark.exe").write_text("", encoding="utf-8")

    monkeypatch.setattr(runtime.sys, "platform", "win32")
    monkeypatch.setenv("ProgramFiles", str(tmp_path))
    monkeypatch.setenv("ProgramFiles(x86)", str(tmp_path))

    assert runtime.resolve_tool_path(None, "tshark.exe") == str(
        (install_root / "tshark.exe").resolve()
    )


def test_keil_discovery_uses_keil_root_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = _load_runtime_module(
        "embeddedskills/keil/scripts/keil_runtime.py", "boundary_keil_runtime"
    )
    executable = tmp_path / "UV4" / "UV4.exe"
    executable.parent.mkdir()
    executable.write_text("", encoding="utf-8")

    monkeypatch.setattr(runtime, "which", lambda _: None)
    monkeypatch.setenv("KEIL_ROOT", str(tmp_path))

    assert runtime._auto_detect_uv4() == str(executable.resolve())


def test_vscode_discovery_uses_program_files_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = _load_runtime_module(
        "embeddedskills/eide/scripts/eide_runtime.py", "boundary_eide_runtime"
    )
    executable = tmp_path / "Microsoft VS Code" / "bin" / "code.cmd"
    executable.parent.mkdir(parents=True)
    executable.write_text("", encoding="utf-8")

    monkeypatch.setattr(runtime, "which", lambda _: None)
    monkeypatch.setenv("ProgramFiles", str(tmp_path))
    monkeypatch.setenv("ProgramFiles(x86)", str(tmp_path / "x86"))

    assert runtime._auto_detect_code() == str(executable.resolve())
