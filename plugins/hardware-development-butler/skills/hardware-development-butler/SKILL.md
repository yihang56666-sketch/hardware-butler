---
name: hardware-development-butler
description: Hardware development butler for embedded projects. Use when Codex needs to onboard or manage a hardware/firmware project; collect schematic, PCB, BOM, datasheet, manual, CubeMX .ioc, Keil, CMake/GCC, EIDE, build logs, debug logs, serial, CAN, network, J-Link, OpenOCD, probe-rs, ST-Link, or CMSIS-DAP evidence; generate board and firmware profiles; propose .embeddedskills/config.json; classify build errors; or coordinate a gated build, flash, debug, observe, diagnose, and fix workflow.
---

# Hardware Development Butler

Use this skill as a safety-first hardware project manager. It combines:

- A packaged CLI runtime under the plugin `scripts/` directory.
- `nextboard` knowledge for hardware design, schematic/BOM risk, board profiles, and validation planning.
- `embeddedskills` tooling for Keil/GCC/EIDE discovery plus gated flash/debug/observe backends.
- Project-local `chip-bringup` workflow, when present, for chip document search/download, manual summaries, CubeMX pin/peripheral configuration, FreeRTOS implementation planning, and hardware safety gates.

## First Pass

1. Identify the project root. Prefer the user's firmware or board-project directory, not the plugin directory.
2. Run a read-only/product check first:

```powershell
python <skill-dir>\scripts\run_hardware_butler.py doctor --root <project-root> --json
```

3. If the user wants the easiest connected flow, run safe automation and read the persisted state:

```powershell
python <skill-dir>\scripts\run_hardware_butler.py auto --root <project-root> --out-dir docs\inspections\<project-name> --json
python <skill-dir>\scripts\run_hardware_butler.py next-step --root <project-root> --json
```

4. If you need the older explicit first pass, run safe onboarding:

```powershell
python <skill-dir>\scripts\run_hardware_butler.py onboard --root <project-root> --out-dir docs\inspections\<project-name> --json
```

5. Read the generated dossier, board profile, firmware profile, build plan, discovery run, config proposal, and `.hardware-butler/project-state.json` before recommending build, flash, debug, or hardware changes.

The wrapper sets `HARDWARE_BUTLER_WORKSPACE_ROOT` to the caller's current directory and executes the packaged runtime from the plugin, so report writes stay inside the active workspace.

## One-Sentence Workflow (preferred for "make it do X" requests)

When the user states a goal in one sentence ("LED blink on PD12", "read the I2C sensor and print over UART"), do NOT assemble per-step commands. Drive the 9-stage goal workflow (requirement-parse → chip-selection → datasheet-collect → cubemx-config → firmware-plan → build → flash → debug-observe → verify-goal) instead:

```powershell
python <skill-dir>\scripts\run_hardware_butler.py workflow-run --root <project-root> --intent develop-feature --goal "<user goal>" --json
```

The runner generates the firmware app module (LLM-written when `.hardware-butler/llm-config.json` has `"codegen": true`, deterministic templates otherwise), scaffolds main.c/main.h, really compiles via PlatformIO when installed, and iterates on build/verify failures on its own.

Host-agent resume loop — when the JSON result shows `"status": "blocked-needs-input"`, the workflow is waiting for YOU (the host agent) to execute a task, then resume:

1. `instruction` mentions LLM tasks (intent parse, chip candidates, codegen, failure analysis):
   ```powershell
   python <skill-dir>\scripts\run_hardware_butler.py workflow-llm-tasks --root <project-root> --json
   ```
   Execute each pending task's prompt yourself (you are the LLM), then append one JSON line `{"task_id": "<id>", "text": "<your answer>"}` to `<project-root>\.hardware-butler\llm-responses.jsonl`, then:
   ```powershell
   python <skill-dir>\scripts\run_hardware_butler.py workflow-run --root <project-root> --resume --json
   ```
   Repeat until the workflow stops asking. This is the default `claude-code` provider mode (aliases: `codex`, `host-agent`); it works from inside Codex, Claude Code, or Cursor without any API key.
2. `instruction` mentions datasheet search: run `workflow-search --root <project-root> --json`, use web search to fill `.hardware-butler/datasheet-evidence.json` as its instruction describes, then `workflow-run --resume`.
3. Chip selection blocked with candidates: either re-run with `--part <chosen>` or add `--auto-select` to take the first LLM candidate.

Progress/status at any time:

```powershell
python <skill-dir>\scripts\run_hardware_butler.py workflow-status --root <project-root> --json
```

Real flashing stays gated: without `HARDWARE_BUTLER_ENABLE_REAL_FLASH=1` the flash stage produces a runbook + goal_token record only. Keep it that way unless the user explicitly prepared a bench.

## Command Guide

Use these packaged commands instead of reimplementing scanners:

