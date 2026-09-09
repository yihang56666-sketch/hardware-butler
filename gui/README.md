# Hardware Butler 源码 GUI

这是 PyQt6 本地工作台，不是实机烧录向导。保持现有 CLI 后端架构；本次不发布 wheel、exe 或插件镜像。

## 安装与启动

需要 Python 3.10+。在仓库根目录创建虚拟环境并安装 UI extra：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[ui]"
.\.venv\Scripts\python.exe launch_gui.py
```

`requirements.txt` 和 `requirements-dev.txt` 不包含 PyQt6。缺少 Qt 时入口会输出安装提示，而不是打开空白窗口。`qt-material` 为可选主题，缺少时回退到 Qt 原生样式。

从任意工作目录可用解释器和启动脚本的绝对路径启动，例如：

```powershell
& "<repo-root>\.venv\Scripts\python.exe" "<repo-root>\launch_gui.py"
```

启动器根据自身文件位置找 `gui/hardware_agent_ui.py`，GUI 根据自身位置找 `tools/hardware_butler.py`，不依赖调用者 cwd 或 editable install 来定位后端。项目目录会规范化为绝对路径。日志文件建议使用绝对路径；命令的工作目录固定为应用根目录。

根 `AGENTS.md` 中“launch_gui.py 路径硬编码”的提示已过时，本次回归已证明当前定位正确，未改写启动器。单独 wheel 是否包含 GUI、nextboard 的非 Python 资源和完整硬件后端，仍由主任务统一验证/修复包装；不能由源码启动成功推断发布包完整。

## 离线与外部能力

- 本地展示：13 个标签页、项目/资料/报告列表、只读项目问答、任务计划、日志分类、固件与 IOC 提案入口。提案生成并不证明生成代码或硬件可用。
- 联网资料搜索/下载：默认不授权，须在“资料搜索”页勾选；API 可能收费。选型参数必须有资料依据，无法查证只标待核。
- 工作流运行/恢复：默认不授权，须单独勾选；可能调用已配置 LLM、编译器或仿真器。读取状态和 LLM 配置无需启用运行。GUI 不保存 API key，只保存环境变量名等配置。
- 真实硬件：GUI 子进程强制 `HARDWARE_BUTLER_ENABLE_REAL_FLASH=0`，不继承父进程的启用值；推荐动作仅接受明确的安全声明及允许的 CLI 命令。真实动作需退出该界面，另走经人工批准的核心执行链。
- `behavior-mock`、`sim` 和仿真证据会在工作流页显示。`completed` 只表示阶段结束，不能当成实机验证成功；本 GUI 没有独立的“一键全功能 mock 模式”。

## 生命周期与诊断

命令和 LLM 配置读取均在后台线程执行。可以取消；关闭窗口会先取消并等待线程收尾。取消/超时会尽力终止当前 CLI 进程树并保留输出，不回滚已写文件。核心工作流若保留 running 状态，应检查状态和产物后再人工决定恢复，不能自动推断失败已回滚。

切换项目会清除旧项目推荐、任务、资料和配置运行授权。非 JSON、错误 JSON 状态、缺依赖或进程启动失败均显示失败，不仅依赖退出码判断。长页面可滚动，窗口不会被工作流表单撑出屏幕。

## 离线回归

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
$env:HARDWARE_BUTLER_ENABLE_REAL_FLASH = "0"
.\.venv\Scripts\python.exe -m pytest tests/unit/test_gui_launch_readiness.py tests/unit/test_gui_tools_tab.py --no-cov --basetemp=gui/.tmp-pytest-readiness
.\.venv\Scripts\python.exe nextboard/tests/validate.py
```

测试仅启动本地短生命周期子进程、读取 CLI 能力/分类示例日志，以及在隔离临时 HOME 中安装 nextboard；不联网、不付费、不连接探针、不烧录、不修改真实用户安装。离屏截图环境可能不自动枚举 Windows 字体；本次视觉检查仅在离屏进程中加载了本机微软雅黑，不修改系统字体或用户配置。
