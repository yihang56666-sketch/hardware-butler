# Core Remaining Audit — 2026-09-06 有界交付

## 结论与停止点

- 按用户收尾指令停止新增调查及批次 C 修复。本轮只交付已经观察 RED 的 A/B 根因修复与必要相邻回归。
- 仓库：`<repo-root>`；基线提交：`cf1cd9e754104eb8c2a1dbeeb027f76073f71478`。没有创建分支、提交、推送或改凭据。
- 授权 16 个模块共 **5,676 基线行：16 份全文分块阅读，0 份部分阅读，0 份未读**。全文阅读不等于所有路径已验证。
- 修改 **9 个生产模块、3 个单测文件、此报告**。其余 7 个模块只读，不能称为已经回归验证或没有缺陷。
- 最终定向回归：**63 passed, 1 skipped（1.17s）**；范围 ruff 通过；mypy 检查 16 个输入文件通过；本任务范围 git diff --check 通过。
- A/B 新增 48 个实例，最终 47 通过、1 环境跳过。其中 **46 个失败实例**先在未修复代码观察 RED；另 1 个是从初次运行就通过的确认拒绝控制。这不是“46 个独立漏洞”。
- 当前没有本轮已复现、已加入测试却仍未修复的失败用例。符号链接用例因 Windows 权限跳过，不能算已验证。

## 授权与实际执行边界

使用 using-superpowers → systematic-debugging / writing-plans / TDD → verification-before-completion。按授权在同一工作目录执行，不开新 worktree/branch，不创建其他用户任务或派发远程 agent。

- 已完整读取根 `AGENTS.md`、`SECURITY.md`。前审报告 `docs/CORE_AUDIT_2026-09-05.md` 的 1–99、189–201 行覆盖范围表及未覆盖清单；其他节仅部分显示/搜索，不计该报告全文阅读。
- 未阅读用户未跟踪的 Word 私人文档；没有扫描真实项目资料来触发问答或 research。
- pytest 未启用 xdist，测试 worker=1；只运行 4 个定向测试文件。CLI 错误用例启动受控本地 Python 子进程，其余新增回归使用 tmp_path / mock。未运行编译器、QEMU、GDB、探针、烧录、真实硬件、账户服务或付费 API。
- 保持现有确认 token、confirm-write 与 real-backend 环境门；没有为测试打开硬件后端。execute-action 回归只 mock 执行器返回值来验证 CLI 退出码，不证明执行器/硬件已经通过测试。
- 原有 core patch、GUI、NextBoard、package/sync/release/github_launch_audit、插件镜像及嵌套 embeddedskills 均未修改。启动时其他任务已有的改动保持原样。
- 软件单测验证的是文件内容/软件状态契约，**不代表实际编译成功、固件时序正确、电气安全或板卡效果**。

## 逐文件真实阅读范围

行号是修改前基线；修改后行数会变化。完整来自逐段实际读取，包括 patcher 被显示截断后补读的 1044–1086 行。搜索命中、import、mypy 间接分析均不用于夸大阅读覆盖。

| 文件 | 基线已读区间 | 本轮处理与不完整处 |
| --- | --- | --- |
| `<repo-root>/tools/evidence_index.py` | 1–200（完整） | 已改：过滤项目外索引条目及扩展证据；已跑越界回归。来源质量推断/完整 schema 未验证。 |
| `<repo-root>/tools/evidence_qa.py` | 1–407（完整） | 已改：文本、IOC 摘要和引用消费前做项目内文件检查；绝对路径/../ 回归通过。符号链接实测跳过。 |
| `<repo-root>/tools/firmware_code_patcher.py` | 1–1086（完整） | 已改：精确目标白名单、全批路径预检、当前文本 SHA-256 对比预览；不保证跨文件事务/并发锁。 |
| `<repo-root>/tools/firmware_intent_planner.py` | 1–286（完整） | 未改：全文静态阅读；本轮未新增 HAL handle、RTOS 计划与芯片组合回归。 |
| `<repo-root>/tools/firmware_project_scaffold.py` | 1–499（完整） | 已改：保留自定义 main/既有 RTT、错误状态、模块名检查、正确的裸机块位置；CubeMX RTOS 明确转人工接入。 |
| `<repo-root>/tools/hardware_butler.py` | 1–1082（完整） | 已改：execute-action 非 ok 及 run-plan error/timeout 返回退出码 2；其他子命令状态没有全量回归。 |
| `<repo-root>/tools/hardware_butler_inspect.py` | 1–286（完整） | 已改：IOC 读取失败返回 partial/errors 并替换陈旧成功摘要；多输出文件的事务性未验证。 |
| `<repo-root>/tools/hardware_risk.py` | 1–199（完整） | 已改：损坏、错误 shape、非 UTF-8、不可读配置报告高风险；不声明电气安全。 |
| `<repo-root>/tools/logger.py` | 1–102（完整） | 未改：全文静态阅读；缓存 logger、handler 复用和非法日志级别未作本轮运行回归。 |
| `<repo-root>/tools/manual_summarizer.py` | 1–210（完整） | 未改：全文静态阅读；PDF 提取器、fallback、空行引用编号和超时未运行验证。 |
| `<repo-root>/tools/pin_capabilities.py` | 1–252（完整） | 未改：全文静态阅读；证据的器件/封装一致性及输入/输出信号解释未新增回归。 |
| `<repo-root>/tools/project_brain.py` | 1–308（完整） | 已改：拒绝传入 scan 中的项目外 IOC 路径；健康计数、摘要来源质量及双文件状态一致性未全面验证。 |
| `<repo-root>/tools/project_scanner.py` | 1–212（完整） | 已改：后缀/精确构建文件名识别、缺失根目录拒绝、项目外文件过滤；保留原日志关键词匹配。 |
| `<repo-root>/tools/qemu_behavior_check.py` | 1–188（完整） | 未改：全文静态阅读；未启动 QEMU/GDB，退出码、命令参数、监听地址、清理路径均没有本轮 RED。 |
| `<repo-root>/tools/research.py` | 1–117（完整） | 未改：全文静态阅读；子阶段返回状态、提前 mkdir、实际只创建 dossier 的行为未新增 RED。 |
| `<repo-root>/tools/document_search_api.py` | 1–242（完整） | 未改：1–242 全部补读（含前审遗漏的 192–242）；未联网，响应大小/schema/重定向与 URL 策略未验证。 |

只读依赖：`tools/safe_io.py` 当时 1–105、`tools/runtime_context.py` 1–142 全文；`tools/chip_dossier.py` 仅 102–165 和相关定义/status 搜索；当前 `hardware_action_executor.py` / `command_runner.py` 只搜索了状态枚举。未把前任务已经审过的依赖算成本轮全文阅读。除上述支持性读取外，不对本授权范围外的完整性作声明。

## 已复现并修复的根因

### A. 文件修改与 scaffold

1. **短 main 误判所有权**：小于 512 字节的自定义程序被当成 stub 替换。现在只识别保守的空 main/空循环形态；其余用户逻辑保留，返回 `needs-manual-integration`，不再声称已完成接入。
2. **RTT 文件交叉覆盖/缺失**：只用 app_rtt.c 是否存在决定是否同时写头/源文件，能覆盖已有自定义头文件，也会漏补头文件。现在分别保留已有文件、仅创建缺失的对应文件。
3. **scaffold 错误吞没**：写失败仍返回 ok，main 读取失败直接抛出。现在记录 files_skipped 且返回 error，已写入清单按实际单个文件更新。
4. **CubeMX 插入位置和未完成状态**：task 调用曾写入全局 USER CODE 4，缺少块/RTOS 情况仍标记 ok。裸机接入改用循环内 USER CODE 3；缺失必要块时 main 不作部分修改；CubeMX RTOS 接入保守地保持 main 原样并明确要求人工接入。不宣称因此实现了 RTOS 接入或真实编译。
5. **模块名未验证**：含路径分隔符/引号/换行/空串的 module 能生成破坏性源文本。现在在任何 scaffold 写入前拒绝非字母、数字、下划线名称。
6. **patch 的“策略说明”没有执行**：确认后的可变 preview 可写 Drivers、main.c、配置文件或同 workspace 中另一项目。现在用模块绑定的三条精确 app/note 路径白名单、当前项目根和整批路径预检；integration 限定 main.c/freertos.c，不相信 preview 内可修改的策略文案。
7. **过期 integration preview 继续写**：预览后源文本变化，只要 USER CODE 块仍存在就会写。现在目标携带 UTF-8 读取文本的 SHA-256 并在修改前重新核对；缺少/过期快照须重新预览。confirm-write 控制仍在。

### B. 证据与状态完整性

8. **风险配置 fail-open**：损坏 JSON、非对象、非法 workflow shape、非 UTF-8 或读失败，原先被当成缺失配置或异常退出。现在用带文件证据的 high `project_config_invalid` 风险保留不确定状态。
9. **扫描误认备份/缺失工程**：.ioc.bak、.ld.old、.uvprojx.disabled、.sch.bak、Makefile.backup、CMakeLists.txt.bak 被当成活动工程文件；不存在根目录被当成空项目。现在修正实际后缀/构建文件名判断并拒绝不存在的项目目录；没有扩展更改日志关键词匹配策略。
10. **证据路径逃逸**：外部绝对路径/../ 能进入索引、文本读取、IOC 摘要或引用。scanner/index/QA/brain 在消费前校验解析后文件属于当前项目；本地夹具复现的路径逃逸回归通过。符号链接实机路径测试仍为跳过，不据此宣称全部链接边界已闭合。
11. **inspection 错误导致二次异常/陈旧成功摘要**：IOC 读取失败生成 error 对象后仍交给成功渲染器，触发 KeyError。现在返回 partial/errors，并用错误摘要替代原成功摘要。
12. **CLI 把失败当成功退出**：execute-action 的 error/timeout/blocked 状态，以及 run-plan 的 error/timeout 计数，原先仍退出 0。现在保留结果输出并返回退出码 2；未改动硬件执行器、安全门或其他子命令的整体契约。

