# Hardware Butler Workflow — Handoff Document

This document is for any AI or developer taking over the project. It covers
the goal, current architecture, what is implemented, what is missing, and
the exact next steps. After reading this you should be able to continue
the work without further context.

Original design doc: [docs/WORKFLOW_RUNNER_DESIGN.md](WORKFLOW_RUNNER_DESIGN.md)
Architecture map: [docs/ARCHITECTURE_MAP.md](ARCHITECTURE_MAP.md)

---

## 1. Project Goal

**User's original ask (verbatim):**

> Build a workflow: user states a requirement, the system plans, searches
> chips and board/module documentation, then implements, compiles, flashes,
> auto-debugs, optimizes code, until the goal is achieved after flashing.
> Must be flexible — not limited to STM32. Could also be TI, ESP32.

**Current positioning:** Upgrade the existing 36 CLI commands from a "parts
library" into a goal-driven state machine + vendor adapter abstraction layer
(multi-MCU family support) + LLM interface (user-configured).

**Core differentiators:**
- Safety-first: goal_token + audit log + fail-closed
- Evidence-driven: outputs label verified / inferred / unknown, never LLM memory
- Multi-MCU family flexibility: STM32 / ESP32 / MSP430 + extensible via JSON-like adapter files

---

## 2. Repository Layout

```text
d:/一些有用的项目/硬件agent/
├── tools/                          # Main CLI + workflow engine
│   ├── hardware_butler.py          # CLI entry (36 subcommands)
│   ├── workflow_runner.py          # 9-stage state machine (CORE)
│   ├── backend_detector.py         # Backend probe + vendor adapter routing
│   ├── vendor_adapters/            # Multi-MCU family adapters
│   │   ├── __init__.py             # VendorAdapter base + registry
│   │   ├── stm32.py                # STM32 adapter (done)
│   │   ├── esp32.py                # ESP32 adapter (done)
│   │   └── msp430.py               # TI MSP430 adapter (done)
│   ├── llm_client.py               # LLM call layer
│   ├── llm_config.py               # LLM config management
│   └── ... (42 .py modules total)
├── embeddedskills/                 # Per-MCU backend scripts (separate .git)
│   ├── safety_gate.py              # goal_token implementation (CORE)
│   ├── keil/scripts/               # Keil build backend
│   ├── gcc/scripts/                # GCC build backend
│   ├── jlink/scripts/              # J-Link flash/debug
│   ├── openocd/scripts/            # OpenOCD flash/debug
│   ├── probe-rs/scripts/           # probe-rs flash/debug
│   ├── serial/scripts/             # Serial observe
│   ├── can/scripts/                # CAN bus
│   └── net/scripts/                # Network debug
├── tests/
│   ├── fixtures/cubemx-basic/      # Minimal STM32 fixture for end-to-end tests
│   └── unit/
│       ├── test_workflow_runner.py # 9 stages + retry loop tests
│       ├── test_goal_token.py      # goal_token mint/check/reuse tests
│       ├── test_vendor_adapters.py # adapter family detection + command gen
│       └── ... (30 test files)
├── docs/                           # All design + usage docs
└── .hardware-butler/               # Runtime state (workflow-state.json etc.)
```

---

## 3. The 9-Stage Workflow State Machine

Defined in [tools/workflow_runner.py](../tools/workflow_runner.py).
State persists to `.hardware-butler/workflow-state.json` after every stage
transition. Supports `--resume` from the last completed stage.

```text
requirement-parse     # Parse natural language goal -> structured context
        |
chip-selection        # Verify/resolve chip part -> family + backends
        |
datasheet-collect     # Fetch + summarize chip datasheet (LLM task package)
        |
cubemx-config         # advise-pin + patch-ioc dry-run (STM32 only)
        |
firmware-plan         # Generate HAL/FreeRTOS firmware plan
        |
build                 # Generate build plan + (if tools present) real build
        |
flash                 # bench-runbook + plan-action + goal_token + (if env) real flash
        |
debug-observe         # sim mode by default; real serial/RTT if env set
        |
verify-goal           # Behavior keyword match against observations
```

### Optimize-loop

