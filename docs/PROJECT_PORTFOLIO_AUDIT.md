# Project Portfolio Audit

| 项目 | 当前判断 | 已验证证据 | 仍需人工验收 |
| --- | --- | --- | --- |
| Hardware Butler | 非硬件路径完整，插件镜像已同步 | `pytest -q -p no:embedded -W error`：1013 passed、12 skipped；`ruff check .` 通过；`mypy tools/ --config-file mypy.ini` 对 72 个源文件通过；插件校验 4/4 通过 | 真实板卡、探针、编译器、供电和串口现场环境 |

## 本次核对记录

- 2026-09-06：重跑完整单元集合为 908 passed、6 skipped；README 徽章与 HR 指导书同步，旧轮次 739/4 仅作为历史记录保留在审计文档中。
- 2026-09-07：修复 GUI 启动测试读取子进程输出缺少 `errors="replace"` 的编码鲁棒性问题；随后发现并修复 `command_runner.run_command` 在正常完成与超时路径的 stdout/stderr 管道泄漏，新增两个回归测试；完整套件在 `-W error` 下重跑通过。插件镜像重新打包并通过 4/4 校验。
- 2026-09-07：清理公开 embeddedskills 文档与示例配置中的硬编码安装路径；Wireshark、Keil、VS Code 改为环境变量驱动发现；打包器新增机器路径半拷贝防护和正则误报回归测试。完整测试 1015 passed、12 skipped，ruff 与 mypy 通过，插件校验 4/4。
- 2026-09-07：新增测试契约自指防护后，完整测试刷新为 1017 passed、12 skipped；文档口径同步，未重复执行硬件实板流程。
- 2026-09-05：核对 `gui/hardware_agent_ui.py` 的 `addTab` 调用，GUI 为 13 个 tab，HR 指导书已同步。
- 2026-09-05：确认 `origin` 指向 `yihang56666-sketch/hardware-butler`；README 的当前仓库链接保持一致。
- 2026-09-05：主 README 与 HR 指导书更新后通过插件同步脚本检查，避免插件副本文档漂移。
- 2026-09-11：完整测试口径刷新为 1013 passed、12 skipped；README、HR 指导书与插件镜像同步，真实板卡流程仍未执行。
