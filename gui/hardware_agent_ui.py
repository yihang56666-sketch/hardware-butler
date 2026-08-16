"""Desktop workflow console for the Hardware Butler CLI."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

try:  # qt-material is packaged into the exe, but source mode should degrade gracefully.
    from qt_material import apply_stylesheet
except ImportError:  # pragma: no cover - optional source-mode dependency
    apply_stylesheet = None


FROZEN = bool(getattr(sys, "frozen", False))
APP_ROOT = Path(sys.executable).resolve().parent if FROZEN else Path(__file__).resolve().parents[1]
SOURCE_CLI = APP_ROOT / "tools" / "hardware_butler.py"
CLI_EXE_NAME = "hardware_butler_cli.exe"
TAB_HOME = 0
TAB_BRAIN = 1
TAB_EVIDENCE = 2
TAB_SEARCH = 3
TAB_ASK = 4
TAB_OVERVIEW = 5
TAB_TASKS = 6
TAB_ACTIONS = 7
TAB_WORKFLOW = 8
TAB_REPORTS = 9
TAB_TUTORIAL = 10
TAB_OUTPUT = 11


def frozen_cli_candidates() -> list[Path]:
    """Return likely CLI exe locations for one-folder and copied bundles."""

    return [
        APP_ROOT / CLI_EXE_NAME,
        APP_ROOT / "hardware_butler_cli" / CLI_EXE_NAME,
        APP_ROOT.parent / "hardware_butler_cli" / CLI_EXE_NAME,
        APP_ROOT.parent / CLI_EXE_NAME,
    ]


def find_frozen_cli() -> Path:
    for candidate in frozen_cli_candidates():
        if candidate.exists():
            return candidate
    return APP_ROOT / CLI_EXE_NAME


class CommandWorker(QThread):
    finished = pyqtSignal(list, int, str, str)

    def __init__(self, argv: list[str], *, cwd: Path, env: dict[str, str]) -> None:
        super().__init__()
        self.argv = argv
        self.cwd = cwd
        self.env = env

    def run(self) -> None:
        try:
            result = subprocess.run(
                self.argv,
                cwd=self.cwd,
                shell=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=120,
                env=self.env,
            )
            self.finished.emit(self.argv, result.returncode, result.stdout, result.stderr)
        except Exception as exc:  # pragma: no cover - UI safety net
            self.finished.emit(self.argv, 1, "", str(exc))


class StatusCard(QFrame):
    def __init__(self, title: str, accent: str) -> None:
        super().__init__()
        self.setObjectName("statusCard")
        self.setProperty("accent", accent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(6)
        self.title = QLabel(title)
        self.title.setObjectName("cardTitle")
        self.value = QLabel("-")
        self.value.setObjectName("cardValue")
        self.value.setWordWrap(True)
        layout.addWidget(self.title)
        layout.addWidget(self.value)

    def set_value(self, value: str) -> None:
        self.value.setText(value or "-")


class HardwareButlerWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.worker: CommandWorker | None = None
        self.current_state: dict[str, Any] = {}
        self.current_workbench: dict[str, Any] = {}
        self.current_brain: dict[str, Any] = {}
        self.current_answer: dict[str, Any] = {}
        self.current_task_steps: list[dict[str, Any]] = []
        self.current_actions: list[dict[str, Any]] = []
        self.current_artifacts: list[dict[str, Any]] = []
        self.command_buttons: list[QPushButton] = []
        self.setWindowTitle("硬件管家工作台")
        self.resize(1360, 860)
        self.setup_ui()

    def setup_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(14)

        root.addLayout(self.project_bar())
        root.addLayout(self.summary_cards())

        self.tabs = QTabWidget()
        self.tabs.setObjectName("workbenchTabs")
        self.tabs.addTab(self.home_tab(), "开始工作")
        self.tabs.addTab(self.brain_tab(), "项目大脑")
        self.tabs.addTab(self.evidence_tab(), "资料中心")
        self.tabs.addTab(self.search_tab(), "资料搜索")
        self.tabs.addTab(self.ask_tab(), "问项目")
        self.tabs.addTab(self.overview_tab(), "总览")
        self.tabs.addTab(self.task_tab(), "任务")
        self.tabs.addTab(self.actions_tab(), "动作")
        self.tabs.addTab(self.workflow_tab(), "工作流")
        self.tabs.addTab(self.reports_tab(), "报告")
        self.tabs.addTab(self.tutorial_tab(), "教程")
        self.tabs.addTab(self.output_tab(), "输出")
        root.addWidget(self.tabs, 1)

    def home_tab(self) -> QWidget:
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(0, 10, 0, 0)
        layout.setSpacing(14)

        left = QVBoxLayout()
        left.setSpacing(12)

        start_box = QGroupBox("今天要做什么")
        start_layout = QVBoxLayout(start_box)
        start_layout.setSpacing(10)
        intro = QLabel("先选项目，再点一个任务。所有按钮默认只做本地安全动作，不会直接烧录、擦除、复位或在线调试。")
        intro.setObjectName("pageHint")
        intro.setWordWrap(True)
        start_layout.addWidget(intro)

        choose = QPushButton("选择项目目录")
        choose.clicked.connect(self.browse_project)
        doctor = QPushButton("一键体检")
        doctor.clicked.connect(self.run_doctor)
        auto = QPushButton("自动分析项目")
        auto.clicked.connect(self.run_auto)
        bringup = QPushButton("准备上板检查")
        bringup.clicked.connect(self.run_prepare_bringup)
        reports = QPushButton("打开报告")
        reports.clicked.connect(self.open_reports)
        for button in (choose, doctor, auto, bringup, reports):
            button.setMinimumHeight(38)
            start_layout.addWidget(button)
            self.command_buttons.append(button)
        left.addWidget(start_box)

        ask_box = QGroupBox("问项目")
        ask_layout = QVBoxLayout(ask_box)
        self.home_question_input = QLineEdit()
        self.home_question_input.setPlaceholderText("例如：这个项目下一步应该做什么？PD12 接了什么？")
        self.home_question_input.returnPressed.connect(self.run_home_ask)
        ask_layout.addWidget(self.home_question_input)
        ask_button = QPushButton("用本地资料回答")
        ask_button.clicked.connect(self.run_home_ask)
        ask_button.setMinimumHeight(36)
        ask_layout.addWidget(ask_button)
        self.command_buttons.append(ask_button)
        left.addWidget(ask_box)

        evidence_box = QGroupBox("整理芯片资料")
        evidence_layout = QVBoxLayout(evidence_box)
        self.home_part_input = QLineEdit()
        self.home_part_input.setPlaceholderText("例如 STM32F407VGTx")
        self.home_part_input.returnPressed.connect(self.run_home_collect_evidence)
        evidence_layout.addWidget(self.home_part_input)
        collect = QPushButton("搜索并整理资料")
        collect.clicked.connect(self.run_home_collect_evidence)
        collect.setMinimumHeight(36)
        evidence_layout.addWidget(collect)
        self.command_buttons.append(collect)
        left.addWidget(evidence_box)
        left.addStretch()

        right = QVBoxLayout()
        right.setSpacing(12)

        state_box = QGroupBox("当前项目")
        state_layout = QGridLayout(state_box)
        state_layout.setHorizontalSpacing(10)
        state_layout.setVerticalSpacing(10)
        self.home_status_value = QLabel("-")
        self.home_backend_value = QLabel("-")
        self.home_report_value = QLabel("-")
        self.home_safety_value = QLabel("仅安全本地动作")
        for value in (self.home_status_value, self.home_backend_value, self.home_report_value, self.home_safety_value):
            value.setWordWrap(True)
        state_layout.addWidget(QLabel("状态"), 0, 0)
        state_layout.addWidget(self.home_status_value, 0, 1)
        state_layout.addWidget(QLabel("后端"), 1, 0)
        state_layout.addWidget(self.home_backend_value, 1, 1)
        state_layout.addWidget(QLabel("报告"), 2, 0)
        state_layout.addWidget(self.home_report_value, 2, 1)
        state_layout.addWidget(QLabel("安全"), 3, 0)
        state_layout.addWidget(self.home_safety_value, 3, 1)
        right.addWidget(state_box)

        next_box = QGroupBox("推荐下一步")
        next_layout = QVBoxLayout(next_box)
        self.home_next_title = QLabel("选择项目后点击刷新或自动分析")
        self.home_next_title.setObjectName("nextTitle")
        self.home_next_title.setWordWrap(True)
        self.home_next_reason = QLabel("这里会显示一个可执行的安全建议。")
        self.home_next_reason.setObjectName("nextReason")
        self.home_next_reason.setWordWrap(True)
        self.home_next_command = QPlainTextEdit()
        self.home_next_command.setReadOnly(True)
        self.home_next_command.setMaximumHeight(92)
        self.home_next_command.setFont(QFont("Consolas", 10))
        next_layout.addWidget(self.home_next_title)
        next_layout.addWidget(self.home_next_reason)
        next_layout.addWidget(self.home_next_command)
        run_next = QPushButton("运行推荐")
        run_next.clicked.connect(self.run_recommended)
        copy_next = QPushButton("复制推荐命令")
        copy_next.clicked.connect(self.copy_home_recommended_command)
        row = QHBoxLayout()
        row.addWidget(run_next)
        row.addWidget(copy_next)
        next_layout.addLayout(row)
        self.command_buttons.extend([run_next, copy_next])
        right.addWidget(next_box)

        output_box = QGroupBox("最近输出")
        output_layout = QVBoxLayout(output_box)
        self.home_output = QPlainTextEdit()
        self.home_output.setReadOnly(True)
        self.home_output.setMaximumHeight(180)
        self.home_output.setFont(QFont("Consolas", 9))
        self.home_output.setPlaceholderText("命令摘要会同步显示在这里")
        output_layout.addWidget(self.home_output)
        right.addWidget(output_box)
        right.addStretch()

        layout.addLayout(left, 2)
        layout.addLayout(right, 3)
        return page

    def project_bar(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.setSpacing(10)
        title = QLabel("硬件管家工作台")
        title.setObjectName("appTitle")
        layout.addWidget(title)

        self.project_input = QLineEdit(str(APP_ROOT))
        self.project_input.setObjectName("projectInput")
        self.project_input.setPlaceholderText("选择项目根目录")
        layout.addWidget(self.project_input, 1)

        self.browse_button = QPushButton("浏览")
        self.browse_button.clicked.connect(self.browse_project)
        layout.addWidget(self.browse_button)

        self.refresh_button = QPushButton("刷新")
        self.refresh_button.clicked.connect(self.run_workbench)
        layout.addWidget(self.refresh_button)

        self.auto_button = QPushButton("自动分析")
        self.auto_button.clicked.connect(self.run_auto)
        layout.addWidget(self.auto_button)

        tutorial = QPushButton("教程")
        tutorial.clicked.connect(self.open_tutorial)
        layout.addWidget(tutorial)

        self.run_status = QLabel("就绪")
        self.run_status.setObjectName("runStatus")
        layout.addWidget(self.run_status)

        self.command_buttons.extend([self.browse_button, self.refresh_button, self.auto_button])
        return layout

    def summary_cards(self) -> QGridLayout:
        layout = QGridLayout()
        layout.setHorizontalSpacing(12)
        self.status_card = StatusCard("状态", "blue")
        self.backend_card = StatusCard("构建后端", "green")
        self.cubemx_card = StatusCard("CubeMX 工程", "purple")
        self.safety_card = StatusCard("硬件安全", "orange")
        layout.addWidget(self.status_card, 0, 0)
        layout.addWidget(self.backend_card, 0, 1)
        layout.addWidget(self.cubemx_card, 0, 2)
        layout.addWidget(self.safety_card, 0, 3)
        return layout

    def overview_tab(self) -> QWidget:
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(0, 10, 0, 0)
        layout.setSpacing(14)
        layout.addWidget(self.workflow_panel(), 3)
        layout.addWidget(self.recommendation_panel(), 2)
        return page

    def workflow_panel(self) -> QGroupBox:
        box = QGroupBox("流程进度")
        layout = QVBoxLayout(box)
        self.phase_table = QTableWidget(0, 3)
        self.phase_table.setHorizontalHeaderLabels(["阶段", "状态", "详情"])
        self.phase_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.phase_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.phase_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.phase_table.verticalHeader().setVisible(False)
        self.phase_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.phase_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        layout.addWidget(self.phase_table)
        return box

    def brain_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 10, 0, 0)
        layout.setSpacing(10)

        self.brain_summary = QLabel("选择项目后点击刷新，项目大脑会整理资料覆盖、缺口、风险和下一步建议。")
        self.brain_summary.setObjectName("pageHint")
        self.brain_summary.setWordWrap(True)
        layout.addWidget(self.brain_summary)

        top = QHBoxLayout()
        top.setSpacing(12)

        health_box = QGroupBox("资料完整度")
        health_layout = QVBoxLayout(health_box)
        self.brain_health_table = QTableWidget(0, 3)
        self.brain_health_table.setHorizontalHeaderLabels(["资料", "状态", "数量"])
        self.brain_health_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.brain_health_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.brain_health_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.brain_health_table.verticalHeader().setVisible(False)
        self.brain_health_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        health_layout.addWidget(self.brain_health_table)
        top.addWidget(health_box, 1)

        missing_box = QGroupBox("缺失资料")
        missing_layout = QVBoxLayout(missing_box)
        self.brain_missing_table = QTableWidget(0, 3)
        self.brain_missing_table.setHorizontalHeaderLabels(["缺口", "下一步", "证据"])
        self.brain_missing_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.brain_missing_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.brain_missing_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.brain_missing_table.verticalHeader().setVisible(False)
        self.brain_missing_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        missing_layout.addWidget(self.brain_missing_table)
        top.addWidget(missing_box, 2)
        layout.addLayout(top, 1)

        risk_box = QGroupBox("硬件风险")
        risk_layout = QVBoxLayout(risk_box)
        self.brain_risk_table = QTableWidget(0, 4)
        self.brain_risk_table.setHorizontalHeaderLabels(["级别", "类别", "问题", "下一步安全检查"])
        self.brain_risk_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.brain_risk_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.brain_risk_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.brain_risk_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.brain_risk_table.verticalHeader().setVisible(False)
        self.brain_risk_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        risk_layout.addWidget(self.brain_risk_table)
        layout.addWidget(risk_box, 2)

        task_box = QGroupBox("建议任务")
        task_layout = QVBoxLayout(task_box)
        self.brain_task_table = QTableWidget(0, 3)
        self.brain_task_table.setHorizontalHeaderLabels(["任务", "原因", "命令/动作"])
        self.brain_task_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.brain_task_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.brain_task_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.brain_task_table.verticalHeader().setVisible(False)
        self.brain_task_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        task_layout.addWidget(self.brain_task_table)
        layout.addWidget(task_box, 1)
        return page

    def evidence_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 10, 0, 0)
        layout.setSpacing(10)

        self.evidence_summary = QLabel("选择项目后点击刷新，系统会整理原理图、手册、BOM、工程文件和日志。")
        self.evidence_summary.setObjectName("pageHint")
        self.evidence_summary.setWordWrap(True)
        layout.addWidget(self.evidence_summary)

        controls = QHBoxLayout()
        copy_path = QPushButton("复制资料路径")
        copy_path.clicked.connect(self.copy_selected_artifact_path)
        controls.addWidget(copy_path)
        controls.addStretch()
        layout.addLayout(controls)

        self.evidence_table = QTableWidget(0, 4)
        self.evidence_table.setHorizontalHeaderLabels(["类型", "作用", "大小", "路径"])
        self.evidence_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.evidence_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.evidence_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.evidence_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.evidence_table.verticalHeader().setVisible(False)
        self.evidence_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.evidence_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.evidence_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        layout.addWidget(self.evidence_table, 1)
        return page

    def search_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 10, 0, 0)
        layout.setSpacing(10)

        hint = QLabel("输入芯片或板卡型号后，工作台会通过配置好的搜索 API 找资料，再交给后端做 PDF 校验、下载、摘要和来源记录。")
        hint.setObjectName("pageHint")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        form = QGridLayout()
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(10)
        self.part_input = QLineEdit()
        self.part_input.setPlaceholderText("例如 STM32F407VGTx")
        self.board_input = QLineEdit()
        self.board_input.setPlaceholderText("可选，例如 Discovery board / 自研板名称")
        self.api_query_input = QLineEdit()
        self.api_query_input.setPlaceholderText("可选，例如 schematic reference manual errata")
        self.search_preset = QComboBox()
        self.search_preset.addItems(["芯片资料", "板卡资料", "器件风险"])
        self.api_provider = QComboBox()
        self.api_provider.addItems(["自动", "Exa", "通用 API"])
        form.addWidget(QLabel("芯片/器件"), 0, 0)
        form.addWidget(self.part_input, 0, 1)
        form.addWidget(QLabel("板卡"), 1, 0)
        form.addWidget(self.board_input, 1, 1)
        form.addWidget(QLabel("补充关键词"), 2, 0)
        form.addWidget(self.api_query_input, 2, 1)
        form.addWidget(QLabel("搜索类型"), 3, 0)
        form.addWidget(self.search_preset, 3, 1)
        form.addWidget(QLabel("API"), 4, 0)
        form.addWidget(self.api_provider, 4, 1)
        layout.addLayout(form)

        controls = QHBoxLayout()
        search = QPushButton("搜索并整理资料")
        search.clicked.connect(self.run_document_search)
        controls.addWidget(search)
        controls.addStretch()
        layout.addLayout(controls)
        self.command_buttons.append(search)

        help_text = QTextBrowser()
        help_text.setMaximumHeight(170)
        help_text.setHtml(
            """
            <b>API 配置</b>
            <ul>
              <li>Exa：设置环境变量 <code>EXA_API_KEY</code>。</li>
              <li>通用 API：设置 <code>DOC_SEARCH_API_URL</code>，可选 <code>DOC_SEARCH_API_KEY</code>。</li>
              <li>下载仍会校验 PDF 头、记录 sha256 和来源质量，非 PDF 不会保存成资料。</li>
            </ul>
            """
        )
        layout.addWidget(help_text)
        layout.addStretch()
        return page

    def ask_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 10, 0, 0)
        layout.setSpacing(10)

        hint = QLabel("基于本地资料索引回答项目问题。答案必须带来源；没有原理图、BOM、手册或日志证据时会明确显示 unknown。")
        hint.setObjectName("pageHint")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        controls = QHBoxLayout()
        self.question_input = QLineEdit()
        self.question_input.setPlaceholderText("例如：PD12 接了什么？USART2 是什么模式？这块板缺什么资料？")
        self.question_input.returnPressed.connect(self.run_ask)
        ask_button = QPushButton("提问")
        ask_button.clicked.connect(self.run_ask)
        controls.addWidget(self.question_input, 1)
        controls.addWidget(ask_button)
        layout.addLayout(controls)
        self.command_buttons.append(ask_button)

        self.answer_text = QPlainTextEdit()
        self.answer_text.setReadOnly(True)
        self.answer_text.setMaximumHeight(120)
        self.answer_text.setPlaceholderText("答案会显示在这里")
        layout.addWidget(self.answer_text)

        self.answer_table = QTableWidget(0, 4)
        self.answer_table.setHorizontalHeaderLabels(["类型", "路径", "行号", "内容"])
        self.answer_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.answer_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.answer_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.answer_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.answer_table.verticalHeader().setVisible(False)
        self.answer_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.answer_table, 1)

        self.unknown_text = QPlainTextEdit()
        self.unknown_text.setReadOnly(True)
        self.unknown_text.setMaximumHeight(110)
        self.unknown_text.setPlaceholderText("unknown 和下一步检查会显示在这里")
        layout.addWidget(self.unknown_text)
        return page

    def task_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 10, 0, 0)
        layout.setSpacing(10)

        hint = QLabel("选择一个硬件开发目标，工作台会展开为可审阅的安全命令。真实硬件动作仍保持确认门控。")
        hint.setObjectName("pageHint")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        form = QGridLayout()
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(8)
        self.task_intent = QComboBox()
        self.task_intent.addItems(["整理资料", "分析原理图风险", "配置一个外设", "诊断构建失败", "准备上板 bring-up"])
        self.task_part_input = QLineEdit()
        self.task_part_input.setPlaceholderText("可选：STM32F407VGTx")
        self.task_pin_input = QLineEdit()
        self.task_pin_input.setPlaceholderText("可选：PD12 / PB6")
        self.task_function_input = QLineEdit()
        self.task_function_input.setPlaceholderText("可选：gpio-output / i2c / uart / can")
        self.task_instance_input = QLineEdit()
        self.task_instance_input.setPlaceholderText("可选：I2C1 / USART2 / CAN1")
        self.task_log_input = QLineEdit()
        self.task_log_input.setPlaceholderText("可选：build.log 路径")
        self.task_question_input = QLineEdit()
        self.task_question_input.setPlaceholderText("可选：这块板缺什么资料和硬件风险？")
        form.addWidget(QLabel("目标"), 0, 0)
        form.addWidget(self.task_intent, 0, 1)
        form.addWidget(QLabel("芯片/器件"), 1, 0)
        form.addWidget(self.task_part_input, 1, 1)
        form.addWidget(QLabel("引脚"), 2, 0)
        form.addWidget(self.task_pin_input, 2, 1)
        form.addWidget(QLabel("功能"), 3, 0)
        form.addWidget(self.task_function_input, 3, 1)
        form.addWidget(QLabel("实例"), 4, 0)
        form.addWidget(self.task_instance_input, 4, 1)
        form.addWidget(QLabel("日志"), 5, 0)
        form.addWidget(self.task_log_input, 5, 1)
        form.addWidget(QLabel("问题"), 6, 0)
        form.addWidget(self.task_question_input, 6, 1)
        layout.addLayout(form)

        controls = QHBoxLayout()
        plan_task = QPushButton("生成任务计划")
        plan_task.clicked.connect(self.run_task_plan)
        run_step = QPushButton("运行所选步骤")
        run_step.clicked.connect(self.run_selected_task_step)
        controls.addWidget(plan_task)
        controls.addWidget(run_step)
        controls.addStretch()
        layout.addLayout(controls)
        self.command_buttons.extend([plan_task, run_step])

        self.task_summary = QLabel("还没有生成任务计划。")
        self.task_summary.setObjectName("pageHint")
        self.task_summary.setWordWrap(True)
        layout.addWidget(self.task_summary)

        self.task_table = QTableWidget(0, 4)
        self.task_table.setHorizontalHeaderLabels(["步骤", "说明", "安全", "命令"])
        self.task_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.task_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.task_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.task_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.task_table.verticalHeader().setVisible(False)
        self.task_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.task_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.task_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        layout.addWidget(self.task_table, 1)
        return page

    def workflow_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 10, 0, 0)
        layout.setSpacing(10)

        hint = QLabel(
            "一句话目标驱动 9 阶段工作流：需求解析 → 选型 → 资料 → CubeMX → 固件生成（可 LLM 编写）→ 构建（可真实编译）→ 烧录（默认只出 runbook）→ 观测 → 验证。"
            "结果为 blocked-needs-input 时按提示处理后再恢复运行。"
        )
        hint.setObjectName("pageHint")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        form = QGridLayout()
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(8)
        self.wf_goal_input = QLineEdit()
        self.wf_goal_input.setPlaceholderText("一句话目标，例如：LED blink on PD12")
        self.wf_feature_input = QLineEdit()
        self.wf_feature_input.setPlaceholderText("可选：led-blink")
        self.wf_pin_input = QLineEdit()
        self.wf_pin_input.setPlaceholderText("可选：PD12")
        self.wf_function_input = QLineEdit()
        self.wf_function_input.setPlaceholderText("可选：gpio-output / i2c / uart")
        self.wf_part_input = QLineEdit()
        self.wf_part_input.setPlaceholderText("可选：STM32F407VGTx")
        self.wf_probe_input = QLineEdit()
        self.wf_probe_input.setPlaceholderText("可选：探针或串口，如 stlink-v3 / COM3")
        self.wf_auto_select = QCheckBox("无芯片时自动选择第一个 LLM 候选")
        form.addWidget(QLabel("目标"), 0, 0)
        form.addWidget(self.wf_goal_input, 0, 1)
        form.addWidget(QLabel("功能名"), 1, 0)
        form.addWidget(self.wf_feature_input, 1, 1)
        form.addWidget(QLabel("引脚"), 2, 0)
        form.addWidget(self.wf_pin_input, 2, 1)
        form.addWidget(QLabel("外设功能"), 3, 0)
        form.addWidget(self.wf_function_input, 3, 1)
        form.addWidget(QLabel("芯片"), 4, 0)
        form.addWidget(self.wf_part_input, 4, 1)
        form.addWidget(QLabel("探针/串口"), 5, 0)
        form.addWidget(self.wf_probe_input, 5, 1)
        form.addWidget(self.wf_auto_select, 6, 1)
        layout.addLayout(form)

        controls = QHBoxLayout()
        run_wf = QPushButton("运行工作流")
        run_wf.clicked.connect(self.run_workflow)
        resume_wf = QPushButton("恢复运行")
        resume_wf.clicked.connect(self.run_workflow_resume)
        status_wf = QPushButton("查看状态")
        status_wf.clicked.connect(self.run_workflow_status)
        llm_wf = QPushButton("待办 LLM 任务")
        llm_wf.clicked.connect(self.run_workflow_llm_tasks)
        controls.addWidget(run_wf)
        controls.addWidget(resume_wf)
        controls.addWidget(status_wf)
        controls.addWidget(llm_wf)
        controls.addStretch()
        layout.addLayout(controls)
        self.command_buttons.extend([run_wf, resume_wf, status_wf, llm_wf])

        self.wf_status_label = QLabel("尚未运行工作流。")
        self.wf_status_label.setObjectName("pageHint")
        self.wf_status_label.setWordWrap(True)
        layout.addWidget(self.wf_status_label)

        self.wf_phase_table = QTableWidget(0, 4)
        self.wf_phase_table.setHorizontalHeaderLabels(["阶段", "状态", "尝试", "错误"])
        self.wf_phase_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.wf_phase_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.wf_phase_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.wf_phase_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.wf_phase_table.verticalHeader().setVisible(False)
        self.wf_phase_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.wf_phase_table, 2)

        llm_box = QGroupBox("待办 LLM 任务（宿主代理模式：由你/宿主 AI 作答）")
        llm_layout = QVBoxLayout(llm_box)
        llm_hint = QLabel(
            "默认 claude-code 提供方把 LLM 调用转成任务文件。作答后把一行 JSON "
            '{"task_id": "...", "text": "<答案>"} 追加到 <项目>\\.hardware-butler\\llm-responses.jsonl，'
            "然后点“恢复运行”。"
        )
        llm_hint.setWordWrap(True)
        llm_layout.addWidget(llm_hint)
        self.wf_llm_table = QTableWidget(0, 2)
        self.wf_llm_table.setHorizontalHeaderLabels(["任务 ID", "提示（截断）"])
        self.wf_llm_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.wf_llm_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.wf_llm_table.verticalHeader().setVisible(False)
        self.wf_llm_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        llm_layout.addWidget(self.wf_llm_table)
        layout.addWidget(llm_box, 1)
        return page

    def run_workflow(self) -> None:
        goal = self.wf_goal_input.text().strip()
        if not goal:
            self.append_output("请先输入一句话目标。")
            self.tabs.setCurrentIndex(TAB_WORKFLOW)
            return
        argv = self.cli(
            "workflow-run", "--root", self.project_root(),
            "--intent", "develop-feature", "--goal", goal, "--json",
        )
        for flag, widget in (
            ("--feature", self.wf_feature_input),
            ("--pin", self.wf_pin_input),
            ("--function", self.wf_function_input),
            ("--part", self.wf_part_input),
            ("--probe", self.wf_probe_input),
        ):
            value = widget.text().strip()
            if value:
                argv.extend([flag, value])
        if self.wf_auto_select.isChecked():
            argv.append("--auto-select")
        self.run_command(argv)

    def run_workflow_resume(self) -> None:
        self.run_command(self.cli("workflow-run", "--root", self.project_root(), "--resume", "--json"))

    def run_workflow_status(self) -> None:
        self.run_command(self.cli("workflow-status", "--root", self.project_root(), "--json"))

    def run_workflow_llm_tasks(self) -> None:
        self.run_command(self.cli("workflow-llm-tasks", "--root", self.project_root(), "--json"))

    def apply_workflow_state(self, state: dict[str, Any]) -> None:
        status = str(state.get("status", ""))
        current = str(state.get("current_stage", ""))
        goal = str(state.get("goal", ""))
        self.wf_status_label.setText(
            f"状态: {status or '-'}    当前阶段: {current or '(无)'}    目标: {goal or '-'}"
        )
        stages = state.get("stages")
        if not isinstance(stages, list):
            return
        self.wf_phase_table.setRowCount(0)
        for stage in stages:
            if not isinstance(stage, dict):
                continue
            row = self.wf_phase_table.rowCount()
            self.wf_phase_table.insertRow(row)
            self.wf_phase_table.setItem(row, 0, QTableWidgetItem(str(stage.get("id", ""))))
            self.wf_phase_table.setItem(row, 1, QTableWidgetItem(str(stage.get("status", ""))))
            self.wf_phase_table.setItem(row, 2, QTableWidgetItem(str(stage.get("attempts", ""))))
            error = str(stage.get("error", "") or "")
            self.wf_phase_table.setItem(row, 3, QTableWidgetItem(error[:200]))

    def apply_workflow_llm_tasks(self, pending: list[Any]) -> None:
        self.wf_llm_table.setRowCount(0)
        for task in pending:
            if not isinstance(task, dict):
                continue
            row = self.wf_llm_table.rowCount()
            self.wf_llm_table.insertRow(row)
            self.wf_llm_table.setItem(row, 0, QTableWidgetItem(str(task.get("task_id", ""))))
            prompt = str(task.get("prompt", "") or "")
            self.wf_llm_table.setItem(row, 1, QTableWidgetItem(prompt[:300]))

    def recommendation_panel(self) -> QGroupBox:
        box = QGroupBox("推荐下一步")
        layout = QVBoxLayout(box)
        layout.setSpacing(12)
        self.next_title = QLabel("等待刷新")
        self.next_title.setObjectName("nextTitle")
        self.next_reason = QLabel("选择项目后点击刷新，工作台会给出下一步安全动作。")
        self.next_reason.setWordWrap(True)
        self.next_reason.setObjectName("nextReason")
        self.next_command = QPlainTextEdit()
        self.next_command.setReadOnly(True)
        self.next_command.setMaximumHeight(92)
        self.next_command.setPlaceholderText("推荐命令会显示在这里")

        controls = QHBoxLayout()
        self.recommended_button = QPushButton("运行推荐")
        self.recommended_button.clicked.connect(self.run_recommended)
        self.selected_button = QPushButton("运行所选")
        self.selected_button.clicked.connect(self.run_selected_action)
        self.copy_recommended_button = QPushButton("复制命令")
        self.copy_recommended_button.clicked.connect(self.copy_recommended_command)
        controls.addWidget(self.recommended_button)
        controls.addWidget(self.selected_button)
        controls.addWidget(self.copy_recommended_button)
        self.command_buttons.extend([self.recommended_button, self.selected_button])

        layout.addWidget(self.next_title)
        layout.addWidget(self.next_reason)
        layout.addWidget(self.next_command)
        layout.addLayout(controls)
        layout.addStretch()
        return box

    def actions_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 10, 0, 0)
        layout.setSpacing(10)
        hint = QLabel("动作表只展示安全本地动作。真实烧录、擦除、调试和观测仍保持确认门控。")
        hint.setObjectName("pageHint")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        controls = QHBoxLayout()
        run_selected = QPushButton("运行所选")
        run_selected.clicked.connect(self.run_selected_action)
        copy_selected = QPushButton("复制所选命令")
        copy_selected.clicked.connect(self.copy_selected_action_command)
        controls.addWidget(run_selected)
        controls.addWidget(copy_selected)
        controls.addStretch()
        layout.addLayout(controls)
        self.command_buttons.append(run_selected)
        self.action_table = QTableWidget(0, 4)
        self.action_table.setHorizontalHeaderLabels(["动作", "说明", "安全", "命令"])
        self.action_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.action_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.action_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.action_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.action_table.verticalHeader().setVisible(False)
        self.action_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.action_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.action_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        layout.addWidget(self.action_table, 1)
        return page

    def reports_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 10, 0, 0)
        controls = QHBoxLayout()
        copy_path = QPushButton("复制报告路径")
        copy_path.clicked.connect(self.copy_selected_report_path)
        controls.addWidget(copy_path)
        controls.addStretch()
        layout.addLayout(controls)
        self.report_table = QTableWidget(0, 4)
        self.report_table.setHorizontalHeaderLabels(["报告", "作用", "状态", "路径"])
        self.report_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.report_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.report_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.report_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.report_table.verticalHeader().setVisible(False)
        self.report_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.report_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        layout.addWidget(self.report_table)
        return page

    def tutorial_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 10, 0, 0)
        browser = QTextBrowser()
        browser.setObjectName("tutorialBrowser")
        browser.setOpenExternalLinks(False)
        browser.setHtml(TUTORIAL_HTML)
        layout.addWidget(browser)
        return page

    def output_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 10, 0, 0)
        controls = QHBoxLayout()
        clear_output = QPushButton("清空输出")
        clear_output.clicked.connect(self.clear_output)
        copy_output = QPushButton("复制全部输出")
        copy_output.clicked.connect(self.copy_output)
        controls.addWidget(clear_output)
        controls.addWidget(copy_output)
        controls.addStretch()
        layout.addLayout(controls)
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setFont(QFont("Consolas", 10))
        self.output.setPlaceholderText("命令输出和摘要会显示在这里")
        layout.addWidget(self.output)
        return page

    def browse_project(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择项目根目录", self.project_input.text() or str(APP_ROOT))
        if path:
            self.project_input.setText(path)
            self.run_workbench()

    def project_root(self) -> str:
        value = self.project_input.text().strip()
        return value or str(APP_ROOT)

    def command_env(self) -> dict[str, str]:
        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "utf-8"
        env["HW_BUTLER_ROOT"] = self.project_root()
        return env

    def cli(self, *args: str) -> list[str]:
        if FROZEN:
            return [str(find_frozen_cli()), *args]
        return [sys.executable, str(SOURCE_CLI), *args]

    def open_tutorial(self) -> None:
        self.tabs.setCurrentIndex(TAB_TUTORIAL)

    def run_workbench(self) -> None:
        self.run_command(self.cli("workbench", "--root", self.project_root(), "--json"))

    def run_doctor(self) -> None:
        self.run_command(self.cli("doctor", "--root", self.project_root(), "--json"))

    def run_auto(self) -> None:
        self.run_command(self.cli("auto", "--root", self.project_root(), "--json"))

    def run_prepare_bringup(self) -> None:
        self.run_command(self.cli("bench-runbook", "--root", self.project_root(), "--action", "build-flash", "--json"))

    def run_home_ask(self) -> None:
        question = self.home_question_input.text().strip() or "这个项目下一步应该做什么？"
        self.question_input.setText(question)
        self.run_command(self.cli("ask", "--root", self.project_root(), "--question", question, "--json"))

    def run_home_collect_evidence(self) -> None:
        part = self.home_part_input.text().strip()
        if not part:
            self.append_output("请先输入芯片或器件型号，例如 STM32F407VGTx。")
            return
        self.part_input.setText(part)
        self.run_document_search()

    def open_reports(self) -> None:
        self.tabs.setCurrentIndex(TAB_REPORTS)

    def run_document_search(self) -> None:
        part = self.part_input.text().strip()
        if not part:
            self.append_output("请先输入芯片或器件型号。")
            self.tabs.setCurrentIndex(TAB_SEARCH)
            return
        out_dir = Path(self.project_root()) / "docs" / "chip" / safe_part_name(part)
        argv = self.cli(
            "chip-dossier",
            "--part",
            part,
            "--out-dir",
            str(out_dir),
            "--api-search",
            "--api-preset",
            search_preset_id(self.search_preset.currentText()),
            "--search",
            "--download",
            "--json",
        )
        board = self.board_input.text().strip()
        if board:
            argv.extend(["--board", board])
        query = self.api_query_input.text().strip()
        if query:
            argv.extend(["--api-query", query])
        provider = self.api_provider.currentText()
        if provider == "Exa":
            argv.extend(["--api-provider", "exa"])
        elif provider == "通用 API":
            argv.extend(["--api-provider", "generic"])
        self.run_command(argv)

    def run_ask(self) -> None:
        question = self.question_input.text().strip()
        if not question:
            self.append_output("请先输入项目问题。")
            self.tabs.setCurrentIndex(TAB_ASK)
            return
        self.run_command(self.cli("ask", "--root", self.project_root(), "--question", question, "--json"))

    def run_task_plan(self) -> None:
        argv = self.cli("task", "--root", self.project_root(), "--intent", task_intent_id(self.task_intent.currentText()), "--json")
        for flag, widget in (
            ("--part", self.task_part_input),
            ("--pin", self.task_pin_input),
            ("--function", self.task_function_input),
            ("--instance", self.task_instance_input),
            ("--log", self.task_log_input),
            ("--question", self.task_question_input),
        ):
            value = widget.text().strip()
            if value:
                argv.extend([flag, value])
        self.run_command(argv)

    def run_selected_task_step(self) -> None:
        row = self.task_table.currentRow()
        if row < 0 or row >= len(self.current_task_steps):
            self.append_output("请先在任务页选择一个步骤。")
            self.tabs.setCurrentIndex(TAB_TASKS)
            return
        self.run_action(self.current_task_steps[row])

    def run_recommended(self) -> None:
        action = self.current_workbench.get("primary_action")
        if isinstance(action, dict):
            self.run_action(action)
            return
        self.run_workbench()

    def run_selected_action(self) -> None:
        action = self.selected_action()
        if action is None:
            self.append_output("请先在动作页选择一个动作。")
            self.tabs.setCurrentIndex(TAB_ACTIONS)
            return
        self.run_action(action)

    def selected_action(self) -> dict[str, Any] | None:
        row = self.action_table.currentRow()
        if row < 0 or row >= len(self.current_actions):
            return None
        return self.current_actions[row]

    def copy_recommended_command(self) -> None:
        text = self.next_command.toPlainText().strip()
        if not text:
            self.append_output("当前没有可复制的推荐命令。")
            return
        QApplication.clipboard().setText(text)
        self.append_output("已复制推荐命令。")

    def copy_home_recommended_command(self) -> None:
        text = self.home_next_command.toPlainText().strip()
        if not text:
            self.copy_recommended_command()
            return
        QApplication.clipboard().setText(text)
        self.append_output("已复制推荐命令。")

    def copy_selected_action_command(self) -> None:
        action = self.selected_action()
        command = str(action.get("command", "")).strip() if action else ""
        if not command:
            self.append_output("请先选择一个带命令的动作。")
            self.tabs.setCurrentIndex(TAB_ACTIONS)
            return
        QApplication.clipboard().setText(command)
        self.append_output("已复制所选动作命令。")

    def copy_selected_artifact_path(self) -> None:
        row = self.evidence_table.currentRow()
        item = self.evidence_table.item(row, 3) if row >= 0 else None
        path = item.text().strip() if item else ""
        if not path:
            self.append_output("请先在资料中心选择一项资料。")
            self.tabs.setCurrentIndex(TAB_EVIDENCE)
            return
        QApplication.clipboard().setText(path)
        self.append_output("已复制资料路径。")

    def copy_selected_report_path(self) -> None:
        row = self.report_table.currentRow()
        item = self.report_table.item(row, 3) if row >= 0 else None
        path = item.text().strip() if item else ""
        if not path:
            self.append_output("请先在报告页选择一个报告。")
            self.tabs.setCurrentIndex(TAB_REPORTS)
            return
        QApplication.clipboard().setText(path)
        self.append_output("已复制报告路径。")

    def clear_output(self) -> None:
        self.output.clear()

    def copy_output(self) -> None:
        text = self.output.toPlainText()
        if not text.strip():
            self.append_output("当前输出为空。")
            return
        QApplication.clipboard().setText(text)
        self.append_output("已复制全部输出。")

    def run_action(self, action: dict[str, Any]) -> None:
        argv = action.get("argv")
        if not isinstance(argv, list) or not all(isinstance(item, str) for item in argv):
            self.append_output("所选动作没有可运行命令。")
            return
        if action.get("touches_hardware"):
            self.append_output("真实硬件动作保持计划门控，不能直接从此界面运行。")
            return
        self.run_command(self.normalize_argv(argv))

    def normalize_argv(self, argv: list[str]) -> list[str]:
        if not argv:
            return argv
        if argv[0] == "python":
            if len(argv) >= 2 and Path(argv[1]).as_posix().endswith("tools/hardware_butler.py"):
                return self.cli(*argv[2:])
            if FROZEN and len(argv) >= 2:
                return self.cli(*argv[2:])
            return [sys.executable, *argv[1:]]
        return argv

    def run_command(self, argv: list[str]) -> None:
        if self.worker and self.worker.isRunning():
            self.append_output("已有命令正在运行。")
            self.tabs.setCurrentIndex(TAB_OUTPUT)
            return
        self.append_output(f"> {' '.join(argv)}")
        self.set_running(True, "运行中...")
        self.worker = CommandWorker(argv, cwd=APP_ROOT, env=self.command_env())
        self.worker.finished.connect(self.command_finished)
        self.worker.start()

    def command_finished(self, argv: list[str], code: int, stdout: str, stderr: str) -> None:
        data = parse_json(stdout)
        if data:
            self.apply_report(data)
            self.append_output(render_summary(data, code))
        elif stdout:
            self.append_output(stdout.rstrip())
        if stderr:
            self.append_output(stderr.rstrip())
        if not data:
            self.append_output(f"退出码: {code}")
        self.set_running(False, "完成" if code == 0 else f"失败: {code}")
        state = data.get("state") if isinstance(data, dict) else None
        if isinstance(state, dict) and isinstance(state.get("stages"), list):
            self.apply_workflow_state(state)
        pending = data.get("pending") if isinstance(data, dict) else None
        if isinstance(pending, list):
            self.apply_workflow_llm_tasks(pending)
        if data.get("part") and data.get("documents_dir"):
            QTimer.singleShot(0, self.run_workbench)

    def set_running(self, running: bool, message: str) -> None:
        self.project_input.setEnabled(not running)
        for button in self.command_buttons:
            button.setEnabled(not running)
        self.run_status.setText(message)

    def append_output(self, text: str) -> None:
        if not text:
            return
        self.output.appendPlainText(text)
        if hasattr(self, "home_output"):
            self.home_output.appendPlainText(text)

    def apply_report(self, data: dict[str, Any]) -> None:
        if data.get("app") == "hardware-butler-workbench":
            self.current_workbench = data
            state = data.get("state") if isinstance(data.get("state"), dict) else {}
            brain = data.get("brain") if isinstance(data.get("brain"), dict) else {}
            actions = data.get("actions") if isinstance(data.get("actions"), list) else []
            reports = data.get("reports") if isinstance(data.get("reports"), list) else []
            artifacts = data.get("artifacts") if isinstance(data.get("artifacts"), list) else []
            self.set_brain(brain)
            self.set_actions([action for action in actions if isinstance(action, dict)])
            self.set_reports([report for report in reports if isinstance(report, dict)])
            self.set_artifacts(
                [artifact for artifact in artifacts if isinstance(artifact, dict)],
                data.get("artifact_summary") if isinstance(data.get("artifact_summary"), dict) else {},
            )
            self.set_home_summary(state, data)
            self.tabs.setCurrentIndex(TAB_HOME)
        elif data.get("app") == "hardware-project-brain":
            self.set_brain(data)
            self.tabs.setCurrentIndex(TAB_BRAIN)
            state = data
        elif "question" in data and "answer" in data and "confidence" in data:
            self.set_answer(data)
            self.tabs.setCurrentIndex(TAB_ASK)
            state = data
        elif "intent" in data and "steps" in data and "missing_inputs" in data:
            self.set_task_plan(data)
            self.tabs.setCurrentIndex(TAB_TASKS)
            state = data
        else:
            state = data.get("state") if isinstance(data.get("state"), dict) else data
        self.current_state = state
        self.status_card.set_value(translate_status(str(state.get("status", data.get("status", "-")))))
        backend = state.get("backend") or data.get("backend") or data.get("selected_backend") or {}
        self.backend_card.set_value(str(backend.get("backend") or "未检测") if isinstance(backend, dict) else "未检测")
        cubemx = state.get("cubemx_project_count", data.get("cubemx_project_count", "-"))
        self.cubemx_card.set_value(str(cubemx))
        safety = state.get("safety", {}) if isinstance(state.get("safety"), dict) else {}
        self.safety_card.set_value(translate_status(str(safety.get("real_hardware_actions", "safe local only"))))

        phases = state.get("phases") if isinstance(state.get("phases"), list) else []
        self.set_phases(phases)

        next_step = data.get("next_step") or state.get("next_step")
        if isinstance(next_step, dict):
            self.next_title.setText(translate_action_title(next_step))
            self.next_reason.setText(translate_detail(str(next_step.get("reason", ""))))
            self.next_command.setPlainText(str(next_step.get("command", "")))
            self.home_next_title.setText(translate_action_title(next_step))
            self.home_next_reason.setText(translate_detail(str(next_step.get("reason", ""))))
            self.home_next_command.setPlainText(str(next_step.get("command", "")))
        self.set_home_summary(state, data)

    def set_home_summary(self, state: dict[str, Any], data: dict[str, Any]) -> None:
        if not hasattr(self, "home_status_value"):
            return
        status = translate_status(str(state.get("status", data.get("status", "-"))))
        backend = state.get("backend") or data.get("backend") or data.get("selected_backend") or {}
        backend_text = str(backend.get("backend") or "未检测") if isinstance(backend, dict) else "未检测"
        reports = data.get("reports") if isinstance(data.get("reports"), list) else []
        ready_reports = sum(1 for report in reports if isinstance(report, dict) and report.get("exists"))
        report_text = f"{ready_reports}/{len(reports)} 可用" if reports else "暂无报告"
        safety = state.get("safety", {}) if isinstance(state.get("safety"), dict) else {}
        safety_text = translate_status(str(safety.get("real_hardware_actions", "safe local only")))
        self.home_status_value.setText(status)
        self.home_backend_value.setText(backend_text)
        self.home_report_value.setText(report_text)
        self.home_safety_value.setText(safety_text)

    def set_answer(self, report: dict[str, Any]) -> None:
        self.current_answer = report
        self.answer_text.setPlainText(
            "\n".join(
                [
                    f"状态：{translate_status(str(report.get('status', '-')))}",
                    f"置信度：{translate_confidence(str(report.get('confidence', '-')))}",
                    "",
                    str(report.get("answer", "unknown")),
                ]
            )
        )
        rows = []
        for item in report.get("citations", []) if isinstance(report.get("citations"), list) else []:
            if isinstance(item, dict):
                rows.append(("引用", str(item.get("path", "")), str(item.get("line", "unknown")), str(item.get("text") or item.get("note", ""))))
        for item in report.get("unknowns", []) if isinstance(report.get("unknowns"), list) else []:
            rows.append(("unknown", "", "", str(item)))
        for item in report.get("next_checks", []) if isinstance(report.get("next_checks"), list) else []:
            rows.append(("下一步", "", "", str(item)))
        self.answer_table.setRowCount(len(rows))
        for row, values in enumerate(rows):
            for col, value in enumerate(values):
                self.answer_table.setItem(row, col, readonly_item(value))
        unknowns = report.get("unknowns") if isinstance(report.get("unknowns"), list) else []
        next_checks = report.get("next_checks") if isinstance(report.get("next_checks"), list) else []
        self.unknown_text.setPlainText(
            "Unknown:\n"
            + ("\n".join(f"- {item}" for item in unknowns) if unknowns else "- 无")
            + "\n\n下一步检查:\n"
            + ("\n".join(f"- {item}" for item in next_checks) if next_checks else "- 无")
        )

    def set_task_plan(self, plan: dict[str, Any]) -> None:
        steps = plan.get("steps") if isinstance(plan.get("steps"), list) else []
        self.current_task_steps = [item for item in steps if isinstance(item, dict)]
        intent = plan.get("intent") if isinstance(plan.get("intent"), dict) else {}
        missing = plan.get("missing_inputs") if isinstance(plan.get("missing_inputs"), list) else []
        self.task_summary.setText(
            f"目标：{intent.get('title', '-')}；状态：{translate_status(str(plan.get('status', '-')))}；"
            f"步骤：{len(self.current_task_steps)}；缺少输入：{', '.join(str(item) for item in missing) or '无'}。"
        )
        self.task_table.setRowCount(len(self.current_task_steps))
        for row, item in enumerate(self.current_task_steps):
            safety = "安全" if item.get("safe_by_default") and not item.get("touches_hardware") else "门控"
            values = [
                str(item.get("id", "")),
                str(item.get("title", "")),
                safety,
                str(item.get("command", "")),
            ]
            for col, value in enumerate(values):
                self.task_table.setItem(row, col, readonly_item(value))
        if self.current_task_steps:
            self.task_table.selectRow(0)

    def set_brain(self, brain: dict[str, Any]) -> None:
        self.current_brain = brain
        identity = brain.get("identity") if isinstance(brain.get("identity"), dict) else {}
        mcu = identity.get("mcu") if isinstance(identity.get("mcu"), dict) else {}
        health = brain.get("evidence_health") if isinstance(brain.get("evidence_health"), dict) else {}
        health_summary = health.get("summary") if isinstance(health.get("summary"), dict) else {}
        risk_snapshot = brain.get("risk_snapshot") if isinstance(brain.get("risk_snapshot"), dict) else {}
        risk_summary = risk_snapshot.get("summary") if isinstance(risk_snapshot.get("summary"), dict) else {}
        self.brain_summary.setText(
            f"项目：{identity.get('project_name', '-')}；MCU：{mcu.get('name', 'unknown')}；"
            f"必需资料：{health_summary.get('required_present', 0)}/{health_summary.get('required_total', 0)}；"
            f"索引资料：{health_summary.get('indexed_items', 0)}；风险：{risk_summary.get('total', 0)}。"
        )

        categories = health.get("categories") if isinstance(health.get("categories"), list) else []
        self.brain_health_table.setRowCount(len(categories))
        for row, category in enumerate(categories):
            if not isinstance(category, dict):
                continue
            values = [
                translate_brain_category(str(category.get("id", category.get("title", ""))),
                                         str(category.get("title", ""))),
                translate_status(str(category.get("status", ""))),
                str(category.get("count", 0)),
            ]
            for col, value in enumerate(values):
                self.brain_health_table.setItem(row, col, readonly_item(value))

        missing = brain.get("missing_evidence") if isinstance(brain.get("missing_evidence"), list) else []
        self.brain_missing_table.setRowCount(len(missing))
        for row, item in enumerate(missing):
            if not isinstance(item, dict):
                continue
            citations = item.get("citations") if isinstance(item.get("citations"), list) else []
            values = [
                translate_brain_category(str(item.get("id", "")), str(item.get("title", ""))),
                str(item.get("next_safe_action", "")),
                citation_paths(citations),
            ]
            for col, value in enumerate(values):
                self.brain_missing_table.setItem(row, col, readonly_item(value))

        risks = risk_snapshot.get("risks") if isinstance(risk_snapshot.get("risks"), list) else []
        self.brain_risk_table.setRowCount(len(risks))
        for row, item in enumerate(risks):
            if not isinstance(item, dict):
                continue
            values = [
                translate_severity(str(item.get("severity", ""))),
                translate_risk_category(str(item.get("category", ""))),
                str(item.get("message", "")),
                str(item.get("next_safe_check", "")),
            ]
            for col, value in enumerate(values):
                self.brain_risk_table.setItem(row, col, readonly_item(value))

        tasks = brain.get("recommended_tasks") if isinstance(brain.get("recommended_tasks"), list) else []
        self.brain_task_table.setRowCount(len(tasks))
        for row, item in enumerate(tasks):
            if not isinstance(item, dict):
                continue
            commands = item.get("commands") if isinstance(item.get("commands"), list) else []
            values = [
                translate_task_title(str(item.get("id", "")), str(item.get("title", ""))),
                str(item.get("reason", "")),
                "\n".join(str(command) for command in commands),
            ]
            for col, value in enumerate(values):
                self.brain_task_table.setItem(row, col, readonly_item(value))

    def set_phases(self, phases: list[dict[str, Any]]) -> None:
        self.phase_table.setRowCount(len(phases))
        for row, phase in enumerate(phases):
            values = [
                translate_phase_title(phase),
                translate_status(str(phase.get("status", ""))),
                translate_detail(str(phase.get("detail", ""))),
            ]
            for col, value in enumerate(values):
                self.phase_table.setItem(row, col, readonly_item(str(value)))

    def set_actions(self, actions: list[dict[str, Any]]) -> None:
        self.current_actions = actions
        self.action_table.setRowCount(len(actions))
        for row, action in enumerate(actions):
            safety = "安全" if action.get("safe_by_default") and not action.get("touches_hardware") else "门控"
            values = [
                translate_action_title(action),
                translate_detail(str(action.get("reason", ""))),
                safety,
                str(action.get("command", "")),
            ]
            for col, value in enumerate(values):
                self.action_table.setItem(row, col, readonly_item(str(value)))
        if actions:
            self.action_table.selectRow(0)

    def set_artifacts(self, artifacts: list[dict[str, Any]], summary: dict[str, Any]) -> None:
        self.current_artifacts = artifacts
        toolchains = summary.get("toolchains") if isinstance(summary.get("toolchains"), list) else []
        total_files = summary.get("total_files", "-")
        self.evidence_summary.setText(
            f"已扫描 {total_files} 个文件；工具链：{', '.join(str(item) for item in toolchains) or '未检测'}；"
            f"资料项：{len(artifacts)}。"
        )
        self.evidence_table.setRowCount(len(artifacts))
        for row, artifact in enumerate(artifacts):
            values = [
                str(artifact.get("type", artifact.get("id", ""))),
                str(artifact.get("role", "")),
                format_size(int(artifact.get("size_bytes", 0) or 0)),
                str(artifact.get("path", "")),
            ]
            for col, value in enumerate(values):
                self.evidence_table.setItem(row, col, readonly_item(value))
        if artifacts:
            self.evidence_table.selectRow(0)

    def set_reports(self, reports: list[dict[str, Any]]) -> None:
        self.report_table.setRowCount(len(reports))
        for row, report in enumerate(reports):
            status = "可用" if report.get("exists") else "缺失"
            values = [
                translate_report_title(report),
                translate_report_role(report),
                status,
                report.get("path", ""),
            ]
            for col, value in enumerate(values):
                self.report_table.setItem(row, col, readonly_item(str(value)))


def readonly_item(value: str) -> QTableWidgetItem:
    item = QTableWidgetItem(value)
    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    return item


def format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.1f} MB"


def safe_part_name(part: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", part.strip())
    return cleaned.strip("-") or "unknown-part"


def search_preset_id(label: str) -> str:
    mapping = {
        "芯片资料": "chip-docs",
        "板卡资料": "board-docs",
        "器件风险": "part-risk",
    }
    return mapping.get(label, "chip-docs")


def task_intent_id(label: str) -> str:
    mapping = {
        "整理资料": "collect-evidence",
        "分析原理图风险": "analyze-hardware-risk",
        "配置一个外设": "configure-peripheral",
        "诊断构建失败": "diagnose-build-failure",
        "准备上板 bring-up": "prepare-bringup",
    }
    return mapping.get(label, "collect-evidence")


def parse_json(text: str) -> dict[str, Any]:
    if not text.strip():
        return {}
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


STATUS_TEXT = {
    "needs-environment-fix": "环境需修复",
    "needs-backend": "需要选择后端",
    "needs-config": "需要配置",
    "config-invalid": "配置 JSON 无效",
    "needs-onboarding": "需要项目入驻",
    "needs-safe-discovery": "需要安全发现",
    "ready-for-config-review": "待审阅配置",
    "ready-with-config-warning": "就绪但配置有警告",
    "ready-for-bench-preflight": "可进行台架预检",
    "ready-with-bench-warnings": "台架就绪但有警告",
    "needs-bench-input": "需要台架输入",
    "needs-risk-review": "需要风险复核",
    "needs-evidence": "需要补资料",
    "ready-with-warnings": "就绪但有警告",
    "ready-for-task-planning": "可规划任务",
    "present": "已找到",
    "optional-missing": "可选缺失",
    "complete": "已完成",
    "needs-action": "需处理",
    "planned-gated": "计划门控",
    "safe local only": "仅安全本地操作",
    "ok": "正常",
    "warn": "警告",
    "error": "错误",
    "missing": "缺失",
}

PHASE_TEXT = {
    "project-detection": "项目检测",
    "safe-onboarding": "安全入驻",
    "configuration": "配置",
    "safe-discovery": "安全发现",
    "bench-readiness": "台架准备",
}

ACTION_TEXT = {
    "refresh": "刷新项目",
    "auto": "自动分析",
    "brain": "项目大脑",
    "doctor": "检查环境",
    "detect": "检测项目",
    "bench-runbook": "准备台架手册",
    "safety-audit": "查看安全审计",
    "recommended": "推荐动作",
    "fix-environment": "修复环境检查",
    "run-onboard": "运行安全入驻",
    "review-config": "生成配置提案",
    "fix-config": "修复配置 JSON",
    "review-hardware-preferences": "审阅硬件后端偏好",
    "prepare-bench-runbook": "准备台架手册",
    "plan-confirmed-action": "规划确认式构建路径",
}

ACTION_TITLE_TEXT = {
    "Refresh project": "刷新项目",
    "Auto analyze": "自动分析",
    "Project brain": "项目大脑",
    "Check environment": "检查环境",
    "Detect project": "检测项目",
    "Prepare bench runbook": "准备台架手册",
    "Review safety audit": "查看安全审计",
    "Fix environment checks": "修复环境检查",
    "Analyze project": "分析项目",
    "Run safe onboarding": "运行安全入驻",
    "Generate config proposal": "生成配置提案",
    "Fix config JSON": "修复配置 JSON",
    "Review hardware backend preferences": "审阅硬件后端偏好",
    "Plan confirmed build path": "规划确认式构建路径",
}

REPORT_TEXT = {
    "manifest": "入驻清单",
    "project_dossier": "项目档案",
    "board_profile": "板卡画像",
    "firmware_profile": "固件画像",
    "build_plan": "构建计划",
    "discovery_run": "安全发现记录",
    "config_proposal": "配置提案",
    "flash_action_plan": "烧录动作计划",
}

REPORT_ROLE_TEXT = {
    "Machine-readable run summary": "机器可读运行摘要",
    "Project overview": "项目概览",
    "Board evidence": "板卡证据",
    "Firmware structure": "固件结构",
    "Build steps": "构建步骤",
    "Safe command evidence": "安全命令证据",
    "Embeddedskills config": "Embeddedskills 配置",
    "Planned-gated hardware action": "门控硬件动作计划",
}

BRAIN_CATEGORY_TEXT = {
    "schematic": "原理图",
    "pcb": "PCB",
    "bom": "BOM",
    "datasheet": "数据手册",
    "manual": "参考/用户手册",
    "cubemx_ioc": "CubeMX IOC",
    "firmware": "固件工程",
    "logs": "日志",
}

RISK_CATEGORY_TEXT = {
    "power": "电源",
    "clock": "时钟",
    "reset": "复位",
    "boot": "BOOT",
    "debug": "调试",
    "pinmux": "引脚复用",
    "build": "构建",
    "documentation": "资料",
}

SEVERITY_TEXT = {
    "critical": "严重",
    "high": "高",
    "medium": "中",
    "low": "低",
    "info": "信息",
}

CONFIDENCE_TEXT = {
    "high": "高",
    "medium": "中",
    "low": "低",
    "unknown": "未知",
}

TASK_TITLE_TEXT = {
    "collect-board-evidence": "收集板级证据",
    "collect-chip-documents": "收集芯片资料",
    "review-risk-snapshot": "复核风险快照",
    "prepare-bringup-checklist": "准备 bring-up checklist",
}

DETAIL_TEXT = {
    "Reload project evidence and update the workbench.": "重新加载项目证据并更新工作台。",
    "Run safe onboarding when needed and update project state.": "在需要时运行安全入驻并更新项目状态。",
    "Check local tools and product readiness.": "检查本地工具和产品就绪状态。",
    "Detect CubeMX metadata and build backend candidates.": "检测 CubeMX 元数据和构建后端候选项。",
    "Create a no-hardware runbook for the bench path.": "为台架路径生成不触碰硬件的运行手册。",
    "Summarize hardware action safety history without exposing tokens.": "汇总硬件动作安全历史，不暴露确认令牌。",
    "Build evidence health, missing evidence, and deterministic hardware risks.": "生成资料完整度、缺失资料和确定性硬件风险。",
    "Run doctor and resolve required environment checks before project automation.": "先运行环境检查并处理必要问题，再进行项目自动化。",
    "No supported build backend has been selected yet.": "尚未选择受支持的构建后端。",
    "Project reports or safe discovery evidence are missing.": "缺少项目报告或安全发现证据。",
    "No onboarding manifest found.": "未找到入驻清单。",
    "The project has no .embeddedskills/config.json yet.": "项目尚未生成 .embeddedskills/config.json。",
    "The existing .embeddedskills/config.json cannot be parsed.": "现有 .embeddedskills/config.json 无法解析。",
    "Hardware action preferences should be explicit before bench work.": "台架工作前应明确硬件动作后端偏好。",
    "Bench readiness still needs inputs or review; generate a no-hardware runbook.": "台架准备仍需要输入或审阅，先生成不触碰硬件的运行手册。",
    "The project is ready for a confirmation-gated build or simulated hardware path.": "项目已可进入确认门控的构建或仿真硬件路径。",
    "No backend detected": "未检测到后端",
    "No manifest found": "未找到清单",
    "No config file": "未找到配置文件",
    "Not run": "尚未运行",
}


def translate_status(value: str) -> str:
    return STATUS_TEXT.get(value, value)


def translate_detail(value: str) -> str:
    return DETAIL_TEXT.get(value, value)


def translate_phase_title(phase: dict[str, Any]) -> str:
    phase_id = str(phase.get("id", ""))
    title = str(phase.get("title", ""))
    return PHASE_TEXT.get(phase_id, title)


def translate_action_title(action: dict[str, Any]) -> str:
    action_id = str(action.get("id", ""))
    title = str(action.get("title", ""))
    if action_id == "recommended":
        return ACTION_TITLE_TEXT.get(title, title or ACTION_TEXT[action_id])
    return ACTION_TEXT.get(action_id, ACTION_TITLE_TEXT.get(title, title))


def translate_report_title(report: dict[str, Any]) -> str:
    report_id = str(report.get("id", ""))
    title = str(report.get("title", ""))
    return REPORT_TEXT.get(report_id, title)


def translate_report_role(report: dict[str, Any]) -> str:
    role = str(report.get("role", ""))
    return REPORT_ROLE_TEXT.get(role, role)


def translate_brain_category(category_id: str, title: str) -> str:
    return BRAIN_CATEGORY_TEXT.get(category_id, title or category_id)


def translate_risk_category(category: str) -> str:
    return RISK_CATEGORY_TEXT.get(category, category)


def translate_severity(severity: str) -> str:
    return SEVERITY_TEXT.get(severity, severity)


def translate_confidence(confidence: str) -> str:
    return CONFIDENCE_TEXT.get(confidence, confidence)


def translate_task_title(task_id: str, title: str) -> str:
    return TASK_TITLE_TEXT.get(task_id, title or task_id)


def citation_paths(citations: list[Any]) -> str:
    paths = []
    for item in citations:
        if isinstance(item, dict):
            paths.append(str(item.get("path", "unknown")))
        else:
            paths.append(str(item))
    return ", ".join(paths) if paths else "unknown"


def render_summary(data: dict[str, Any], code: int) -> str:
    lines = [f"完成，退出码: {code}"]
    if data.get("app") == "hardware-butler-workbench":
        project = data.get("project") if isinstance(data.get("project"), dict) else {}
        state = data.get("state") if isinstance(data.get("state"), dict) else {}
        primary = data.get("primary_action") if isinstance(data.get("primary_action"), dict) else {}
        reports = data.get("reports") if isinstance(data.get("reports"), list) else []
        brain = data.get("brain") if isinstance(data.get("brain"), dict) else {}
        health = brain.get("evidence_health") if isinstance(brain.get("evidence_health"), dict) else {}
        health_summary = health.get("summary") if isinstance(health.get("summary"), dict) else {}
        risks = brain.get("risk_snapshot") if isinstance(brain.get("risk_snapshot"), dict) else {}
        risk_summary = risks.get("summary") if isinstance(risks.get("summary"), dict) else {}
        ready_reports = sum(1 for report in reports if isinstance(report, dict) and report.get("exists"))
        lines.extend(
            [
                f"项目: {project.get('name', '-')}",
                f"状态: {translate_status(str(state.get('status', '-')))}",
                f"推荐: {translate_action_title(primary) if primary else '-'}",
                f"资料覆盖: {health_summary.get('required_present', 0)}/{health_summary.get('required_total', 0)}",
                f"风险: {risk_summary.get('total', 0)}",
                f"报告: {ready_reports}/{len(reports)} 可用",
            ]
        )
        return "\n".join(lines)
    if data.get("app") == "hardware-project-brain":
        health = data.get("evidence_health") if isinstance(data.get("evidence_health"), dict) else {}
        health_summary = health.get("summary") if isinstance(health.get("summary"), dict) else {}
        risks = data.get("risk_snapshot") if isinstance(data.get("risk_snapshot"), dict) else {}
        risk_summary = risks.get("summary") if isinstance(risks.get("summary"), dict) else {}
        lines.extend(
            [
                f"状态: {translate_status(str(data.get('status', '-')))}",
                f"资料覆盖: {health_summary.get('required_present', 0)}/{health_summary.get('required_total', 0)}",
                f"风险: {risk_summary.get('total', 0)}",
            ]
        )
        return "\n".join(lines)
    if "question" in data and "answer" in data and "confidence" in data:
        citations = data.get("citations") if isinstance(data.get("citations"), list) else []
        unknowns = data.get("unknowns") if isinstance(data.get("unknowns"), list) else []
        lines.extend(
            [
                f"问题: {data.get('question', '-')}",
                f"状态: {translate_status(str(data.get('status', '-')))}",
                f"置信度: {translate_confidence(str(data.get('confidence', '-')))}",
                f"引用: {len(citations)}",
                f"Unknown: {len(unknowns)}",
            ]
        )
        return "\n".join(lines)
    if "intent" in data and "steps" in data and "missing_inputs" in data:
        intent = data.get("intent") if isinstance(data.get("intent"), dict) else {}
        steps = data.get("steps") if isinstance(data.get("steps"), list) else []
        missing = data.get("missing_inputs") if isinstance(data.get("missing_inputs"), list) else []
        lines.extend(
            [
                f"任务: {intent.get('title', '-')}",
                f"状态: {translate_status(str(data.get('status', '-')))}",
                f"步骤: {len(steps)}",
                f"缺少输入: {', '.join(str(item) for item in missing) or '无'}",
            ]
        )
        return "\n".join(lines)

    status = data.get("status")
    if status is not None:
        lines.append(f"状态: {translate_status(str(status))}")
    next_step = data.get("next_step")
    if isinstance(next_step, dict):
        lines.append(f"下一步: {translate_action_title(next_step)}")
    error = data.get("error")
    if error:
        lines.append(f"错误: {error}")
    return "\n".join(lines)


STYLE = """
QMainWindow, QWidget {
    font-family: Microsoft YaHei UI, Segoe UI, Arial, sans-serif;
    font-size: 13px;
}
QLabel#appTitle {
    font-size: 22px;
    font-weight: 700;
    padding-right: 12px;
}
QLabel#runStatus {
    color: #1e5b9a;
    font-weight: 700;
    min-width: 72px;
}
QLineEdit#projectInput {
    min-height: 34px;
}
QTabWidget#workbenchTabs::pane {
    border: 1px solid rgba(40, 53, 147, 0.18);
    border-radius: 8px;
    padding: 8px;
}
QFrame#statusCard {
    background: rgba(255, 255, 255, 0.82);
    border: 1px solid rgba(40, 53, 147, 0.14);
    border-radius: 8px;
}
QLabel#cardTitle, QLabel#pageHint, QLabel#nextReason {
    color: #54606f;
    font-weight: 600;
}
QLabel#cardValue {
    font-size: 17px;
    font-weight: 700;
}
QLabel#nextTitle {
    font-size: 20px;
    font-weight: 700;
}
QGroupBox {
    border: 1px solid rgba(40, 53, 147, 0.18);
    border-radius: 8px;
    margin-top: 12px;
    padding: 12px;
    font-weight: 700;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 4px;
}
QTableWidget {
    gridline-color: rgba(40, 53, 147, 0.12);
}
QHeaderView::section {
    padding: 7px;
    font-weight: 700;
}
QTextBrowser#tutorialBrowser {
    padding: 18px;
}
"""

TUTORIAL_HTML = """
<h2>硬件管家工作台教程</h2>
<p>这个 exe 的核心是把一个硬件项目整理成可查看、可追踪、可执行的资料中心：原理图、手册、数据手册、BOM、工程文件、报告和安全动作都在同一个界面里。</p>