When `verify-goal` fails (status=failed) and `attempts < MAX_STAGE_ATTEMPTS`
(default 3), the runner resets 5 stages (`firmware-plan` through `verify-goal`)
back to `pending` and re-iterates. `attempts` counters are preserved so the
total tries are bounded. Other failures (missing evidence, safety block)
return immediately — they need user input.

### Stage status values

- `pending` — not started
- `running` — in progress
- `completed` — evidence collected, proceed to next stage
- `failed` — stage failed; if verify-goal and retries remain, optimize-loop triggers
- `blocked-needs-input` — missing required context, user must provide
- `paused` — awaiting confirmation (e.g. goal_token approval)

---

## 4. Vendor Adapter System (Multi-MCU Support)

This is the key to "flexible, not limited to STM32". Defined in
[tools/vendor_adapters/](../tools/vendor_adapters/).

### Base class

[tools/vendor_adapters/__init__.py](../tools/vendor_adapters/__init__.py)
defines `VendorAdapter` (frozen dataclass) with these methods:

- `detect_tools()` — probe host for this vendor's tools, returns `{tool_name: bool}`
- `build_command(ctx)` — return argv list to build firmware
- `flash_command(ctx)` — return argv list to flash firmware
- `observe_command(ctx)` — return argv list to observe (serial/RTT/ITM)
- `datasheet_queries(part)` — return search query strings for datasheet-collect stage
- `to_dict()` — serialize for evidence

### Family detection

`detect_family(part)` maps a chip part number to its vendor family:

- `STM32xx` -> `stm32`
- `ESP32-xx` / `ESP8266` -> `esp32`
- `MSP430xx` -> `msp430`
- `TM4C` / `LM4F` / `CC2538` / `CC26xx` -> `ti-tiva`
- `TMS320` / `F280xx` -> `c2000`
- `ATmega` / `ATtiny` / `ATxmega` -> `avr`
- `GD32` / `CH32` (Cortex-M) -> `stm32` (compatible)
- `NRF5xx` -> `nordic`
- else -> `""` (unknown)

### Existing adapters

| Family | File | Build tool | Flash tool | Observe tool |
|---|---|---|---|---|
| stm32 | stm32.py | arm-none-eabi-gcc + cmake/ninja | pyOCD / STM32_Programmer_CLI / openocd / JLink / st-flash | serial (miniterm) |
| esp32 | esp32.py | idf.py | esptool.py | idf.py monitor / serial |
| msp430 | msp430.py | msp430-gcc + make | mspdebug / dslite | serial |

### How to add a new vendor (e.g. AVR, Nordic, RISC-V)

1. Create `tools/vendor_adapters/<family>.py`
2. Define a subclass of `VendorAdapter` with vendor_id, family, display_name,
   build_tool, flash_tool, observe_tool, datasheet_term
3. Override `detect_tools()`, `build_command()`, `flash_command()`,
   `observe_command()`, `datasheet_queries()`
4. Call `register_adapter(YourAdapter())` at module bottom
5. Import it in `tools/backend_detector.py` and `tools/workflow_runner.py`
6. Add family to `detect_family()` in `__init__.py` if part-number heuristic needed
7. Add a test in `tests/unit/test_vendor_adapters.py`

### How the runner uses adapters

In [tools/workflow_runner.py](../tools/workflow_runner.py), the function
`_get_vendor_adapter(state)` resolves the adapter from chip-selection stage
evidence or context.part. The `build`, `flash`, `debug-observe` stages call
`adapter.build_command(ctx)` etc. and execute via `_run_subprocess(cmd)`.
If no adapter matches, falls back to embeddedskills scripts (Keil/GCC/EIDE).

---

## 5. Goal Token Security Model

Defined in [embeddedskills/safety_gate.py](../embeddedskills/safety_gate.py).

### Two coexisting token types

| Property | `confirmation_token` (existing) | `goal_token` (new) |
|---|---|---|
| Derivation | sha256 of public plan fields (deterministic) | `secrets.token_hex` (cryptographically random) |
| Scope | single action, single record | multiple actions within a workflow_id |
| Reuse | one-shot (replay-blocked via `consume_token`) | up to `max_uses` uses |
| Expiry | no explicit expiry | `expires_at` enforced |
| Cross-workflow | not applicable | blocked with `error_code: cross_workflow` |
| Use case | human-in-the-loop single flash | automated workflow with repeated flash |

