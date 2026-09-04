# Project Portfolio Audit

| 项目 | 当前判断 | 已验证证据 | 仍需人工验收 |
| --- | --- | --- | --- |
| Hardware Butler | 非硬件路径完整，文档计数与 GUI 结构已核对 | `pytest tests/unit/ -q --no-cov`：739 passed、4 skipped；`ruff check tools/ tests/` 通过；`mypy tools/ --config-file mypy.ini` 对 72 个源文件通过 | 真实板卡、探针、编译器、供电和串口现场环境 |

## 本次核对记录

- 2026-09-05：实测单元测试为 739 passed、4 skipped，README 测试徽章从过时的 832 更新为实测结果。
- 2026-09-05：核对 `gui/hardware_agent_ui.py` 的 `addTab` 调用，GUI 为 13 个 tab，HR 指导书已同步。
- 2026-09-05：确认 `origin` 指向 `yihang56666-sketch/hardware-butler`；README 的当前仓库链接保持一致。
- 2026-09-05：主 README 与 HR 指导书更新后通过插件同步脚本检查，避免插件副本文档漂移。
