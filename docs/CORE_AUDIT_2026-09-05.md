# Python Execution Core 审计交接 — 2026-09-05

## 结论与停止边界

- 仓库：`<repo-root>`；起点 `main` / `cf1cd9e754104eb8c2a1dbeeb027f76073f71478`。
- 报告文件日期遵循委托；实际收尾日期为 2026-09-06（Asia/Shanghai）。主线程要求有界收尾后，没有再扩大问题发现或生产修复范围。
- 自有 Python 模块清单共 **70 份 / 20,669 基线行**：**52 份完整逐行阅读，1 份部分阅读，17 份未完整阅读**。计入逐行阅读的基线行共 14,381；不是“70 份全部审完”，更不是硬件覆盖率。
- 5 组 TDD 批次共新增 58 个参数化回归实例，均先观察旧代码 RED，再修改根因；终检定向集合 **99 passed, 1 skipped**。
- 当前没有已新增 RED、却尚未完成根因修复的回归用例。后文列出的静态候选和未覆盖模块尚未验证，不能当作已修复或已排除。
- 未运行真实硬件、烧录、探针调试；未打开 real backend，未绕过 token/env 门，未调用付费 LLM，未向外上传项目，未提交、推送、切分支或改凭据。
- 插件镜像、全仓 tests 和指南由主线程继续集成；本子任务没有更新生成镜像。

## 产品与写范围

开始前完整阅读根 `AGENTS.md`、`SECURITY.md`、`pyproject.toml`、`README.md`。以默认离线/计划与 mock、受控本地执行和实机安全门为边界；测试成功不代表任一真实板卡可安全执行。

生产改动仅限现有 `tools/` 核心模块；测试改动仅限 `tests/unit/`；额外报告为本文件。明确排除 `tools/package_hardware_butler_plugin.py`、`tools/install_plugin_sync_hook.py`、`plugins/`、`gui/`、`nextboard/`、嵌套 `embeddedskills/`。后续只按用户补充授权将命令日志放入 `output/readiness/`。

收尾时 GUI/NextBoard 等有其他执行者的并发工作区改动，不属于此补丁，未复原或清理。未触碰用户未跟踪的 `docs/项目概述与项目计划书.docx`。

## 逐份阅读清单

行数来自基线提交；修复后行数会变。完整表示有分块全文阅读记录，不表示该模块没有剩余缺陷。搜索定位、测试间接导入不计入完整审查。`document_search_api.py` 停在第 191 行后按要求收尾。