### API

- `mint_goal_token(workflow_id, scope, max_uses, ttl_seconds)` -> returns
  plaintext token + public record (token_hash, scope, max_uses, expires_at).
  Plaintext is kept in-memory for the session.
- `check_goal_token(workspace, workflow_id, token, record, action, consume)`
  -> validates against safety log. Blocks on: `invalid_token`,
  `cross_workflow`, `out_of_scope`, `expired`, `exhausted`. When `consume=True`
  and allowed, appends a `goal-token-use` event to `safety-log.jsonl`.

### Defaults

- `max_uses=5`
- `ttl_seconds=3600` (1 hour)
- scope: `"build-flash-debug"`

### Where the runner uses it

In `_stage_flash`, the runner calls `mint_goal_token` on first entry. The
public record is persisted to `workflow-state.json["goal_token"]`. On resume,
the existing token is reused and `uses` is incremented. Exhaustion blocks
the next flash with `error_code: exhausted` and surfaces as `failed` stage.

---

## 6. LLM Integration

### Config

- [tools/llm_config.py](../tools/llm_config.py) manages LLM provider config
- Config file: `.hardware-butler/llm-config.json` (user-edited)
- Supported providers: `claude-code` (default, uses host agent), `anthropic`, `openai`
- For `anthropic`/`openai`: user provides `api_key` and `model` in config
- For `claude-code`: no key needed, LLM runs through the host agent (me)

### Client

- [tools/llm_client.py](../tools/llm_client.py) — single `complete(prompt, system)` function
- Reads config via `llm_config.load_config()`
- For `claude-code` provider: writes prompt to `.hardware-butler/llm-tasks/<task-id>.json`
  and waits for the host agent to write a response file. The host agent (Claude
  Code in the session) is expected to execute the task and write back the result.
- For `anthropic`/`openai`: makes a direct HTTP API call

### Where the workflow uses LLM

1. **requirement-parse stage** — Parse natural language goal into structured
   context (feature/pin/function/instance). When LLM provider is `claude-code`,
   it generates a task package for the host agent to execute.
2. **optimize-loop** — When `verify-goal` fails, LLM analyzes the failure
   (build log + observe result) and suggests context patches (e.g. wrong pin,
   wrong function). The runner applies `patch_fields` to workflow context
   and retries.

### How to configure for testing

For testing without an API key, set provider to `claude-code`:

```json
{"provider": "claude-code", "model": "claude-sonnet-4-6"}
```

The host Claude Code agent will execute LLM tasks. For production, switch to:

```json
{"provider": "anthropic", "api_key": "sk-ant-...", "model": "claude-sonnet-4-5"}
```

---

## 7. Current Status — What Is Done

### Done and tested

| Component | Status | Test file |
|---|---|---|
| 9-stage state machine | Done | test_workflow_runner.py (13 tests pass) |
| goal_token mint/check/reuse | Done | test_goal_token.py |
| Vendor adapters (STM32/ESP32/MSP430) | Done | test_vendor_adapters.py (15 tests pass) |
| backend_detector with adapter routing | Done | covered in test_vendor_adapters.py |
| LLM config + client (claude-code/anthropic/openai) | Done | test_llm_config.py |
| workflow-state.json persistence + resume | Done | covered in test_workflow_runner.py |
| optimize-loop retry on verify-goal failure | Done | covered in test_workflow_runner.py |
| sim-mode debug-observe | Done | covered in test_workflow_runner.py |
| behavior keyword match in verify-goal | Done | covered in test_workflow_runner.py |

### Done but not wired into workflow

- `firmware_code_patcher.py` — exists as a CLI command (`firmware-patch` /
  `firmware-integrate`) but NOT called from the workflow runner. The workflow
  only generates plans, not actual .c/.h files.
- `chip-dossier` / `summarize-manual` CLI commands exist but workflow's
  `datasheet-collect` stage generates LLM task packages instead of calling
  them directly.

### CLI commands (36 total)

Run `python tools/hardware_butler.py capabilities --json` for the full list.
Key commands for the workflow:

- `workflow-run --root <project> --intent develop-feature --goal "..." --json`
- `workflow-status --root <project> --json`
- `workflow-resume --root <project> --json`
- `workflow-parse-requirement --goal "..." --json`
- `workflow-llm-task --task-file <path> --json`