```powershell
python <skill-dir>\scripts\run_hardware_butler.py capabilities --json
python <skill-dir>\scripts\run_hardware_butler.py auto --root <project-root> --out-dir docs\inspections\<project-name> --json
python <skill-dir>\scripts\run_hardware_butler.py next-step --root <project-root> --json
python <skill-dir>\scripts\run_hardware_butler.py brain --root <project-root> --json
python <skill-dir>\scripts\run_hardware_butler.py ask --root <project-root> --question "PD12 接了什么？" --json
python <skill-dir>\scripts\run_hardware_butler.py task --root <project-root> --intent prepare-bringup --json
python <skill-dir>\scripts\run_hardware_butler.py chip-dossier --part <chip> --api-search --api-preset chip-docs --download --json
python <skill-dir>\scripts\run_hardware_butler.py detect --root <project-root> --json
python <skill-dir>\scripts\run_hardware_butler.py plan-build --root <project-root>
python <skill-dir>\scripts\run_hardware_butler.py run-plan --root <project-root> --phase build-discovery --json
python <skill-dir>\scripts\run_hardware_butler.py propose-config --root <project-root> --target <KeilTarget> --json
python <skill-dir>\scripts\run_hardware_butler.py classify-log <build-log-path> --json
python <skill-dir>\scripts\run_hardware_butler.py status --root <project-root> --json
python <skill-dir>\scripts\run_hardware_butler.py patch-ioc --root <project-root> --function gpio-output --pin PD12 --json
python <skill-dir>\scripts\run_hardware_butler.py firmware-integrate --root <project-root> --feature led-blink --pin PD12 --function gpio-output --json
python <skill-dir>\scripts\run_hardware_butler.py bench-runbook --root <project-root> --action build-flash --target <chip> --probe <probe> --voltage <voltage> --current-limit <limit> --erase-scope <scope> --recovery <path> --backend openocd --json
python <skill-dir>\scripts\run_hardware_butler.py safety-audit --root <project-root> --json
python <skill-dir>\scripts\run_hardware_butler.py workflow-run --root <project-root> --intent develop-feature --goal "<goal>" --json
python <skill-dir>\scripts\run_hardware_butler.py workflow-run --root <project-root> --resume --json
python <skill-dir>\scripts\run_hardware_butler.py workflow-status --root <project-root> --json
python <skill-dir>\scripts\run_hardware_butler.py workflow-llm-tasks --root <project-root> --json
python <skill-dir>\scripts\run_hardware_butler.py workflow-search --root <project-root> --json
python <skill-dir>\scripts\run_hardware_butler.py workflow-llm-config --root <project-root> --provider claude-code --codegen on --json
```

Write `.embeddedskills/config.json` only when all required inputs are explicit and the user has approved the write:

```powershell
python <skill-dir>\scripts\run_hardware_butler.py propose-config --root <project-root> --target <KeilTarget> --write --confirm-write --json
```

## Safety Rules

- Treat `doctor`, `capabilities`, `detect`, `plan-build`, `status`, and `classify-log` as read-only.
- Treat `inspect` and `onboard` as report-writing commands only.
- Treat `bench-runbook`, `bench-preflight`, and workflow `--dry-run` as no-hardware preparation paths: no subprocess hardware action, no token consumption, no safety log/state/config writes.
- Treat `safety-audit` as read-only; it may reveal token hashes and artifact hashes, but never raw token values.
- Treat `patch-ioc` and `firmware-integrate` as preview-only by default; writing requires `--write --confirm-write` and must stay inside safe `.ioc` keys or CubeMX `USER CODE` blocks.
- Do not build, flash, erase, halt, reset, resume, write memory, transmit CAN frames, or scan networks without explicit user confirmation for the exact device and action.
- Do not claim real flash/debug/observe is implemented by the butler runtime yet. Those paths remain planned-gated unless a backend-specific executor has verified device identity, voltage/current evidence, artifact hash binding, rollback logging, and bounded observation.
- Use `run-plan --phase build-discovery` for automatic execution; the safe runner has a hard allowlist and blocks build/flash/debug/bus actions.
- If evidence is missing or contradictory, write the uncertainty into the project docs instead of guessing pinouts, electrical limits, flash algorithms, or device identity.

## Routing

- For a specific chip/board request such as finding datasheets/manuals/schematics, summarizing a chip manual, explaining CubeMX configuration for a pin/peripheral, or designing a FreeRTOS implementation for an already configured interface, use the project-local `.agents/skills/chip-bringup` workflow when available.
- For schematic interpretation, component selection, BOM risk, power/clock/reset/boot/debug-interface reasoning, read `references/agent-routing.md` and use the `nextboard` role.
- For Keil, CMake/GCC, EIDE, J-Link, OpenOCD, probe-rs, serial, CAN, network, RTT/SWO, or workflow tooling, read `references/agent-routing.md` and use the `embeddedskills` role.
- For product status, packaging, safety boundaries, and task orchestration, stay in the butler role.

## References

- `references/usage.md`: command examples and expected project flow.
- `references/safety-model.md`: execution gates and hardware-action policy.
- `references/agent-routing.md`: when to use nextboard vs embeddedskills.
- `references/runtime-package.md`: packaged runtime layout and validation commands.
