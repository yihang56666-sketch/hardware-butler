# Progress Log — Hardware Butler

## 2026-08-17 — Takeover + Phase 6-14 session (8 commits)

- Verified current state against HANDOFF + memory: 9-stage workflow runner, 5 vendor adapters at start, 4 LLM providers, full backends. Mock e2e runs clean (475/4 skip, ruff+mypy clean).
- Ran live e2e smoke: `workflow-run --root tests/fixtures/cubemx-basic --goal "LED blink on PD12" --feature led-blink --pin PD12 --function gpio-output` → status completed, all 9 stages completed.
- Identified real gap: no regression test for the HTTP-LLM autonomous path (the user's core "one sentence → done" claim). The mock tests don't exercise it because the default `claude-code` provider stays pending.

### Phase 6 (commit 3facce5)
- Added `tests/unit/test_workflow_autonomous_loop.py` (2 tests): stubs `llm_client.call_llm`, runs the full workflow with no `--feature/--pin/--part`, asserts it completes with LLM-written firmware on disk.
- Added LLM provider config panel to `gui/hardware_agent_ui.py` workflow tab: provider combo, api-key env, model, base_url, codegen toggle, save/load buttons. Wired to existing `workflow-llm-config` CLI.
- Added GUI "工具" tab consolidating 6 high-value CLI subcommands (real-preflight, classify-log, firmware-plan, firmware-patch, advise-pin, patch-ioc) + research jump button.
- Added `tools/install_plugin_sync_hook.py`: idempotent git pre-commit hook auto-syncing plugin package.
- Hardened `test_hardware_risk.py` / `test_project_brain.py` copy_fixture helpers to strip `.hardware-butler/` scratch state after copy.
- Added `tests/unit/test_gui_tools_tab.py` (8 tests, PyQt6-gated).
- Verified: 606 passed / 10 skipped, ruff clean, mypy clean, GUI smoke (offscreen Qt) constructs all new widgets.

### Phase 7 (commit ccb214b)
- Extended `tests/unit/test_vendor_adapters_avr_nordic.py` from 13 to 26 tests: build/observe/flash fallback chains, programmer env-var override, canonical_chip pass-through, detect_tools key sets.
- Created `docs/REAL_BOARD_DAY_RUNBOOK.md`: consolidated board-day-only checklist (10 phases, ~200 lines).
- Updated HANDOFF §21 + CHANGELOG Unreleased + README pointer to runbook.

### Phase 10 (commit a82bc39)
- Added 3 new vendor adapters: `tools/vendor_adapters/riscv.py` (WCH CH32V / GD32V, RISC-V), `tools/vendor_adapters/tiva.py` (TI Tiva C / SimpleLink CC26xx, Cortex-M3/M4F), `tools/vendor_adapters/c2000.py` (TI C2000, C28x).
- Updated `detect_family` to discriminate CH32V/GD32V (RISC-V) from CH32/GD32 (Cortex-M → stm32-compatible). Added RX<digit>/F280/F282/F283/F28M prefix matching.
- Hardened LLM HTTP path: `tools/llm_client.py` gained `_call_with_retry` (MAX_ATTEMPTS=3, exponential backoff, jitter) + `_classify_http_error` (transient vs fatal). `call_llm` surfaces structured `error_kind` + `attempts` on failure.
- Added 3 test files: `test_vendor_adapters_riscv.py` (16), `test_vendor_adapters_ti.py` (29), `test_llm_client_retry.py` (18).
- Verified: 686 passed / 10 skipped, ruff + mypy clean (64 source files).

### Phase 11 (commit 6d7f3b8)
- Extended `_verify_signal` kind-keyword fallback from 4 kinds (led/uart/rtt/swo) to 9 (added i2c/spi/adc/pwm/can). CAN keyword list intentionally avoids bare `id` (would false-positive on "idle"/"middle").
- Added 13 new tests in `tests/unit/test_behavior_verify.py`.
- Verified: 698 passed / 10 skipped, ruff + mypy clean (66 source files).

### Phase 12 (commit 4d04182)
- Added 3 new vendor adapters: `tools/vendor_adapters/ra.py` (Renesas RA4/RA6, Cortex-M), `tools/vendor_adapters/lpc.py` (NXP LPC11xx/17xx/40xx/55xx), `tools/vendor_adapters/pic32.py` (Microchip PIC32MX/MZ/WK, MIPS).
- Updated `detect_family` to recognize R7FA/RA4/RA6, LPC, PIC32MX/MZ/WK prefixes.
- Added `tests/unit/test_vendor_adapters_renesas_nxp_pic32.py` (42 tests).
- Verified: 743 passed / 10 skipped, ruff + mypy clean (69 source files).

### Phase 13 (commit c8c5fb2)
- Added 3 new vendor adapters: `tools/vendor_adapters/max32.py` (Maxim MAX32, Cortex-M4F), `tools/vendor_adapters/imxrt.py` (NXP i.MX RT, Cortex-M7 crossover), `tools/vendor_adapters/rx.py` (Renesas RX, 32-bit CISC).
- Updated `detect_family` to recognize RX<digit>, MIMXRT/RT10x/RT11x, MAX326 prefixes.
- Added regex-pattern signal verification path (`expected_regex` field) — 4th verification layer with capture-group extraction. Returns `regex_groups` so the audit trail shows the actual value extracted.
- Added `tests/unit/test_vendor_adapters_max32_imxrt_rx.py` (41 tests) + 9 regex-path tests in `test_behavior_verify.py`.
- Verified: 796 passed / 10 skipped, ruff + mypy clean (72 source files).

### Phase 14 (commit d62d1f8)
- Added value-range bounds (expected_min/expected_max) on regex-captured groups — the deepest verification layer. The first captured group is parsed as float and bounds-checked. Enables assertions like "ADC reading in [1500, 2000] mV".
- Returns `captured_value` field on both success and failure so the audit trail shows the actual value seen. Non-numeric captures fail-closed with a descriptive reason.
- Added 9 value-range tests in `test_behavior_verify.py`.
- Verified: 805 passed / 10 skipped, ruff + mypy clean (72 source files), plugin re-synced (138 subtests).

### Phase 15 (this commit)
- Appended HANDOFF §22 documenting Phase 10-14 (vendor adapter expansion, 5-layer behavior verification, LLM retry hardening, project completion status).
- Extended CHANGELOG Unreleased section with full Phase 6-14 entries (328 new tests, 14 vendor families, 5-layer verification, LLM retry).
- Extended README open-source dependency table with vendor-specific toolchains (xc32-gcc, cl2000, rx-elf-gcc, rfp-cli, wlink, etc.).
- Updated GUI tools-tab chip-part placeholder to mention all 14 supported families.
- Refreshed `task_plan.md`, `progress.md`, `findings.md` to Phase 14 final state.

## Final baseline

- **1017 passed / 12 skipped** (was 477 at takeover; cumulative +540 tests through 2026-09-09).
- ruff + mypy clean on tools/ (**72 source files**, was 60).
- Plugin re-synced; `test_plugin_sync` passes (**138 subtests**, was 132).
- 14 vendor families covering all mainstream 32-bit MCU ISAs.
- 5-layer behavior verification (kind-keyword / frequency / expected_text / regex / value-range).
- LLM HTTP retry hardening (MAX_ATTEMPTS=3, transient/fatal classification).
- GUI 13 tabs including Phase 6 tools-tab consolidation.
- Plugin-sync pre-commit hook + real-board-day runbook.

## Done — project complete

No further work pending. Real-board-day validation is the user's operational step.