### Environment variables

- `HARDWARE_BUTLER_ENABLE_REAL_FLASH=1` — enable real flash execution
  (otherwise flash stage produces runbook only)
- `HARDWARE_BUTLER_LLM_PROVIDER=claude-code|anthropic|openai`
- `HARDWARE_BUTLER_LLM_API_KEY=<key>` (for anthropic/openai)
- `HARDWARE_BUTLER_LLM_MODEL=<model-id>`

---

## 8. Gaps — What Is Missing

### Critical gaps (block "real automation")

1. **Real firmware code generation** — `firmware-plan` stage outputs a plan
   (HAL handle, init function, callbacks, integration hooks), NOT actual
   .c/.h source code. `firmware_code_patcher.py` exists as a CLI command but
   is NOT called from the workflow. The workflow never writes actual firmware
   source files. This is the biggest gap between "scaffold" and "tool".

2. **Real datasheet fetch** — `datasheet-collect` stage generates an LLM
   task package asking the host agent to do web_search + open_url. The runner
   itself does not perform network I/O. This means the workflow cannot run
   headless; it requires a host agent (like Claude Code) to execute the LLM
   tasks manually.

3. **Real behavior verification** — `verify-goal` only does keyword matching
   (goal contains "led" -> check if debug-observe has led signal observation).
   It does NOT verify real behaviors like "LED blinks at 2Hz" or "UART outputs
   expected string". Sim-mode debug-observe always returns `matched: True`,
   so verify-goal always passes in sim mode — this is a fake pass.

4. **Real chip selection** — `chip-selection` stage only validates a
   user-declared part number. It does NOT do "user describes requirement ->
   recommend chip". nextboard subproject has part-selection capability but
   is NOT wired into the workflow.

5. **End-to-end hardware validation never done** — The full workflow has
   never been run against real hardware. All "real" stages (build/flash/
   debug-observe) are either plan-only or sim-mode in tests. Adapter command
   arguments (pyOCD target name, openocd config, esptool flash address) are
   unverified against real boards.

### Non-critical gaps (engineering debt)

6. **plugins/ duplicate copy** — `plugins/hardware-development-butler/`
   contains a copy of tools/, embeddedskills/, nextboard/. Changes to source
   must be re-synced via `python tools/package_hardware_butler_plugin.py`.
   Currently the vendor_adapters/ files are NOT synced — plugin_sync tests
   fail. Fix: re-run the packaging script.

7. **embeddedskills has no pytest** — backend scripts (keil_build.py etc.)
   only validate via JSON `status: ok` output. No regression tests. Adding
   pytest to embeddedskills/ would require either a separate test runner
   or restructuring (embeddedskills has its own .git).

8. **Code coverage ~68%** — below the 80% baseline. Critical paths like
   real-backend block, token consumption ledger, replay prevention need
   more tests.

9. **nextboard subproject disconnected** — nextboard/ has its own agents,
   skills, hooks, scripts. It is NOT wired into the tools/ workflow.
   Part selection -> tools verification -> embeddedskills flash is not a
   continuous data flow.

10. **GUI not covering all 36 CLI commands** — see
    [docs/WORKBENCH_FEATURE_COVERAGE.md](WORKBENCH_FEATURE_COVERAGE.md).
    The PyQt6 workbench (gui/hardware_agent_ui.py, ~1746 lines) covers a
    subset of CLI commands.

---

## 9. Next Steps — Concrete Actions

### Priority order (by ROI)

#### Step A: Re-sync plugin package (engineering debt, 5 minutes)

The vendor_adapters/ directory was added but not synced to the plugin copy.
This causes `tests/unit/test_plugin_sync.py` to fail.

```bash
cd "d:/一些有用的项目/硬件agent"
python tools/package_hardware_butler_plugin.py
python plugins/hardware-development-butler/scripts/validate_package.py
pytest tests/unit/test_plugin_sync.py -q --no-cov
```

Expected: all plugin_sync tests pass.

#### Step B: Wire firmware_code_patcher into the workflow (P3 critical)

This is the single biggest gap. Currently `firmware-plan` stage only outputs
a plan dict. It does NOT call `firmware_code_patcher.py` to actually write
.c/.h files.

