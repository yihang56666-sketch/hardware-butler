# Findings — Hardware Butler

## Session 2026-08-17 (takeover audit)

### Verified against live code

- 9-stage workflow runner exists and **completes end-to-end in mock mode** (ran `workflow-run` on the cubemx-basic fixture: all 9 stages `completed`, status `completed`).
- 3 vendor adapters: stm32 / esp32 / msp430.
- Backends: Keil/GCC/EIDE build, J-Link/OpenOCD/probe-rs/pyOCD flash, serial/CAN/net/QEMU observe.
- LLM client supports 4 providers: `claude-code` (host-agent task-file), `anthropic`/`openai` (HTTP), `local` (OpenAI-compatible base_url). `claude-code`/`codex`/`host-agent` aliases all normalize to the task-file mode.
- `workflow-llm-config` CLI already existed; `--auto-select` for empty `--part` already existed.
- Real-mode gating intact: `HARDWARE_BUTLER_ENABLE_REAL_FLASH=1` + token + value-sanity checks.
- Test baseline: **475 passed / 4 skipped**, ruff clean, mypy clean on tools/.

### What was actually missing (vs user's stated goal)

1. **No regression test proved the autonomous loop closes** with an HTTP LLM provider. The mock-mode e2e tests run with the default `claude-code` provider, which never actually exercises the LLM parse/codegen code paths (the LLM stays pending). So a future change could silently break "one sentence → done" and no test would catch it.
2. **GUI had no LLM provider config UI** — user had to hand-edit `.hardware-butler/llm-config.json`. The `workflow-llm-config` CLI existed but wasn't surfaced in the UI.

### What was NOT broken (despite user worry)

- No "mess from previous AI sessions" — the codebase is coherent, tested, lint-clean. The previous sessions delivered a real P3 + 4 incremental features (FreeRTOS codegen, RTT observability, QEMU backend, real-preflight canonicalization).
- Plugin sync tests pass; plugins/ is not currently drifted.

## Changes this session

### 1. `tests/unit/test_workflow_autonomous_loop.py` (NEW)

Two tests that stub `llm_client.call_llm` to simulate an HTTP LLM provider
answering intent-parse + codegen tasks:

- `test_one_sentence_goal_completes_via_http_llm_stub`: one-sentence goal with
  no `--feature/--pin/--part` → workflow completes all 9 stages, no stage
  enters `blocked-needs-input`. This is the regression net for the user's
  core product claim.
- `test_autonomous_loop_uses_llm_written_firmware`: firmware-plan evidence
  records `llm_codegen.status == "ok"` AND the LLM-written `.c` file lands
  on disk with the stub's signatures (proving the LLM's content, not the
  template, was written).

### 2. `gui/hardware_agent_ui.py` — LLM provider config panel

Added a `QGroupBox` to the workflow tab with:
- Provider combo (claude-code / anthropic / openai / local)
- API key env var field
- Model field
- Base URL field
- Codegen toggle
- "保存 LLM 配置" / "读取当前配置" buttons

Wired to the existing `workflow-llm-config` CLI so persistence goes through
the same path the runner reads. Verified with a GUI smoke test
(offscreen Qt platform) that all new widgets construct and the handlers
are callable.

## Next pass (deferred)

- Auxiliary features consolidation (datasheet/RAG/research entrypoint).
- Docs: update HANDOFF §19 with the autonomous-loop test + GUI LLM panel.
- Plugin re-sync + commit.
