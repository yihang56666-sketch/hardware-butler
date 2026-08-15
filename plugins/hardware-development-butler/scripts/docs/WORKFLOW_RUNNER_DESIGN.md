# Workflow Runner — 自动化硬件开发闭环设计

## 目标

把现有的 36 个 CLI 命令从"脚手架"升级为"目标驱动的状态机"：用户给一个高层意图
（如"把 sensor-read 跑通并烧录到板子"），系统自主分解为多阶段 pipeline，每阶段
复用现有命令，阶段间靠 `workflow-state.json` 传递证据，失败时自诊断并回环。

设计原则：

1. **状态机而非 agent loop** — 状态、转移、证据可审计、可恢复、可重放
2. **目标级 token** — 一次人工确认覆盖同一目标内的重复 flash；单次动作仍写审计
   日志。这是"全自动"与"脚手架"的分水岭
3. **复用而非重写** — 每个阶段调用现有 CLI 命令，runner 只负责编排和证据传递
4. **fail-closed** — 任何阶段证据不足或安全检查失败，runner 阻断而非降级

## 状态 Schema

`<project-root>/.hardware-butler/workflow-state.json`:

```json
{
  "schema_version": 1,
  "workflow_id": "wf-20260815-001",
  "intent": "develop-feature",
  "goal": "实现 sensor-read 外设并烧录验证",
  "root": "<project-root>",
  "created_at": "2026-08-15T12:00:00Z",
  "updated_at": "2026-08-15T12:05:00Z",
  "status": "running|paused|completed|failed|blocked-needs-input|blocked-needs-confirmation",
  "current_stage": "cubemx-config",
  "context": {
    "part": "STM32F407VGT6",
    "feature": "sensor-read",
    "pin": "PB7",
    "function": "i2c",
    "instance": "I2C1",
    "target": "stm32f4xx",
    "probe": "stlink-v3",
    "backend": "openocd"
  },
  "stages": [
    {
      "id": "requirement-parse",
      "title": "需求解析",
      "status": "completed",
      "started_at": "...",
      "finished_at": "...",
      "command": "tools/hardware_butler.py workflow-parse-requirement ...",
      "evidence": {"parsed_requirements": {...}},
      "attempts": 1
    }
  ],
  "goal_token": {
    "token": "<random-256bit-hex>",
    "token_hash": "<sha256>",
    "scope": "build-flash-debug",
    "created_at": "...",
    "expires_at": "...",
    "max_reuses": 10,
    "uses": 0
  },
  "safety_log_path": ".embeddedskills/safety-log.jsonl"
}
```

## 阶段清单（垂直切片先行）

P0（不碰硬件，已实现）：
1. `requirement-parse` — 解析用户自然语言需求 → 结构化 context（feature/pin/function/instance）
2. `chip-selection` — nextboard 选型或验证已有 part（P0 做"验证"分支）
3. `datasheet-collect` — chip-dossier + summarize-manual 拉取并解析芯片资料（P0 skip 网络拉取）
4. `cubemx-config` — advise-pin + patch-ioc dry-run 生成 CubeMX 配置方案

P1（碰硬件门控，已实现）：
5. `firmware-plan` — firmware-plan + firmware-patch + firmware-integrate
6. `build` — plan-build + run-plan --phase build-discovery
7. `flash` — bench-runbook + plan-action + execute-action（目标 token 复用）
8. `verify-goal` — 对照原始需求验证目标达成（P1: evidence-completeness）

P2（行为验证 + 优化回环，已实现）：
9. `debug-observe` — sim 模式从 firmware-plan verification 字段提取预期信号
   （LED/UART/RTT/SWO），生成观测报告。P3 将接 embeddedskills 真实 serial/jlink
   后端读取实际观测证据
10. `verify-goal`（升级） — 从"证据完整"升级到"行为关键词匹配"：goal 含 "led" →
    检查 debug-observe 是否有 led 信号 observation；失败则触发 optimize-loop