**Where to edit**: [tools/workflow_runner.py](../tools/workflow_runner.py)
function `_stage_firmware_plan`.

**What to do**:

1. Read the existing `firmware_code_patcher.py` API — it has a function
   like `generate_patch(root, feature, pin, function, ...) -> dict`.
2. After the current `firmware_intent_planner.plan_implementation(...)` call
   in `_stage_firmware_plan`, also call `firmware_code_patcher.generate_patch(...)`
   with `--write --confirm-write` semantics (or a workflow-local equivalent
   that writes to `<project-root>/firmware-modules/<feature>/`).
3. Capture the patch result as additional evidence:
   `evidence["firmware_patch"] = patch_result`.
4. If `firmware_code_patcher` writes files, gate the write behind
   `safe_io.validate_write_path()` and `runtime_context.allowed_write_roots()`.
5. Update `tests/unit/test_workflow_runner.py` to assert that
   `firmware-plan` stage evidence includes a `firmware_patch` field.

**Acceptance**: Running the workflow on `tests/fixtures/cubemx-basic` with
feature=`led-blink` produces actual .c/.h files under
`<project-root>/firmware-modules/led-blink/`.

#### Step C: Real datasheet fetch via web_search (P3 critical)

Currently `datasheet-collect` generates an LLM task package and waits for
the host agent. This breaks headless automation.

**Where to edit**: [tools/workflow_runner.py](../tools/workflow_runner.py)
function `_stage_datasheet_collect`.

**What to do**:

1. Add a new module `tools/web_fetcher.py` with a function
   `search_and_fetch(queries: list[str], out_dir: Path) -> dict` that:
   - Calls a search API (start with DuckDuckGo HTML scraper — no API key needed)
   - For each result URL, downloads the content (limit to PDF + HTML)
   - Saves to `out_dir/datasheet-<n>.<ext>`
   - Returns `{queries, results: [{url, title, saved_path, content_type}]}`
2. In `_stage_datasheet_collect`, call
   `adapter.datasheet_queries(part)` to get vendor-specific search terms,
   then call `web_fetcher.search_and_fetch(queries, out_dir)`.
3. For PDF parsing, reuse the existing `chip_dossier.py` PDF extraction logic.
4. Keep the LLM task package as a fallback when web fetch fails (offline
   mode, no network).

**Acceptance**: Running the workflow with `context.part="STM32F407VGT6"`
fetches at least one PDF or HTML datasheet to
`<project-root>/.hardware-butler/datasheets/`.

#### Step D: Real behavior verification (P3 critical)

Currently `verify-goal` does keyword matching. Need real behavioral checks.

**Where to edit**: [tools/workflow_runner.py](../tools/workflow_runner.py)
function `_stage_verify_goal`.

**What to do**:

1. Extend `_expected_signals(firmware_plan)` to extract concrete
   verification criteria from the firmware plan's `verification` field.
   E.g. "LED on PD12 toggles at 2Hz" -> `{kind: "led", pin: "PD12", frequency_hz: 2}`.
2. In `_stage_debug_observe`, when `HARDWARE_BUTLER_ENABLE_REAL_FLASH=1` and
   observe mode is real serial/RTT, capture a 5-second window of output.
   Parse the capture for the expected signal pattern (e.g. for LED, look
   for "toggle" or "on/off" markers in RTT output; for UART, look for the
   expected string).
3. In `_stage_verify_goal`, instead of just keyword matching, call a new
   `_verify_signal(expected, observed_capture)` function that checks
   whether the observed capture actually contains evidence of the expected
   signal.
4. Only when `HARDWARE_BUTLER_ENABLE_REAL_FLASH` is NOT set, fall back to
   the current sim-mode keyword matching.

**Acceptance**: With real flash + serial observe enabled, and a firmware
that prints "LED toggled" over UART, `verify-goal` returns
`verification_level: "behavior-real"` with `matched: ["led"]` based on
actual UART capture content.

#### Step E: Real chip selection (P3)

Currently `chip-selection` only validates user-declared part. Need
"requirement -> recommended chip" via LLM.

**Where to edit**: [tools/workflow_runner.py](../tools/workflow_runner.py)
function `_stage_chip_selection`.

**What to do**:

1. Add a new stage mode: when `context.part` is empty, the stage calls
   LLM with the user's goal + a prompt asking for chip recommendations.
2. LLM returns a list of candidate parts with reasoning.
3. Stage writes `evidence["candidates"] = [...]` and marks status as
   `blocked-needs-input` (user must pick one).
4. User re-runs workflow with `--part <chosen>`.
5. When `context.part` is set, current validation logic runs as before.

**Acceptance**: Running `workflow-run --goal "I want a low-power MCU with
BLE and 256KB flash"` with no `--part` produces a candidate list of 3-5
chips (e.g. nRF52832, ESP32-C3, STM32WB55) in the stage evidence.

#### Step F: End-to-end hardware validation (P3, requires real board)

This step needs you to plug in a real board and run the full workflow.

**Prerequisites**: Pick one board you own (e.g. STM32 Nucleo, ESP32 dev
kit, or MSP430 LaunchPad). Install its toolchain (arm-none-eabi-gcc for
STM32, ESP-IDF for ESP32, msp430-gcc for MSP430).

**What to do**:

1. Set env: `HARDWARE_BUTLER_ENABLE_REAL_FLASH=1`
2. Run: `python tools/hardware_butler.py workflow-run --root <project>
   --intent develop-feature --goal "LED blink on <pin>" --feature led-blink
   --pin <pin> --function gpio-output --part <chip> --json`
3. Watch the workflow progress through all 9 stages.
4. If `build` stage fails: read `build_log` in evidence, fix adapter
   command parameters (e.g. wrong target name for pyOCD).
5. If `flash` stage fails: check `flash_result.stderr`. Common issues:
   - pyOCD target name mismatch (e.g. `STM32F407VG` vs `stm32f407vg`)
   - probe not connected / driver issue
   - goal_token exhausted (increase `max_uses`)
6. If `debug-observe` fails: check `observe_result.stderr`. Common issues:
   - wrong serial port (set `context.probe` to COM port on Windows)
   - baud rate mismatch
7. If `verify-goal` fails: check `unmet` list. LLM optimize-loop should
   suggest context patches (e.g. wrong pin).

**Acceptance**: Full 9-stage workflow completes with `status: completed`
and `verify-goal` returns `verification_level: "behavior-real"` with real
UART/RTT capture evidence.

---

## 10. How to Run the Workflow Right Now

### Prerequisites

```bash
cd "d:/一些有用的项目/硬件agent"
python -m pip install -e .
```

### Sim-mode end-to-end (no hardware needed)

```bash
# Use the bundled fixture
python tools/hardware_butler.py workflow-run \
  --root tests/fixtures/cubemx-basic \
  --intent develop-feature \
  --goal "LED blink on PD12" \
  --feature led-blink \
  --pin PD12 \
  --function gpio-output \
  --json
```

Expected output: all 9 stages complete, status `completed`. State written
to `tests/fixtures/cubemx-basic/.hardware-butler/workflow-state.json`.

### Real-mode end-to-end (requires toolchain + board)

```bash
# Set env vars
export HARDWARE_BUTLER_ENABLE_REAL_FLASH=1
export HARDWARE_BUTLER_LLM_PROVIDER=claude-code
export HARDWARE_BUTLER_LLM_MODEL=claude-sonnet-4-6

# Run with real chip
python tools/hardware_butler.py workflow-run \
  --root <your-project> \
  --intent develop-feature \
  --goal "实现 LED 闪烁" \
  --feature led-blink \
  --pin PD12 \
  --function gpio-output \
  --part STM32F407VGT6 \
  --probe stlink-v3 \
  --json
```

### Check status / resume

```bash
python tools/hardware_butler.py workflow-status --root <project> --json
python tools/hardware_butler.py workflow-resume --root <project> --json
```

### Run tests

```bash
cd "d:/一些有用的项目/硬件agent"
ruff check tools/ tests/
mypy tools/ --config-file mypy.ini
pytest tests/unit/ -v --no-cov
```

### Known test failures (as of last run)

- `tests/unit/test_plugin_sync.py` — vendor_adapters/ not synced to plugin
  copy. Fix: Step A above.
- `tests/unit/test_project_brain.py::test_build_project_brain_detects_identity_evidence_gaps_and_risks`
  — pre-existing failure, unrelated to workflow changes.