## RED / GREEN 证据

完整 argv、cwd、起始时间、退出码与 stdout/stderr 在本文件附录保存，无日志截断。以下是实际结果，而非预计结果。

| 日志标识 | 选择 | 退出码与实际结果 |
| --- | --- | --- |
| A-RED-file-safety | 新 file_safety 文件 | 1；20 failed, 1 passed，0.69s |
| A1-GREEN-scaffold | file_safety -k scaffold | 0；14 passed, 7 deselected，0.27s |
| A2-GREEN-file-safety | 新 file_safety 文件 | 0；21 passed，0.40s |
| B-RED-state-integrity | 初版 state_integrity 文件 | 1；25 failed, 1 skipped，0.48s |
| B-RED-ioc-consumers | 拆开 QA/brain 两消费者，均未先修 | 1；2 failed, 25 deselected，0.21s |
| B1-GREEN-risk | state_integrity -k risk | 0；6 passed, 21 deselected，0.13s |
| B2-GREEN-evidence-paths | 路径/扫描/索引选择 | 0；13 passed, 1 skipped, 13 deselected，0.17s |
| B3-GREEN-state-integrity | 最终 state_integrity 文件 | 0；26 passed, 1 skipped，0.30s |
| FINAL-targeted | 4 个定向文件，见命令 | 0；63 passed, 1 skipped，1.17s |
| FINAL-ruff | 16 个授权模块 + 3 个本任务测试 | 0；All checks passed! |
| FINAL-mypy | 16 个授权模块 | 0；Success: no issues found in 16 source files |
| FINAL-diff-check | 9 个生产模块 + 3 个测试 + 报告路径 | 0；无输出；报告/新增测试当时未跟踪，git diff 不检查未跟踪内容 |

必要回归中间结果也保留：首次加入旧 scaffold 回归为 2 failed / 61 passed / 1 skipped；两条旧断言分别使用了错误的循环块 4、把未接入自定义 main 当 ok，已对齐到已修复契约。旧测试增加 tmp_path 隔离，避免固定 tests/tmp 目录互相影响。首次 ruff 的两个 I001、mypy 的一个 no-any-return 均仅修复本轮新增代码；后续实际重跑通过。

唯一跳过：`test_ask_does_not_read_external_symlink_evidence`，`WinError 1314`（客户端没有创建符号链接所需的特权）。没有提高权限或绕过环境来让它通过。

### 最终测试完整命令

运行目录：`<repo-root>`。

```powershell
& '<repo-root>\.venv\Scripts\python.exe' '-B' '-X' 'utf8' '-m' 'pytest' 'tests/unit/test_core_remaining_file_safety.py' 'tests/unit/test_core_remaining_state_integrity.py' 'tests/unit/test_firmware_project_scaffold.py' 'tests/unit/test_hardware_butler_cli_errors.py' '-q' '--no-cov' '--tb=short' '--basetemp=<repo-root>\tests\unit\test_core_remaining_final_targeted.tmp' '-rs'
```

ruff 使用 `check --no-cache` 和逐项授权文件列表；mypy 使用 `--config-file mypy.ini --follow-imports=silent` 与本任务私有 cache-dir。完整列表及实参在 FINAL-ruff / FINAL-mypy 日志内。mypy 可以为类型解析读取导入依赖，但诊断交付范围仅这 16 个输入模块；不把类型检查文件数当阅读覆盖率。

## 剩余确认项与主线程交接

**已复现未修复：本轮没有。未证明项不要登记为已修复、已排除或已实机验证。**

- 需要主线程确认下游调用者是否正确处理新的 `needs-manual-integration` / `partial` 状态；本轮没有重跑 workflow 全链路，也没有改其他任务拥有的 workflow_runner。尤其不得只看到 scaffold 返回 dict 就宣称可编译。
- 需要主线程同步下面 9 个生产模块的插件镜像；package/sync/release/github_launch_audit、插件镜像校验和全仓验证均未执行。
- 本轮只有确定性路径预检和源文本快照，不是文件事务：并发 TOCTOU、预检后替换路径、跨文件中途 I/O 失败、共享 safe_io 的 backup/hardlink/祖先链接问题没有得到本轮完整证明。safe_io 属于其他 core 工作，不在本次修复中改动。
- 停止前静态看到但**未新增 RED、未修**：QEMU 进程返回码/文件参数/GDB 监听及清理；research 子阶段 status 重标 ok、提前 mkdir、文档声称下载而当前调用 create_dossier；manual_summarizer 引用行号/fallback；pin 证据与 GPIO 输入输出解释；document_search_api 响应大小/schema/URL 与重定向边界。请作为后续候选，不当成本轮确认漏洞数。
- 未验证全部 MCU/RTOS/模板组合、真实 C 编译与板卡观测；RTT、时钟、GPIO 配置、任务生命周期及电气效果仍需要独立可授权的 bench 方案。本轮不启动这些动作。
- 未继续原计划批次 C 的运行验证：planner/logger/manual/pin/qemu/research/document_search_api 七份只读，保留上表逐文件未完成说明。

## 本任务实际修改文件

- `<repo-root>/tools/evidence_index.py`
- `<repo-root>/tools/evidence_qa.py`
- `<repo-root>/tools/firmware_code_patcher.py`
- `<repo-root>/tools/firmware_project_scaffold.py`
- `<repo-root>/tools/hardware_butler.py`
- `<repo-root>/tools/hardware_butler_inspect.py`
- `<repo-root>/tools/hardware_risk.py`
- `<repo-root>/tools/project_brain.py`
- `<repo-root>/tools/project_scanner.py`
- `<repo-root>/tests/unit/test_core_remaining_file_safety.py`
- `<repo-root>/tests/unit/test_core_remaining_state_integrity.py`
- `<repo-root>/tests/unit/test_firmware_project_scaffold.py`
- `<repo-root>/docs/CORE_REMAINING_AUDIT_2026-09-06.md`

共 13 条源码/测试/报告路径。`test_hardware_butler_cli_errors.py` 只读取和运行，没有修改。其他任务变更未重置、覆盖或纳入本补丁清单。

## 日志与临时文件

- 完整日志直接保存在本报告附录，共 20 条已返回命令记录。命令输出文本仅规范化 CRLF 和行末空白，未省略失败记录。没有另外向授权范围外写日志。
- 临时夹具和 mypy 缓存仅使用 tests/unit 下带 test_core_remaining_ 前缀的私有 .tmp 目录；逐个检查 lstat、realpath、绝对父目录和固定命名后才用 Node 原生 FS 删除，没有前缀泛删、跨 shell 删除或删除其他任务目录。
- 已清理 12 个明确自有目录；RED 破坏场景只发生在这些隔离夹具中，源码中的测试可重新创建相同复现。
- 本轮命令均已返回；没有本任务启动的后台服务、真实工具会话或待等待扫描。

<details>
<summary>清理验证清单</summary>

```json
[
  {
    "target": "<repo-root>\\tests\\unit\\test_core_remaining_red_files.tmp",
    "resolved": "<repo-root>\\tests\\unit\\test_core_remaining_red_files.tmp",
    "status": "removed after absolute-path and lstat verification"
  },
  {
    "target": "<repo-root>\\tests\\unit\\test_core_remaining_green_scaffold.tmp",
    "resolved": "<repo-root>\\tests\\unit\\test_core_remaining_green_scaffold.tmp",
    "status": "removed after absolute-path and lstat verification"
  },
  {
    "target": "<repo-root>\\tests\\unit\\test_core_remaining_green_files.tmp",
    "resolved": "<repo-root>\\tests\\unit\\test_core_remaining_green_files.tmp",
    "status": "removed after absolute-path and lstat verification"
  },
  {
    "target": "<repo-root>\\tests\\unit\\test_core_remaining_red_state.tmp",
    "resolved": "<repo-root>\\tests\\unit\\test_core_remaining_red_state.tmp",
    "status": "removed after absolute-path and lstat verification"
  },
  {
    "target": "<repo-root>\\tests\\unit\\test_core_remaining_red_ioc_consumers.tmp",
    "resolved": "<repo-root>\\tests\\unit\\test_core_remaining_red_ioc_consumers.tmp",
    "status": "removed after absolute-path and lstat verification"
  },
  {
    "target": "<repo-root>\\tests\\unit\\test_core_remaining_green_risk.tmp",
    "resolved": "<repo-root>\\tests\\unit\\test_core_remaining_green_risk.tmp",
    "status": "removed after absolute-path and lstat verification"
  },
  {
    "target": "<repo-root>\\tests\\unit\\test_core_remaining_green_evidence.tmp",
    "resolved": "<repo-root>\\tests\\unit\\test_core_remaining_green_evidence.tmp",
    "status": "removed after absolute-path and lstat verification"
  },
  {
    "target": "<repo-root>\\tests\\unit\\test_core_remaining_green_state.tmp",
    "resolved": "<repo-root>\\tests\\unit\\test_core_remaining_green_state.tmp",
    "status": "removed after absolute-path and lstat verification"
  },
  {
    "target": "<repo-root>\\tests\\unit\\test_core_remaining_finish_initial.tmp",
    "resolved": "<repo-root>\\tests\\unit\\test_core_remaining_finish_initial.tmp",
    "status": "removed after absolute-path and lstat verification"
  },
  {
    "target": "<repo-root>\\tests\\unit\\test_core_remaining_finish_targeted.tmp",
    "resolved": "<repo-root>\\tests\\unit\\test_core_remaining_finish_targeted.tmp",
    "status": "removed after absolute-path and lstat verification"
  },
  {
    "target": "<repo-root>\\tests\\unit\\test_core_remaining_final_targeted.tmp",
    "resolved": "<repo-root>\\tests\\unit\\test_core_remaining_final_targeted.tmp",
    "status": "removed after absolute-path and lstat verification"
  },
  {
    "target": "<repo-root>\\tests\\unit\\test_core_remaining_mypy.tmp",
    "resolved": "<repo-root>\\tests\\unit\\test_core_remaining_mypy.tmp",
    "status": "removed after absolute-path and lstat verification"
  }
]
```

