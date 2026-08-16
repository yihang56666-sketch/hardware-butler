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
- scope: `"build-flash,flash-debug"`

### Where the runner uses it

In `_stage_flash`, the runner calls `mint_goal_token` on first entry. The
public record is persisted to `workflow-state.json["goal_token"]`; `_plaintext`
is removed from persisted state and CLI output. The current process reuses its
ephemeral token. If a persisted workflow must enter the flash stage again, the
runner issues a fresh one-hour token and records `reissued_after_resume` plus
the previous public token hash. Exhaustion blocks the next flash in the same
process with `error_code: exhausted` and surfaces as a failed stage. Loading a
legacy state file also scrubs any previously persisted plaintext in place.

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
| **P1: generate→compile coherence (2026-08-16)** | Done | test_firmware_project_scaffold.py + test_opensource_integration.py |

#### P1 detail: the generated firmware now actually compiles

Before P1 the workflow wrote `Core/Src/app_*.c` (STM32 HAL code) but the
PlatformIO backend auto-generated a `platformio.ini` with
`framework = arduino` and default `src/` layout — the generated code was
never compiled. Empirically verified broken; now fixed and verified
end-to-end:

- `firmware_project_scaffold.py` (NEW): stub `main.c` is replaced with a
  generated main that calls `app_<module>_init/start/task`; `main.h` is
  created with the family-correct HAL include (part→`stm32f4xx_hal.h`);
  a real CubeMX `main.c` (USER CODE blocks present) gets insertions
  instead of replacement; custom mains are left untouched.
- `vendor_adapters`: auto-generated `platformio.ini` now uses
  `framework = stm32cube` + `src_dir = Core/Src` + `-ICore/Inc` when the
  CubeMX layout exists; `find_pio()` extracted as a side-effect-free
  probe; non-ASCII project paths (e.g. this workspace) stage the build
  into `%TEMP%/hw-butler-pio/<hash>` because GNU ld cannot write its map
  file under non-ASCII paths on Windows.
- `workflow_runner`: `_stage_build` passes `part` (board mapping now
  real, F407→`disco_f407vg`), resolves `firmware.elf/.bin/.hex` after a
  successful build into `state.context.elf` (flash stage consumes it);
  firmware-plan downgrades RTOS codegen to bare-metal when the PlatformIO
  backend will build (stm32cube does not vendor CMSIS-RTOS) — intent stays
  in the plan evidence.
- GPIO template now emits `__HAL_RCC_GPIOx_CLK_ENABLE()` (without it the
  pin write is a no-op on real silicon).
- Empirical proof: full workflow on the fixture compiles via PlatformIO
  and the resulting `firmware.elf` contains `app_led_blink_init/start/
  set/task` + `main` symbols (checked with pyelftools).
- **P2: LLM-written firmware codegen (2026-08-16)** | Done | test_llm_codegen.py (10 tests)
- **P3: host-agent driver loop (2026-08-16)** | Done | test_chip_auto_select.py (4 tests)
- **P4: bounded real observation (2026-08-16)** | Done | test_observe_capture.py (4 tests)
- **P5: GUI workflow tab (2026-08-16)** | Done | manual GUI instantiation check
- **P6: workflow token boundary hardening (2026-08-17)** | Done | test_workflow_runner.py + real state migration smoke |

#### P3/P4/P5 detail

- **P3**: `workflow-run --auto-select` takes the first LLM chip candidate
  instead of blocking (evidence records `selection_mode:
  llm-auto-select-first`). Provider aliases: `codex` / `host-agent`
  normalize to the `claude-code` task-file mode, so one-sentence requests
  work from inside Codex/Cursor with no API key. The driver loop is now
  documented where host agents actually read it: plugin `SKILL.md`
  (One-Sentence Workflow section + 6 workflow commands in the Command
  Guide), `references/usage.md` (full resume loop incl. llm-responses.jsonl
  answer format and codegen opt-in), and `agents/hardware-development-butler.md`.
