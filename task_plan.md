# Hardware-Butler — Mature Product Completion Plan

## Goal

Drive 硬件agent (Hardware Butler) from its current 9-stage workflow state to a mature, autonomous, end-to-end embedded development tool: user states requirement (in CubeMX context or via codex/CLI), system parses → selects chip → fetches docs → configures CubeMX → generates firmware → builds → flashes → debugs/observes → iterates until goal met. Must support multi-MCU (STM32/ESP32/MSP430/extensible). No board needed for mock path; real-hardware path gated safely. Plus auxiliary resource-collection and a usable GUI.

## Current State Snapshot (verified 2026-08-17, takeover session)

- **Mock-mode e2e workflow runs clean** (live smoke test on cubemx-basic fixture: all 9 stages completed, status `completed`).
- **Autonomous LLM loop is real** — added `tests/unit/test_workflow_autonomous_loop.py` proves: with a stubbed HTTP LLM provider, a one-sentence goal with NO `--feature/--pin/--part` auto-fills via LLM intent parse, writes LLM-generated firmware, completes all 9 stages. No `blocked-needs-input`.
- GUI has a workflow tab with full input form + 9-stage status table + pending-LLM-task view + **NEW** LLM provider config panel (provider/api-key-env/model/base-url/codegen).
- 3 vendor adapters: stm32 / esp32 / msp430 (extensible).
- Backends: Keil/GCC/EIDE build, J-Link/OpenOCD/probe-rs/pyOCD flash, serial/CAN/net/QEMU observe.
- Real-mode gating intact: `HARDWARE_BUTLER_ENABLE_REAL_FLASH=1` + goal_token + value-sanity checks.
- Test baseline: **477 passed / 4 skipped**, ruff + mypy clean on tools/.
- Most-recent commits: QEMU observe backend, RTT observability, real-preflight canonicalization, FreeRTOS codegen.

## Phase Map

| # | Phase | Status | Exit Criterion |
|---|-------|--------|----------------|
| 1 | Project state verification (actual vs documented) | done | findings.md confirms claims against current code |
| 2 | Test/lint/build green baseline | done | pytest 477/4, ruff+mypy clean |
| 3 | Mock e2e smoke (live) | done | workflow-run completes 9 stages |
| 4 | Autonomous LLM loop regression net | done | new test_workflow_autonomous_loop.py |
| 5 | GUI: LLM provider config panel | done | save/load roundtrip via CLI |
| 6 | Auxiliary feature consolidation (datasheet/RAG/research) | pending | single "research" entrypoint; reachable from GUI |
| 7 | Multi-MCU family expansion polish (AVR/Nordic/RISC-V) | pending | at least 1 more family adapter added with tests |
| 8 | Real-hardware readiness review | pending | real-mode docs + dry-run runbook + safety review checklist; no board required to certify |
| 9 | Documentation, packaging, release | pending | HANDOFF §19, CHANGELOG, plugin sync, commit |

## Decisions Log

- 2026-08-17 (takeover): Adopted planning-with-files. Verified state before any code changes. Did NOT assume "mess from previous AI" — verified first, found codebase coherent.
- 2026-08-17: Added autonomous-loop regression test rather than refactoring working code — the gap was test coverage, not architecture.
- 2026-08-17: GUI LLM config panel reuses existing `workflow-llm-config` CLI (no new persistence code path). Persistence stays single-sourced through that CLI.
- 2026-08-17 (carried forward from prior session): HMAC token model declined by user; value-sanity 防呆 layer remains the safety approach. Do not re-propose HMAC.

## Errors Encountered

- Ruff I001 import-order auto-fix on the new test file (fixed automatically).

## Next Pass (deferred)

- Auxiliary features consolidation (datasheet/RAG/research entrypoint reachable from GUI).
- HANDOFF §19 doc update.
- Plugin re-sync + commit.
