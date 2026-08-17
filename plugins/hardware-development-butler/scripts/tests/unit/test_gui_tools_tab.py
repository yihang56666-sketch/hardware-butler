"""GUI regression tests for the PyQt6 desktop UI.

Skipped automatically when PyQt6 is unavailable (e.g. CI without the
``[ui]`` extra installed). When PyQt6 is present the tests construct the
main window on the offscreen Qt platform so no display is required.

The assertions here only cover the *structure* and *handler wiring* of the
window — they don't exercise real CLI subprocess invocations. The point is to
catch regressions where someone adds a new tab/widget but forgets to wire a
handler, or where a tab index shifts and a handler dispatches into the wrong
page.
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
GUI_DIR = REPO_ROOT / "gui"


def _pyqt6_available() -> bool:
    try:
        importlib.import_module("PyQt6.QtWidgets")  # noqa: PLC0415
    except Exception:
        return False
    return True


pytestmark = pytest.mark.skipif(
    not _pyqt6_available(),
    reason="PyQt6 not installed (install the [ui] extra to enable GUI tests)",
)


@pytest.fixture(scope="module")
def _qt_app() -> object:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    sys.path.insert(0, str(GUI_DIR))
    from PyQt6.QtWidgets import QApplication  # noqa: PLC0415

    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture()
def main_window(_qt_app: object):
    from hardware_agent_ui import HardwareButlerWindow  # noqa: PLC0415

    win = HardwareButlerWindow()
    yield win
    win.close()


def test_tab_order_is_stable(main_window) -> None:
    """Tab indices are load-bearing: handlers reference them by integer.

    If a tab is inserted in the middle, every TAB_* constant in
    hardware_agent_ui must be renumbered. This test pins the order so the
    breakage is loud.
    """
    from hardware_agent_ui import (  # noqa: PLC0415
        TAB_ACTIONS,
        TAB_ASK,
        TAB_BRAIN,
        TAB_EVIDENCE,
        TAB_HOME,
        TAB_OUTPUT,
        TAB_OVERVIEW,
        TAB_REPORTS,
        TAB_SEARCH,
        TAB_TASKS,
        TAB_TOOLS,
        TAB_TUTORIAL,
        TAB_WORKFLOW,
    )

    expected = [
        "开始工作",
        "项目大脑",
        "资料中心",
        "资料搜索",
        "问项目",
        "总览",
        "任务",
        "动作",
        "工具",
        "工作流",
        "报告",
        "教程",
        "输出",
    ]
    actual = [main_window.tabs.tabText(i) for i in range(main_window.tabs.count())]
    assert actual == expected, actual
    # Spot-check a few indices that handlers dispatch into.
    assert main_window.tabs.tabText(TAB_HOME) == "开始工作"
    assert main_window.tabs.tabText(TAB_BRAIN) == "项目大脑"
    assert main_window.tabs.tabText(TAB_EVIDENCE) == "资料中心"
    assert main_window.tabs.tabText(TAB_SEARCH) == "资料搜索"
    assert main_window.tabs.tabText(TAB_TOOLS) == "工具"
    assert main_window.tabs.tabText(TAB_OUTPUT) == "输出"
    assert main_window.tabs.tabText(TAB_WORKFLOW) == "工作流"
    assert main_window.tabs.tabText(TAB_OVERVIEW) == "总览"
    assert main_window.tabs.tabText(TAB_ASK) == "问项目"
    assert main_window.tabs.tabText(TAB_TASKS) == "任务"
    assert main_window.tabs.tabText(TAB_ACTIONS) == "动作"
    assert main_window.tabs.tabText(TAB_REPORTS) == "报告"
    assert main_window.tabs.tabText(TAB_TUTORIAL) == "教程"


def test_tools_tab_widgets_constructed(main_window) -> None:
    """The tools tab must surface the 5 high-value CLI commands the user
    previously had to remember to invoke."""
    for attr in (
        "tools_preflight_part",
        "tools_preflight_probe",
        "tools_log_path",
        "tools_fw_feature",
        "tools_fw_pin",
        "tools_fw_function",
        "tools_fw_part",
    ):
        assert hasattr(main_window, attr), attr


def test_tools_tab_handlers_callable(main_window) -> None:
    """Each tools-tab button must have a callable handler wired."""
    for attr in (
        "run_real_preflight",
        "run_classify_log",
        "run_firmware_plan",
        "run_firmware_patch",
        "run_advise_pin",
        "run_patch_ioc",
        "jump_to_search_tab",
        "_browse_log_path",
    ):
        handler = getattr(main_window, attr, None)
        assert callable(handler), attr


def test_real_preflight_requires_part(main_window, monkeypatch) -> None:
    """Without a chip part entered, run_real_preflight must NOT call the CLI;
    it should emit a hint and switch to the tools tab instead."""
    main_window.tools_preflight_part.setText("")
    main_window.tools_preflight_probe.setText("")

    invoked: list[list[str]] = []

    def fake_run_command(self, argv):  # noqa: ANN001
        invoked.append(list(argv))

    monkeypatch.setattr(type(main_window), "run_command", fake_run_command, raising=True)
    monkeypatch.setattr(type(main_window), "append_output", lambda self, msg: None, raising=True)

    main_window.run_real_preflight()
    assert invoked == [], "should refuse to run without a chip part"

    main_window.tools_preflight_part.setText("STM32F407VGT6")
    main_window.run_real_preflight()
    assert invoked, "should invoke CLI once part is provided"
    argv = invoked[-1]
    assert "real-preflight" in argv
    assert "STM32F407VGT6" in argv


def test_classify_log_requires_path(main_window, monkeypatch) -> None:
    main_window.tools_log_path.setText("")
    invoked: list[list[str]] = []
    monkeypatch.setattr(type(main_window), "run_command", lambda self, argv: invoked.append(list(argv)), raising=True)
    monkeypatch.setattr(type(main_window), "append_output", lambda self, msg: None, raising=True)

    main_window.run_classify_log()
    assert invoked == []

    main_window.tools_log_path.setText("/tmp/build.log")
    main_window.run_classify_log()
    argv = invoked[-1]
    assert "classify-log" in argv
    assert "/tmp/build.log" in argv


def test_firmware_plan_passes_optional_fields(main_window, monkeypatch) -> None:
    monkeypatch.setattr(
        type(main_window),
        "run_command",
        lambda self, argv: setattr(self, "_captured_argv", list(argv)),
        raising=True,
    )
    main_window.tools_fw_feature.setText("led-blink")
    main_window.tools_fw_pin.setText("PD12")
    main_window.tools_fw_function.setText("gpio-output")
    main_window.run_firmware_plan()
    argv = main_window._captured_argv  # type: ignore[attr-defined]
    assert "firmware-plan" in argv
    assert "--feature" in argv and "led-blink" in argv
    assert "--pin" in argv and "PD12" in argv
    assert "--function" in argv and "gpio-output" in argv


def test_advise_pin_uses_pin_and_function(main_window, monkeypatch) -> None:
    monkeypatch.setattr(
        type(main_window),
        "run_command",
        lambda self, argv: setattr(self, "_captured_adv", list(argv)),
        raising=True,
    )
    main_window.tools_fw_pin.setText("PD12")
    main_window.tools_fw_function.setText("gpio-output")
    main_window.run_advise_pin()
    argv = main_window._captured_adv  # type: ignore[attr-defined]
    assert "advise-pin" in argv
    assert "--pin" in argv and "PD12" in argv
    assert "--function" in argv and "gpio-output" in argv


def test_research_button_jumps_to_search_tab(main_window) -> None:
    """The tools tab surfaces a 'jump to research' button. Verify it dispatches
    to TAB_SEARCH so the existing research form remains the single source of
    truth."""
    from hardware_agent_ui import TAB_SEARCH, TAB_TOOLS  # noqa: PLC0415

    main_window.tabs.setCurrentIndex(TAB_TOOLS)
    main_window.jump_to_search_tab()
    assert main_window.tabs.currentIndex() == TAB_SEARCH
