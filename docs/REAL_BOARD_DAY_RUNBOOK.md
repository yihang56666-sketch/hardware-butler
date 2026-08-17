# Real-Board-Day Runbook

A self-contained, **board-day-only** checklist for going from mock-mode to
flashing real hardware with the Hardware Butler. Mock mode (default) never
touches a board; this runbook is the only sanctioned path to real flash, real
debug, and real observe.

> Read this whole document once before the first flash. The tooling refuses to
> flash without explicit env-var opt-in and a value-sanity gate, but those are
> guardrails — the human is still responsible for the checklist below.

## 0. Prerequisites (do this once, before board day)

- Local checkout of this repo; `python -m pip install -e .` succeeds.
- One probe in the supported set (probe-rs, OpenOCD, J-Link, or pyOCD). Run
  `python tools/hardware_butler.py real-preflight --root <project> --part <PART> --json`
  to confirm tool detection. `probes_attached` will be `[]` until the board is
  plugged in — that is expected at this step.
- (Optional but recommended) `pip install platformio` for cross-vendor builds.
  PlatformIO is the preferred build/flash path when it supports your chip.
- CubeMX project, or a PlatformIO project, in `<project-root>`. If you do not
  have one, start from `tests/fixtures/cubemx-basic` (mock) until you do.

## 1. Pre-flight (no hardware yet, safe)

```powershell
python tools/hardware_butler.py real-preflight --root <project> --part <PART> --json
```

What this checks (read-only, never writes):

- `flash_tool_installed` — at least one flash backend is on PATH.
- `target_resolves` — the chip part normalizes to a canonical probe-rs target.
- `probe_attached` — at least one debug probe enumerates (will be False until
  the board is connected; that is fine).
- `com_ports` — detected serial ports (for the observe stage).
- `flash_backend` — which backend will be selected first.

If `status != "ok"`, fix the reported gap before continuing. The `summary`
string is a one-line digest for clipboard paste.

## 2. Mock-mode end-to-end dry run (still no hardware)

Run the full 9-stage workflow in mock mode against your project. This is the
closest rehearsal to real board day that doesn't touch a probe:

```powershell
python tools/hardware_butler.py workflow-run --root <project> `
  --intent develop-feature --goal "LED blink on PD12" `
  --feature led-blink --pin PD12 --function gpio-output --json
```

Verify: `status == "completed"`, all 9 stages `completed`, and the firmware
artifacts land under `<project>/.hardware-butler/`. If mock mode can't
complete, real mode won't either — fix it here.

## 3. Connect the board (the only point at which hardware is involved)

- Power the board through its spec'd supply. Do NOT rely on USB current alone
  unless the board's manual explicitly allows it.
- Connect the probe's SWD/JTAG/ISP/PDI lines per the board manual. For
  STM32/Cortex-M: SWDIO+SWCLK+GND (optionally nRST and SWO). For AVR:
  6-pin ISP. For ATxmega: PDI. For Nordic: SWD as Cortex-M.
- Run `real-preflight` again. Expect `probes_attached` to be non-empty and
  `probe_attached` to be `true`. If `probe_attached` is still `false`, check
  the probe driver and the cable before continuing.

## 4. Generate the bench runbook (still no flashing)

```powershell
python tools/hardware_butler.py bench-runbook --root <project> `
  --action build-flash --json
```

This produces a markdown runbook with the exact commands the workflow will
run on real hardware. Read it. If anything looks wrong, fix the workflow
inputs before opting into real flash.

## 5. Value-sanity gate (automated, but verify the inputs)

The `safety_gate` module blocks physically-impossible values automatically:

- Voltage ≤ 0 or > 6 V → blocked.
- Current ≤ 0 or unparseable → blocked.
- Voltage > 3.6 V → warned (allowed through, but flagged).
- Current > 1000 mA → warned.
- Destructive keywords (`整片擦除` / `全片擦除` / `mass erase` / `option byte`)
  → warned.

This is a backstop, not a substitute for human review. The plan-action output
includes a `value_safety` block — read it before executing.

## 6. Opt into real flash

Set the env var (PowerShell syntax; `export` for POSIX shells):

```powershell
$env:HARDWARE_BUTLER_ENABLE_REAL_FLASH = "1"
```

This must be combined with a non-empty `--token` for `execute-action`. The
token is a sha256 of the canonical plan fields — the workflow emits it for
you in `plan-action` output; copy it into `execute-action --token <...>`.

Without both, `execute-action` returns `blocked-real-backend-not-enabled` or
`blocked-missing-token`. Never bypass these by editing source.

## 7. Run the real workflow

```powershell
python tools/hardware_butler.py workflow-run --root <project> `
  --intent develop-feature --goal "LED blink on PD12" `
  --feature led-blink --pin PD12 --function gpio-output `
  --part STM32F407VGT6 --probe stlink-v3 --json
```

With the env var set, the flash + debug + observe stages will use real
backends. The workflow still runs the same 9 stages as mock mode; only the
backend selection differs.

Watch the output for:

- `flash` stage: `evidence.status == ok` with the actual tool's stdout. If
  the tool fails, the workflow's optimize-loop will run a few iterations
  before giving up.
- `debug-observe` stage: `evidence.rtt_output` or `evidence.serial_output`
  captures the live board output.
- `verify-signal` stage: the value-sanity gate, then keyword/RTT-heartbeat
  matching against your goal.

## 8. If something goes wrong

- **`blocked-real-backend-not-enabled`**: env var not set in the shell that
  launched the workflow. Set it and retry.
- **`blocked-unsafe-safety-value`**: a plan field failed the value-sanity
  gate. Read the `value_safety` block; fix the offending value; re-run
  `plan-action`.
- **`blocked-missing-token`**: you ran `execute-action` without the token
  from `plan-action`. The token is sha256 of the canonical plan fields; it's
  in the plan-action JSON output.
- **Probe not detected**: re-run `real-preflight`. If `probes_attached` is
  still empty, check the probe driver and cable.
- **Flash failed mid-stage**: the workflow records the failure evidence
  under `<project>/.hardware-butler/<run>/`. Inspect it; do NOT just retry
  without understanding why.

## 9. After the run

- The workflow writes audit records under
  `<project>/.hardware-butler/audit/`. Review them before the next run.
- The plugin-sync pre-commit hook keeps `plugins/.../scripts/` in sync with
  source. If you modify source after the run, the hook will re-sync on
  commit — let it.
- For repeated runs, you can leave `HARDWARE_BUTLER_ENABLE_REAL_FLASH=1`
  set in the shell, but unset it when switching to mock work to avoid
  accidentally flashing the wrong board.

## Safety contract (one paragraph)

Default mode is mock. Real flash requires an explicit env-var opt-in AND a
non-empty confirmation token AND a value-sanity gate pass. None of these
layers may be bypassed by source edits — they exist because hardware is
destructive. If a layer blocks you, that is a feature: figure out why the
plan looked unsafe, fix the plan, and try again. Never `--no-verify`, never
patch out the gate, never hardcode a token.
