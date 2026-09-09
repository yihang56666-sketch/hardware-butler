# Start Here

这页只解决一个问题：第一次打开这个工作区时，应该先做什么。

Hardware Butler 不是某一个 STM32 固件工程，而是一个硬件开发工作台。你把真实项目作为 `<project-root>` 交给它，它会先做安全分析、生成报告、判断下一步，而不是直接烧录或调试硬件。

## 先跑指南

先安装工作区：

```powershell
python -m pip install -e .
```

普通 GitHub checkout 会优先使用插件里自带的 `embeddedskills` 运行时镜像。如果你在精简包、外部后端或本地后端开发场景下看到 `doctor` 报 `embeddedskills.runtime` 不可用，再把 embeddedskills 放在根目录 `embeddedskills/`，或设置：

```powershell
$env:HW_BUTLER_EMBEDDEDSKILLS_ROOT="<path-to-embeddedskills>"
```

然后跑指南：

```powershell
python tools\hardware_butler.py guide --root <project-root>
```

`guide` 是只读命令。它不会扫描网络、不会烧录、不会写项目配置，只会打印当前项目根目录对应的第一天路径。

## 还没有真实板卡工程

可以先用仓库自带的最小 CubeMX/Keil fixture 体验流程，不需要连接硬件：

```powershell
python tools\hardware_butler.py guide --root tests\fixtures\cubemx-basic
python tools\hardware_butler.py doctor --root tests\fixtures\cubemx-basic --json
python tools\hardware_butler.py brain --root tests\fixtures\cubemx-basic --json
```

这个示例用于验证入口、项目识别、CubeMX/Keil 线索、证据健康度和安全提示。`doctor` 里出现 Keil、J-Link、OpenOCD、probe-rs、构建产物或台架 state 的 warning 是正常的，因为示例不要求安装这些外部工具，也不会执行真实硬件动作。

## 如果你想用 GUI

安装依赖：

```powershell
python -m pip install -e ".[ui]"
```

启动工作台：

```powershell
python gui\hardware_agent_ui.py
```

推荐使用方式：

1. 在顶部选择项目根目录。
2. 点击刷新。
3. 查看状态卡和流程表。
4. 点击推荐的安全动作。
5. 从报告表打开生成的项目档案、板卡画像、固件画像和构建计划。

GUI 适合不想记命令、想先看项目状态的人。

## 如果你想用 CLI

建议把真实项目放在本工作区内，或挂载到本工作区下。这样安全 runner 可以检查写入边界。

第一轮命令：

```powershell
python tools\hardware_butler.py doctor --root <project-root> --json
python tools\hardware_butler.py auto --root <project-root> --out-dir docs\inspections\<project-name> --json
python tools\hardware_butler.py next-step --root <project-root> --json
```

这三步的意义：

| 命令 | 作用 | 是否碰硬件 |
| --- | --- | --- |
| `doctor` | 检查 Python、必要文件、可选工具、项目后端和台架准备度。 | 否 |
| `auto` | 必要时运行安全入驻，生成报告和 `.hardware-butler\project-state.json`。 | 否 |
| `next-step` | 根据当前状态给出一个推荐的安全下一步。 | 否 |

## 你会得到什么

`auto` 之后重点看这些文件：

| 输出 | 用途 |
| --- | --- |
| `.hardware-butler\project-state.json` | 当前工作流状态和下一步动作。 |
| `docs\inspections\<project-name>\onboarding-manifest.json` | 入驻结果摘要。 |
| `docs\inspections\<project-name>\project-dossier.md` | 项目总览。 |
| `docs\inspections\<project-name>\board-profile.md` | 板卡和 MCU 线索。 |
| `docs\inspections\<project-name>\firmware-profile.md` | 固件结构线索。 |
| `docs\inspections\<project-name>\build-plan.md` | 安全构建发现计划。 |
| `docs\inspections\<project-name>\config-proposal.md` | `.embeddedskills/config.json` 提案。 |

## Safety Boundary

第一天命令只做这些事：

- 读取项目文件
- 生成本地报告
- 写本地状态文件
- 给出下一条安全命令

它们不会做这些事：

- 烧录、擦除、复位、在线调试
- 发送串口、CAN 或网络报文
- 扫描网络
- 绕过确认 token
- 静默写 `.embeddedskills/config.json`

需要台架准备时，先生成 runbook：

```powershell
python tools\hardware_butler.py bench-runbook --root <project-root> --action build-flash --json
```

真正执行硬件动作前，再生成动作计划：

```powershell
python tools\hardware_butler.py plan-action --root <project-root> --action flash --target <mcu> --artifact <firmware> --json
```

只有当你已经确认板卡身份、电源限制、探针身份、产物路径、擦除范围和恢复路径时，才继续后面的确认流程。

## 第一天到哪里算成功

先停在这里就很好：

1. `doctor` 没有 required error。
2. `auto` 生成了 inspection 目录。
3. `next-step` 返回了一个安全建议。
4. 你知道项目识别出了哪个构建后端。
5. 你知道下一步是否会触碰真实硬件。

后续再看 [COMMANDS.md](COMMANDS.md) 选择具体任务命令。

想理解完整架构但不想读历史报告，继续看 [ARCHITECTURE_MAP.md](ARCHITECTURE_MAP.md)。

如果你的目标是把一块具体板子真正吃透，再继续走 [HARDWARE_UNDERSTANDING.md](HARDWARE_UNDERSTANDING.md)：它会把芯片资料、CubeMX 引脚、固件入口和台架安全串成一条证据链。
