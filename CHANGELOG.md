# Changelog

All notable changes are documented here.

## Unreleased

### Added (2026-08-17 takeover session — Phase 6 through Phase 14)

The takeover session closed every non-hardware gap in the user's
"一句话需求 → 完成" goal across 8 commits (3facce5 → ccb214b → a82bc39 →
6d7f3b8 → 4d04182 → c8c5fb2 → d62d1f8). Final baseline: 805 passed / 10
skipped (was 477 at takeover; +328 tests), ruff + mypy clean on tools/
(72 source files, was 60), plugin re-synced (138 subtests).

**GUI + infrastructure (Phase 6):**

- GUI "工具" tab consolidating 6 high-value CLI subcommands (real-preflight,
  classify-log, firmware-plan, firmware-patch, advise-pin, patch-ioc) and a
  research shortcut that jumps to the existing "资料搜索" tab. Real-hardware
  actions (plan-action / execute-action) stay behind the Actions tab's
  confirmation-token flow — no new safety surface introduced.
- `tests/unit/test_gui_tools_tab.py` (8 tests, skipped when PyQt6 absent):
  tab-order stability, widget construction, handler wiring, and four
  input-validation guards.
- `tools/install_plugin_sync_hook.py`: idempotent git pre-commit hook that
  re-runs `package_hardware_butler_plugin.py` when source files change and
  auto-stages the resulting plugin diff. Eliminates the silent drift that
  `test_plugin_sync.py` only catches downstream.

**Vendor adapter expansion (Phase 10/12/13 — 9 new families, 14 total):**

- `tools/vendor_adapters/riscv.py`: WCH CH32V / GigaDevice GD32V (RISC-V
  32-bit). Build via riscv64-unknown-elf-gcc or PlatformIO wch-riscv; flash
  via wlink (preferred) or openocd; observe via pyserial UART.
- `tools/vendor_adapters/tiva.py`: TI Tiva C / SimpleLink CC26xx
  (TM4C/LM4F/CC2538/CC2650/CC2640). Build via arm-none-eabi-gcc or
  PlatformIO titiva; flash via dslite/lm4flash/openocd fallback chain.
- `tools/vendor_adapters/c2000.py`: TI C2000 (TMS320F280xx/F2837x). C28x
  architecture, no GCC port. Build via cl2000 (TI proprietary); flash via
  dslite/c2kprog; observe via pyserial UART. PlatformIO: not supported.
- `tools/vendor_adapters/ra.py`: Renesas RA4/RA6 (Cortex-M). Build via
  arm-none-eabi-gcc or PlatformIO renesas-ra; flash via J-Link (preferred,
  Renesas official), pyOCD (RA6 supported), or openocd.
- `tools/vendor_adapters/lpc.py`: NXP LPC11xx/17xx/40xx/55xx
  (Cortex-M0+/M3/M4F/M33). Build via arm-none-eabi-gcc or PlatformIO nxplpc
  (mbed framework); flash via probe-rs (preferred), pyOCD, J-Link, or openocd.
- `tools/vendor_adapters/pic32.py`: Microchip PIC32MX/MZ/WK (MIPS core).
  Build via xc32-gcc (Microchip GCC); flash via pic32prog (preferred, open
  source) or MPLAB IPE CLI; observe via pyserial UART only (PIC32 has no
  SWD/RTT). Programmer default: PICkit3 (env-overridable).
- `tools/vendor_adapters/max32.py`: Analog Devices Maxim MAX32
  (MAX32660/66/70/90, Cortex-M4F). Build via arm-none-eabi-gcc or PlatformIO
  maxim32 (mbed); flash via openocd (Maxim official), pyOCD, probe-rs, or
  J-Link; observe via probe-rs RTT or pyserial UART.
