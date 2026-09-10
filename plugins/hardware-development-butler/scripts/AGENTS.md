# Hardware Agent Workspace Instructions

根目录是工作区容器，不是单一项目。处理任务时先判断归属：

- `nextboard/` — 硬件方案设计、器件选型、BOM 风险、PCB/原理图约束、评审和报告输出
- `embeddedskills/` — Keil/GCC/EIDE 构建、J-Link/OpenOCD/probe-rs 烧录调试、串口/CAN/网络/终端和工作流编排
- `tools/` — 统一 CLI + 芯片资料、CubeMX 分析、固件生成、安全门控等后端模块

## Agent 分工

- 方案设计/器件选型/BOM/PCB → `agents/nextboard-hardware-architect.md`
- 构建/烧录/调试/总线/观测 → `agents/embeddedskills-lab-operator.md`
- 跨阶段调度/文档组织/闭环推进 → `agents/hardware-development-butler.md`
- 跨阶段任务按 `nextboard → embeddedskills → nextboard` 流程推进

## 关键命令

```powershell
# 安装依赖
pip install -r requirements-dev.txt

# 验证顺序（推荐）：lint → typecheck → test
ruff check tools/ tests/           # lint 子集
ruff check .                       # lint 全部
mypy tools/ --config-file mypy.ini # typecheck（仅 tools/，embeddedskills 无类型检查）
pytest tests/ -v                   # 运行所有测试（排除硬件标记）
pytest tests/ -v --run-hardware    # 包含硬件测试（需连接探针/板子）
pytest tests/unit/test_*.py -v     # 单个测试文件

# 硬件管家 CLI（等效：python -m tools.hardware_butler）
python tools/hardware_butler.py --help
python tools/hardware_butler.py capabilities --json
python tools/hardware_butler.py doctor --root <project-root> --json
python tools/hardware_butler.py onboard --root <project-root> --out-dir <dir> --json

# nextboard 校验
python nextboard/tests/validate.py
```

## 子项目边界

- **不要把两个子项目混成一个目录**；共享说明放根目录，实现留各自目录。
- `embeddedskills/` 保留独立 `.git`（远程: `zhinkgit/embeddedskills`），不要删除或合并。父仓库不追踪它。若需纳入版本管理，先定为 submodule。
- `embeddedskills` 无 pytest/CI，修改后手动运行对应 skill 脚本验证 JSON `"status": "ok"` 返回值。
- `tools/` 由根目录 pytest 覆盖（`--cov=tools --cov=embeddedskills`）。
- `nextboard/CLAUDE.md` 有自己的文档约定：器件参数必须来自数据手册/分销商，不能凭记忆；方案输出前需通过 5 道验证门控。

## 测试结构 & 陷阱

- `tests/unit/` — 纯 Python 单元测试
- `tests/validate_hardware_butler.py` — 集成校验（导入所有工具模块 + safety_gate）
- `tests/hardware/` — 硬件测试（标记 `@pytest.mark.hardware`，需 `--run-hardware`），还支持 `--target <mcu>` 和 `--port <port>` 参数
- `conftest.py` 自动将 `tools/` 和 `embeddedskills/` 加入 `sys.path`，测试中可直接 `import tools.x`
- **pytest 默认始终开启覆盖**（`addopts` 含 `--cov=tools --cov=embeddedskills`），需抑制时加 `--no-cov`
- **pytest 禁用缓存提供者**（`-p no:cacheprovider`），`--cache-clear` 无效

## 关键约束

- **安全门控**: `tools/hardware_action_executor.py` 默认阻止真实硬件操作。真实刷写需同时设 `HARDWARE_BUTLER_ENABLE_REAL_FLASH=1` 并提供确认 token。不要绕过。详见 `SECURITY.md`。
- **embeddedskills 纯标准库**: 除 `can`/`serial`/`terminal`（需 `pyserial`）外，只用 Python 标准库。
- **embeddedskills JSON 输出**: 所有脚本返回 `{"status": "ok|error", "action": "...", "summary": "...", "details": {...}, ...}`，流式命令用 JSON Lines。
- **Python >= 3.10** 必须。

## GUI & 插件

- GUI: `python gui/hardware_agent_ui.py`（PyQt6）。也可用根目录 `launch_gui.py`（已改为基于文件路径解析，无硬编码）。
- Codex 插件: `plugins/hardware-development-butler/`
- 重新打包: `python tools/package_hardware_butler_plugin.py`
- 校验: `python plugins/hardware-development-butler/scripts/validate_package.py`
- CLI 包入口（pyproject.toml `[project.scripts]`）: `hardware-butler` → `tools.hardware_butler:main`，`butler` → `tools.butler_cli:main`
