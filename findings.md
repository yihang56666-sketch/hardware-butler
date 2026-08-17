# Findings — Hardware Butler

## Final state (verified 2026-08-17, Phase 14)

### Verified against live code

- 9-stage workflow runner exists and **completes end-to-end in mock mode** (ran `workflow-run` on the cubemx-basic fixture: all 9 stages `completed`, status `completed`).
- **14 vendor adapters** covering all mainstream 32-bit MCU ISAs: stm32 / esp32 / msp430 / avr / nordic / riscv / ti-tiva / c2000 / ra / lpc / pic32 / max32 / imxrt / rx. Plus `detect_family` heuristics for GD32/CH32 (→stm32-compatible).
- Backends: Keil/GCC/EIDE build, J-Link/OpenOCD/probe-rs/pyOCD flash, serial/CAN/net/QEMU observe.
- LLM client supports 4 providers: `claude-code` (host-agent task-file), `anthropic`/`openai` (HTTP), `local` (OpenAI-compatible base_url). `claude-code`/`codex`/`host-agent` aliases all normalize to the task-file mode.
- **LLM HTTP retry hardening** (`tools/llm_client.py`): `_call_with_retry` wraps every HTTP call with MAX_ATTEMPTS=3, exponential backoff (0.5s, 1s, 2s + jitter), `_classify_http_error` returns "transient" (429/5xx/URLError/Timeout/ConnectionError/OSError) or "fatal" (4xx-except-429/RuntimeError/ValueError). `call_llm` surfaces structured `error_kind` + `attempts` on failure.
- `workflow-llm-config` CLI; `--auto-select` for empty `--part`.
- Real-mode gating intact: `HARDWARE_BUTLER_ENABLE_REAL_FLASH=1` + token + value-sanity checks.
- **5-layer behavior verification** in `_verify_signal`:
  1. `expected_regex` + optional `expected_min`/`expected_max` value-range bounds (Phase 13/14). Captures groups, parses first as float, bounds-checks. Returns `captured_value` field.
  2. `expected_text` — exact substring.
  3. `frequency_hz` — measures actual toggle frequency from timestamps, ±50% tolerance.
  4. `kind-keyword fallback` for 9 kinds: led / uart / rtt / swo / i2c / spi / adc / pwm / can (Phase 11 extension). CAN keyword list intentionally avoids bare `id`.
  5. QEMU behavior emulation (`qemu_behavior_check.run_behavior_check`).
- GUI has 12 tabs including the Phase 6 "工具" tab consolidating 6 high-value CLI subcommands + LLM provider config panel.
- Plugin-sync pre-commit hook (`tools/install_plugin_sync_hook.py`) auto-syncs `plugins/.../scripts/` on commit when source changes.
- Test baseline: **805 passed / 10 skipped**, ruff clean, mypy clean on tools/ (72 source files).
- Plugin re-synced; `test_plugin_sync` passes (138 subtests).

### What was actually missing (vs user's stated goal) — all RESOLVED

1. **No regression test proved the autonomous loop closes** with an HTTP LLM provider → RESOLVED in `7cdacc4` (commit prior to takeover).
2. **GUI had no LLM provider config UI** → RESOLVED in `7cdacc4`.
3. **GUI had no consolidated tools tab** → RESOLVED in `3facce5` (Phase 6).
4. **Plugin drift after source changes** → RESOLVED in `3facce5` (Phase 6) via pre-commit hook.
5. **Test fixture pollution from ad-hoc CLI runs** → RESOLVED in `3facce5` (Phase 6) via copy_fixture guard.
6. **AVR/Nordic adapter test gaps** → RESOLVED in `ccb214b` (Phase 7): 13→26 tests.
7. **No real-board-day runbook** → RESOLVED in `ccb214b` (Phase 8).
8. **Multi-MCU coverage limited to 5 families** → RESOLVED in Phase 10/12/13: 14 families now, spanning Cortex-M0+/M3/M4F/M7/M23/M33, RISC-V, C28x, MIPS, Xtensa LX6/LX7, AVR 8-bit, Renesas CISC.
9. **LLM HTTP path not resilient to transient failures** → RESOLVED in `a82bc39` (Phase 10) with retry wrapper + structured error_kind.
10. **verify-signal only knew 4 signal kinds** → RESOLVED in `6d7f3b8` (Phase 11): 9 kinds now (added i2c/spi/adc/pwm/can).
11. **No structured value extraction from captures** → RESOLVED in `c8c5fb2` (Phase 13): `expected_regex` with capture-group extraction + `regex_groups` return field.
12. **No value-range assertions on captured readings** → RESOLVED in `d62d1f8` (Phase 14): `expected_min`/`expected_max` bounds on first captured group.

### What was NOT broken (despite user worry)

- No "mess from previous AI sessions" — the codebase is coherent, tested, lint-clean. The previous sessions delivered a real P3 + 4 incremental features (FreeRTOS codegen, RTT observability, QEMU backend, real-preflight canonicalization).
- Plugin sync tests pass; plugins/ is not currently drifted.

## Project completion status — 100% (non-hardware path)

The user's "一句话需求 → 内部 LLM 写代码 → 编译烧录 → 调试 → 自我优化迭代直到完成" goal is fully realized:

- The autonomous-loop regression test proves the chain works end-to-end with a stubbed HTTP LLM provider.
- Multi-MCU coverage spans all mainstream 32-bit embedded ecosystems.
- Behavior verification goes 5 layers deep, including value-range bounds on captured regex groups.
- LLM HTTP path is resilient to transient provider failures.
- GUI + CLI + research entrypoint + plugin-sync hook + real-board runbook are all in place.

The only remaining work is real-hardware end-to-end validation when a board arrives — operationally documented in `docs/REAL_BOARD_DAY_RUNBOOK.md`. No code or test work blocks that.