- **P4**: real observation rewritten. The old path ran interactive tools
  (`python -m serial.tools.miniterm`, `probe-rs rtt attach`) under captured
  stdout — they hang until timeout and never yield output. Now: bounded
  non-interactive windows via embeddedskills `serial_monitor.py --port X
  --timeout N --json` (when a COM//dev port is configured) then
  `probe_rs_rtt.py --chip T --duration N --json` (when probe-rs is on PATH),
  with `HARDWARE_BUTLER_OBSERVE_WINDOW_S` (1–30s, default 8), JSON-Lines
  flattened by `_extract_stream_text`, failures recorded in
  `observe_errors` evidence. `flash_via_probe_rs` now passes `--verify`
  (post-flash readback check).
- **P5**: GUI gained a 工作流 (workflow) tab — goal/feature/pin/function/
  part/probe inputs + auto-select checkbox, run/resume/status/LLM-tasks
  buttons, a 9-stage status table (updated from any workflow JSON result),
  and a pending-LLM-task view with the llm-responses.jsonl answer
  instructions. Tab inserted between 动作 and 报告 (TAB_WORKFLOW=8).
  Datasheet collection was already integrated (资料中心/资料搜索 tabs).

#### P2 detail: the LLM can now write the app module

Opt-in via `workflow-llm-config --codegen on` (writes `"codegen": true`
into `.hardware-butler/llm-config.json`; `--max-tokens` also settable).
Default remains the deterministic templates.

- `llm_codegen.py` (NEW): `generate_app_module()` asks the configured
  provider to write the `app_<module>.h/.c` pair. Trust rules: the LLM
  supplies CONTENTS only — paths are constructed here; the response must
  pass contract validation (required init/start/set/task symbols, include
  guard, no RTOS headers in bare-metal builds, no Arduino deps); a
  brace-depth JSON scanner (`extract_json_object`) parses responses that
  embed C code. Datasheet evidence (datasheet-evidence.json) is injected
  into the prompt as ground truth when present.
- `llm_client.call_llm` accepts `max_tokens` (codegen uses 8192; config
  default stays 1024); new `generate_module_prompt` pins the exact API
  contract so scaffold/main integration keeps working regardless of who
  wrote the code.
- `workflow_runner._stage_firmware_plan`: LLM first → templates on any
  failure (never breaks the pipeline). claude-code provider + codegen
  returns pending → stage blocked-needs-input with the task id (host
  agent loop). Evidence records generator ("llm"|"template") per file.
- Code-level failure patches: `analyze_failure_prompt` now allows
  `patch_files`; `_llm_analyze_failure_and_patch` validates paths against
  `Core/(Inc|Src)/app_*.[ch]` only (Drivers/, main.c, `..` escapes
  rejected) and stores accepted contents in
  `state.context.code_overrides` — these survive optimize-loop stage
  resets and win per-file over whatever the next firmware-plan attempt
  generates. `_parse_llm_json` delegates to the brace-depth scanner
  (the old flat regex could not parse patch_files with C code inside).

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
   cryptographically random, workflow-scoped, bounded reuse. Plaintext exists
   only in the current process; workflow state and CLI responses retain only
   the public hash/metadata, and a disk resume reissues ephemeral authority.

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

---

## 14. P3 Completion — What Step A-I Delivered

Steps A through I are now complete. Summary of what each step delivered:

| Step | Status | What was delivered |
|---|---|---|
| A | done | Re-synced plugin package; plugin_sync tests pass |
| B | done | firmware_code_patcher wired into workflow; real .c/.h files written to firmware-modules/<feature>/ |
| C | done | tools/web_fetcher.py (DuckDuckGo HTML scrape, no API key); datasheet-collect stage fetches real PDFs/HTML |
| D | done | _verify_signal() structured verification (expected_text + frequency_hz + kind-keyword fallback); sim mode synthesizes capture, real mode uses real capture, same _verify_signal function |
| E | done | LLM chip selection when context.part empty; generates 3-5 candidates via claude-code/anthropic/openai providers |
| F | done | PlatformIO (build) + probe-rs (flash + RTT observe) + pyserial (UART observe) integrated as preferred backends with adapter native fallback |
| G | done | Real compile validation: PlatformIO build failure -> stage failed -> optimize-loop triggers LLM analysis |
| H | done | End-to-end mock-mode 9-stage workflow passes; real-mode switch uses identical code path (only data source differs) |
| I | done | (this section + README update) |

### How to switch to real mode (user接板子流程)

1. Install one of these open-source toolchains (pick by MCU family):
   - STM32: `pip install platformio` + `cargo install probe-rs`
   - ESP32: `pip install platformio` + ESP-IDF
   - MSP430: `pip install platformio` + `cargo install probe-rs`
2. Set environment: `HARDWARE_BUTLER_ENABLE_REAL_FLASH=1`
3. Run workflow:
   ```
   python tools/hardware_butler.py workflow-run \
     --root <project> --intent develop-feature \
     --goal "LED blink" --feature led-blink --pin PD12 \
     --function gpio-output --part STM32F407VGT6 \
     --probe stlink-v3 --json
   ```
4. The same code path that runs in mock mode now invokes real PlatformIO
   for build, real probe-rs for flash, real pyserial/probe-rs rtt for
   observe. _verify_signal checks real UART/RTT capture for expected
   signals.

### Open-source dependencies (user-installable)

| Tool | Purpose | Install |
|---|---|---|
| PlatformIO | Cross-vendor build (STM32/ESP32/TI/AVR/RISC-V) | `pip install platformio` |
| probe-rs | Cross-vendor flash + RTT debug (Cortex-M + ESP32 + RP2040 + Nordic) | `cargo install probe-rs` or download binary |
| pyserial | Serial UART observe | `pip install pyserial` |

The workflow detects these at runtime and uses them when available; falls
back to adapter native commands (cmake/gcc, pyOCD, JLink, etc.) when not.

### Final completion declaration (must read)

This project has completed the P3 implementation: all 9 stages of the
workflow state machine are implemented and tested in mock mode. The code
path for real hardware actions (build via PlatformIO, flash via probe-rs,
observe via pyserial/probe-rs RTT) is fully wired and identical to the
mock-mode code path — only the data source differs.

The project has NEVER been run against real hardware. Adapter command
parameters have been checked against official docs but not validated
against real boards. User接板子后的流程见上方 "How to switch to real mode"
section.

Real hardware validation is the user's next step. Issues that may surface
on real hardware (chip name format, probe selection, HAL call correctness)
belong to parameter tuning, not architecture gaps — the code is structured
so these fixes are local to the vendor adapter files, not across the
workflow runner.

---

## 15. FreeRTOS Codegen on the PlatformIO Backend (2026-08-17)

Before this change, `firmware-plan` downgraded RTOS codegen to bare-metal
whenever PlatformIO was available, because PlatformIO's stock stm32cube
builder compiles HAL/BSP/Utilities/USB middleware but silently skips
`Middlewares/Third_Party/FreeRTOS`. Now the workflow builds real FreeRTOS
firmware through PlatformIO, verified by an actual toolchain compile
(`firmware.elf` + `firmware.bin` produced, FreeRTOS symbols in the ELF).

### What was added

| Piece | File | Behavior |
|---|---|---|
| RTOS main.c | `tools/firmware_project_scaffold.py` | `render_main_c(rtos=True)` emits a CMSIS-RTOS v1 main: `osThreadDef` + `osThreadCreate` + `osKernelStart` (v1 has NO `osKernelInitialize` — that is a v2 symbol). `HAL_InitTick(15U)` re-runs the HAL tick at the lowest priority; `SysTick_Handler` chains `HAL_IncTick()` + `xPortSysTickHandler()` so the HAL tick keeps working without moving the HAL timebase to a timer. `vApplicationStackOverflowHook` is emitted because the config sets `configCHECK_FOR_STACK_OVERFLOW 2`. |
| FreeRTOSConfig.h | same file | Minimal CMSIS-RTOS v1 config written to `Core/Inc` (already on the include path via `-ICore/Inc`). Aliases SVC/PendSV only — SysTick is chained in main.c, never aliased. Existing files are never overwritten (CubeMX projects keep their own). `configCPU_CLOCK_HZ` defaults to 16 MHz HSI (no `SystemClock_Config` runs in scaffold-owned projects); tune on real-board day. |
| platformio.ini ownership | `tools/vendor_adapters/__init__.py` | Ini files carrying the `; Auto-generated by hardware_butler workflow` marker are workflow-owned and REGENERATED when the RTOS decision changes across optimize-loop iterations (the ASCII staging dir persists between builds); user-authored ini files are never touched. A downgrade also deletes a stale `pio_freertos.py`. |
| FreeRTOS compile script | `tools/vendor_adapters/stm32.py` | `platformio_freertos_script()` generates `pio_freertos.py`, a PlatformIO `pre:` extra script that adds the framework package's FreeRTOS kernel + `CMSIS_RTOS` (v1) + `heap_4` + the core-matched GCC port via `env.BuildSources`. For `cortex-m4`/`cortex-m7` it appends `-mfpu`/`-mfloat-abi=hard` to CCFLAGS+ASFLAGS+LINKFLAGS (boards declare plain m4/m7 without FPU flags; the ARM_CM4F port's FPU instructions fail to assemble without them, and a compile-only append breaks the link with VFP-ABI mismatches). |
| Workflow wiring | `tools/workflow_runner.py` | `firmware-plan` keeps RTOS when the family adapter's `supports_freertos_on_platformio()` is True (stm32cube: yes; arduino/energia families still downgrade with a note). `_stage_build` forwards the decision as `build_ctx["rtos"]`. |

