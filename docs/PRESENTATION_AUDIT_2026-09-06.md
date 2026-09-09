# Hardware Butler GUI / NextBoard 限定审计

- 日期：2026-09-06，Asia/Shanghai。
- 仓库：`<repo-root>`；以下文件名均相对该仓库。
- 分工：first-party GUI、源码启动器、nextboard 设计协议/引用/验证器及干净安装入口；保留现有 CLI 架构，验证驱动修复。
- 结论边界：本报告不是整个项目完成、发布就绪、器件参数核验或实机通过的结论。
- Transport 恢复后先检查了在途进程：未发现本次 GUI、针对性 pytest、nextboard validator 的在途 Python 进程。未重做已有修复；仅重新验证、归档临时产物并完成本报告。
- 本分工未修改 `tools/`、`plugins/`、独立 `embeddedskills/`、根 requirements/pyproject；未运行烧录/调试、真实设备操作、付费 LLM、外部服务修改、commit/push/branch 或凭据修改。主任务/另一 agent 的已有修改均保留。
- 用户预存的 `docs/项目概述与项目计划书.docx` 仅在目录清单中出现，未打开、转换、修改或删除。

## 0. 本轮有界交接（2026-09-06 08:30 +08:00）

- 本轮首先检查当前命令终态：未发现指向本仓库或本任务脚本的 Python / pytest / Ruff 在途进程；进程查询、限定路径 `git status` 和限定已追踪补丁 `git diff --check` 均已结束，exit 0。
- 保留全部既有修改，不重做、不扩大审查。本轮仅增补本报告，没有再次修改 GUI、nextboard 实现或测试，更没有修改 core/tools、plugins、embeddedskills、根包装文件或用户预存 Word。
- 交接快照为 **16 个已追踪文件修改 + 4 个新增文件，共 20 个路径**；逐项列于第 4 节。`launch_gui.py` 未修改，外部 cwd 回归已通过。
- 第 1 节的 **63 pytest passed、70 validator PASS、Ruff exit 0** 是 transport 恢复后最后一次已完成验证，本轮没有重新启动这些测试或新的长审查。它们证明当次受测源码状态，不替代其他 agent 后续改动整合后的总验收。
- **没有遗留的已记录测试 RED**：第 2 节的三轮失败均已获得 GREEN。第 6 节的包装、核心取消契约、历史资料及实机缺口仍然保留，未把未执行或无法在本分工完成的项目改称 PASS。
- 已逐行/全文审读的范围以第 3 节逐份台账为准；副本 hash、部分读取、仅清单、未读、第三方实现及历史 PDF/HTML 分开登记，本轮不追加未经实际阅读的覆盖声明。
- main 集成时仍需在统一源码状态下重跑第 1 节命令，并另行完成干净分发包资源、镜像策略和发布前总验收。本报告仅作为 GUI/nextboard 子任务交接，不宣布项目完成或允许实机操作。

## 1. 最终验证终态

运行环境：仓库已有 `.venv`，Windows / Python 3.13.14 / pytest 9.1.1；Qt 为 `offscreen`。这里不是全新 venv 或发布 wheel 的安装验证。

```powershell
$env:PYTHONIOENCODING = "utf-8"
$env:QT_QPA_PLATFORM = "offscreen"
$env:HARDWARE_BUTLER_ENABLE_REAL_FLASH = "0"
.\.venv\Scripts\python.exe -m pytest tests/unit/test_gui_launch_readiness.py tests/unit/test_gui_tools_tab.py --no-cov --basetemp=gui/.tmp-pytest-readiness-final-resume --tb=short -q
.\.venv\Scripts\python.exe nextboard/tests/validate.py
.\.venv\Scripts\python.exe -m ruff check gui/hardware_agent_ui.py tests/unit/test_gui_launch_readiness.py nextboard/tests/validate.py
git -c core.safecrlf=false diff --check -- gui launch_gui.py nextboard tests/unit/test_gui_launch_readiness.py
```

