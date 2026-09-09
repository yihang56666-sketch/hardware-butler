import sys
from pathlib import Path
from unittest.mock import patch


def test_pyinstaller_lookup_uses_path_and_environment_without_private_fallback(tmp_path: Path) -> None:
    sys.path.insert(0, "tools")
    try:
        import build_workbench_exe
    finally:
        sys.path.remove("tools")

    with (
        patch("build_workbench_exe.shutil.which", return_value=None) as which,
        patch.dict("os.environ", {"HW_BUTLER_PYINSTALLER": ""}, clear=False),
    ):
        try:
            build_workbench_exe.pyinstaller_path()
        except SystemExit as exc:
            assert "HW_BUTLER_PYINSTALLER" in str(exc.code)
            assert "zonghesheji" not in str(exc.code)
        else:
            raise AssertionError("pyinstaller_path should fail when PyInstaller is unavailable")
        which.assert_called_once_with("pyinstaller")


def test_pyinstaller_lookup_prefers_environment_override(tmp_path: Path) -> None:
    sys.path.insert(0, "tools")
    try:
        import build_workbench_exe
    finally:
        sys.path.remove("tools")

    expected = str(tmp_path / "pyinstaller.exe")
    with (
        patch.dict("os.environ", {"HW_BUTLER_PYINSTALLER": expected}, clear=False),
        patch("build_workbench_exe.shutil.which", return_value=None) as which,
    ):
        assert build_workbench_exe.pyinstaller_path() == expected
        which.assert_not_called()