| 模块 | 基线行数 | 阅读边界 |
| --- | ---: | --- |
| `tools/__init__.py` | 17 | 完整逐行阅读 |
| `tools/backend_detector.py` | 201 | 完整逐行阅读 |
| `tools/backends/__init__.py` | 10 | 完整逐行阅读 |
| `tools/backends/chip_manual_rag.py` | 184 | 完整逐行阅读 |
| `tools/backends/langchain_agent.py` | 235 | 完整逐行阅读 |
| `tools/backends/pyocd_backend.py` | 279 | 完整逐行阅读 |
| `tools/bench_runbook.py` | 561 | 完整逐行阅读 |
| `tools/build_log_classifier.py` | 144 | 完整逐行阅读 |
| `tools/build_plan.py` | 343 | 完整逐行阅读 |
| `tools/build_workbench_exe.py` | 104 | 完整逐行阅读 |
| `tools/butler_cli.py` | 125 | 完整逐行阅读 |
| `tools/butler_types.py` | 146 | 完整逐行阅读 |
| `tools/cache.py` | 127 | 完整逐行阅读 |
| `tools/chip_dossier.py` | 779 | 完整逐行阅读 |
| `tools/command_runner.py` | 484 | 完整逐行阅读 |
| `tools/config.py` | 132 | 完整逐行阅读 |
| `tools/config_plan.py` | 25 | 完整逐行阅读 |
| `tools/config_proposal.py` | 219 | 完整逐行阅读 |
| `tools/cube_detect.py` | 242 | 完整逐行阅读 |
| `tools/cubemx_config_advisor.py` | 746 | 完整逐行阅读 |
| `tools/cubemx_ioc_summary.py` | 307 | 完整逐行阅读 |
| `tools/debug_logbook.py` | 61 | 完整逐行阅读 |
| `tools/document_providers.py` | 118 | 完整逐行阅读 |
| `tools/document_search_api.py` | 242 | 部分：1–191；192–242 未读 |
| `tools/evidence_index.py` | 200 | 未完整阅读；不计入审完 |
| `tools/evidence_qa.py` | 407 | 未完整阅读；不计入审完 |
| `tools/firmware_code_patcher.py` | 1086 | 未完整阅读；不计入审完 |
| `tools/firmware_intent_planner.py` | 286 | 未完整阅读；不计入审完 |
| `tools/firmware_project_scaffold.py` | 499 | 未完整阅读；不计入审完 |
| `tools/github_launch_audit.py` | 582 | 未完整阅读；不计入审完 |
| `tools/hardware_action_audit.py` | 223 | 完整逐行阅读 |
| `tools/hardware_action_executor.py` | 623 | 完整逐行阅读 |
| `tools/hardware_action_plan.py` | 634 | 完整逐行阅读 |
| `tools/hardware_butler.py` | 1082 | 未完整阅读；不计入审完 |
| `tools/hardware_butler_inspect.py` | 286 | 未完整阅读；不计入审完 |
| `tools/hardware_risk.py` | 199 | 未完整阅读；不计入审完 |
| `tools/llm_client.py` | 352 | 完整逐行阅读 |
| `tools/llm_codegen.py` | 199 | 完整逐行阅读 |
| `tools/llm_config.py` | 106 | 完整逐行阅读 |
| `tools/logger.py` | 102 | 未完整阅读；不计入审完 |
| `tools/manual_summarizer.py` | 210 | 未完整阅读；不计入审完 |
| `tools/pin_capabilities.py` | 252 | 未完整阅读；不计入审完 |
| `tools/product_doctor.py` | 699 | 完整逐行阅读 |
| `tools/project_brain.py` | 308 | 未完整阅读；不计入审完 |
| `tools/project_scanner.py` | 212 | 未完整阅读；不计入审完 |
| `tools/project_workflow.py` | 419 | 完整逐行阅读 |
| `tools/qemu_behavior_check.py` | 188 | 未完整阅读；不计入审完 |
| `tools/real_preflight.py` | 248 | 完整逐行阅读 |
| `tools/release_verify.py` | 221 | 未完整阅读；不计入审完 |
| `tools/research.py` | 117 | 未完整阅读；不计入审完 |
| `tools/runtime_context.py` | 142 | 完整逐行阅读 |
| `tools/safe_io.py` | 86 | 完整逐行阅读 |
| `tools/task_workflows.py` | 246 | 完整逐行阅读 |
| `tools/vendor_adapters/__init__.py` | 439 | 完整逐行阅读 |
| `tools/vendor_adapters/avr.py` | 97 | 完整逐行阅读 |
| `tools/vendor_adapters/c2000.py` | 107 | 完整逐行阅读 |
| `tools/vendor_adapters/esp32.py` | 112 | 完整逐行阅读 |
| `tools/vendor_adapters/imxrt.py` | 165 | 完整逐行阅读 |
| `tools/vendor_adapters/lpc.py` | 155 | 完整逐行阅读 |
| `tools/vendor_adapters/max32.py` | 144 | 完整逐行阅读 |
| `tools/vendor_adapters/msp430.py` | 113 | 完整逐行阅读 |
| `tools/vendor_adapters/nordic.py` | 119 | 完整逐行阅读 |
| `tools/vendor_adapters/pic32.py` | 122 | 完整逐行阅读 |
| `tools/vendor_adapters/ra.py` | 142 | 完整逐行阅读 |
| `tools/vendor_adapters/riscv.py` | 126 | 完整逐行阅读 |
| `tools/vendor_adapters/rx.py` | 129 | 完整逐行阅读 |
| `tools/vendor_adapters/stm32.py` | 238 | 完整逐行阅读 |
| `tools/vendor_adapters/tiva.py` | 133 | 完整逐行阅读 |
| `tools/web_fetcher.py` | 142 | 完整逐行阅读 |
| `tools/workflow_runner.py` | 2141 | 完整逐行阅读 |

