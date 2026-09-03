# Hardware Butler 硬件 Agent HR 面试指导书

## 一句话介绍

Hardware Butler 是一个安全优先的嵌入式开发助手，把一句话硬件需求编排成需求解析、芯片选择、资料搜集、CubeMX 配置、固件生成、构建、烧录、观测和目标验证的 9 阶段工作流。

## 技术与架构

- Python 3.10+，核心入口在 `tools/`；`embeddedskills/` 提供构建、烧录、串口/CAN/网络/终端等后端；`nextboard/` 负责硬件方案和 BOM 风险。
- 支持 STM32、ESP32、MSP430、AVR、Nordic、RISC-V、TI、Renesas、NXP、Microchip、Maxim 等厂商族，并将 GD32/CH32 映射到 STM32 兼容路径。
- LLM provider 支持 host-agent、Anthropic、OpenAI 和 local；HTTP 调用对 429/5xx/网络错误指数退避，认证和参数错误不重试。
- 行为验证按 expected regex/范围、expected text、频率测量、kind 关键词和 QEMU 仿真分层；真实烧录必须同时满足环境变量、确认 token、值域检查和产物校验。
- PyQt6 GUI 提供 12 个 tab，CLI 提供 36+ 子命令；插件副本可由同步脚本校验。

## 可演示路径

```powershell
cd D:\一些有用的项目\硬件agent
python -m pip install -e .
python tools\hardware_butler.py guide --root tests\fixtures\cubemx-basic
python tools\hardware_butler.py workflow-run --root tests\fixtures\cubemx-basic --mock --json
pytest tests/unit/ -q --no-cov
ruff check tools/ tests/
mypy tools/ --config-file mypy.ini
```

验证结果：ruff 通过，mypy 对 72 个源文件无问题，单元测试 739 通过、4 skipped。真实板卡、探针、编译器和供电环境不是当前环境可证明的范围。

## HR 常问与回答

**为什么要分 9 个阶段？** 每阶段有输入、产物和状态，失败可定位和恢复；把高风险烧录放在需求和构建之后，避免“直接操作硬件”。

**安全门控如何落地？** 默认 mock；切换真实 flash 需要显式环境变量和确认 token，并校验目标值、固件产物 hash 和操作审计，代码路径不能被普通输入绕过。

**没有板子怎么验证？** 用 CubeMX fixture 跑完整 mock workflow，用 QEMU 或 behavior-mock 验证观测信号，再把真实板卡日流程单独记录为 runbook。

**LLM 在哪里发挥作用？** LLM 负责把自然语言转成结构化意图和固件计划；执行器、门控和验证器仍由确定性代码掌控，避免模型直接获得硬件副作用权限。

**目前限制是什么？** 非硬件路径已完成并回归；真实板卡的 probe、编译器版本、供电和串口环境仍需现场验证，不能声称已经完成真实硬件闭环。

## 下一步

按 `docs/REAL_BOARD_DAY_RUNBOOK.md` 完成一次真实板卡日演练，并将板卡型号、探针、固件 hash 和观测日志归档。
