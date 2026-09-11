"""Pytest configuration and fixtures."""

import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

import pytest

# Add tools and embeddedskills to path
REPO_ROOT = Path(__file__).parent
TOOLS_DIR = REPO_ROOT / "tools"

if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import runtime_context  # noqa: E402

EMBEDDED_DIR = runtime_context.embeddedskills_root()
if str(EMBEDDED_DIR) not in sys.path:
    sys.path.insert(0, str(EMBEDDED_DIR))

PYTEST_TEMP_PARENT = REPO_ROOT / "tests" / ".tmp-pytest-isolated"


def _remove_with_retry(path: Path) -> None:
    """Remove temporary directories while tolerating Windows handle races."""
    for attempt in range(3):
        try:
            if path.is_symlink() or path.is_file():
                path.unlink()
            elif path.exists():
                shutil.rmtree(path)
            return
        except FileNotFoundError:
            return
        except PermissionError:
            if attempt == 2:
                raise
            time.sleep(0.1 * (attempt + 1))


def pytest_configure(config: pytest.Config) -> None:
    """Give each pytest process a private, workspace-local basetemp.

    A fixed ``--basetemp`` made simultaneous pytest runs delete each other's
    temporary files on Windows. Per-process directories keep parallel runs
    isolated while retaining the accessibility requirement tested by the suite.
    """
    if config.getoption("--basetemp", default=None):
        return
    PYTEST_TEMP_PARENT.mkdir(parents=True, exist_ok=True)
    prefix = f"pytest-{os.getpid()}-"
    basetemp = Path(tempfile.mkdtemp(prefix=prefix, dir=PYTEST_TEMP_PARENT))
    config.option.basetemp = basetemp


def pytest_unconfigure(config: pytest.Config) -> None:
    """Remove only this process's private basetemp directory."""
    current = getattr(config.option, "basetemp", None)
    if current:
        _remove_with_retry(Path(str(current)))


@pytest.fixture
def repo_root() -> Path:
    """Repository root directory."""
    return REPO_ROOT


@pytest.fixture
def tools_dir() -> Path:
    """Tools directory."""
    return TOOLS_DIR


@pytest.fixture
def test_fixture_dir() -> Path:
    """Test fixtures directory."""
    return REPO_ROOT / "tests" / "fixtures"


@pytest.fixture
def cubemx_basic_fixture(test_fixture_dir: Path) -> Path:
    """CubeMX basic test fixture."""
    fixture = test_fixture_dir / "cubemx-basic"
    if not fixture.exists():
        pytest.skip("CubeMX basic fixture not found")
    return fixture


@pytest.fixture
def temp_workspace(tmp_path: Path) -> Path:
    """Temporary workspace for tests."""
    workspace = tmp_path / "test-workspace"
    workspace.mkdir()
    return workspace


def _pytest_embedded_plugin_active(pluginmanager: pytest.PytestPluginManager) -> bool:
    """Return True when the pytest-embedded plugin is active.

    pytest-embedded already registers ``--target`` and ``--port`` (and a real
    ``dut`` fixture). When it is active we must not re-register those options
    or pytest aborts with an argparse conflict; we only add our own
    ``--run-hardware`` gate. The project's default addopts disables the plugin
    because its 2.8 fixture setup emits experimental-API warnings that turn
    into setup errors under ``-W error``; local fixtures provide fallbacks so
    hardware tests remain collectable.
    """
    return pluginmanager.hasplugin("pytest_embedded")


def pytest_addoption(
    parser: pytest.Parser, pluginmanager: pytest.PytestPluginManager
) -> None:
    """Register opt-in switches for tests with physical side effects.

    ``pytest_addoption`` is only honoured in the rootdir ``conftest.py`` (or a
    plugin), so the hardware-bench options live here even though the matching
    fixtures live in ``tests/conftest.py``.
    """
    parser.addoption(
        "--run-hardware",
        action="store_true",
        default=False,
        help="Run tests marked hardware. These may require connected probes or boards.",
    )
    if _pytest_embedded_plugin_active(pluginmanager):
        # pytest-embedded owns --target/--port; re-registering them would make
        # pytest fail to start with an argparse conflict.
        return
    parser.addoption(
        "--target",
        action="store",
        default="stm32f407vgtx",
        help="Target MCU for hardware tests.",
    )
    parser.addoption(
        "--port",
        action="store",
        default=None,
        help="Serial port for hardware communication.",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Keep normal test runs off real probes and boards unless explicitly requested."""
    if config.getoption("--run-hardware"):
        return

    skip_hardware = pytest.mark.skip(reason="requires --run-hardware")
    for item in items:
        if "hardware" in item.keywords:
            item.add_marker(skip_hardware)