- `tests/unit/test_project_scanner.py::test_write_output_allows_workspace_paths`
  — pre-existing failure, unrelated to workflow changes.

---

## 11. Key Design Decisions (for context)

1. **State machine over agent loop** — deterministic, auditable, resumable.
   LLM is only called for intent parsing and failure analysis, not for
   deciding what stage to run next.

2. **Goal-level token, not keyless** — User explicitly rejected HMAC token
   upgrade in an earlier session, but goal_token was added as a compromise:
   cryptographically random, workflow-scoped, bounded reuse. The plaintext
   token stays in-memory for the session (acceptable for P1; P2 should move
   to a session-kept secret store).

3. **Vendor adapters, not PlatformIO** — User wanted direct integration of
   each ecosystem's native tools (STM32CubeCLT, ESP-IDF, Code Composer
   Studio), NOT a middleware like PlatformIO. Adapters are thin declaration
   layers; the runner fills in context and executes via subprocess.

4. **LLM config is user-managed** — User explicitly wanted LLM provider/key
   to be user-configured. For testing, `claude-code` provider uses the host
   agent (me) as LLM, no API key needed.

5. **Datasheet search uses host agent's web capability** — User pointed out
   that the host AI (Claude Code) already has web_search/open_url tools.
   No need to integrate a separate search API. Step D above proposes adding
   a direct `web_fetcher.py` for headless mode, but the LLM-task-package
   approach remains as fallback.

6. **Safety model is fail-closed** — Any stage that cannot collect sufficient
   evidence or pass safety checks returns `failed` or `blocked-needs-input`,
   never degrades silently. `HARDWARE_BUTLER_ENABLE_REAL_FLASH=1` must be
   explicitly set; default is plan-only / sim-mode.

---

## 12. File Index (most important)

| File | Purpose |
|---|---|
| tools/workflow_runner.py | 9-stage state machine, optimize-loop, stage dispatch |
| tools/backend_detector.py | Host + project probe, vendor adapter routing |
| tools/vendor_adapters/__init__.py | VendorAdapter base class + registry + detect_family |
| tools/vendor_adapters/stm32.py | STM32 adapter |
| tools/vendor_adapters/esp32.py | ESP32 adapter |
| tools/vendor_adapters/msp430.py | TI MSP430 adapter |
| tools/llm_client.py | LLM call layer (claude-code/anthropic/openai) |
| tools/llm_config.py | LLM config management |
| tools/firmware_intent_planner.py | Firmware plan generation |
| tools/firmware_code_patcher.py | Firmware code patch (NOT wired into workflow — Step B) |
| tools/bench_runbook.py | No-hardware runbook generation |
| tools/hardware_action_plan.py | Safety action plan + single-use token |
| embeddedskills/safety_gate.py | goal_token + confirmation_token + safety log |
| tools/hardware_butler.py | CLI entry (36 subcommands) |
| tests/unit/test_workflow_runner.py | 13 tests covering all 9 stages + retry loop |
| tests/unit/test_goal_token.py | goal_token tests |
| tests/unit/test_vendor_adapters.py | adapter family detection + command gen tests |
| tests/unit/test_llm_config.py | LLM config tests |
| tests/fixtures/cubemx-basic/ | Minimal STM32 fixture for end-to-end tests |

---

## 13. Contact Context

This project is at `d:/一些有用的项目/硬件agent/` on Windows 11. The user
is Yihang56666-sketch on GitHub. The repo is a container for STM32/CubeMX/
Keil/CMake projects — real hardware projects should be placed under this
workspace as `<project-root>` and analyzed by the tools.

The user's host machine has: cmake, ninja, pyocd, Python 3.13. It does NOT
have arm-none-eabi-gcc, ESP-IDF, or TI tools on PATH (STM32CubeCLT paths
are in PATH but the directories appear empty — likely uninstalled). For
real hardware validation, the user needs to install the relevant toolchain
or point the workflow at a project that already has its toolchain
configured.

---

End of handoff document. If you are an AI taking over this project, start
by reading sections 8 (gaps) and 9 (next steps), then pick a step and
execute. The most impactful single step is Step B: wiring
`firmware_code_patcher` into the workflow — that is the difference between
"scaffold" and "tool".