11. `optimize-loop` — verify-goal 失败且 attempts < MAX_STAGE_ATTEMPTS 时，重置
    firmware-plan / build / flash / debug-observe / verify-goal 五阶段为 pending，
    runner 自动回环重试。MAX_STAGE_ATTEMPTS=3 限制总尝试次数，超过则整体 failed

## 状态转移规则

- 每阶段进入：`running`；证据充分：`completed`；证据不足：`blocked-needs-input`；
  安全检查失败：`failed`；需确认：`paused`
- Runner 持久化每次转移前的 state snapshot 到 `workflow-state.json`，支持
  `--resume <workflow-id>` 从最后 completed 阶段继续
- 同一阶段最多重试 3 次（`attempts`），超过则 `failed`
- verify-goal 失败触发 optimize-loop：重置 5 个后续阶段，runner 重新迭代，
  直到 verify-goal completed 或 attempts 用尽

## 目标级 Token 模型

**已实现（P1 轮次）。**

- `mint_goal_token(workflow_id, scope, max_uses, ttl_seconds)` in
  [embeddedskills/safety_gate.py](../embeddedskills/safety_gate.py) —
  cryptographically random (`secrets.token_hex`), NOT derived from public
  fields. Returns plaintext token + public record (token_hash, scope,
  max_uses, expires_at).
- `check_goal_token(workspace, workflow_id, token, record, action, consume)`
  validates against the safety log: blocks on `invalid_token`,
  `cross_workflow`, `out_of_scope`, `expired`, `exhausted`. When `consume=True`
  and allowed, appends a `goal-token-use` event to `safety-log.jsonl` with
  `workflow_id + token_hash + action + use_count + max_uses`.
- Workflow runner mints the goal_token on first entry to the `flash` stage,
  binds it to `state["workflow_id"]`, and persists the public record (not the
  plaintext) to `workflow-state.json`. Plaintext stays in-memory for the
  session (acceptable for P1; P2 will move it to a session-kept secret store).
- Resume reuses the existing goal_token: re-entering `flash` consumes one
  more use, modelling the "flash → observe → reflash" loop without
  re-prompting. Exhaustion (uses >= max_uses) blocks the next flash with
  `error_code: exhausted`, surfacing as `failed` stage.
- Default: `max_uses=5`, `ttl_seconds=3600` (1 hour).

## Goal Token vs Existing Keyless Token

| Property | `confirmation_token` (existing) | `goal_token` (new) |
|---|---|---|
| Derivation | sha256 of public plan fields (deterministic) | `secrets.token_hex` (random) |
| Scope | single action, single record | multiple actions within a workflow_id |
| Reuse | one-shot (replay-blocked via `consume_token`) | up to `max_uses` uses |
| Expiry | no explicit expiry | `expires_at` enforced |
| Cross-workflow | not applicable (derivation includes all fields) | blocked (`error_code: cross_workflow`) |
| Use case | human-in-the-loop single flash | automated workflow with repeated flash |

The two coexist: `confirmation_token` is still used by `plan-action` /
`execute-action` for the single-flash gate; `goal_token` wraps a set of
those single-flash events under one workflow-scoped authorisation.

## CLI 入口

```powershell
# 启动新 workflow
python tools\hardware_butler.py workflow-run \
  --root <project> \
  --intent develop-feature \
  --goal "实现 sensor-read I2C 外设并烧录验证" \
  --feature sensor-read --pin PB7 --function i2c --instance I2C1 \
  --json

# 恢复
python tools\hardware_butler.py workflow-run --root <project> --resume --json

# 查看状态
python tools\hardware_butler.py workflow-status --root <project> --json
```

## 垂直切片范围（本次实现）

只做 P0 四阶段 + runner 骨架 + workflow-state.json + 一个能在
`tests/fixtures/cubemx-basic` 上跑通的端到端测试。不碰硬件，不需要 goal_token。

后续迭代再接入 P1 阶段和 token 复用逻辑。