| 验证 | 恢复后的终态 | 证明范围 |
|---|---|---|
| 针对性 pytest + 已有 GUI 测试 | **63 passed，7.48s，exit 0** | 新文件 55 例、已有文件 8 例；启动路径、UI/CLI 契约、异步/取消/退出、错误展示、隔离安装等 |
| nextboard validator | **70 PASS / 0 FAIL / 0 WARN，exit 0** | 源码结构、文档本地链接、门控/模板结构、reviewer 维度、配置版本；不是硬件验证 |
| 针对性 Ruff | **All checks passed，exit 0** | 修改的 Python GUI、验证器和新测试；Qt 必需的 `closeEvent` 命名由 GUI 局部配置精确豁免 |
| scoped `git diff --check` | **exit 0** | 已追踪的限定补丁无空白错误；本轮复查 exit 0，未追踪新增文件（含本报告）不在该命令检查范围内 |

没有跑全仓 pytest、mypy、发布验证器、packager、PyInstaller，也没有重建插件镜像。未把别的 agent 的测试结果当成本分工验证结果。

## 2. RED → GREEN 证据与缺陷

原 nextboard validator 基线是 **60 PASS / 0 FAIL / 0 WARN**，但没有检出下述真实一致性缺口；静态通过并不表示协议已经一致。

| 轮次 | RED 实际结果 | GREEN / 处理 |
|---|---|---|
| 首批回归 | 39 例中 **32 failed / 7 passed** | 修 GUI 生命周期/边界及 nextboard 协议/安装后，连同已有 8 例达到 **47 passed** |
| 可视化/真实 CLI 契约补充 | 7 例 **7 failed** | 补 Qt 安装提示、滚动容器、日志位置参数、状态类型处理；同时修正本次白名单遗漏的 3 个既有安全命令；最终该阶段 **54 passed** |
| JSON / frozen 定位补充 | 5 例 **5 failed** | 非 JSON 不再报完成，frozen 后端候选须为文件；加入生命周期、隔离安装用例后 **63 passed** |

32/7/5 是测试失败数，不是独立根因数。第二轮 `status` / `inspect` / `plan-build` 三例暴露的是本次安全白名单中间实现遗漏，已修正，不冒充历史缺陷。中途既有日志测试还发现本次路径规范化改变了显示参数，已保留原日志路径表示，仅修正 CLI 的位置参数契约。

### 已证实并修复