</details>

## 附录：完整命令日志

<details>
<summary>A-RED-file-safety — exit 1</summary>

- Started: 2026-09-06T00:05:06.629Z
- CWD: `<repo-root>`
- Exit: `1`

```powershell
& '<repo-root>\.venv\Scripts\python.exe' '-B' '-X' 'utf8' '-m' 'pytest' 'tests/unit/test_core_remaining_file_safety.py' '-q' '--no-cov' '--tb=short' '--basetemp=<repo-root>\tests\unit\test_core_remaining_red_files.tmp'
```

stdout:

```text
============================= test session starts =============================
platform win32 -- Python 3.13.14, pytest-9.1.1, pluggy-1.6.0
rootdir: <repo-root>
configfile: pyproject.toml
plugins: anyio-4.14.2, cov-7.1.0
collected 21 items

tests\unit\test_core_remaining_file_safety.py FFFFFFFFFFFFFFFFFFFF.      [100%]

================================== FAILURES ===================================
_ test_scaffold_does_not_classify_short_user_code_as_stub[int main(void) { user_init(); for (;;) { user_tick(); } }\n] _
tests\unit\test_core_remaining_file_safety.py:50: in test_scaffold_does_not_classify_short_user_code_as_stub
    assert scaffold.classify_main_c(source) == "custom"
E   AssertionError: assert 'stub' == 'custom'
E
E     - custom
E     + stub
_ test_scaffold_does_not_classify_short_user_code_as_stub[int important = 7;\nint main(void) { while (1) {} }\n] _
tests\unit\test_core_remaining_file_safety.py:50: in test_scaffold_does_not_classify_short_user_code_as_stub
    assert scaffold.classify_main_c(source) == "custom"
E   AssertionError: assert 'stub' == 'custom'
E
E     - custom
E     + stub
_ test_scaffold_does_not_classify_short_user_code_as_stub[int main(void) { return application(); }\n] _
tests\unit\test_core_remaining_file_safety.py:50: in test_scaffold_does_not_classify_short_user_code_as_stub
    assert scaffold.classify_main_c(source) == "custom"
E   AssertionError: assert 'stub' == 'custom'
E
E     - custom
E     + stub
__ test_scaffold_preserves_small_custom_main_and_reports_manual_integration ___
tests\unit\test_core_remaining_file_safety.py:57: in test_scaffold_preserves_small_custom_main_and_reports_manual_integration
    assert (root / "Core" / "Src" / "main.c").read_text(encoding="utf-8") == original
E   assert '#include "ma...{\n    }\n}\n' == 'int main(voi...tick(); } }\n'
E
E     - int main(void) { user_init(); for (;;) { user_tick(); } }
E     + #include "main.h"
E     + #include "app_led.h"
E     +
E     + void Error_Handler(void);
E     + ...
E
E     ...Full output truncated (23 lines hidden), use '-vv' to show
_ test_scaffold_preserves_each_existing_rtt_file_and_creates_its_missing_peer[Core/Inc/app_rtt.h] _
tests\unit\test_core_remaining_file_safety.py:69: in test_scaffold_preserves_each_existing_rtt_file_and_creates_its_missing_peer
    assert (root / existing).read_text(encoding="utf-8") == original
E   AssertionError: assert '#ifndef APP_...PP_RTT_H */\n' == 'user-owned R...lementation\n'
E
E     - user-owned RTT implementation
E     + #ifndef APP_RTT_H
E     + #define APP_RTT_H
E     +
E     + #include <stdint.h>
E     + ...
E
E     ...Full output truncated (16 lines hidden), use '-vv' to show
_ test_scaffold_preserves_each_existing_rtt_file_and_creates_its_missing_peer[Core/Src/app_rtt.c] _
tests\unit\test_core_remaining_file_safety.py:70: in test_scaffold_preserves_each_existing_rtt_file_and_creates_its_missing_peer
    assert (root / "Core/Inc/app_rtt.h").is_file()
E   AssertionError: assert False
E    +  where False = is_file()
E    +    where is_file = (WindowsPath('<repo-root>/tests/unit/test_core_remaining_red_files.tmp/test_scaffold_preserves_each_e1/project') / 'Core/Inc/app_rtt.h').is_file
_________________ test_scaffold_write_failure_is_not_success __________________
tests\unit\test_core_remaining_file_safety.py:86: in test_scaffold_write_failure_is_not_success
    assert result["status"] == "error"
E   AssertionError: assert 'ok' == 'error'
E
E     - error
E     + ok
___________________ test_scaffold_read_failure_is_recorded ____________________
tests\unit\test_core_remaining_file_safety.py:101: in test_scaffold_read_failure_is_recorded
    result = scaffold.ensure_compilable(root, part="STM32F407VGTx", module="led")
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
tools\firmware_project_scaffold.py:449: in ensure_compilable
    original = main_c.read_text(encoding="utf-8", errors="replace")
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
tests\unit\test_core_remaining_file_safety.py:97: in fail_main_read
    raise PermissionError("fixture: main.c is not readable")
E   PermissionError: fixture: main.c is not readable
_______ test_scaffold_rejects_invalid_module_before_writing[../outside] _______
tests\unit\test_core_remaining_file_safety.py:110: in test_scaffold_rejects_invalid_module_before_writing
    assert result["status"] == "blocked-needs-input"
E   AssertionError: assert 'ok' == 'blocked-needs-input'
E
E     - blocked-needs-input
E     + ok
_ test_scaffold_rejects_invalid_module_before_writing[led"\n#error injected] __
tests\unit\test_core_remaining_file_safety.py:110: in test_scaffold_rejects_invalid_module_before_writing
    assert result["status"] == "blocked-needs-input"
E   AssertionError: assert 'ok' == 'blocked-needs-input'
E
E     - blocked-needs-input
E     + ok
____________ test_scaffold_rejects_invalid_module_before_writing[] ____________
tests\unit\test_core_remaining_file_safety.py:110: in test_scaffold_rejects_invalid_module_before_writing
    assert result["status"] == "blocked-needs-input"
E   AssertionError: assert 'ok' == 'blocked-needs-input'
E
E     - blocked-needs-input
E     + ok
________ test_scaffold_places_bare_metal_task_in_loop_not_global_block ________
tests\unit\test_core_remaining_file_safety.py:122: in test_scaffold_places_bare_metal_task_in_loop_not_global_block
    assert "app_led_task(NULL);" in loop_body
E   AssertionError: assert 'app_led_task(NULL);' in '\n        '
____ test_scaffold_missing_loop_block_does_not_claim_complete_integration _____
tests\unit\test_core_remaining_file_safety.py:131: in test_scaffold_missing_loop_block_does_not_claim_complete_integration
    assert result["status"] == "needs-manual-integration"
E   AssertionError: assert 'ok' == 'needs-manual-integration'
E
E     - needs-manual-integration
E     + ok
________ test_scaffold_does_not_call_rtos_task_as_bare_metal_in_cubemx ________
tests\unit\test_core_remaining_file_safety.py:138: in test_scaffold_does_not_call_rtos_task_as_bare_metal_in_cubemx
    assert result["status"] == "needs-manual-integration"
E   AssertionError: assert 'ok' == 'needs-manual-integration'
E
E     - needs-manual-integration
E     + ok
_ test_patch_prevalidates_all_paths_before_modifying_any_file[Drivers/user.c] _
tests\unit\test_core_remaining_file_safety.py:150: in test_patch_prevalidates_all_paths_before_modifying_any_file
    with pytest.raises(ValueError):
         ^^^^^^^^^^^^^^^^^^^^^^^^^
E   Failed: DID NOT RAISE ValueError
_ test_patch_prevalidates_all_paths_before_modifying_any_file[Core/Src/main.c] _
tests\unit\test_core_remaining_file_safety.py:150: in test_patch_prevalidates_all_paths_before_modifying_any_file
    with pytest.raises(ValueError):
         ^^^^^^^^^^^^^^^^^^^^^^^^^
E   Failed: DID NOT RAISE ValueError
_ test_patch_prevalidates_all_paths_before_modifying_any_file[.embeddedskills/config.json] _
tests\unit\test_core_remaining_file_safety.py:150: in test_patch_prevalidates_all_paths_before_modifying_any_file
    with pytest.raises(ValueError):
         ^^^^^^^^^^^^^^^^^^^^^^^^^
E   Failed: DID NOT RAISE ValueError
______ test_patch_cannot_write_to_another_project_in_the_same_workspace _______
tests\unit\test_core_remaining_file_safety.py:165: in test_patch_cannot_write_to_another_project_in_the_same_workspace
    with pytest.raises(ValueError):
         ^^^^^^^^^^^^^^^^^^^^^^^^^
E   Failed: DID NOT RAISE ValueError
_____________ test_integration_rejects_changed_file_since_preview _____________
tests\unit\test_core_remaining_file_safety.py:183: in test_integration_rejects_changed_file_since_preview
    with pytest.raises(ValueError, match="changed since preview"):
         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
E   Failed: DID NOT RAISE ValueError
________ test_integration_rejects_unlisted_target_before_other_changes ________
tests\unit\test_core_remaining_file_safety.py:196: in test_integration_rejects_unlisted_target_before_other_changes
    with pytest.raises(ValueError):
         ^^^^^^^^^^^^^^^^^^^^^^^^^
E   Failed: DID NOT RAISE ValueError
=========================== short test summary info ===========================
FAILED tests/unit/test_core_remaining_file_safety.py::test_scaffold_does_not_classify_short_user_code_as_stub[int main(void) { user_init(); for (;;) { user_tick(); } }\n]
FAILED tests/unit/test_core_remaining_file_safety.py::test_scaffold_does_not_classify_short_user_code_as_stub[int important = 7;\nint main(void) { while (1) {} }\n]
FAILED tests/unit/test_core_remaining_file_safety.py::test_scaffold_does_not_classify_short_user_code_as_stub[int main(void) { return application(); }\n]
FAILED tests/unit/test_core_remaining_file_safety.py::test_scaffold_preserves_small_custom_main_and_reports_manual_integration
FAILED tests/unit/test_core_remaining_file_safety.py::test_scaffold_preserves_each_existing_rtt_file_and_creates_its_missing_peer[Core/Inc/app_rtt.h]
FAILED tests/unit/test_core_remaining_file_safety.py::test_scaffold_preserves_each_existing_rtt_file_and_creates_its_missing_peer[Core/Src/app_rtt.c]
FAILED tests/unit/test_core_remaining_file_safety.py::test_scaffold_write_failure_is_not_success
FAILED tests/unit/test_core_remaining_file_safety.py::test_scaffold_read_failure_is_recorded
FAILED tests/unit/test_core_remaining_file_safety.py::test_scaffold_rejects_invalid_module_before_writing[../outside]
FAILED tests/unit/test_core_remaining_file_safety.py::test_scaffold_rejects_invalid_module_before_writing[led"\n#error injected]
FAILED tests/unit/test_core_remaining_file_safety.py::test_scaffold_rejects_invalid_module_before_writing[]
FAILED tests/unit/test_core_remaining_file_safety.py::test_scaffold_places_bare_metal_task_in_loop_not_global_block
FAILED tests/unit/test_core_remaining_file_safety.py::test_scaffold_missing_loop_block_does_not_claim_complete_integration
FAILED tests/unit/test_core_remaining_file_safety.py::test_scaffold_does_not_call_rtos_task_as_bare_metal_in_cubemx
FAILED tests/unit/test_core_remaining_file_safety.py::test_patch_prevalidates_all_paths_before_modifying_any_file[Drivers/user.c]
FAILED tests/unit/test_core_remaining_file_safety.py::test_patch_prevalidates_all_paths_before_modifying_any_file[Core/Src/main.c]
FAILED tests/unit/test_core_remaining_file_safety.py::test_patch_prevalidates_all_paths_before_modifying_any_file[.embeddedskills/config.json]
FAILED tests/unit/test_core_remaining_file_safety.py::test_patch_cannot_write_to_another_project_in_the_same_workspace
FAILED tests/unit/test_core_remaining_file_safety.py::test_integration_rejects_changed_file_since_preview
FAILED tests/unit/test_core_remaining_file_safety.py::test_integration_rejects_unlisted_target_before_other_changes
======================== 20 failed, 1 passed in 0.69s =========================
```

