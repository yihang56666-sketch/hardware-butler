# Changelog

All notable changes are documented here.

## Unreleased

### Added (2026-08-17 takeover session + Phase 6/7/8)

- GUI "工具" tab consolidating 6 high-value CLI subcommands (real-preflight,
  classify-log, firmware-plan, firmware-patch, advise-pin, patch-ioc) and a
  research shortcut that jumps to the existing "资料搜索" tab. Real-hardware
  actions (plan-action / execute-action) stay behind the Actions tab's
  confirmation-token flow — no new safety surface introduced.
- `tests/unit/test_gui_tools_tab.py` (8 tests, skipped when PyQt6 absent):
  tab-order stability, widget construction, handler wiring, and four
  input-validation guards (real-preflight / classify-log require input;
  firmware-plan / advise-pin pass through optional fields).
- `tools/install_plugin_sync_hook.py`: idempotent git pre-commit hook that
  re-runs `package_hardware_butler_plugin.py` when source files change and
  auto-stages the resulting plugin diff. Eliminates the silent drift that
  `test_plugin_sync.py` only catches downstream.
- 13 new AVR/Nordic adapter tests covering build/observe/flash fallback
  chains, programmer env-var override, canonical-chip pass-through, and
  tool-detection key sets. Adapter coverage on `tools/vendor_adapters/` is
  now uniformly exercised across all 5 vendor families.
- `docs/REAL_BOARD_DAY_RUNBOOK.md`: consolidated, board-day-only checklist
  for going from mock-mode to real flash. Covers pre-flight, mock dry-run,
  board connection, bench-runbook generation, value-sanity gate, env-var
  opt-in, real workflow execution, failure-mode triage, and the safety
  contract.

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

- 632 passed / 10 skipped (was 477 at takeover; +155 tests).
- ruff + mypy clean on tools/ (63 files), gui/, tests/.

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