| 问题 | 修复及可复核证据 |
|---|---|
| `load_workflow_llm_config` 在 GUI 线程同步 `subprocess.run`，最多阻塞 30 秒 | 改用同一异步命令路径，结果回填独立处理；测试禁止在槽函数同步调用 subprocess |
| worker 无取消入口，窗口关闭没有线程收尾协议，业务 signal 覆盖 `QThread.finished` | 改为 `result_ready` + 原生 `finished`；取消按钮、延迟关闭、线程释放后才允许下一命令；真实本地睡眠子进程用于测试，不连接设备 |
| 超时丢失已产生的输出 | 保留 stdout/stderr，超时 124、取消 130；提示已写文件不自动回滚；Windows 尽力终止当前子进程树，不弹控制台 |
| GUI 继承父进程 `HARDWARE_BUTLER_ENABLE_REAL_FLASH=1` | 子进程环境强制为 `0`，不修改父环境；验证 opt-in 不会继承。仍需核心保持所有硬件路径的统一门控 |
| 推荐动作仅检查 `touches_hardware`，可接受缺安全声明或任意 argv | 要求严格布尔安全声明、限定 Hardware Butler CLI 入口和安全命令集，拒绝任意解释器脚本及 `execute-action` |
| 工作流/搜索按钮未区分离线展示与外部调用 | 默认不勾选网络/工作流运行授权；读取配置和状态仍可单独操作；界面提示可能收费、编译、仿真，真实硬件仍禁用 |
| 项目切换后仍保留旧项目可运行推荐/任务 | 清空旧状态、表格、推荐和授权；项目目录规范化为绝对路径 |
| 器件目录名 `.` / `..` 可变成上层或当前目录 | 清理点目录名，回退 `unknown-part`；不涉及任何器件参数补全 |
| JSON 错误状态 + exit 0、非 JSON 等显示“完成”，坏字段可抛出到 Qt | 检查响应类型和状态、捕获展示边界错误、显示明确失败；过滤非对象阶段项 |
| 工作流 `completed` 未提示 mock/sim 证据层级 | 新增阶段证据列及“非实机”提示；缺证据显示 unknown，不合成器件或观测数据 |
| `classify-log --log ...` 不符合真实 CLI 契约 | 改为位置参数；用临时离线日志真实调用 CLI，修复前 argparse exit 2，修复后 exit 0 |
| GUI 最小高度被最长表单撑至 1148px | 每个标签页使用可滚动容器，保留 13 个标签和已有 handler 顺序；1360×860 可用 |
| 缺 Qt 时只有导入 traceback；frozen 定位接受同名目录 | 提供源码 `[ui]` 安装提示，候选使用 `is_file()`；未打包 exe |
| nextboard 主技能/工作流要求聚合站优先，与 Gate 3 / sourcing 原厂优先冲突 | 统一原厂 → 授权分销商 → 元器件平台 → 聚合线索；参数需版本/封装/页码，无证据只标待核 |
| 下载经验写入已安装共享技能，安装副本易受污染 | 登记模板只读，实际记录放用户项目 `docs/hardware/download-sources.md` |
| 模板缺决策三分类、证据定位和门控记录；Gate 6 被混同必需门；自检可冒充独立复核 | 增加明确结构；Gate 1–5 必需，Gate 6 依用户请求；自检必须标非独立，FAIL 不能仅改待确认即 PASS |
| validator 只查 SKILL 链接，未查 reference 链、脚本/metadata；installed 固定读真实 Claude HOME | 扩充静态检查；外链/fragment 不当本地文件；显式安装目录优先，可选 Codex 默认目录，并检查 reviewer |
| `--uninstall-project` 删除通用 `skills/agents/hooks/.claude-plugin/.nextboard` 并改 `.gitignore` | 仅删除项目中指定的 NextBoard Codex 两个安装目标，检查重定向；在隔离项目实际运行前后断言用户文件保留 |
| Claude 交互安装可遗漏 reviewer，导致 SKILL 相对链接缺失 | 始终包含 reviewer 文档；Claude/Codex 都在临时隔离 HOME 实际安装并运行 installed validator |

### 未证实为缺陷：启动器定位

根 `AGENTS.md` 提醒 `launch_gui.py` 硬编码错误，但当前源码已经以 `Path(__file__).resolve().parent` 定位 sibling GUI。测试从外部 cwd 验证路径、调用解释器、子进程退出码传播；GUI `runpy` 构造和 CLI `capabilities --json` 也从外部 cwd 验证通过。因此 **未修改 `launch_gui.py`，没有声称修复一个不存在的问题**。隔离了 cwd/PYTHONPATH，不等同于重新创建无 editable metadata 的干净发行环境。

## 3. 逐份审读清单

“全文”表示实际按内容审读（长文件分段），不是仅 `rg` 扫词；只看清单、抽段或副本 hash 的文件另列。新写文件列为“本次编写/验证”，不伪装成对原文件的全文审计。

### 3.1 GUI、主协议、引用与安装源码