stderr:

```text
(empty)
```

</details>

<details>
<summary>A1-GREEN-scaffold — exit 0</summary>

- Started: 2026-09-06T00:11:37.915Z
- CWD: `<repo-root>`
- Exit: `0`

```powershell
& '<repo-root>\.venv\Scripts\python.exe' '-B' '-X' 'utf8' '-m' 'pytest' 'tests/unit/test_core_remaining_file_safety.py' '-q' '--no-cov' '--tb=short' '--basetemp=<repo-root>\tests\unit\test_core_remaining_green_scaffold.tmp' '-k' 'scaffold'
```

stdout:

```text
============================= test session starts =============================
platform win32 -- Python 3.13.14, pytest-9.1.1, pluggy-1.6.0
rootdir: <repo-root>
configfile: pyproject.toml
plugins: anyio-4.14.2, cov-7.1.0
collected 21 items / 7 deselected / 14 selected

tests\unit\test_core_remaining_file_safety.py ..............             [100%]

====================== 14 passed, 7 deselected in 0.27s =======================
```

stderr:

```text
(empty)
```

</details>

<details>
<summary>A2-GREEN-file-safety — exit 0</summary>

- Started: 2026-09-06T00:18:38.769Z
- CWD: `<repo-root>`
- Exit: `0`

```powershell
& '<repo-root>\.venv\Scripts\python.exe' '-B' '-X' 'utf8' '-m' 'pytest' 'tests/unit/test_core_remaining_file_safety.py' '-q' '--no-cov' '--tb=short' '--basetemp=<repo-root>\tests\unit\test_core_remaining_green_files.tmp'
```

stdout:

```text
============================= test session starts =============================
platform win32 -- Python 3.13.14, pytest-9.1.1, pluggy-1.6.0
rootdir: <repo-root>
configfile: pyproject.toml
plugins: anyio-4.14.2, cov-7.1.0
collected 21 items

tests\unit\test_core_remaining_file_safety.py .....................      [100%]

============================= 21 passed in 0.40s ==============================
```

stderr:

```text
(empty)
```

</details>

<details>
<summary>baseline-revision — exit 0</summary>

- Started: 2026-09-06T00:51:40.452Z
- CWD: `<repo-root>`
- Exit: `0`

```powershell
& 'git' 'rev-parse' 'HEAD'
```

stdout:

```text
cf1cd9e754104eb8c2a1dbeeb027f76073f71478
```

stderr:

```text
(empty)
```

</details>

<details>
<summary>B-RED-state-integrity — exit 1</summary>

- Started: 2026-09-06T00:56:16.878Z
- CWD: `<repo-root>`
- Exit: `1`

```powershell
& '<repo-root>\.venv\Scripts\python.exe' '-B' '-X' 'utf8' '-m' 'pytest' 'tests/unit/test_core_remaining_state_integrity.py' '-q' '--no-cov' '--tb=short' '--basetemp=<repo-root>\tests\unit\test_core_remaining_red_state.tmp'
```

stdout:

```text
============================= test session starts =============================
platform win32 -- Python 3.13.14, pytest-9.1.1, pluggy-1.6.0
rootdir: <repo-root>
configfile: pyproject.toml
plugins: anyio-4.14.2, cov-7.1.0
collected 26 items

tests\unit\test_core_remaining_state_integrity.py FFFFFFFFFFFFFFFFFFsFFF [ 84%]
FFFF                                                                     [100%]

================================== FAILURES ===================================
____ test_risk_reports_invalid_config_instead_of_treating_it_as_missing[{] ____
tests\unit\test_core_remaining_state_integrity.py:30: in test_risk_reports_invalid_config_instead_of_treating_it_as_missing
    assert len(invalid) == 1
E   assert 0 == 1
E    +  where 0 = len([])
___ test_risk_reports_invalid_config_instead_of_treating_it_as_missing[[]] ____
tests\unit\test_core_remaining_state_integrity.py:30: in test_risk_reports_invalid_config_instead_of_treating_it_as_missing
    assert len(invalid) == 1
E   assert 0 == 1
E    +  where 0 = len([])
__ test_risk_reports_invalid_config_instead_of_treating_it_as_missing[null] ___
tests\unit\test_core_remaining_state_integrity.py:30: in test_risk_reports_invalid_config_instead_of_treating_it_as_missing
    assert len(invalid) == 1
E   assert 0 == 1
E    +  where 0 = len([])
_ test_risk_reports_invalid_config_instead_of_treating_it_as_missing[{"workflow": []}] _
tests\unit\test_core_remaining_state_integrity.py:30: in test_risk_reports_invalid_config_instead_of_treating_it_as_missing
    assert len(invalid) == 1
E   assert 0 == 1
E    +  where 0 = len([])
__ test_risk_reports_invalid_config_instead_of_treating_it_as_missing[\xff] ___
tests\unit\test_core_remaining_state_integrity.py:28: in test_risk_reports_invalid_config_instead_of_treating_it_as_missing
    result = hardware_risk.analyze_risks(tmp_path)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
tools\hardware_risk.py:99: in analyze_risks
    config = read_project_config(root)
             ^^^^^^^^^^^^^^^^^^^^^^^^^
tools\hardware_risk.py:187: in read_project_config
    data = json.loads(path.read_text(encoding="utf-8"))
                      ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
<python-home>\Lib\pathlib\_local.py:546: in read_text
    return PathBase.read_text(self, encoding, errors, newline)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
<python-home>\Lib\pathlib\_abc.py:633: in read_text
    return f.read()
           ^^^^^^^^
<frozen codecs>:325: in decode
    ???
E   UnicodeDecodeError: 'utf-8' codec can't decode byte 0xff in position 0: invalid start byte
_____________________ test_risk_reports_unreadable_config _____________________
tests\unit\test_core_remaining_state_integrity.py:48: in test_risk_reports_unreadable_config
    assert any(item["id"] == "project_config_invalid" for item in result["risks"])
E   assert False
E    +  where False = any(<generator object test_risk_reports_unreadable_config.<locals>.<genexpr> at 0x0000023F5658BE00>)
_ test_scanner_does_not_treat_backup_names_as_active_artifacts[board.ioc.bak-cubemx_ioc] _
tests\unit\test_core_remaining_state_integrity.py:63: in test_scanner_does_not_treat_backup_names_as_active_artifacts
    assert label not in project_scanner.classify_file(Path(filename))
E   AssertionError: assert 'cubemx_ioc' not in {'cubemx_ioc'}
E    +  where {'cubemx_ioc'} = <function classify_file at 0x0000023F5614E020>(WindowsPath('board.ioc.bak'))
E    +    where <function classify_file at 0x0000023F5614E020> = project_scanner.classify_file
E    +    and   WindowsPath('board.ioc.bak') = Path('board.ioc.bak')
_ test_scanner_does_not_treat_backup_names_as_active_artifacts[memory.ld.old-linker_script] _
tests\unit\test_core_remaining_state_integrity.py:63: in test_scanner_does_not_treat_backup_names_as_active_artifacts
    assert label not in project_scanner.classify_file(Path(filename))
E   AssertionError: assert 'linker_script' not in {'linker_script'}
E    +  where {'linker_script'} = <function classify_file at 0x0000023F5614E020>(WindowsPath('memory.ld.old'))
E    +    where <function classify_file at 0x0000023F5614E020> = project_scanner.classify_file
E    +    and   WindowsPath('memory.ld.old') = Path('memory.ld.old')
_ test_scanner_does_not_treat_backup_names_as_active_artifacts[board.uvprojx.disabled-keil_project] _
tests\unit\test_core_remaining_state_integrity.py:63: in test_scanner_does_not_treat_backup_names_as_active_artifacts
    assert label not in project_scanner.classify_file(Path(filename))
E   AssertionError: assert 'keil_project' not in {'keil_project'}
E    +  where {'keil_project'} = <function classify_file at 0x0000023F5614E020>(WindowsPath('board.uvprojx.disabled'))
E    +    where <function classify_file at 0x0000023F5614E020> = project_scanner.classify_file
E    +    and   WindowsPath('board.uvprojx.disabled') = Path('board.uvprojx.disabled')
_ test_scanner_does_not_treat_backup_names_as_active_artifacts[board.sch.bak-schematic] _
tests\unit\test_core_remaining_state_integrity.py:63: in test_scanner_does_not_treat_backup_names_as_active_artifacts
    assert label not in project_scanner.classify_file(Path(filename))
E   AssertionError: assert 'schematic' not in {'schematic'}
E    +  where {'schematic'} = <function classify_file at 0x0000023F5614E020>(WindowsPath('board.sch.bak'))
E    +    where <function classify_file at 0x0000023F5614E020> = project_scanner.classify_file
E    +    and   WindowsPath('board.sch.bak') = Path('board.sch.bak')
_ test_scanner_does_not_treat_backup_names_as_active_artifacts[Makefile.backup-makefile] _
tests\unit\test_core_remaining_state_integrity.py:63: in test_scanner_does_not_treat_backup_names_as_active_artifacts
    assert label not in project_scanner.classify_file(Path(filename))
E   AssertionError: assert 'makefile' not in {'makefile'}
E    +  where {'makefile'} = <function classify_file at 0x0000023F5614E020>(WindowsPath('Makefile.backup'))
E    +    where <function classify_file at 0x0000023F5614E020> = project_scanner.classify_file
E    +    and   WindowsPath('Makefile.backup') = Path('Makefile.backup')
_ test_scanner_does_not_treat_backup_names_as_active_artifacts[CMakeLists.txt.bak-cmake_project] _
tests\unit\test_core_remaining_state_integrity.py:63: in test_scanner_does_not_treat_backup_names_as_active_artifacts
    assert label not in project_scanner.classify_file(Path(filename))
E   AssertionError: assert 'cmake_project' not in {'cmake_project'}
E    +  where {'cmake_project'} = <function classify_file at 0x0000023F5614E020>(WindowsPath('CMakeLists.txt.bak'))
E    +    where <function classify_file at 0x0000023F5614E020> = project_scanner.classify_file
E    +    and   WindowsPath('CMakeLists.txt.bak') = Path('CMakeLists.txt.bak')
_________________ test_scanner_rejects_a_missing_project_root _________________
tests\unit\test_core_remaining_state_integrity.py:67: in test_scanner_rejects_a_missing_project_root
    with pytest.raises(ValueError, match="directory"):
         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
E   Failed: DID NOT RAISE ValueError
___________ test_qa_text_search_rejects_outside_index_paths[False] ____________
tests\unit\test_core_remaining_state_integrity.py:79: in test_qa_text_search_rejects_outside_index_paths
    assert evidence_qa.search_indexed_text(root, index, "needle") == []
E   AssertionError: assert [{'path': '.....ct evidence'}] == []
E
E     Left contains one more item: {'path': '../outside-manual.txt', 'line': 1, 'note': 'keyword match score=1', 'text': 'needle: must not be read through project evidence'}
E     Use -v to get more diff
____________ test_qa_text_search_rejects_outside_index_paths[True] ____________
tests\unit\test_core_remaining_state_integrity.py:79: in test_qa_text_search_rejects_outside_index_paths
    assert evidence_qa.search_indexed_text(root, index, "needle") == []
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
tools\evidence_qa.py:268: in search_indexed_text
    "path": str(path.relative_to(root).as_posix()),
                ^^^^^^^^^^^^^^^^^^^^^^
<python-home>\Lib\pathlib\_local.py:385: in relative_to
    raise ValueError(f"{str(self)!r} is not in the subpath of {str(other)!r}")
E   ValueError: '<repo-root>\\tests\\unit\\test_core_remaining_red_state.tmp\\test_qa_text_search_rejects_ou1\\outside-manual.txt' is not in the subpath of '<repo-root>\\tests\\unit\\test_core_remaining_red_state.tmp\\test_qa_text_search_rejects_ou1\\project'
_______________ test_qa_ioc_summary_rejects_outside_index_paths _______________
tests\unit\test_core_remaining_state_integrity.py:88: in test_qa_ioc_summary_rejects_outside_index_paths
    assert evidence_qa.ioc_summaries(root, index) == []
E   AssertionError: assert [{'schema_ver...t': ''}, ...}] == []
E
E     Left contains one more item: {'schema_version': 1, 'ioc_file': '<repo-root>\\tests\\unit\\test_core_remaining_red_state.tmp\\test_qa_ioc_s...', 'package': '', 'line': ''}, 'project': {'name': '', 'toolchain': '', 'firmware_package': '', 'hal_assert': ''}, ...}
E     Use -v to get more diff
____________ test_qa_ioc_citations_reject_an_outside_summary_path _____________
tests\unit\test_core_remaining_state_integrity.py:97: in test_qa_ioc_citations_reject_an_outside_summary_path
    assert evidence_qa.ioc_line_citations(root, {"ioc_file": str(outside)}, ["PA1."]) == []
E   AssertionError: assert [{'path': 'D:...IDE_FIXTURE'}] == []
E
E     Left contains one more item: {'path': '<repo-root>\\tests\\unit\\test_core_remaining_red_state.tmp\\test_qa_ioc_citations_reject_a0\\outside.ioc', 'line': 1, 'note': 'CubeMX IOC evidence', 'text': 'PA1.GPIO_Label=OUTSIDE_FIXTURE'}
E     Use -v to get more diff
_____________ test_index_drops_outside_artifacts_in_supplied_scan _____________
tests\unit\test_core_remaining_state_integrity.py:106: in test_index_drops_outside_artifacts_in_supplied_scan
    assert index["items"] == []
E   AssertionError: assert [{'path': '.....eters.', ...}] == []
E
E     Left contains one more item: {'path': '../outside-manual.txt', 'kind': 'manual', 'source_quality': 'unknown', 'summary': 'Manual candidate; extract reference, user, or programming details before using parameters.', ...}
E     Use -v to get more diff
_______ test_inspection_records_ioc_failure_without_rendering_a_success _______
tests\unit\test_core_remaining_state_integrity.py:141: in test_inspection_records_ioc_failure_without_rendering_a_success
    result = hardware_butler_inspect.inspect_project(root, out_dir)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
tools\hardware_butler_inspect.py:59: in inspect_project
    write_text(out_dir / "cubemx-ioc-summary.md", cubemx_ioc_summary.render_markdown(ioc_summaries[0]))
                                                  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
tools\cubemx_ioc_summary.py:259: in render_markdown
    mcu = data["mcu"]
          ^^^^^^^^^^^
E   KeyError: 'mcu'
___ test_execute_action_cli_has_nonzero_exit_for_unsuccessful_result[error] ___
tests\unit\test_core_remaining_state_integrity.py:163: in test_execute_action_cli_has_nonzero_exit_for_unsuccessful_result
    assert exit_code == 2
E   assert 0 == 2
---------------------------- Captured stdout call -----------------------------
{
  "status": "error"
}
__ test_execute_action_cli_has_nonzero_exit_for_unsuccessful_result[timeout] __
tests\unit\test_core_remaining_state_integrity.py:163: in test_execute_action_cli_has_nonzero_exit_for_unsuccessful_result
    assert exit_code == 2
E   assert 0 == 2
---------------------------- Captured stdout call -----------------------------
{
  "status": "timeout"
}
_ test_execute_action_cli_has_nonzero_exit_for_unsuccessful_result[blocked-real-backend-not-enabled] _
tests\unit\test_core_remaining_state_integrity.py:163: in test_execute_action_cli_has_nonzero_exit_for_unsuccessful_result
    assert exit_code == 2
E   assert 0 == 2
---------------------------- Captured stdout call -----------------------------
{
  "status": "blocked-real-backend-not-enabled"
}
_ test_execute_action_cli_has_nonzero_exit_for_unsuccessful_result[blocked-plan-token-mismatch] _
tests\unit\test_core_remaining_state_integrity.py:163: in test_execute_action_cli_has_nonzero_exit_for_unsuccessful_result
    assert exit_code == 2
E   assert 0 == 2
---------------------------- Captured stdout call -----------------------------
{
  "status": "blocked-plan-token-mismatch"
}
_______ test_run_plan_cli_has_nonzero_exit_for_command_failures[error] ________
tests\unit\test_core_remaining_state_integrity.py:177: in test_run_plan_cli_has_nonzero_exit_for_command_failures
    assert exit_code == 2
E   assert 0 == 2
---------------------------- Captured stdout call -----------------------------
{
  "summary": {
    "error": 1
  }
}
______ test_run_plan_cli_has_nonzero_exit_for_command_failures[timeout] _______
tests\unit\test_core_remaining_state_integrity.py:177: in test_run_plan_cli_has_nonzero_exit_for_command_failures
    assert exit_code == 2
E   assert 0 == 2
---------------------------- Captured stdout call -----------------------------
{
  "summary": {
    "timeout": 1
  }
}
=========================== short test summary info ===========================
FAILED tests/unit/test_core_remaining_state_integrity.py::test_risk_reports_invalid_config_instead_of_treating_it_as_missing[{]
FAILED tests/unit/test_core_remaining_state_integrity.py::test_risk_reports_invalid_config_instead_of_treating_it_as_missing[[]]
FAILED tests/unit/test_core_remaining_state_integrity.py::test_risk_reports_invalid_config_instead_of_treating_it_as_missing[null]
FAILED tests/unit/test_core_remaining_state_integrity.py::test_risk_reports_invalid_config_instead_of_treating_it_as_missing[{"workflow": []}]
FAILED tests/unit/test_core_remaining_state_integrity.py::test_risk_reports_invalid_config_instead_of_treating_it_as_missing[\xff]
FAILED tests/unit/test_core_remaining_state_integrity.py::test_risk_reports_unreadable_config
FAILED tests/unit/test_core_remaining_state_integrity.py::test_scanner_does_not_treat_backup_names_as_active_artifacts[board.ioc.bak-cubemx_ioc]
FAILED tests/unit/test_core_remaining_state_integrity.py::test_scanner_does_not_treat_backup_names_as_active_artifacts[memory.ld.old-linker_script]
FAILED tests/unit/test_core_remaining_state_integrity.py::test_scanner_does_not_treat_backup_names_as_active_artifacts[board.uvprojx.disabled-keil_project]
FAILED tests/unit/test_core_remaining_state_integrity.py::test_scanner_does_not_treat_backup_names_as_active_artifacts[board.sch.bak-schematic]
FAILED tests/unit/test_core_remaining_state_integrity.py::test_scanner_does_not_treat_backup_names_as_active_artifacts[Makefile.backup-makefile]
FAILED tests/unit/test_core_remaining_state_integrity.py::test_scanner_does_not_treat_backup_names_as_active_artifacts[CMakeLists.txt.bak-cmake_project]
FAILED tests/unit/test_core_remaining_state_integrity.py::test_scanner_rejects_a_missing_project_root
FAILED tests/unit/test_core_remaining_state_integrity.py::test_qa_text_search_rejects_outside_index_paths[False]
FAILED tests/unit/test_core_remaining_state_integrity.py::test_qa_text_search_rejects_outside_index_paths[True]
FAILED tests/unit/test_core_remaining_state_integrity.py::test_qa_ioc_summary_rejects_outside_index_paths
FAILED tests/unit/test_core_remaining_state_integrity.py::test_qa_ioc_citations_reject_an_outside_summary_path
FAILED tests/unit/test_core_remaining_state_integrity.py::test_index_drops_outside_artifacts_in_supplied_scan
FAILED tests/unit/test_core_remaining_state_integrity.py::test_inspection_records_ioc_failure_without_rendering_a_success
FAILED tests/unit/test_core_remaining_state_integrity.py::test_execute_action_cli_has_nonzero_exit_for_unsuccessful_result[error]
FAILED tests/unit/test_core_remaining_state_integrity.py::test_execute_action_cli_has_nonzero_exit_for_unsuccessful_result[timeout]
FAILED tests/unit/test_core_remaining_state_integrity.py::test_execute_action_cli_has_nonzero_exit_for_unsuccessful_result[blocked-real-backend-not-enabled]
FAILED tests/unit/test_core_remaining_state_integrity.py::test_execute_action_cli_has_nonzero_exit_for_unsuccessful_result[blocked-plan-token-mismatch]
FAILED tests/unit/test_core_remaining_state_integrity.py::test_run_plan_cli_has_nonzero_exit_for_command_failures[error]
FAILED tests/unit/test_core_remaining_state_integrity.py::test_run_plan_cli_has_nonzero_exit_for_command_failures[timeout]
======================== 25 failed, 1 skipped in 0.48s ========================
```