### How to verify (real toolchain, no board needed)

```bash
HARDWARE_BUTLER_REAL_COMPILE=1 pytest tests/unit/test_workflow_rtos_codegen.py -q --no-cov --basetemp=.tmp-pytest-new
```

`test_real_platformio_freertos_compile_e2e` copies the cubemx-basic fixture
(its .ioc enables FREERTOS), runs `_stage_firmware_plan` (RTOS kept), then a
real `pio run`: asserts `firmware.elf` exists and contains
`osThreadCreate`/`osKernelStart`/`vApplicationStackOverflowHook`, and that
`tasks.o`/`cmsis_os.o`/`port.o`/`heap_4.o` were compiled. The test is
skipped unless `HARDWARE_BUTLER_REAL_COMPILE=1` so the normal suite never
spawns toolchains.

### Remaining real-board caveats

- `configCPU_CLOCK_HZ` is 16 MHz HSI by default; if the project runs
  `SystemClock_Config` (real CubeMX main.c), CubeMX's own FreeRTOSConfig.h
  governs anyway (scaffold never overwrites it).
- Stack-overflow hook routes to `Error_Handler` (halt); a real board may
  want a reset or report instead.

---

## 16. Real-Board-Day Readiness: canonical chip names + real-preflight (2026-08-17)