| 文件 | 覆盖 |
|---|---|
| `AGENTS.md` | 全文，只读；明确子仓库边界与过时启动器提示 |
| `launch_gui.py` | 全文 + 路径/退出码回归，未修改 |
| `gui/hardware_agent_ui.py` | 原 2226 行分段全文，含全部标签、handler、输出解析、翻译、样式和内置教程；修改路径验证 |
| `gui/README.md` | 本次编写；源码安装、离线/外部边界、取消、发布限制 |
| `gui/ruff.toml` | 本次编写；只豁免 Qt 虚函数名 |
| `tests/unit/test_gui_tools_tab.py` | 全文，原有 8 测试只运行不修改 |
| `tests/unit/test_gui_launch_readiness.py` | 本次编写并 RED/GREEN，最终 55 测试 |
| `nextboard/AGENTS.md` | 全文，门控说明一致性修订 |
| `nextboard/CLAUDE.md` | 全文，安装协议和门控说明 |
| `nextboard/README.md` | 分段全文，安装/卸载/平台/静态检查范围 |
| `nextboard/skills/hardware-solution/SKILL.md` | 分段全文，工作流程、阶段产物、门控、交接 |
| `nextboard/skills/hardware-solution/references/design-workflow.md` | 分段全文，模式、冻结、选型、下载、可选原理图、PDF |
| `nextboard/skills/hardware-solution/references/verification-gates.md` | 全文，逐门与模板/reviewer 对照 |
| `nextboard/skills/hardware-solution/references/output-template.md` | 全文，补决策和证据/门控，不填写虚构器件值 |
| `nextboard/skills/hardware-solution/references/download-sources.md` | 全文；空登记不是已验证来源库 |
| `nextboard/skills/hardware-solution/references/sourcing-and-risk.md` | 全文，未修改 |
| `nextboard/skills/hardware-solution/references/domestic-sources.md` | 全文，作为来源线索目录；未联网验证各网站/厂商当前状态 |
| `nextboard/skills/hardware-solution/references/review-checklists.md` | 全文，未修改 |
| `nextboard/agents/hardware-reviewer.md` | 全文，修复循环“已过 Gate”跳过证据和可选原理图条件 |
| `nextboard/skills/hardware-solution/agents/openai.yaml` | 全文，静态 metadata；未声称客户端实际加载 |
| `nextboard/tests/validate.py` | 原 529 行分段全文，实际运行基线及最终版本 |
| `nextboard/scripts/install.sh` | 原 405 行分段全文；仅隔离 HOME/项目安装卸载测试，没有修改真实安装 |
| `nextboard/scripts/bump-version.sh` | 分段全文，只读；没有运行版本变更 |
| `nextboard/hooks/session-start` | 全文；validator 在本地 Bash 调用并验证 JSON，无网络/设备 |
| `nextboard/hooks/hooks.json` | 全文，只读 |
| `nextboard/hooks/hooks-cursor.json` | 全文，只读；未验证实际 Cursor 会话加载 |
| `nextboard/.claude-plugin/plugin.json` | 全文，静态核对 |
| `nextboard/.claude-plugin/marketplace.json` | 全文，静态核对；未调用 marketplace |
| `nextboard/.codex-plugin/plugin.json` | 全文，静态核对 |
| `nextboard/.cursor-plugin/plugin.json` | 全文，静态核对 |
| `nextboard/.version-bump.json` | 全文，静态核对 |
| `nextboard/.github/PULL_REQUEST_TEMPLATE.md` | 全文，贡献和场景验证要求 |
| `nextboard/__init__.py` | 全文；Python `0.1.0` 与插件 `0.2.0` 未在本次统一 |

### 3.2 历史、复制、个人/第三方边界

| 文件 | 覆盖与分类 |
|---|---|
| `nextboard/skills/hardware-solution/scripts/md_to_pdf.py` | 分段审读转换、样式、合并和 CLI；未运行渲染。此路径是技能运行入口 |
| `nextboard/scripts/md_to_pdf.py` | 副本，只比 SHA-256 相同，没有重复宣称两份独立全文审计 |
| `nextboard/hermes_launcher_gui.py` | 分段全文；历史个人 Hermes/AI 日报启动器，含外部本机目录、API 配置写入和新控制台，不运行不修改 |
| `nextboard/docs/hardware/stm32-quadrotor/README.md` | 全文，增加历史待核说明和逐门缺口 |
| `nextboard/docs/hardware/stm32-quadrotor/01-requirements.md` | 全文，历史草案，无冻结授权/完整约束证据 |
| `nextboard/docs/hardware/stm32-quadrotor/02-architecture.md` | 全文，历史候选及取舍，未验证器件能力 |
| `nextboard/docs/hardware/stm32-quadrotor/03-components.md` | 全文，精确封装/来源/参数证据缺失，未补参数 |
| `nextboard/docs/hardware/stm32-quadrotor/04-constraints.md` | 全文，历史走线数值新增待核提示，未把估算当标准值 |
| `nextboard/docs/hardware/stm32-quadrotor/05-validation.md` | 全文，台架/飞行文字计划而非测试记录；未执行 |
| `nextboard/docs/hardware/stm32-quadrotor/06-decisions.md` | 全文，“已决定”不能代替 Gate 证据 |
| `nextboard/docs/hardware/stm32-quadrotor/07-schematics.md` | 全文，功能级连接草案而非精确引脚级验证成果 |
| `nextboard/docs/hardware/stm32-quadrotor/hardware-solution.md` | 全文，新增待核草案声明 |
| `nextboard/docs/hardware/stm32-quadrotor/plan.md` | 全文，历史实施计划；没有跟随其指令启动其他工作或硬件测试 |
| `nextboard/docs/hardware/stm32-quadrotor/stm32-quadrotor-report.md` | 全文，历史汇总新增未验证说明 |
| `nextboard/docs/hardware/stm32-quadrotor/make_pdf.py` | 读取了字体、转换和构建相关代码；长输出有截断，不计严格逐行全文审计；未运行 |
| `nextboard/docs/hardware/stm32-quadrotor/stm32-quadrotor-report.html` | 只列清单/大小，未全文或视觉审读，保持原样 |
| `nextboard/docs/hardware/stm32-quadrotor/stm32-quadrotor-report.pdf` | 只列清单/大小，未解析/视觉审读/重生成，保持原样 |
| `nextboard/.codex` | 只确认目录清单中为零字节文件，不是有效运行配置验证 |
| `nextboard/.claude/settings.local.json` | 仅清单，私有状态未读未改 |