- `tools/vendor_adapters/imxrt.py`: NXP i.MX RT (RT1010/1020/1050/1060/
  1160/1170, Cortex-M7 crossover). Build via cmake+ninja, make, or
  arm-none-eabi-gcc; flash via probe-rs (Cortex-M7), pyOCD, J-Link, or
  openocd; observe via probe-rs RTT, pyOCD RTT, or UART.
- `tools/vendor_adapters/rx.py`: Renesas RX (RX65N/RX72N/RX130/RX231,
  32-bit CISC — distinct from the Cortex-M RA family). Build via rx-elf-gcc
  (open source GCC) or CC-RX (proprietary); flash via rfp-cli (Renesas Flash
  Programmer via E2 Lite probe), J-Link (RX mode), or openocd; observe via
  pyserial UART only (RX uses Renesas proprietary 1-wire debug, not SWD).
  detect_family discriminates RX<digit> from RA4/RA6/R7FA so the two
  Renesas families never collide.

`detect_family` now recognizes 14 family prefixes: STM32 / ESP32 / MSP430 /
TM4C+LM4F+CC2538/26xx (ti-tiva) / TMS320+F280+F282+F283+F28M (c2000) /
ATmega+ATtiny+ATxmega (avr) / CH32V+GD32V (riscv) / GD32+CH32
(stm32-compatible) / NRF5 (nordic) / R7FA+RA4+RA6 (ra) / RX<digit> (rx) /
LPC (lpc) / MIMXRT+RT10x+RT11x (imxrt) / PIC32MX+MZ+WK (pic32) / MAX326
(max32).

**Behavior verification (Phase 11/13/14 — 5-layer hierarchy):**

`_verify_signal` now has 5 verification paths, checked deepest-first:

1. `expected_regex` + optional `expected_min` / `expected_max` value-range
   bounds. The signal spec carries a regex with capture groups (e.g.
   `r"vbus_mv=(\d+)"`) AND optional min/max bounds on the first captured
   group. Enables assertions like "ADC reading in [1500, 2000] mV" — the
   optimize-loop can act on range violations even when the regex shape
   matches. Returns `captured_value` field on both success and failure.
   Non-numeric captures fail-closed with a descriptive reason.
2. `expected_text` — exact substring match.
3. `frequency_hz` — measures actual toggle frequency from timestamped
   captures with ±50% tolerance.
4. `kind-keyword fallback` — extended from 4 kinds (led/uart/rtt/swo) to
   9 (added i2c/spi/adc/pwm/can). The CAN keyword list intentionally
   avoids bare `id` (would false-positive on "idle"/"middle").
5. QEMU behavior emulation — runs the generated ELF and verifies behavior
   beyond keyword matching.

The regex path compiles with `re.IGNORECASE | re.MULTILINE` so LED-state
captures are robust to firmware that prints "LED" vs "led", and `^`
anchors work per-line in multi-line RTT captures.

**LLM HTTP retry hardening (Phase 10):**

`tools/llm_client.py` gained a `_call_with_retry` wrapper:

- `MAX_ATTEMPTS = 3` (1 initial + 2 retries) with exponential backoff
  (0.5s, 1s, 2s) plus a small jitter (0-0.15s).
- `_classify_http_error(exc)` returns `"transient"` for retryable failures
  (HTTP 408/429/5xx, `URLError`, `TimeoutError`, `ConnectionError`,
  `OSError`) and `"fatal"` for non-retryable failures (HTTP 4xx except
  429, `RuntimeError` for missing API key, `ValueError` for bad JSON).
- `call_llm` surfaces structured `error_kind` ("transient"|"fatal") and
  `attempts` count on failure, and an `attempts` count when retries
  eventually succeed.
- Unknown provider short-circuits before any HTTP call.

**Real-board runbook (Phase 8):**

- `docs/REAL_BOARD_DAY_RUNBOOK.md`: consolidated board-day-only checklist
  covering pre-flight, mock dry-run, board connection, bench-runbook
  generation, value-sanity gate, env-var opt-in, real workflow execution,
  failure-mode triage, post-run audit, and the safety contract paragraph.