两个排除的打包/安装工具不在 70 份清单内；mypy 报告的 **72 source files** 包含它们，仅是静态检查文件数，不能替代审查覆盖。

## 已证实问题与根因修复

### 1. 安全写入的固定临时文件逃逸与并发冲突

- 证据：预先把 `.state.json.tmp` 做成另一文件的硬链接，旧代码覆盖无关文件；两个写入者共用临时文件会覆盖/丢失彼此的结果。
- 修复：文本/二进制写入均使用独占创建的随机 `NamedTemporaryFile`，写完 flush/fsync、关闭后原子 replace，finally 清理；没有把“唯一临时文件”宣称为跨进程业务状态合并。
- 回归：`test_safe_write_preserves_preexisting_temp_hardlink`、`test_concurrent_safe_writes_have_independent_temporary_files`，各覆盖文本和 bytes。
- 边界：Windows 下两个 replace 本身仍可产生共享冲突；测试在双方完成写入后串行执行底层 rename，只隔离验证临时文件复用根因。未实现 OS 重试、父目录竞态彻底消除或事务合并。

### 2. 确认绑定可被可变 plan、root/backend 和解释器替换削弱

- 证据：清除 plan 的风险布尔字段能影响确认要求；确认后改工作区、升级 backend；只验证脚本而不验证 Python 解释器。
- 修复：确认需求由规范 action 集合决定；root 纳入 TOKEN_FIELDS 且执行 root 必须匹配确认记录；拒绝未经同一确认绑定的 backend 升级（仅保留 fake/preflight 安全降级）；runbook 要求绝对且等于当前 `sys.executable` 的解释器。
- 回归：`test_core_action_boundaries.py` 的 5 个实例，包含修改外层 root 和同时修改记录 root 两种路径。
- 兼容性：本核心旧版预备确认 token 需要重新生成；没有修改嵌套 embeddedskills 的 token 格式。

### 3. 一次性 token 仅线程锁导致跨进程双消费

- 证据：两个真实本地 Python 子进程在旧锁下同时得到 `ok`。
- 修复：日志 append 与 token 检查/消费共用线程锁加持久锁文件；Windows 用 msvcrt，POSIX 用 flock。平台判断使用 `sys.platform`，让 mypy 正确识别平台分支。
- 回归：`test_consume_token_is_atomic_across_processes`；本机实际执行两个进程，没有硬件调用。
- 边界：Windows 分支已执行；POSIX 分支本次未运行。未宣称抗本地有写权限攻击者篡改日志/锁文件。

### 4. workflow 等待/恢复和实际失败被记为成功

- 证据：等待 host failure-analysis 的 resume 会重跑失败阶段并花掉 attempts；blocked-needs-input 消耗重试预算；修复 pin 等只改 context，下一轮 codegen 仍用旧 parsed_requirements；firmware 部分/无写入或 native build error/timeout 仍可推进。
- 修复：pending 时原地阻断并保留状态；阻断不扣失败尝试预算；同步接受的修复字段到解析证据；不完整固件写入立即失败；已运行 native adapter build 出错/超时立即失败，不再称 completed。
- 回归：`test_core_workflow_integrity.py` 中等待、状态同步、firmware 写失败、native error/timeout 用例。
- 不扩大修复：embeddedskills build fallback、scaffold 结果传播、切换 part 后的上游阶段失效仍列入候选，不因本修复而推定已解决。

### 5. workflow 环境变量加自签 goal token 绕过统一物理执行门