两份通用 PDF 脚本基线 hash 均为 `817CFAE013DEBD6C29581792C26E51E088F7322E9EDFF9974DF16BBE9E6DE913`。未对历史 HTML/PDF 宣称跟新 Markdown 同步。

已有四旋翼设计场景用于逐门人工对照：缺需求冻结、选型来源、引脚/电源预算证据、量化验收和独立评审，因此标为未通过的待核草案。这是实际既有文档场景检查，不是新器件研究或实机实验。

### 3.3 根目录只读上下文与未扩张范围

| 文件 | 覆盖 |
|---|---|
| `requirements.txt` | 全文，只读：最小运行依赖，无 Qt |
| `requirements-dev.txt` | 全文，只读：测试工具不包含 Qt |
| `requirements-all.txt` | 全文，只读：可选依赖聚合 |
| `pyproject.toml` | 全文，只读：UI extra、package find、CLI scripts、pytest/Ruff 配置 |
| `conftest.py` | 读取相关 fixture/硬件默认禁用部分；组合输出有截断，不计全文审计 |
| `tests/conftest.py` | 读取 fixture 定义；未使用真实串口 fixture |
| `docs/INSTALL.md` | 全文，只读；源码优先及 `[ui]` 指引正确 |
| `docs/WORKBENCH_FEATURE_COVERAGE.md` | 全文，只读；部分“还没有 GUI”描述已过时 |
| `docs/WORKBENCH_TUTORIAL.md` | 全文，只读；错误地用最小 requirements 修复 Qt 缺失 |
| `docs/AUTO_WORKFLOW_GUI.md` | 全文，只读；同样存在最小 requirements 的 GUI 安装说明偏差 |
| `docs/START_HERE.md` | 分段读取入门/GUI/边界部分；不纳入严格全文清单 |
| `tools/build_workbench_exe.py` | 全文，只读；已有 embeddedskills 路径和构建依赖假设 |
| `tools/package_hardware_butler_plugin.py` | 仅检查复制名单、排除规则及复制函数片段，不是 core 全文审计 |
| `tools/hardware_butler.py` | 仅 CLI 导入、参数、报告契约片段及实际离线 capabilities/classify-log |
| `tools/project_workflow.py` | 仅推荐动作/安全 metadata/工作台构造片段 |
| `tools/task_workflows.py` | 读取任务到 argv 的契约，重点核对 inspect/plan-build/classify-log；不作为 core 修复 |
| `tools/workflow_runner.py` | 仅真实开关、观测及验证证据层级相关片段；并发修改中，不以旧片段替代 main 最终审计 |
| `hardware_butler.egg-info/SOURCES.txt` | 仅过滤 GUI / nextboard 条目，旧生成清单不是最终 wheel 内容证明 |
| `.gitattributes` / `.gitignore` | 读取行尾和临时目录规则，只读 |

