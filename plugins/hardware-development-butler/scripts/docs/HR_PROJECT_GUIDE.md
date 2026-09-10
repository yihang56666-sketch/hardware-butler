# Hardware Butler 硬件 Agent HR 面试指导书

更新：2026-09-30。测试口径：**1017 passed / 12 skipped**。真实板卡仍未在本材料中证明。

## 一句话介绍

Hardware Butler 是安全优先的嵌入式开发助手：把一句话硬件需求编排成需求解析→芯片选型→资料→CubeMX→固件→构建→烧录→观测→验证的 9 阶段工作流。

## 30 秒说法

> 我做的是嵌入式工作流 Agent。说「在 PD12 上让 LED 以 2Hz 闪烁」，它会走九个阶段；默认 mock 不碰硬件，真实烧录必须环境变量、确认 token、值域检查和固件 hash 同时通过。LLM 只产结构化意图，执行器和门控是确定性代码。非硬件路径 1017 个单测回归通过。

## 架构怎么讲

| 区域 | 职责 |
|---|---|
| `tools/` | CLI、9 阶段状态机、安全门控、LLM client、14 厂商 adapter |
| `embeddedskills/` | 独立仓的构建/烧录/串口/CAN 后端（clone 后可能无此目录，用 plugins 镜像） |
| `nextboard/` | 方案选型、BOM 风险、评审门 |
| `gui/` | PyQt6 13 tab |
| `plugins/` | Codex 插件镜像 + 同步校验 |

**状态机**：`.hardware-butler/workflow-state.json` 可 resume；每阶段有输入/产物/状态；`MAX_STAGE_ATTEMPTS=3`；optimize-loop 最多 3 轮。

## 安全模型（必考，要讲透）

1. **默认 mock / sim**，真实后端 `blocked-real-backend-not-enabled`  
2. **`HARDWARE_BUTLER_ENABLE_REAL_FLASH=1`** 显式 opt-in  
3. **确认 token**：`hwc1-` + sha256(计划字段)——是**完整性绑定**（防字段被改），**不是**密码学人工授权（SECURITY.md 已诚实披露）  
4. **值域防呆**：电压 0–6V、电流 warn  
5. **artifact hash** + 一次性 token 跨进程原子消费 + 审计日志  

话术：「门控保证的是：普通输入不能直接产生硬件副作用；token 保证的是计划字段不被静默篡改。人工知情授权仍依赖操作者，我不把它说成密码学签字。」

## 五个可深挖技术点

1. **九阶段状态机与 resume**：失败可定位到阶段，不从头重跑。  
2. **14 厂商 adapter**：STM32/ESP32/MSP430/AVR/Nordic/RISC-V/TI/Renesas/NXP/PIC32/Maxim/i.MX RT/RX；GD32/CH32 映射 STM32 兼容路径。  
3. **5 层行为验证**：kind 关键词 → 频率测量 → expected_text → regex 捕获组 → 数值范围；再加 QEMU 可选仿真。  
4. **多 Provider LLM 工程化**：host-agent JSONL 桥 / Anthropic / OpenAI / local；429/5xx 指数退避；transient vs fatal 分类；codegen 显式 opt-in。  
5. **无板可验证**：CubeMX fixture 完整 mock e2e；真实板卡日单独 runbook。  

## 可演示路径

```powershell
python tools\hardware_butler.py guide --root tests\fixtures\cubemx-basic
python tools\hardware_butler.py workflow-run --root tests\fixtures\cubemx-basic --intent develop-feature --goal "LED blink on PD12" --feature led-blink --pin PD12 --function gpio-output --json
```

## HR 高频追问（含最难的）

**为什么分 9 阶段？**  
每阶段有输入/产物/状态；失败可定位可 resume；高风险烧录放在需求和构建之后。

**烧过真板吗？**  
**诚实：没有在本材料宣称完成真实硬件闭环。** 有完整 mock 回归与 `REAL_BOARD_DAY_RUNBOOK.md`。这是当前最大边界。

**LLM 会不会乱烧板子？**  
LLM 只产结构化意图/固件计划；执行器、门控、验证器是确定性代码。模型没有直接硬件副作用权限。

**没有板子怎么验证？**  
fixture + mock workflow + 行为验证分层；真板日流程单独记录。

**token 是不是人工确认？**  
不是。它是计划字段的完整性绑定（keyless SHA256）。SECURITY.md 明确区分「防篡改」≠「人工授权」。这是威胁建模上的诚实。

**embeddedskills 为什么 clone 后没有？**  
父仓把它当独立仓库维护；公开可用 `plugins/hardware-development-butler/scripts/embeddedskills/` 镜像。README 已写清。

**1017 个测试证明什么？**  
证明非硬件路径（编排、adapter、门控、LLM client、验证器）可回归；不证明探针/供电/真编译器环境。

**为什么 LLM 要 4 种 provider？**  
宿主可驱动（claude-code JSONL）、云 API、本地兼容端点；同一套 retry/分类错误策略。

## 限制（主动说）

- 真实板卡、探针、编译器、供电未在本材料证明  
- 频率测量启发式在真实串口噪声下可能有假阳/假阴  
- CI 主要 Windows matrix；POSIX 路径分支覆盖有限  

## 简历可用句

实现安全优先的嵌入式工作流 Agent Hardware Butler：9 阶段可 resume 编排、14 厂商族适配、5 层行为验证、多层硬件门控；LLM 仅产出结构化意图。非硬件路径 1017 单测、ruff/mypy 全绿。