- 证据：旧 flash/observe 分支在设置环境变量后直接运行 adapter/embeddedskills 物理命令，未走受审 executor 的授权约束。
- 修复：移除 workflow 的裸 flash fallback 链和裸 serial/RTT 调用；真实请求明确返回 `blocked-needs-input` / `blocked-real-backend-not-enabled`，要求 reviewed executor plan 和对应 backend bench validation；保留原有 value/artifact-hash 检查；默认 mock 路径不升级硬件权限。
- 回归：`test_environment_opt_in_alone_cannot_dispatch_physical_flash`、`test_environment_opt_in_alone_cannot_dispatch_physical_observe`；mock 断言没有底层调用。
- 集成注意：这是有意收紧契约，不是实机功能已完成。四个旧 flash 模拟分支和一个旧端到端“切 env 即实机成功”断言已改为阻断/no-call；不得为使演示通过而恢复裸执行。主线程指南需同步此说明。

### 6. vendor 命令注入、假构建和用户脚本覆盖

- 证据：J-Link target 可嵌入换行/命令；8 个 adapter 的 OpenOCD Tcl 字符串直接拼 firmware path；STM32 以 gcc --version 或仅 CMake configure 当构建；PlatformIO 覆盖或删除用户自有 pio_freertos.py。
- 修复：J-Link target 字符白名单；统一 OpenOCD helper 拒绝 Tcl 控制/插值字符、括起带空格路径并规范分隔符；STM32 只对有 CMakeCache 的目录执行 cmake --build，或对真实 Makefile 执行 make，其余返回计划态空命令；只更新/删除带生成器所有权标记的脚本，冲突时在写 ini 前拒绝。
- 回归：`test_core_vendor_boundaries.py` 共 40 个实例；旧 STM32 命令测试补上真正构建元数据与 mocked 工具发现。
- 边界：只验证字符串、路径和本地文件所有权；未运行 J-Link/OpenOCD/PlatformIO 的实机命令，不保证 14 个 vendor family 的固件生态已验证。

## RED / GREEN 运行证据

以下为前段实际 TDD 运行记录。早期定向运行使用单次 runner，原始 stdout 留在会话中而非日志文件；这里保留已记录的测试入口、临时目录与实际结果，不伪造旧 stdout。完整终检 argv、stdout、stderr 和退出码已单独保存（见末节）。

公共入口：`.venv/Scripts/python.exe -m pytest`，各次使用 `-q --no-cov`；下表列测试选择与 basetemp。UTF-8/traceback 显示选项不影响 RED/GREEN 判定。

| 批次 | RED 测试选择 / basetemp | 旧代码结果 | GREEN 测试选择 / basetemp | 修复后结果 |
| --- | --- | --- | --- | --- |
| IO | `tests/unit/test_safe_io.py -k "preexisting_temp_hardlink or independent_temporary_files" --basetemp=tests/unit/.tmp-core-audit-red-io` | 退出 1；4 failed, 10 deselected | `tests/unit/test_safe_io.py --basetemp=tests/unit/.tmp-core-audit-green-io` | 退出 0；13 passed, 1 skipped |
| action | `tests/unit/test_core_action_boundaries.py --basetemp=tests/unit/.tmp-core-audit-red-actions` | 退出 1；5 failed | `tests/unit/test_core_action_boundaries.py tests/unit/test_value_safety_paths.py tests/unit/test_phase16_audit_fixes.py --basetemp=tests/unit/.tmp-core-audit-green-actions` | 退出 0；22 passed |
| ledger | `tests/unit/test_hardware_action_audit_atomicity.py -k across_processes --basetemp=tests/unit/.tmp-core-audit-red-ledger` | 退出 1；1 failed，两个进程均返回 ok | `tests/unit/test_hardware_action_audit_atomicity.py tests/unit/test_core_action_boundaries.py --basetemp=tests/unit/.tmp-core-audit-green-ledger` | 退出 0；11 passed |
| workflow | `tests/unit/test_core_workflow_integrity.py --basetemp=tests/unit/.tmp-core-audit-red-workflow` | 退出 1；8 failed | `tests/unit/test_core_workflow_integrity.py --basetemp=tests/unit/.tmp-core-audit-green-workflow` | 退出 0；8 passed |
| vendor | `tests/unit/test_core_vendor_boundaries.py --basetemp=tests/unit/.tmp-core-audit-red-vendor`（-X utf8、--tb=no） | 退出 1；40 failed | `tests/unit/test_core_vendor_boundaries.py tests/unit/test_workflow_runner.py --basetemp=tests/unit/.tmp-core-audit-green-vendor`（-X utf8、--tb=short） | 退出 0；55 passed，4.32s |