<h3>日常流程</h3>
<ol>
  <li>点击顶部 <b>浏览</b>，选择包含原理图、手册、BOM、CubeMX、Keil、CMake 或 EIDE 文件的项目根目录。</li>
  <li>点击 <b>刷新</b>，先看 <b>资料中心</b>：它会按原理图、PCB、BOM、数据手册、手册、工程文件和日志分类。</li>
  <li>如果本地资料不全，打开 <b>资料搜索</b> 页，输入芯片型号，通过 API 搜索并整理数据手册、参考手册、errata、应用笔记和板卡资料。</li>
  <li>打开 <b>报告</b> 页查看入驻清单、项目档案、板卡画像、固件画像、构建计划和配置提案是否已生成。</li>
  <li>不确定下一步时，回到 <b>总览</b> 页点击 <b>运行推荐</b>。</li>
  <li>需要手动选择流程时，打开 <b>动作</b> 页，选中安全本地动作后点击 <b>运行所选</b>。</li>
</ol>

<h3>按钮含义</h3>
<table border="1" cellspacing="0" cellpadding="6">
  <tr><th>按钮</th><th>用途</th></tr>
  <tr><td>刷新</td><td>重新扫描项目资料、报告状态和推荐动作。</td></tr>
  <tr><td>自动分析</td><td>在需要时运行安全入驻，生成项目档案、板卡画像、固件画像等报告并更新状态。</td></tr>
  <tr><td>搜索并整理资料</td><td>调用配置好的搜索 API，下载经过校验的 PDF，并生成 source-map、document-coverage 和 manual-summary。</td></tr>
  <tr><td>运行推荐</td><td>执行当前推荐的安全动作。</td></tr>
  <tr><td>运行所选</td><td>执行动作表里选中的安全动作。</td></tr>
  <tr><td>复制资料路径</td><td>复制资料中心里选中的原理图、手册、BOM 或工程文件路径。</td></tr>
  <tr><td>教程</td><td>打开当前内置说明，不依赖外部 Markdown 文件。</td></tr>