stderr:

```text
(empty)
```

</details>

<details>
<summary>B-RED-ioc-consumers — exit 1</summary>

- Started: 2026-09-06T00:56:59.955Z
- CWD: `<repo-root>`
- Exit: `1`

```powershell
& '<repo-root>\.venv\Scripts\python.exe' '-B' '-X' 'utf8' '-m' 'pytest' 'tests/unit/test_core_remaining_state_integrity.py' '-q' '--no-cov' '--tb=short' '--basetemp=<repo-root>\tests\unit\test_core_remaining_red_ioc_consumers.tmp' '-k' 'ioc_summary_rejects'
```

stdout:

```text
============================= test session starts =============================
platform win32 -- Python 3.13.14, pytest-9.1.1, pluggy-1.6.0
rootdir: <repo-root>
configfile: pyproject.toml
plugins: anyio-4.14.2, cov-7.1.0
collected 27 items / 25 deselected / 2 selected

tests\unit\test_core_remaining_state_integrity.py FF                     [100%]

================================== FAILURES ===================================
______________ test_ioc_summary_rejects_outside_index_paths[qa] _______________
tests\unit\test_core_remaining_state_integrity.py:90: in test_ioc_summary_rejects_outside_index_paths
    assert evidence_qa.ioc_summaries(root, index) == []
E   AssertionError: assert [{'schema_ver...t': ''}, ...}] == []
E
E     Left contains one more item: {'schema_version': 1, 'ioc_file': '<repo-root>\\tests\\unit\\test_core_remaining_red_ioc_consumers.tmp\\test_...', 'package': '', 'line': ''}, 'project': {'name': '', 'toolchain': '', 'firmware_package': '', 'hal_assert': ''}, ...}
E     Use -v to get more diff
_____________ test_ioc_summary_rejects_outside_index_paths[brain] _____________
tests\unit\test_core_remaining_state_integrity.py:92: in test_ioc_summary_rejects_outside_index_paths
    assert project_brain.summarize_iocs(root, {"artifacts": {"cubemx_ioc": index["items"]}}) == []
E   AssertionError: assert [{'schema_ver...t': ''}, ...}] == []
E
E     Left contains one more item: {'schema_version': 1, 'ioc_file': '<repo-root>\\tests\\unit\\test_core_remaining_red_ioc_consumers.tmp\\test_...', 'package': '', 'line': ''}, 'project': {'name': '', 'toolchain': '', 'firmware_package': '', 'hal_assert': ''}, ...}
E     Use -v to get more diff
=========================== short test summary info ===========================
FAILED tests/unit/test_core_remaining_state_integrity.py::test_ioc_summary_rejects_outside_index_paths[qa]
FAILED tests/unit/test_core_remaining_state_integrity.py::test_ioc_summary_rejects_outside_index_paths[brain]
====================== 2 failed, 25 deselected in 0.21s =======================
```

stderr:

```text
(empty)
```

</details>

<details>
<summary>B1-GREEN-risk — exit 0</summary>

- Started: 2026-09-06T00:57:30.906Z
- CWD: `<repo-root>`
- Exit: `0`

```powershell
& '<repo-root>\.venv\Scripts\python.exe' '-B' '-X' 'utf8' '-m' 'pytest' 'tests/unit/test_core_remaining_state_integrity.py' '-q' '--no-cov' '--tb=short' '--basetemp=<repo-root>\tests\unit\test_core_remaining_green_risk.tmp' '-k' 'risk'
```

stdout:

```text
============================= test session starts =============================
platform win32 -- Python 3.13.14, pytest-9.1.1, pluggy-1.6.0
rootdir: <repo-root>
configfile: pyproject.toml
plugins: anyio-4.14.2, cov-7.1.0
collected 27 items / 21 deselected / 6 selected

tests\unit\test_core_remaining_state_integrity.py ......                 [100%]

====================== 6 passed, 21 deselected in 0.13s =======================
```