IO 首次修复后曾暴露 Windows 并发 rename 的 WinError 5；测试将 rename 序列化但保留双方同时写入的屏障后才得到上述 GREEN，没有声称修好了 Windows rename 冲突。

## Baseline 与最终命令终态

所有命令 cwd 均为仓库根。未使用 `--run-hardware`。

### Baseline（改动前）

| 完整命令 | 退出码 / 实际结果 |
| --- | --- |
| `.venv/Scripts/python.exe -m pytest tests/unit/ -q --no-cov --basetemp=tests/unit/.tmp-core-audit-baseline` | 0；739 passed, 4 skipped，48.06s |
| `.venv/Scripts/ruff.exe check tools/ tests/` | 0；All checks passed! |
| `.venv/Scripts/python.exe -m mypy tools/ --config-file mypy.ini` | 0；Success: no issues found in 72 source files |

### 收尾（新修复与旧契约断言对齐后）

| 完整命令 | 退出码 / 实际结果 |
| --- | --- |
| `.venv/Scripts/python.exe -X utf8 -m pytest tests/unit/test_core_action_boundaries.py tests/unit/test_core_workflow_integrity.py tests/unit/test_core_vendor_boundaries.py tests/unit/test_safe_io.py tests/unit/test_hardware_action_audit_atomicity.py tests/unit/test_workflow_real_backends.py tests/unit/test_workflow_e2e_mock.py tests/unit/test_vendor_adapters.py -q --no-cov --tb=short --basetemp=tests/unit/.tmp-core-audit-finish-targeted` | 0；99 passed, 1 skipped，3.98s |
| `.venv/Scripts/python.exe -X utf8 -m pytest tests/unit/ --ignore=tests/unit/test_plugin_sync.py -q --no-cov --tb=short --basetemp=tests/unit/.tmp-core-audit-finish-unit` | 0；711 passed, 4 skipped，27.78s |
| `.venv/Scripts/python.exe -X utf8 -m pytest tests/unit/test_plugin_sync.py -q --no-cov --tb=no --basetemp=tests/unit/.tmp-core-audit-finish-plugin` | 1；15 failed, 126 passed，0.24s；失败均为 15 个已改 tools 源文件与未再生成的镜像不一致 |
| `.venv/Scripts/ruff.exe check tools/ tests/` | 0；All checks passed! |
| `.venv/Scripts/python.exe -X utf8 -m mypy tools/ --config-file mypy.ini` | 0；Success: no issues found in 72 source files |
| `git diff --check -- tools/ tests/unit/` | 0；无输出 |

完整 unit 中间轮次也如实保留：round1 为 25 failed / 771 passed / 4 skipped（24.53s）；round2 为 21 failed / 831 passed / 4 skipped（27.26s）。随后修正 STM32 假构建契约与 6 个旧测试断言，最终非镜像单元集合如上通过。没有声称含镜像的全套当前通过。

初次收尾 ruff 因本子任务 basetemp 下的测试样本而报 19 个问题；清理已知临时目录后原命令通过，没有改宽 lint 配置。初次 mypy 的 4 条错误来自 POSIX flock 的 Windows 类型分支，已用 sys.platform 分支修正后通过。

并发工作区已有主线程 GUI/NextBoard 改动，终检总例数不是全部由本子任务增加。非镜像单元包含本地文件、真实 Python 子进程、mock、localhost HTTP stub 和可用本地工具冒烟；不能把它统称全部 mock。实机未验证；本机 QEMU 相关实际执行用例仍跳过。本轮按主线程收尾指令不再运行整个 `tests/`，全仓集成验证留主线程。

## 未覆盖与剩余风险

以下均为**未完成回归验证的候选/边界**，没有计入已修复问题数，也不以静态怀疑宣称漏洞已经复现：