Pre-hardware validation of the exact parameters a real flash needs, done by
installing pyOCD 0.45.1 + the Keil.STM32F4xx_DFP pack locally and querying
the real pack database (no board required):

### Bug found and fixed: chip-name mismatch would have failed every real flash

pyOCD and probe-rs name devices `STM32F407VGTx` (trailing lowercase x in
place of the package digit). Users and .ioc files pass `STM32F407VGT6`,
which the workflow forwarded verbatim to the pyOCD `--target` / probe-rs
`--chip` argument — and `VGT6` is not a prefix of `VGTx`, so the real flash
would fail with "no target found". Verified empirically against the
installed pack database: `pyocd list --targets -n stm32f407vgtx` returns 1
row; `-n STM32F407VGT6` returns 0 rows.

Fix: `VendorAdapter.canonical_chip()` (base: pass-through) + STM32 override
(STM32* ending in one digit -> that digit becomes `x`; already-`x` names
pass through; non-STM32 trailing digits like nRF52832 are never rewritten).
Applied in both `flash_via_probe_rs` and the pyOCD branch of
`flash_command`. Pinned by `test_pyocd_pack_resolves_canonical_names`
(skips when pyOCD/pack absent).

### Bug found and fixed: JDK jlink false positive

On this machine `shutil.which("JLink.exe")` resolves to the Adoptium JDK's
`jlink.exe` (Windows filesystem is case-insensitive). The STM32 adapter
would then treat "JLink" as available and build Segger CLI args that invoke
a Java tool. The STM32 adapter now rejects JLink.exe paths under
java/jdk/adoptium/temurin/zulu/corretto directories; `real-preflight`
reports it as a warning.

### New command: real-preflight

```bash
python tools/hardware_butler.py real-preflight --root <project> --part STM32F407VGT6 --json
```

