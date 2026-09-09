# Chip Bring-Up Knowledge And Safety Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a reusable chip bring-up workflow that covers datasheet/manual acquisition, knowledge summarization, CubeMX-style pin/peripheral configuration guidance, FreeRTOS-aware firmware implementation, and hardware safety gates.

**Architecture:** Keep `hardware-development-butler` as the orchestrator, `nextboard` as the hardware evidence layer, and `embeddedskills` as the build/flash/debug layer. Add a project-local `.agents/skills/chip-bringup` skill to bridge chip documents, CubeMX configuration, firmware implementation, and safety-controlled lab actions.

**Tech Stack:** Codex skill markdown, project documentation, existing Python validation, existing hardware butler CLI.

---

### Task 1: Project-Local Chip Bring-Up Skill

**Files:**
- Modify: `.agents/skills/chip-bringup/SKILL.md`
- Modify: `.agents/skills/chip-bringup/agents/openai.yaml`
- Create: `.agents/skills/chip-bringup/references/source-and-download-policy.md`
- Create: `.agents/skills/chip-bringup/references/manual-summary-template.md`
- Create: `.agents/skills/chip-bringup/references/cubemx-pin-config-guide.md`
- Create: `.agents/skills/chip-bringup/references/firmware-rtos-implementation.md`
- Create: `.agents/skills/chip-bringup/references/hardware-safety-gates.md`

- [x] **Step 1: Define trigger and top-level workflow**

Write `SKILL.md` with triggers for chip datasheets, reference manuals, schematics, CubeMX `.ioc`, pin/peripheral configuration, FreeRTOS implementation, flashing, and debug bring-up.

- [x] **Step 2: Add source and download policy**

Create a reference that requires official manufacturer pages, official PDFs, reference manuals, errata, application notes, and authorized distributors before relying on mirrors.

- [x] **Step 3: Add manual summary template**

Create a structured output format for quick-start summaries: identity, package, power, clocks, reset/boot, debug, memory, peripherals, electrical limits, register/HAL notes, errata, and first bring-up checklist.

- [x] **Step 4: Add CubeMX pin configuration guide**

Create a workflow for explaining exact pin choices, alternate functions, clocks, pull-ups, output levels, interrupt/DMA/timer settings, conflicts, and alternatives.

- [x] **Step 5: Add FreeRTOS firmware implementation guide**

Create rules for when to use tasks, queues, event groups, timers, DMA, interrupts, mutexes, and HAL callbacks.

- [x] **Step 6: Add hardware safety gates**

Create confirmation gates for voltage, current limit, pin drive mode, boot/debug access, external loads, buses, flash/erase scope, thermal risk, and rollback.

### Task 2: Documentation Routing

**Files:**
- Modify: `README.md`
- Modify: `docs/hardware-butler-blueprint.md`
- Modify: `docs/implementation-roadmap.md`
- Modify: `docs/hardware-butler-usage.md`
- Modify: `agents/hardware-development-butler.md`
- Modify: `plugins/hardware-development-butler/skills/hardware-development-butler/SKILL.md`

- [x] **Step 1: Update workspace overview**

Document `chip-bringup` as the bridge between `nextboard` and `embeddedskills`.

- [x] **Step 2: Update blueprint and roadmap**

Promote hardware knowledge base, chip handbook summarization, CubeMX configuration, firmware implementation, and safety gates from vague future work to defined product modules.

- [x] **Step 3: Update usage guide**

Add practical user request patterns and the expected workflow for “I have chip X,” “configure pin Y,” and “implement function Z.”

- [x] **Step 4: Update butler routing**

Teach the orchestrator skill and agent role to route chip-specific bring-up requests through `chip-bringup`.

### Task 3: Validation

**Files:**
- Validate: `.agents/skills/chip-bringup`
- Validate: `tests/validate_hardware_butler.py`

- [x] **Step 1: Run skill validation**

Run:

```powershell
python <user-home>/.codex/skills/.system/skill-creator/scripts/quick_validate.py .agents/skills/chip-bringup
```

Expected: validation passes.

- [x] **Step 2: Run existing hardware butler validation**

Run:

```powershell
python tests\validate_hardware_butler.py
```

Expected: existing safety/discovery tests pass.
