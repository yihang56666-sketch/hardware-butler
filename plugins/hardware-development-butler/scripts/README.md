# Hardware Butler

[![CI](https://github.com/yihang56666-sketch/NextBoard/actions/workflows/ci.yml/badge.svg)](https://github.com/yihang56666-sketch/NextBoard/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

A safety-first embedded hardware copilot that turns board evidence, CubeMX projects, firmware plans, and bench bring-up into clear, gated next steps.

这是一个面向嵌入式硬件开发的工作区容器，不是单一固件工程。它把项目扫描、CubeMX/构建识别、芯片资料整理、固件补丁规划、台架预检和安全门控放在同一个工作流里。

目标不是一上来就替你烧录板子，而是先安全地回答三个问题：

1. 这个项目是什么？
2. 现在可以安全做什么？
3. 下一步如果要碰真实硬件，需要哪些证据和确认？

## Start Here

推荐以源码工作区方式使用：

```powershell
git clone https://github.com/yihang56666-sketch/NextBoard.git
cd NextBoard
python -m pip install -e .
```

最短路径是先让 CLI 打印一页启动指南：

```powershell
python tools\hardware_butler.py guide --root <project-root>
```

还没有真实板卡工程也可以先跑内置示例，不需要硬件：

```powershell
python tools\hardware_butler.py guide --root tests\fixtures\cubemx-basic
python tools\hardware_butler.py doctor --root tests\fixtures\cubemx-basic --json
```

这个 fixture 是一个最小 CubeMX/Keil 项目。`doctor` 可能提示 Keil、J-Link、OpenOCD、probe-rs 或构建产物缺失，这是预期的可选工具/台架 warning；只要没有 required error，就足够体验第一天路径。

如果你喜欢 GUI：

```powershell
python -m pip install -e ".[ui]"
python gui\hardware_agent_ui.py
```

如果你喜欢命令行：

```powershell
python tools\hardware_butler.py doctor --root <project-root> --json
python tools\hardware_butler.py auto --root <project-root> --out-dir docs\inspections\<project-name> --json
python tools\hardware_butler.py next-step --root <project-root> --json
```

第一天只需要跑到 `next-step` 能给出一个安全建议为止。详细教程见 [docs/START_HERE.md](docs/START_HERE.md)。

想先理解整体结构，可以看一页版 [docs/ARCHITECTURE_MAP.md](docs/ARCHITECTURE_MAP.md)。
安装方式和 runtime 选择见 [docs/INSTALL.md](docs/INSTALL.md)。
想把一块板子从资料、CubeMX、固件到台架安全完整理解，走 [docs/HARDWARE_UNDERSTANDING.md](docs/HARDWARE_UNDERSTANDING.md)。

## One-Command Workflow (P3)

完整 9 阶段自动化工作流：需求解析 → 芯片选型 → 资料拉取 → CubeMX 配置 → 固件代码生成 → 构建 → 烧录 → 调试观测 → 目标验证。默认 mock 模式不碰硬件；接板子后设 `HARDWARE_BUTLER_ENABLE_REAL_FLASH=1` 切真实模式。

```powershell
# Mock 模式（不碰硬件，使用内置 fixture）
python tools\hardware_butler.py workflow-run \
  --root tests\fixtures\cubemx-basic \
  --intent develop-feature --goal "LED blink on PD12" \
  --feature led-blink --pin PD12 --function gpio-output --json

# Real 模式（接板子后）
set HARDWARE_BUTLER_ENABLE_REAL_FLASH=1
python tools\hardware_butler.py workflow-run \
  --root <project> --intent develop-feature --goal "LED blink" \
  --feature led-blink --pin PD12 --function gpio-output \
  --part STM32F407VGT6 --probe stlink-v3 --json
```

开源依赖（可选，装了就能切真实硬件路径）：

| 工具 | 用途 | 安装 |
|---|---|---|
| PlatformIO | 跨厂商构建（STM32/ESP32/TI/AVR/RISC-V，600+ board） | `pip install platformio` |
| probe-rs | 跨厂商烧录 + RTT 调试（Cortex-M + ESP32 + RP2040 + Nordic） | `cargo install probe-rs` 或下载二进制 |
| pyserial | 串口观测 | `pip install pyserial` |

工作流检测到这些工具时优先用它们；没装时降级到 adapter 原生命令（cmake/gcc、pyOCD、JLink 等）。详见 [docs/HANDOFF.md](docs/HANDOFF.md) 第 14 节。

## What This Is

这个工作区分成三块：

| 区域 | 负责什么 |
| --- | --- |
| `tools/` | 主 CLI、项目扫描、资料处理、安全门控、报告生成。 |
| `embeddedskills/` | Keil/GCC/EIDE 构建，J-Link/OpenOCD/probe-rs，串口、CAN、网络和 workflow 后端。 |
| `nextboard/` | 硬件方案、器件选型、BOM 风险、PCB/原理图约束、评审和报告。 |

根目录是容器。真实 STM32/CubeMX/Keil/CMake 项目应作为 `<project-root>` 放在这个工作区内或挂载进来，再让工具分析。

## Golden Path

没有真实工程时，先把 `<project-root>` 换成 `tests\fixtures\cubemx-basic` 熟悉流程。这个示例不会触碰硬件。

1. 打印启动指南：

```powershell
python tools\hardware_butler.py guide --root <project-root>
```

2. 检查环境和项目边界：

```powershell
python tools\hardware_butler.py doctor --root <project-root> --json
```

3. 运行安全自动入驻：

```powershell
python tools\hardware_butler.py auto --root <project-root> --out-dir docs\inspections\<project-name> --json
```

4. 查看下一步：

```powershell
python tools\hardware_butler.py next-step --root <project-root> --json
```

5. 需要台架准备时，先生成不触碰硬件的 runbook：

```powershell
python tools\hardware_butler.py bench-runbook --root <project-root> --action build-flash --json
```

完整命令速查见 [docs/COMMANDS.md](docs/COMMANDS.md)。

## Safety Model

默认安全命令只允许本地发现、报告生成、dry-run、状态汇总和推荐动作。它们不会：

- build、flash、erase、reset 或进入在线调试
- 发送串口/CAN/网络报文
- 扫描网络
- 绕过硬件动作确认 token
- 写入 `.embeddedskills/config.json`，除非命令明确要求 `--write --confirm-write`

真实 `flash/debug/observe` 仍是 `planned-gated`。在完成具体后端的板级验证前，物理烧录、擦除、复位、在线调试和长时间观测都必须经过计划、预检、确认 token、设备身份、电压电流证据、产物 hash 和回滚记录。

## Documentation Map

| 文档 | 用途 |
| --- | --- |
| [docs/BEGINNER_GUIDE.md](docs/BEGINNER_GUIDE.md) | 5 分钟体验、真实项目第一轮命令和硬件前置安全底线。 |
| [docs/START_HERE.md](docs/START_HERE.md) | 第一天怎么跑，适合新接触项目时阅读。 |
| [docs/INSTALL.md](docs/INSTALL.md) | 源码工作区、editable install 和 embeddedskills runtime 选择。 |
| [docs/ARCHITECTURE_MAP.md](docs/ARCHITECTURE_MAP.md) | 一页理解入口、证据层、计划层、执行后端和安全网络。 |
| [docs/HARDWARE_UNDERSTANDING.md](docs/HARDWARE_UNDERSTANDING.md) | 从本地证据、芯片资料、CubeMX、固件计划到台架动作的硬件理解闭环。 |
| [docs/COMMANDS.md](docs/COMMANDS.md) | 按工作流分组的命令速查。 |
| [docs/README.md](docs/README.md) | 文档目录和历史材料索引。 |
| [CHANGELOG.md](CHANGELOG.md) | 版本变化和首发范围。 |
| [docs/WORKBENCH_TUTORIAL.md](docs/WORKBENCH_TUTORIAL.md) | GUI 工作台教程。 |
| [docs/AUTO_WORKFLOW_GUI.md](docs/AUTO_WORKFLOW_GUI.md) | `auto` / `next-step` 安全自动流程说明。 |
| [docs/WORKBENCH_FEATURE_COVERAGE.md](docs/WORKBENCH_FEATURE_COVERAGE.md) | GUI 已接入能力和仍需 CLI 的能力。 |

## Core Commands

```powershell
python tools\hardware_butler.py guide --root <project-root>
python tools\hardware_butler.py capabilities --json
python tools\hardware_butler.py doctor --root <project-root> --json
python tools\hardware_butler.py auto --root <project-root> --json
python tools\hardware_butler.py next-step --root <project-root> --json
python tools\hardware_butler.py brain --root <project-root> --json
python tools\hardware_butler.py task --root <project-root> --intent prepare-bringup --json
```

## Verification

常用验证顺序：

```powershell
python tools\release_verify.py --profile quick
ruff check tools/ tests/
mypy tools/ --config-file mypy.ini
pytest tests/unit/ -v
python tests\validate_hardware_butler.py
```

发布前跑完整本地矩阵：

```powershell
python tools\release_verify.py
```

如果只改 CLI 或文档入口，优先跑：

```powershell
pytest tests\unit\test_hardware_butler_guide.py tests\unit\test_hardware_butler_cli_errors.py -v --no-cov
pytest tests\unit\test_plugin_sync.py -q --no-cov
```

## Packaged Plugin

Codex 插件目录：

```text
plugins/hardware-development-butler/
```

主源码改动后需要同步插件运行时：

```powershell
python tools\package_hardware_butler_plugin.py
python plugins\hardware-development-butler\scripts\validate_package.py
```

插件运行时包含 `tools/`、`embeddedskills/`、`nextboard/`、agent roles、docs 和 tests。

## Important Boundaries

- `embeddedskills/` 保留独立 `.git`，不要删除或合并。若需纳入父仓库版本管理，先决定 submodule 策略；也可以用 `HW_BUTLER_EMBEDDEDSKILLS_ROOT` 指向外部 checkout。
- `embeddedskills` 以标准库为主，除串口/CAN 等必要依赖外不要随意加重依赖。
- 真实硬件动作必须遵守 `tools/hardware_action_executor.py` 和 `embeddedskills/safety_gate.py` 的确认门控。
- 修改插件可分发内容后，使用 `python tools\package_hardware_butler_plugin.py` 同步副本。