**Tests added (Phase 6-14):**

- `tests/unit/test_gui_tools_tab.py` (8 tests, PyQt6-gated)
- `tests/unit/test_vendor_adapters_avr_nordic.py` (+13 tests, Phase 7)
- `tests/unit/test_vendor_adapters_riscv.py` (16 tests, Phase 10)
- `tests/unit/test_vendor_adapters_ti.py` (29 tests, Phase 10)
- `tests/unit/test_vendor_adapters_renesas_nxp_pic32.py` (42 tests, Phase 12)
- `tests/unit/test_vendor_adapters_max32_imxrt_rx.py` (41 tests, Phase 13)
- `tests/unit/test_llm_client_retry.py` (18 tests, Phase 10)
- `tests/unit/test_behavior_verify.py` extended with +22 regex + value-range
  + extended kind-keyword tests (Phase 11/13/14)

Total: +328 tests across 7 new files and 2 extensions.

### Fixed

- `tests/unit/test_hardware_risk.py` and `tests/unit/test_project_brain.py`
  `copy_fixture` helpers now strip `.hardware-butler/` scratch state after
  copying the fixture. Previously, ad-hoc CLI invocations against the
  fixture (e.g. `research --root tests/fixtures/cubemx-basic`) would write
  generated evidence under the fixture's `.hardware-butler/research/`,
  which the scanner then picked up — masking the "missing chip documents"
  and "missing manual" assertions in subsequent test runs.
- Re-synced plugin runtime with the latest `embeddedskills/` defensive
  assertions (`assert proc.stderr is not None` etc.) that had drifted.

### Verification

- 805 passed / 10 skipped (was 477 at takeover; +328 tests).
- ruff + mypy clean on tools/ (72 source files, was 60), gui/, tests/.
- Plugin re-synced; `test_plugin_sync` passes (138 subtests).

## 0.1.0 - GitHub Launch Candidate

First public launch candidate for Hardware Butler: a safe-first embedded
hardware development workspace that helps users understand projects before
touching real hardware.

### Added

- Safe first-day path through `guide`, `doctor`, `auto`, and `next-step`.
- No-hardware demo flow using `tests/fixtures/cubemx-basic`.
- Source-backed hardware understanding workflow covering project evidence,
  chip documents, CubeMX pin/config review, firmware planning, and bench
  runbooks.
- CLI and GUI entry points for project scanning, evidence Q&A, firmware
  planning, safety audits, and workbench status.
- GitHub CI, issue templates, pull request template, contribution guide, code
  of conduct, support policy, security policy, Dependabot, launch checklist,
  and release process.
- Read-only `github_launch_audit.py` for checking remote HEAD, GitHub About
  metadata, repository topics, and the latest `ci.yml` run.
- Codex plugin runtime packaging with source-sync drift guards.

### Changed

- README and package metadata now use the public `Hardware Butler` identity and
  the same safe-first project description as the GitHub launch settings.
- Dependencies are split into minimal runtime, development verification, UI,
  hardware, AI, reporting, and all-in optional sets.
- Generated inspection/chip outputs are ignored so first-time demo commands do
  not pollute the Git worktree.

### Safety

- Real flash, erase, reset, debug, bus writes, network scans, and long
  observation remain blocked, simulated, confirmation-gated, or planned-gated.
- Hardware tests remain opt-in behind `--run-hardware`.
- Clean GitHub clones can use the bundled
  `plugins/hardware-development-butler/scripts/embeddedskills/` runtime mirror
  without requiring the ignored root `embeddedskills/` checkout.

### Launch Gates

- Push local launch commits to `main`.
- Set GitHub About description, homepage, and topics from
  `docs/GITHUB_REPOSITORY_SETTINGS.md`.
- Wait for `ci.yml` to pass on `main`.
- Rerun `python tools\github_launch_audit.py --json` and require
  `"status": "ok"` before tagging `v0.1.0`.