未读/不覆盖：根 `README.md`、`SECURITY.md` 除清单外未在本分工审完；`docs/` 中除上表和本报告外的历史/规划/架构/发布文档未逐份审读；`study_notes/`、`build/`、`dist/`、插件生成镜像及独立 embeddedskills 内容未审计。未访问厂商站点、分销商、实际 datasheet/EDA 库，也未审计 PyQt/qt-material/WeasyPrint 等第三方实现。不能把引用到第三方名称当成资料查证。

## 4. 所有实际修改路径

源文件/文档共 20 个；启动器未改。M 为修改，A 为本次新增。

| 状态 | 路径 | 内容 |
|---|---|---|
| M | `gui/hardware_agent_ui.py` | 生命周期、安全边界、错误/证据展示、滚动布局、日志契约、安装提示 |
| A | `gui/README.md` | 正确源码 UI 安装及离线/实机边界 |
| A | `gui/ruff.toml` | Qt closeEvent 命名的局部 lint 配置 |
| A | `tests/unit/test_gui_launch_readiness.py` | 55 个限定回归 |
| M | `nextboard/AGENTS.md` | 必需/可选门控与待核边界 |
| M | `nextboard/CLAUDE.md` | 同上，保持核心规则一致 |
| M | `nextboard/README.md` | 安装完整性、卸载保留范围、客户端验证限制、历史入口分组 |
| M | `nextboard/agents/hardware-reviewer.md` | 独立复核与证据复用约束 |
| M | `nextboard/scripts/install.sh` | reviewer 完整安装与项目卸载范围修复 |
| M | `nextboard/skills/hardware-solution/SKILL.md` | 来源优先级、项目登记、待核及 PDF 主文档边界 |
| M | `nextboard/skills/hardware-solution/references/design-workflow.md` | 同步流程/下载/PDF 说明 |
| M | `nextboard/skills/hardware-solution/references/download-sources.md` | 只读模板和核验字段 |
| M | `nextboard/skills/hardware-solution/references/output-template.md` | 参数来源、决策三分类、门控记录 |
| M | `nextboard/skills/hardware-solution/references/verification-gates.md` | 独立评审、不适用和待核规则 |
| M | `nextboard/tests/validate.py` | 引用链、安装资源/reviewer、可指定安装目录和静态范围声明 |
| M | `nextboard/docs/hardware/stm32-quadrotor/README.md` | 历史草案逐门缺口 |
| M | `nextboard/docs/hardware/stm32-quadrotor/04-constraints.md` | 无来源走线估算待核提示 |
| M | `nextboard/docs/hardware/stm32-quadrotor/hardware-solution.md` | 历史未验证声明 |
| M | `nextboard/docs/hardware/stm32-quadrotor/stm32-quadrotor-report.md` | 与未重建 PDF/HTML 的边界 |
| A | `docs/PRESENTATION_AUDIT_2026-09-06.md` | 本报告 |

对 skill/reference 的前后对比已在第 2 节逐项记录；没有更改器件参数以让模板看起来完整。

临时产物只在 `gui/`：旧 RED/GREEN 临时树与截图已用原生 PowerShell 移入被既有 ignore 规则覆盖的 `gui/.tmp-pytest-readiness-audit/`，移动前逐一验证源和目的绝对路径在 GUI 目录内。保留最终测试目录 `gui/.tmp-pytest-readiness-final/` 与 `gui/.tmp-pytest-readiness-final-resume/`；不作为源补丁或发布内容。

## 5. 当前可演示功能与视觉证据

已实际离线验证：13 页窗口构造/切换、已有工具按钮 wiring、安全动作及模拟报告展示、真实 CLI capabilities、临时构建日志分类、命令 stdout/stderr、超时/取消、关闭回收、下一命令、Claude/Codex 隔离安装与 installed validator。其余按钮保留现有后端契约，并不意味着本次完整执行过 auto/onboard/固件生成/研究/工作流。

窗口布局修复前离屏高度为 1148px；修复后 1360×860，最小高度提示 253px。首页、工具、工作流页截图实际查看；其余标签仅做结构/窗口高度测试，没有宣称逐页视觉审核。工作流长表单通过滚动访问，不压缩到不可读。