1. LLM/network 错误传播：host 响应状态、重复 task/first-response 选择、成功 HTTP 的畸形 JSON/空内容、local provider 无 key 语义、bool("false") 和无效配置 shape；尚未新增对应 RED。
2. workflow 状态：embeddedskills build fallback 与 scaffold 错误是否仍可完成；part 修复后的 chip-selection/上游证据失效；requirement part 传播；verify_signal 的非有限数、缺失正则组和频率计算边界。
3. 文件与配置：safe_io 的祖先 symlink/TOCTOU、备份固定路径、完整状态的并发读改写；PIO staging 的删除同步与符号链接；畸形 config/doctor 的错误状态；chip dossier 特殊 part/同名下载路径；CubeMX 字段换行、pin 格式及同一 I2C pin 的验证尚未完成。
4. 进程/审计：command_runner spawn OSError 与 timeout bytes、结果 status 传播、相对参数 cwd、大小写文件系统差异、损坏 audit 行/锁文件路径、workflow goal token 的进一步作用域审查。
5. 网络策略：web_fetcher/资料来源支持本地 file URL 与重定向/内网请求的边界，尚未有经过回归验证的统一策略。本次未联网下载或上传项目。
6. 平台/硬件：POSIX 文件锁未实跑；本地有写权限的攻击者仍可篡改状态；实际编译/烧录工具、J-Link/OpenOCD target 配置、探针选择、14-family 固件兼容性与恢复流程均需专门 bench 验证。统一安全门保持关闭。
7. 表中 17 个未完整阅读模块和 document_search_api 余下 51 行均未完成全文审计；完整阅读的 52 份也不等同“所有路径都用测试证明正确”。

## 本子任务全部修改路径

共 15 个生产模块、8 个单元测试文件（其中 3 个新增）、本报告；日志不作为源码补丁。

- `tools/bench_runbook.py`
- `tools/hardware_action_audit.py`
- `tools/hardware_action_executor.py`
- `tools/hardware_action_plan.py`
- `tools/safe_io.py`
- `tools/vendor_adapters/__init__.py`
- `tools/vendor_adapters/imxrt.py`
- `tools/vendor_adapters/lpc.py`
- `tools/vendor_adapters/max32.py`
- `tools/vendor_adapters/ra.py`
- `tools/vendor_adapters/riscv.py`
- `tools/vendor_adapters/rx.py`
- `tools/vendor_adapters/stm32.py`
- `tools/vendor_adapters/tiva.py`
- `tools/workflow_runner.py`
- `tests/unit/test_core_action_boundaries.py`
- `tests/unit/test_core_vendor_boundaries.py`
- `tests/unit/test_core_workflow_integrity.py`
- `tests/unit/test_hardware_action_audit_atomicity.py`
- `tests/unit/test_safe_io.py`
- `tests/unit/test_vendor_adapters.py`
- `tests/unit/test_workflow_e2e_mock.py`
- `tests/unit/test_workflow_real_backends.py`
- `docs/CORE_AUDIT_2026-09-05.md`

## 日志、清理与主线程下一步

- 完整保存的命令 stdout/stderr、argv、退出码：`output/readiness/core-audit-2026-09-05.log.tmp`。
- 精确逐文件基线行数/阅读区间：`output/readiness/core-audit-2026-09-05-inventory.json.tmp`。
- 清理前验证过的绝对路径与结果：`output/readiness/core-audit-2026-09-05-cleanup.json.tmp`。
- 当前 .gitignore 未整体忽略 output/readiness，因此日志使用现有 `*.tmp` 规则忽略；已用 git check-ignore 验证，不修改用户 ignore/config。
- 已将 15 个明确属于本子任务的 `tests/unit/.tmp-core-audit-*` 目录逐个 lstat/realpath，确认是 tests/unit 的直接子目录且非根 symlink，再用 Node 原生 FS rm 安全删除；没有前缀泛删。指定的 finish-plugin 目录未生成，未删除其他路径。日志在清理前保存。
- 主线程：复核这 24 个源码/报告路径；同步 15 个 tools 生成镜像；更新“设置 env 不足以启用物理执行”的指南；再执行镜像检查与全仓验证。没有待后台运行的审查/测试进程。