</table>

<h3>API 接入</h3>
<p>工作台不保存 API key，只读取启动 exe 时已有的环境变量。</p>
<ul>
  <li>Exa 搜索：设置 <code>EXA_API_KEY</code>。</li>
  <li>通用搜索 API：设置 <code>DOC_SEARCH_API_URL</code>，可选 <code>DOC_SEARCH_API_KEY</code>。</li>
  <li>搜索结果只作为候选来源，下载仍会校验 PDF 文件头、记录 sha256、来源质量和缺失资料。</li>
</ul>

<h3>安全边界</h3>
<p>工作台默认只运行安全本地动作。它不会直接烧录、擦除、复位、在线调试、长时间观测、发送总线帧或扫描网络。</p>
<p>真实硬件动作保持 <b>planned-gated</b>：需要动作计划、确认 token、设备身份、电压电流证据、产物 hash 和回滚记录。</p>

<h3>exe 目录</h3>
<pre>
dist\\HardwareButlerWorkbench\\HardwareButlerWorkbench.exe
dist\\hardware_butler_cli\\hardware_butler_cli.exe
</pre>
<p>两个目录需要放在同一个 <code>dist</code> 下，GUI 会自动寻找旁边的 CLI 后端。</p>

<h3>常见问题</h3>
<ul>
  <li>显示未检测到后端：确认选中的是项目根目录，里面应有 .ioc、.uvprojx、CMakeLists.txt 或 EIDE 工程文件。</li>
  <li>报告缺失：点击运行推荐或自动分析。</li>
  <li>动作失败：打开输出页查看命令摘要和错误信息。</li>
  <li>需要真实烧录或调试：先生成 bench-runbook 和 plan-action，再走确认 token 流程。</li>
</ul>
"""


def main() -> None:
    app = QApplication(sys.argv)
    if apply_stylesheet is not None:
        apply_stylesheet(app, theme="light_blue.xml")
    app.setStyleSheet(app.styleSheet() + STYLE)
    window = HardwareButlerWindow()
    window.show()
    QTimer.singleShot(0, window.run_workbench)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
