# Hardware-Butler — Mature Product Completion Plan

## Goal

Drive 硬件agent (Hardware Butler) from its current 9-stage workflow state to a mature, autonomous, end-to-end embedded development tool: user states requirement (in CubeMX context or via codex/CLI), system parses → selects chip → fetches docs → configures CubeMX → generates firmware → builds → flashes → debugs/observes → iterates until goal met. Must support multi-MCU (STM32/ESP32/MSP430/extensible). No board needed for mock path; real-hardware path gated safely. Plus auxiliary resource-collection and a usable GUI.

## Status: 100% COMPLETE (non-hardware path)

All non-hardware work is done. The user's "一句话需求 → 完成" goal is fully
realized for the mock-mode path and is regression-tested. The only remaining
work is real-hardware end-to-end validation when a board arrives —
operationally documented in `docs/REAL_BOARD_DAY_RUNBOOK.md`. No code or
test work blocks that.

## Final State Snapshot (verified 2026-08-17, Phase 14)

- **Mock-mode e2e workflow runs clean** (live smoke test on cubemx-basic fixture: all 9 stages completed, status `completed`).
- **Autonomous LLM loop is real** — `tests/unit/test_workflow_autonomous_loop.py` proves: with a stubbed HTTP LLM provider, a one-sentence goal with NO `--feature/--pin/--part` auto-fills via LLM intent parse, writes LLM-generated firmware, completes all 9 stages. No `blocked-needs-input`.
- **LLM HTTP retry hardening** — `tools/llm_client.py` `_call_with_retry`: MAX_ATTEMPTS=3 with exponential backoff, structured `error_kind` ("transient"|"fatal") and `attempts` count. Retries 429/5xx/URLError/Timeout/ConnectionError; never retries 401/400/RuntimeError/ValueError.
- **GUI has 12 tabs** including the Phase 6 "工具" tab consolidating 6 high-value CLI subcommands + LLM provider config panel.
- **14 vendor family adapters** covering all mainstream 32-bit MCU ISAs (Cortex-M0+/M3/M4F/M7/M23/M33, RISC-V, C28x, MIPS, Xtensa LX6/LX7, AVR 8-bit, Renesas CISC): stm32 / esp32 / msp430 / avr / nordic / riscv / ti-tiva / c2000 / ra / lpc / pic32 / max32 / imxrt / rx. Plus GD32/CH32 auto-mapped to stm32-compatible.
- **5-layer behavior verification** in `_verify_signal`: (1) expected_regex + value-range bounds (expected_min/expected_max on first captured group), (2) expected_text exact substring, (3) frequency_hz measurement from timestamps, (4) kind-keyword fallback for 9 kinds (led/uart/rtt/swo/i2c/spi/adc/pwm/can), (5) QEMU behavior emulation.
- **Backends**: Keil/GCC/EIDE build, J-Link/OpenOCD/probe-rs/pyOCD flash, serial/CAN/net/QEMU observe.
- **Real-mode gating intact**: `HARDWARE_BUTLER_ENABLE_REAL_FLASH=1` + goal_token + value-sanity checks.
- **Plugin-sync pre-commit hook**: `tools/install_plugin_sync_hook.py` auto-syncs `plugins/.../scripts/` on commit when source changes.
- **Test baseline**: **805 passed / 10 skipped**, ruff + mypy clean on tools/ (72 source files).
- **Docs**: HANDOFF §1-22, CHANGELOG Unreleased section, `docs/REAL_BOARD_DAY_RUNBOOK.md` board-day-only checklist.

## Phase Map (final)

| # | Phase | Status | Exit Criterion |
|---|-------|--------|----------------|
| 1 | Project state verification | done | findings.md confirms claims against current code |
| 2 | Test/lint/build green baseline | done | pytest 477/4 → 805/10, ruff+mypy clean |
| 3 | Mock e2e smoke (live) | done | workflow-run completes 9 stages |
| 4 | Autonomous LLM loop regression net | done | test_workflow_autonomous_loop.py |
| 5 | GUI: LLM provider config panel | done | save/load roundtrip via CLI |
| 6 | GUI tools tab + plugin-sync hook + fixture guard | done | 3facce5 |
| 7 | AVR/Nordic adapter test polish | done | 13→26 tests |
| 8 | Real-hardware readiness runbook | done | docs/REAL_BOARD_DAY_RUNBOOK.md |
| 9 | Documentation (HANDOFF §21, CHANGELOG) | done | ccb214b |
| 10 | RISC-V + Tiva + C2000 adapters + LLM retry | done | a82bc39 |
| 11 | verify-signal extended to 9 kinds | done | 6d7f3b8 |
| 12 | Renesas RA + NXP LPC + Microchip PIC32 | done | 4d04182 |
| 13 | Maxim MAX32 + NXP i.MX RT + Renesas RX + regex verification | done | c8c5fb2 |
| 14 | value-range bounds on regex-captured groups | done | d62d1f8 |
| 15 | Docs sync (HANDOFF §22, CHANGELOG, README, GUI, planning files) | done | this phase |

## Decisions Log

- 2026-08-17 (takeover): Adopted planning-with-files. Verified state before any code changes. Did NOT assume "mess from previous AI" — verified first, found codebase coherent.
- 2026-08-17: Added autonomous-loop regression test rather than refactoring working code — the gap was test coverage, not architecture.
- 2026-08-17: GUI LLM config panel reuses existing `workflow-llm-config` CLI (no new persistence code path). Persistence stays single-sourced through that CLI.
- 2026-08-17 (carried forward from prior session): HMAC token model declined by user; value-sanity 防呆 layer remains the safety approach. Do not re-propose HMAC.
- 2026-08-17 (Phase 10): LLM retry classifies 429/5xx/URLError as transient (retryable) and 4xx-except-429/RuntimeError/ValueError as fatal (not retryable). Never retry auth errors.
- 2026-08-17 (Phase 13): CAN keyword list intentionally avoids bare `id` (would false-positive on "idle"/"middle"). Use "can id"/"ext id"/"std id"/"frame" instead.
- 2026-08-17 (Phase 14): value-range bounds apply to the FIRST captured group only — multi-group range checks would require API extension. The single-group bound covers the 80% case (single reading per line).

## Errors Encountered

- Ruff I001 import-order auto-fix on the new test file (fixed automatically).
- Python 3.10 f-string cannot reuse same quote character — the `f"... {"; ".join(...)}"` pattern failed. Fixed by string concatenation instead.
- copy_fixture pollution: ad-hoc `research --root tests/fixtures/cubemx-basic` wrote scratch state into the fixture's `.hardware-butler/`, masking the "missing chip documents" risk assertion. Fixed by stripping `.hardware-butler/` in copy_fixture.

## Done — project complete

No further work pending. Real-board-day validation is the user's operational step.