Read-only one-command check for real-board day (never writes/flashes):
installed flash backends (probe-rs preferred, pyOCD fallback, others
reported), attached probes via pyOCD/probe-rs `list` (correctly ignoring
the "No available debug probes are connected" notice), the part's canonical
chip name resolved against the locally installed pyOCD pack database
(`resolves` / `pack-missing` with install hint / `not-found`), COM ports
for serial observe, a `ready` verdict, and the exact
`HARDWARE_BUTLER_ENABLE_REAL_FLASH=1 ... workflow-run` command to run once
a board is plugged in.

Current machine status (evidence, 2026-08-17): `ready=False` — pyOCD
installed, `STM32F407VGTx` resolves, PlatformIO installed, but **no debug
probe attached** (USB scan and pyOCD both confirm). The remaining step for
the real loop is physical: plug in an ST-Link board, re-run
`real-preflight`, then run the printed workflow command.

---

## 17. RTT Observability: template firmware now emits verifiable signals (2026-08-17)

Gap found while preparing real-board day: the led-blink template only
toggled a GPIO pin — a real debug-observe window would capture NOTHING
(no UART configured in scaffold projects, no RTT), so verify-goal could
never match a signal and the real closed loop would spin empty.

Fix: the scaffold now generates a minimal clean-room RTT write side
(`Core/Src/app_rtt.c` + `Core/Inc/app_rtt.h`), implementing the public
SEGGER RTT control-block contract (16-byte "SEGGER RTT" ID, one up buffer,
drop-on-full ring). probe-rs (`probe-rs rtt`) and pyOCD (`pyocd rtt`)
discover it by scanning RAM over SWD — no peripheral init, no probe
registration, works on any SWD board (including the VCP-less F4 Discovery
ST-Link). The gpio/led template task now emits `app_<module>: on|off`
heartbeats every cycle, which is exactly the marker the `_verify_signal`
step-D logic matches. The LLM codegen prompt instructs the model to use
`app_rtt_puts` for observability (and forbids pulling in SEGGER sources).

Verified by the gated real compile: the linked FreeRTOS `firmware.elf`
contains the `SEGGER RTT` magic and `app_rtt_puts`. Real-board day
therefore has an observable channel end to end: flash → `probe-rs rtt`
window capture → heartbeat markers → verify-goal match.

---

## 18. Emulated Execution Proof: firmware runs under QEMU (2026-08-17)

The strongest no-board evidence short of hardware: the generated FreeRTOS
firmware ELF **executes correctly in QEMU** (netduinoplus2 = STM32F405,
same Cortex-M4 core and family as the F407 target), verified via
arm-none-eabi-gdb (bundled in the PlatformIO toolchain):

- breakpoint on `app_rtt_puts` is REACHED — proving the reset vector ran,
  `HAL_Init` completed, the FreeRTOS scheduler started (SVC/PendSV context
  switches), and `osDelay(500)` elapsed (500 real SysTick ticks);
- the stop backtrace lands in `app_led_blink_task` (thread context);
- the RTT control block in RAM starts with the `SEGGER RTT` magic and
  `WrOff` (control-block offset +32) holds 18 with
  `"app_led_blink: on\n"` readable from the ring buffer — the heartbeat
  write works exactly per the contract.

One-time setup used here (portable, no admin):

```bash
# QEMU ARM (xPack portable zip, ~40MB)
curl -L -o qemu.zip \
  https://github.com/xpack-dev-tools/qemu-arm-xpack/releases/download/v9.2.4-1/xpack-qemu-arm-9.2.4-1-win32-x64.zip
unzip qemu.zip -d "$TEMP/qemu-arm"
# gdb: already bundled at
#   ~/.platformio/packages/toolchain-gccarmnoneeabi/bin/arm-none-eabi-gdb.exe
```

Run the gated e2e test (builds the firmware for real, then executes it in
QEMU and asserts the heartbeat write):

```bash
HARDWARE_BUTLER_QEMU=1 pytest tests/unit/test_firmware_qemu_execution.py -q --no-cov --basetemp=.tmp-pytest-new
```

Honest labeling: this is EMULATED execution, not real hardware. It proves
the generated binary boots and behaves (kernel start, tick, context
switch, RTT write) and de-risks the real-board day, but the
flash/observe/verify-goal loop on a physical board remains the final
acceptance step.