stderr:

```text
(empty)
```

</details>

<details>
<summary>B2-GREEN-evidence-paths — exit 0</summary>

- Started: 2026-09-06T00:58:22.889Z
- CWD: `<repo-root>`
- Exit: `0`

```powershell
& '<repo-root>\.venv\Scripts\python.exe' '-B' '-X' 'utf8' '-m' 'pytest' 'tests/unit/test_core_remaining_state_integrity.py' '-q' '--no-cov' '--tb=short' '--basetemp=<repo-root>\tests\unit\test_core_remaining_green_evidence.tmp' '-k' 'scanner or qa or ioc_summary or index or symlink'
```

stdout:

```text
============================= test session starts =============================
platform win32 -- Python 3.13.14, pytest-9.1.1, pluggy-1.6.0
rootdir: <repo-root>
configfile: pyproject.toml
plugins: anyio-4.14.2, cov-7.1.0
collected 27 items / 13 deselected / 14 selected

tests\unit\test_core_remaining_state_integrity.py .............s         [100%]

================ 13 passed, 1 skipped, 13 deselected in 0.17s =================
```

stderr:

```text
(empty)
```

</details>

<details>
<summary>B3-GREEN-state-integrity — exit 0</summary>

- Started: 2026-09-06T00:59:05.717Z
- CWD: `<repo-root>`
- Exit: `0`

```powershell
& '<repo-root>\.venv\Scripts\python.exe' '-B' '-X' 'utf8' '-m' 'pytest' 'tests/unit/test_core_remaining_state_integrity.py' '-q' '--no-cov' '--tb=short' '--basetemp=<repo-root>\tests\unit\test_core_remaining_green_state.tmp'
```

stdout:

```text
============================= test session starts =============================
platform win32 -- Python 3.13.14, pytest-9.1.1, pluggy-1.6.0
rootdir: <repo-root>
configfile: pyproject.toml
plugins: anyio-4.14.2, cov-7.1.0
collected 27 items

tests\unit\test_core_remaining_state_integrity.py ...................s.. [ 81%]
.....                                                                    [100%]

======================== 26 passed, 1 skipped in 0.30s ========================
```

stderr:

```text
(empty)
```

</details>

<details>
<summary>finish-targeted-before-contract-alignment — exit 1</summary>

- Started: 2026-09-06T01:19:01.558Z
- CWD: `<repo-root>`
- Exit: `1`

```powershell
& '<repo-root>\.venv\Scripts\python.exe' '-B' '-X' 'utf8' '-m' 'pytest' 'tests/unit/test_core_remaining_file_safety.py' 'tests/unit/test_core_remaining_state_integrity.py' 'tests/unit/test_firmware_project_scaffold.py' 'tests/unit/test_hardware_butler_cli_errors.py' '-q' '--no-cov' '--tb=short' '--basetemp=<repo-root>\tests\unit\test_core_remaining_finish_initial.tmp'
```

stdout:

```text
============================= test session starts =============================
platform win32 -- Python 3.13.14, pytest-9.1.1, pluggy-1.6.0
rootdir: <repo-root>
configfile: pyproject.toml
plugins: anyio-4.14.2, cov-7.1.0
collected 64 items

tests\unit\test_core_remaining_file_safety.py .....................      [ 32%]
tests\unit\test_core_remaining_state_integrity.py ...................s.. [ 67%]
.....                                                                    [ 75%]
tests\unit\test_firmware_project_scaffold.py ...FF..........             [ 98%]
tests\unit\test_hardware_butler_cli_errors.py .                          [100%]

================================== FAILURES ===================================
_______ test_ensure_compilable_integrates_into_cubemx_user_code_blocks ________
tests\unit\test_firmware_project_scaffold.py:94: in test_ensure_compilable_integrates_into_cubemx_user_code_blocks
    assert result["status"] == "ok"
E   AssertionError: assert 'needs-manual-integration' == 'ok'
E
E     - ok
E     + needs-manual-integration
_____________ test_ensure_compilable_leaves_custom_main_untouched _____________
tests\unit\test_firmware_project_scaffold.py:115: in test_ensure_compilable_leaves_custom_main_untouched
    assert result["status"] == "ok"
E   AssertionError: assert 'needs-manual-integration' == 'ok'
E
E     - ok
E     + needs-manual-integration
=========================== short test summary info ===========================
FAILED tests/unit/test_firmware_project_scaffold.py::test_ensure_compilable_integrates_into_cubemx_user_code_blocks
FAILED tests/unit/test_firmware_project_scaffold.py::test_ensure_compilable_leaves_custom_main_untouched
=================== 2 failed, 61 passed, 1 skipped in 1.31s ===================
```

stderr:

```text
(empty)
```

</details>

<details>
<summary>finish-ruff-initial — exit 1</summary>

- Started: 2026-09-06T01:19:03.284Z
- CWD: `<repo-root>`
- Exit: `1`

```powershell
& '<repo-root>\.venv\Scripts\ruff.exe' 'check' '--no-cache' 'tools/evidence_index.py' 'tools/evidence_qa.py' 'tools/firmware_code_patcher.py' 'tools/firmware_intent_planner.py' 'tools/firmware_project_scaffold.py' 'tools/hardware_butler.py' 'tools/hardware_butler_inspect.py' 'tools/hardware_risk.py' 'tools/logger.py' 'tools/manual_summarizer.py' 'tools/pin_capabilities.py' 'tools/project_brain.py' 'tools/project_scanner.py' 'tools/qemu_behavior_check.py' 'tools/research.py' 'tools/document_search_api.py' 'tests/unit/test_core_remaining_file_safety.py' 'tests/unit/test_core_remaining_state_integrity.py' 'tests/unit/test_firmware_project_scaffold.py'
```

stdout:

```text
I001 [*] Import block is un-sorted or un-formatted
  --> tests\unit\test_core_remaining_file_safety.py:1:1
   |
 1 | / from __future__ import annotations
 2 | |
 3 | | from pathlib import Path
 4 | |
 5 | | import pytest
 6 | |
 7 | | import firmware_code_patcher as patcher
 8 | | import firmware_project_scaffold as scaffold
   | |____________________________________________^
 9 |
10 |   CUBEMX_MAIN = """/* USER CODE BEGIN Includes */
   |
help: Organize imports
  |
4 |
  - import pytest
  -
5 | import firmware_code_patcher as patcher
6 | import firmware_project_scaffold as scaffold
7 + import pytest
8 |
  |

I001 [*] Import block is un-sorted or un-formatted
  --> tests\unit\test_core_remaining_state_integrity.py:1:1
   |
 1 | / from __future__ import annotations
 2 | |
 3 | | import json
 4 | | from pathlib import Path
 5 | |
 6 | | import pytest
 7 | |
 8 | | import evidence_index
 9 | | import evidence_qa
10 | | import hardware_butler
11 | | import hardware_butler_inspect
12 | | import hardware_risk
13 | | import project_brain
14 | | import project_scanner
   | |______________________^
help: Organize imports
   |
5  |
   - import pytest
   -
6  | import evidence_index
--------------------------------------------------------------------------------
12 | import project_scanner
13 + import pytest
14 |
   |

Found 2 errors.
[*] 2 fixable with the `--fix` option.
```

stderr:

```text
(empty)
```

</details>

<details>
<summary>finish-mypy — exit 1</summary>

- Started: 2026-09-06T01:19:03.428Z
- CWD: `<repo-root>`
- Exit: `1`

```powershell
& '<repo-root>\.venv\Scripts\python.exe' '-B' '-X' 'utf8' '-m' 'mypy' 'tools/evidence_index.py' 'tools/evidence_qa.py' 'tools/firmware_code_patcher.py' 'tools/firmware_intent_planner.py' 'tools/firmware_project_scaffold.py' 'tools/hardware_butler.py' 'tools/hardware_butler_inspect.py' 'tools/hardware_risk.py' 'tools/logger.py' 'tools/manual_summarizer.py' 'tools/pin_capabilities.py' 'tools/project_brain.py' 'tools/project_scanner.py' 'tools/qemu_behavior_check.py' 'tools/research.py' 'tools/document_search_api.py' '--config-file' 'mypy.ini' '--follow-imports=silent' '--cache-dir' 'tests/unit/test_core_remaining_mypy.tmp'
```

stdout:

```text
tools\firmware_code_patcher.py:982: error: Returning Any from function declared to return "Path"  [no-any-return]
Found 1 error in 1 file (checked 16 source files)
```

stderr:

```text
(empty)
```

</details>

<details>
<summary>finish-targeted — exit 0</summary>

- Started: 2026-09-06T01:19:30.297Z
- CWD: `<repo-root>`
- Exit: `0`

```powershell
& '<repo-root>\.venv\Scripts\python.exe' '-B' '-X' 'utf8' '-m' 'pytest' 'tests/unit/test_core_remaining_file_safety.py' 'tests/unit/test_core_remaining_state_integrity.py' 'tests/unit/test_firmware_project_scaffold.py' 'tests/unit/test_hardware_butler_cli_errors.py' '-q' '--no-cov' '--tb=short' '--basetemp=<repo-root>\tests\unit\test_core_remaining_finish_targeted.tmp'
```

stdout:

```text
============================= test session starts =============================
platform win32 -- Python 3.13.14, pytest-9.1.1, pluggy-1.6.0
rootdir: <repo-root>
configfile: pyproject.toml
plugins: anyio-4.14.2, cov-7.1.0
collected 64 items

tests\unit\test_core_remaining_file_safety.py .....................      [ 32%]
tests\unit\test_core_remaining_state_integrity.py ...................s.. [ 67%]
.....                                                                    [ 75%]
tests\unit\test_firmware_project_scaffold.py ...............             [ 98%]
tests\unit\test_hardware_butler_cli_errors.py .                          [100%]

======================== 63 passed, 1 skipped in 1.18s ========================
```

stderr:

```text
(empty)
```

</details>

<details>
<summary>finish-ruff — exit 0</summary>

- Started: 2026-09-06T01:19:31.837Z
- CWD: `<repo-root>`
- Exit: `0`

```powershell
& '<repo-root>\.venv\Scripts\ruff.exe' 'check' '--no-cache' 'tools/evidence_index.py' 'tools/evidence_qa.py' 'tools/firmware_code_patcher.py' 'tools/firmware_intent_planner.py' 'tools/firmware_project_scaffold.py' 'tools/hardware_butler.py' 'tools/hardware_butler_inspect.py' 'tools/hardware_risk.py' 'tools/logger.py' 'tools/manual_summarizer.py' 'tools/pin_capabilities.py' 'tools/project_brain.py' 'tools/project_scanner.py' 'tools/qemu_behavior_check.py' 'tools/research.py' 'tools/document_search_api.py' 'tests/unit/test_core_remaining_file_safety.py' 'tests/unit/test_core_remaining_state_integrity.py' 'tests/unit/test_firmware_project_scaffold.py'
```

stdout:

```text
All checks passed!
```

stderr:

```text
(empty)
```

</details>

<details>
<summary>finish-mypy-final — exit 0</summary>

- Started: 2026-09-06T01:19:31.894Z
- CWD: `<repo-root>`
- Exit: `0`

```powershell
& '<repo-root>\.venv\Scripts\python.exe' '-B' '-X' 'utf8' '-m' 'mypy' 'tools/evidence_index.py' 'tools/evidence_qa.py' 'tools/firmware_code_patcher.py' 'tools/firmware_intent_planner.py' 'tools/firmware_project_scaffold.py' 'tools/hardware_butler.py' 'tools/hardware_butler_inspect.py' 'tools/hardware_risk.py' 'tools/logger.py' 'tools/manual_summarizer.py' 'tools/pin_capabilities.py' 'tools/project_brain.py' 'tools/project_scanner.py' 'tools/qemu_behavior_check.py' 'tools/research.py' 'tools/document_search_api.py' '--config-file' 'mypy.ini' '--follow-imports=silent' '--cache-dir' 'tests/unit/test_core_remaining_mypy.tmp'
```

stdout:

```text
Success: no issues found in 16 source files
```

stderr:

```text
(empty)
```

</details>

<details>
<summary>FINAL-targeted — exit 0</summary>

- Started: 2026-09-06T01:23:14.363Z
- CWD: `<repo-root>`
- Exit: `0`

```powershell
& '<repo-root>\.venv\Scripts\python.exe' '-B' '-X' 'utf8' '-m' 'pytest' 'tests/unit/test_core_remaining_file_safety.py' 'tests/unit/test_core_remaining_state_integrity.py' 'tests/unit/test_firmware_project_scaffold.py' 'tests/unit/test_hardware_butler_cli_errors.py' '-q' '--no-cov' '--tb=short' '--basetemp=<repo-root>\tests\unit\test_core_remaining_final_targeted.tmp' '-rs'
```

stdout:

```text
============================= test session starts =============================
platform win32 -- Python 3.13.14, pytest-9.1.1, pluggy-1.6.0
rootdir: <repo-root>
configfile: pyproject.toml
plugins: anyio-4.14.2, cov-7.1.0
collected 64 items

tests\unit\test_core_remaining_file_safety.py .....................      [ 32%]
tests\unit\test_core_remaining_state_integrity.py ...................s.. [ 67%]
.....                                                                    [ 75%]
tests\unit\test_firmware_project_scaffold.py ...............             [ 98%]
tests\unit\test_hardware_butler_cli_errors.py .                          [100%]

=========================== short test summary info ===========================
SKIPPED [1] tests\unit\test_core_remaining_state_integrity.py:120: symlink unavailable: [WinError 1314] 客户端没有所需的特权。: '<repo-root>\\tests\\unit\\test_core_remaining_final_targeted.tmp\\test_ask_does_not_read_externa0\\outside.txt' -> '<repo-root>\\tests\\unit\\test_core_remaining_final_targeted.tmp\\test_ask_does_not_read_externa0\\project\\manual.txt'
======================== 63 passed, 1 skipped in 1.17s ========================
```

stderr:

```text
(empty)
```

</details>

<details>
<summary>FINAL-ruff — exit 0</summary>

- Started: 2026-09-06T01:23:15.904Z
- CWD: `<repo-root>`
- Exit: `0`

```powershell
& '<repo-root>\.venv\Scripts\ruff.exe' 'check' '--no-cache' 'tools/evidence_index.py' 'tools/evidence_qa.py' 'tools/firmware_code_patcher.py' 'tools/firmware_intent_planner.py' 'tools/firmware_project_scaffold.py' 'tools/hardware_butler.py' 'tools/hardware_butler_inspect.py' 'tools/hardware_risk.py' 'tools/logger.py' 'tools/manual_summarizer.py' 'tools/pin_capabilities.py' 'tools/project_brain.py' 'tools/project_scanner.py' 'tools/qemu_behavior_check.py' 'tools/research.py' 'tools/document_search_api.py' 'tests/unit/test_core_remaining_file_safety.py' 'tests/unit/test_core_remaining_state_integrity.py' 'tests/unit/test_firmware_project_scaffold.py'
```

stdout:

```text
All checks passed!
```

stderr:

```text
(empty)
```

</details>

<details>
<summary>FINAL-mypy — exit 0</summary>

- Started: 2026-09-06T01:23:15.960Z
- CWD: `<repo-root>`
- Exit: `0`

```powershell
& '<repo-root>\.venv\Scripts\python.exe' '-B' '-X' 'utf8' '-m' 'mypy' 'tools/evidence_index.py' 'tools/evidence_qa.py' 'tools/firmware_code_patcher.py' 'tools/firmware_intent_planner.py' 'tools/firmware_project_scaffold.py' 'tools/hardware_butler.py' 'tools/hardware_butler_inspect.py' 'tools/hardware_risk.py' 'tools/logger.py' 'tools/manual_summarizer.py' 'tools/pin_capabilities.py' 'tools/project_brain.py' 'tools/project_scanner.py' 'tools/qemu_behavior_check.py' 'tools/research.py' 'tools/document_search_api.py' '--config-file' 'mypy.ini' '--follow-imports=silent' '--cache-dir' 'tests/unit/test_core_remaining_mypy.tmp'
```

stdout:

```text
Success: no issues found in 16 source files
```

stderr:

```text
(empty)
```

</details>

<details>
<summary>FINAL-diff-check — exit 0</summary>

- Started: 2026-09-06T01:23:16.208Z
- CWD: `<repo-root>`
- Exit: `0`

```powershell
& 'git' 'diff' '--check' '--' 'tools/evidence_index.py' 'tools/evidence_qa.py' 'tools/firmware_code_patcher.py' 'tools/firmware_project_scaffold.py' 'tools/hardware_butler.py' 'tools/hardware_butler_inspect.py' 'tools/hardware_risk.py' 'tools/project_brain.py' 'tools/project_scanner.py' 'tests/unit/test_core_remaining_file_safety.py' 'tests/unit/test_core_remaining_state_integrity.py' 'tests/unit/test_firmware_project_scaffold.py' 'docs/CORE_REMAINING_AUDIT_2026-09-06.md'
```

stdout:

```text
(empty)
```

stderr:

```text
(empty)
```

</details>

<details>
<summary>FINAL-scoped-change-list — exit 0</summary>

- Started: 2026-09-06T01:23:16.284Z
- CWD: `<repo-root>`
- Exit: `0`

```powershell
& 'git' 'status' '--short' '--' 'tools/evidence_index.py' 'tools/evidence_qa.py' 'tools/firmware_code_patcher.py' 'tools/firmware_intent_planner.py' 'tools/firmware_project_scaffold.py' 'tools/hardware_butler.py' 'tools/hardware_butler_inspect.py' 'tools/hardware_risk.py' 'tools/logger.py' 'tools/manual_summarizer.py' 'tools/pin_capabilities.py' 'tools/project_brain.py' 'tools/project_scanner.py' 'tools/qemu_behavior_check.py' 'tools/research.py' 'tools/document_search_api.py' 'tests/unit/test_core_remaining_file_safety.py' 'tests/unit/test_core_remaining_state_integrity.py' 'tests/unit/test_firmware_project_scaffold.py' 'docs/CORE_REMAINING_AUDIT_2026-09-06.md'
```

stdout:

```text
 M tests/unit/test_firmware_project_scaffold.py
 M tools/evidence_index.py
 M tools/evidence_qa.py
 M tools/firmware_code_patcher.py
 M tools/firmware_project_scaffold.py
 M tools/hardware_butler.py
 M tools/hardware_butler_inspect.py
 M tools/hardware_risk.py
 M tools/project_brain.py
 M tools/project_scanner.py
?? docs/CORE_REMAINING_AUDIT_2026-09-06.md
?? tests/unit/test_core_remaining_file_safety.py
?? tests/unit/test_core_remaining_state_integrity.py
```

stderr:

```text
(empty)
```

</details>

<a id="core-remaining-log-end"></a>