离屏 Qt 初始枚举字体为 0，最初截图中文方框不能算视觉通过；随后仅在截图进程中加载本机 `C:/Windows/Fonts/msyh.ttc`，确认中文 glyph 可用并重新截图，没有安装或修改系统字体。经查看的截图保留于：

- `gui/.tmp-pytest-readiness-audit/.tmp-readiness-green-third/gui-home-after.png`
- `gui/.tmp-pytest-readiness-audit/.tmp-readiness-green-third/gui-tools-after.png`
- `gui/.tmp-pytest-readiness-audit/.tmp-readiness-green-third/gui-workflow-after.png`

GUI 没有独立“一键全功能 mock 产品模式”。测试中的 fixture/合成报告是边界测试，不是硬件观测；工作流的 mock/sim/仿真证据仅显示原始层级，不能证明硬件达标。报告按钮切换/展示清单，不能把它描述成已经实现完整文件预览或 EDA 编辑器。

## 6. Main 仍需跟进与未覆盖项

1. **统一包装与发布**：根 setuptools find 当前只含 `tools*`、`nextboard*`，没有 GUI 包/启动脚本入口；旧 SOURCES 也未列 GUI 和 nextboard Markdown/YAML/JSON 资源。请 main 在独立干净 wheel/sdist/exe 环境确认真实资源清单，不能凭源码通过或旧 manifest 下最终结论。本次不修改根包装、不重建镜像。
2. **插件排除和拷贝策略**：现 packager 复制整个 nextboard 及 tests，未复制 GUI/launcher；新测试被同步而 GUI 不在镜像时可能失配。需 main 决定测试排除或 GUI 同步，并排除 `hermes_launcher_gui.py`、个人/历史/临时资料、生成历史报告和本地 settings；不要把宽泛 nextboard 复制当成干净分发。
3. **根文档**：`AGENTS.md` 的启动器告警过时；`docs/WORKBENCH_TUTORIAL.md` / `docs/AUTO_WORKFLOW_GUI.md` 的 Qt 安装指引和功能覆盖文档需 main 同步。限定范围内的新 `gui/README.md` 已给出正确路径，根文档未越权改动。
4. **核心取消语义**：GUI 尽力终止 CLI 进程树，不负责核心事务回滚、断点状态 repair 或日志原子性；取消后的文件可能部分写入，需 main 审定恢复协议。进程树终止失败的 fallback 不等于对所有外部进程的绝对回收保证。
5. **硬件安全契约**：GUI 只做入口防御并强制真实开关为 0，仍依赖核心不从其他环境变量/项目配置绕开安全门。未连接硬件测试，不认证整个 core 的真实操作路径。
6. **表单/CLI 能力差距**：`tools_fw_part` 字段未参与固件计划/补丁参数；通用 I2C 等场景的 `.ioc` 页面没有完整 instance/SCL/SDA 表单，CLI 仍是高级入口。没有为赶收尾扩展 UI 或擅自改核心参数。
7. **验证器范围**：本地链接目标存在不等于外链可用、anchor 正确或语义一致；未全面结构校验异常配置 JSON，也未实际运行客户端插件注册。Python 包版本 0.1.0 与插件版本 0.2.0 的发布策略待 main 确认。
8. **安装边界**：验证的是隔离空 HOME 干净安装和限定项目卸载；未操作真实用户全局安装，也未覆盖覆盖安装的事务备份、所有 junction/symlink 组合、全部 Bash 参数异常和 marketplace 发布。
9. **PDF/器件数据**：最小运行/报告 extras 不保证有 Markdown/WeasyPrint/native libraries/ReportLab/中文字体。PDF 脚本仍按文件名合并全部 Markdown、不能自动渲染 Mermaid/D2、不能当验证门；本次通过正式主文档指引避免混入计划，不重构渲染器。历史 PDF/HTML 未视觉核验，不分发为通过审核的最新成果。
10. **设计场景**：四旋翼包缺数据手册支持的参数、电源预算、引脚级证据与验收阈值只标待核；没有凭记忆补任何数值，没有实施任何电机/飞行/烧录测试。

本分工到此有界收尾；main 仍负责统一核心契约、包资源、发布验证与全项目结论。
