# NextBoard Universal R&D Platform Master Implementation Plan

> **For agentic workers:** REQUIRED PROCESS: read `AGENTS.md` and the approved design first, create an isolated Git worktree, execute phases in order with test-driven development, and stop at every phase gate. Do not begin future phases early. Do not modify or commit the independent `embeddedskills/` worktree unless a separately approved task explicitly owns those changes.

**Goal:** Evolve NextBoard from an STM32-oriented hardware butler into a mature, local-first, provider-neutral software and hardware R&D platform spanning project discovery, firmware, vision/AI boards, host software, EDA evidence, devices, safe execution, desktop workflows, plugins, and future Web/remote nodes.

**Architecture:** A Python application kernel owns stable domain models, persistence, adapter registries, task orchestration, evidence, and safety policy. CLI, PyQt desktop UI, future local HTTP API, and remote nodes are clients of that kernel. Platform-specific behavior is implemented through versioned adapters which wrap existing `tools/`, `embeddedskills/`, and `nextboard/` capabilities rather than duplicating them.

**Tech Stack:** Python 3.10+, dataclasses, Protocol, sqlite3, pathlib, subprocess, JSON, PyQt6, pytest, Ruff, mypy; optional keyring and HTTP dependencies introduced only in their owning phases.

**Approved design:** `docs/superpowers/specs/2026-08-12-universal-rd-workbench-design.md`

---

## 1. How Another AI Must Use This Plan

This is a program-level plan, not one oversized coding task. It contains nineteen
sequential phases, numbered 0 through 18. Each phase must produce working software,
tests, documentation, and a Git commit before the next phase begins.

Execution rules:

1. Read the root `AGENTS.md`, then read any nested instruction file before changing
   files in that subtree.
2. Create a feature worktree and branch such as `feature/universal-rd-platform`.
3. Run the baseline gates before editing: `ruff check tools/ tests/`,
   `mypy tools/ --config-file mypy.ini`, and `pytest tests/ -v`.
4. If baseline failures exist, record exact failures in the phase journal. Do not
   silently repair unrelated failures or claim they were introduced by this work.
5. For every behavior change: add one focused failing test, run it and confirm the
   expected failure, implement the smallest production change, run the focused test,
   then run the phase regression set.
6. Use `apply_patch` for manual edits. Do not rewrite large files mechanically unless
   the task explicitly requires it.
7. Preserve current command names and JSON behavior unless this plan gives a
   compatibility migration.
8. Do not bypass `hardware_action_plan`, `hardware_action_audit`,
   `hardware_action_executor`, `command_runner`, or `safe_io`.
9. Do not hardcode D-drive paths. D-drive projects are acceptance fixtures selected
   by the user at runtime.
10. Do not store model API keys, hardware confirmation tokens, raw secrets, or private
    source contents in Git, logs, SQLite, or evidence previews.
11. After every phase, update the phase checklist in this document or a local execution
    copy and produce an evidence note with commands and results.
12. Never label simulation, dry-run, or unavailable-hardware tests as real execution.

Recommended commit sequence:

```text
chore: establish universal platform baseline
feat: add workbench domain and storage kernel
feat: add versioned adapter sdk
feat: discover projects tools and devices
feat: add workspace application services and cli
feat: add task evidence and safety orchestration
feat: add provider neutral ai routing
feat: add modular desktop workbench
feat: connect initial rd platform adapters
feat: add adapter sdk packaging and diagnostics
feat: add local api and remote node protocol
feat: harden platform migration and recovery
docs: complete universal platform beta workflow
feat: add maintained cross-platform rd adapters
feat: add instruments industrial and motion workflows
feat: add production web and cloud collaboration
feat: add governed multi-agent collaboration
feat: add product updates diagnostics and quality gates
release: qualify NextBoard 1.0
```

### Mandatory TDD Loop Inside Every Task

Each task in every phase expands into these exact execution steps. The implementing AI
must copy the task into its tracker and record command output at RED and GREEN:

1. Create or extend the exact test file named by the task with one behavior-focused
   test. Prefer real domain/service objects; use fakes only for network, subprocess,
   clock, credential store, AI provider, or physical hardware boundaries.
2. Run the narrowest node, for example:
   `pytest path/to/test_file.py::test_behavior -v --no-cov`.
3. Confirm it fails because the required behavior is absent. Import/syntax/fixture errors
   are not valid RED; fix the test harness until the assertion fails for the intended
   reason.
4. Implement the smallest production change in the task-owned files. Do not implement
   another task or phase opportunistically.
5. Re-run the narrow test and require PASS.
6. Run the entire owning test file and require PASS.
7. Run the phase verification command and require PASS or document a pre-existing
   baseline failure with unchanged reproduction.
8. Run Ruff on changed Python files, mypy on changed `tools/` modules, and
   `git diff --check`.
9. Review `git diff` for secrets, absolute private paths, generated files, ownership
   violations, weakened safety conditions, and accidental API/schema drift.
10. Commit only the task's coherent files. Record commit ID, tests, and remaining risks
    before starting the next task.

### Required Phase Handoff Record

At every phase gate, create a review note in the pull request, task log, or
`docs/platform/execution/phase-XX.md` containing:

```markdown
# Phase XX Verification
- Scope delivered:
- Commits:
- Files added/changed:
- RED tests observed:
- Focused tests:
- Regression tests:
- Manual/read-only acceptance:
- Hardware tests: passed / failed / not-run, with exact reason
- Security/privacy checks:
- Performance observations:
- Known limitations:
- Rollback procedure:
- Gate result: pass / blocked
```

Do not commit execution notes containing usernames, private paths, credentials, tokens,
proprietary source, or raw device payloads.

## 2. Non-Negotiable Ownership Boundaries

| Area | Owner | Rule |
| --- | --- | --- |
| `tools/platform/` | New platform kernel | Source of truth for domain, persistence, registries, services, tasks, evidence, AI routing |
| Existing `tools/*.py` | Legacy capability implementations | Wrap first; refactor only when required by an adapter and covered by regression tests |
| `embeddedskills/` | Independent Git repository | Treat as external runtime; never reset, bulk format, or commit its current dirty state from the root plan |
| `nextboard/` | Hardware solution and review system | Keep its evidence rules and five verification gates; expose via an adapter |
| `gui/` | Desktop client | Calls application services only; no tool-specific subprocess construction in widgets |
| `plugins/hardware-development-butler/` | Generated/distributed package | Update through `tools/package_hardware_butler_plugin.py`, then validate package parity |
| `.hardware-butler/` | Per-project local state | Compatibility state only; new global catalog lives outside project roots by default |

Default local state location:

```text
Windows: %LOCALAPPDATA%\NextBoard\
Linux:   $XDG_STATE_HOME/nextboard/ or ~/.local/state/nextboard/
macOS:   ~/Library/Application Support/NextBoard/
```

Tests must always inject a temporary state directory. No test may write to the real
user state location.

## 3. Target Repository Structure

Create this structure gradually in the owning phases:

```text
tools/platform/
  __init__.py
  errors.py
  models.py
  paths.py
  serialization.py
  persistence.py
  migrations/
    __init__.py
    v001_initial.py
    v002_ai_profiles.py
    v003_remote_nodes.py
  registry.py
  contracts.py
  discovery/
    __init__.py
    projects.py
    tools.py
    devices.py
    exclusions.py
  adapters/
    __init__.py
    builtin.py
    stm32.py
    cmake.py
    python_project.py
    maixcam.py
    openmv.py
    eda_documents.py
    transports.py
    nextboard_solution.py
  tasks/
    __init__.py
    planner.py
    engine.py
    policies.py
    executor.py
  evidence/
    __init__.py
    store.py
    redaction.py
    export.py
  ai/
    __init__.py
    contracts.py
    profiles.py
    router.py
    openai_compatible.py
    local_http.py
  services/
    __init__.py
    workspace_service.py
    task_service.py
    settings_service.py
  api/
    __init__.py
    schemas.py
    local_server.py
    auth.py
  remote/
    __init__.py
    protocol.py
    node_agent.py
    scheduler.py

gui/
  hardware_agent_ui.py
  app_context.py
  navigation.py
  workers.py
  viewmodels/
    workspace.py
    projects.py
    tasks.py
    devices.py
    evidence.py
    settings.py
  views/
    home.py
    projects.py
    tasks.py
    devices.py
    evidence.py
    settings.py
  dialogs/
    workspace_setup.py
    confirmation.py
    ai_provider.py

tests/unit/platform/
tests/integration/platform/
tests/contract/adapters/
tests/gui/
tests/fixtures/platform/
tests/acceptance/

docs/platform/
  architecture.md
  adapter-sdk.md
  safety-model.md
  ai-providers.md
  workspace-data.md
  remote-nodes.md
  migration.md
  release-checklist.md
```

Do not create empty modules for future phases. The tree above is the destination and
each file appears only when its phase implements real behavior.

## 4. Stable Core Contracts

All later phases depend on these names. Change them only through a schema/contract
migration and update all contract tests in the same commit.

```python
class AuthorityLevel(str, Enum):
    AUTOMATIC = "automatic"
    CONFIRMED = "confirmed"
    HIGH_RISK = "high-risk"

class TaskStatus(str, Enum):
    DRAFT = "draft"
    PLANNED = "planned"
    AWAITING_CONFIRMATION = "awaiting-confirmation"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"

@dataclass(frozen=True)
class CapabilityDescriptor:
    id: str
    adapter_id: str
    operation: str
    authority: AuthorityLevel
    input_schema: Mapping[str, object]
    output_schema: Mapping[str, object]
    supports_dry_run: bool
    supports_cancel: bool

class CapabilityAdapter(Protocol):
    adapter_id: str
    contract_version: int
    implementation_version: str
    def health(self, context: AdapterContext) -> AdapterHealth: ...
    def detect(self, context: DetectionContext) -> Sequence[DetectionMatch]: ...
    def capabilities(self) -> Sequence[CapabilityDescriptor]: ...
    def invoke(self, request: CapabilityRequest) -> CapabilityResult: ...

class SecretStore(Protocol):
    def set(self, key: str, value: str) -> None: ...
    def get(self, key: str) -> str | None: ...
    def delete(self, key: str) -> None: ...
```

Every serialized response has these envelope fields:

```json
{
  "schema_version": 1,
  "status": "ok",
  "request_id": "uuid",
  "data": {},
  "warnings": [],
  "error": null
}
```

Normalized errors contain `code`, `message`, `retryable`, `resource`,
`details_reference`, and `recovery_actions`. Raw exception strings may be retained in
a protected evidence file, but the user-facing envelope must be stable and sanitized.

## 5. Database Contract

SQLite is the local catalog. Enable `PRAGMA foreign_keys=ON`, use WAL where supported,
and run all migrations in one transaction. Initial tables:

```sql
schema_meta(version INTEGER NOT NULL)
workspaces(id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TEXT NOT NULL,
           updated_at TEXT NOT NULL, last_opened_at TEXT)
scan_roots(id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, canonical_path TEXT NOT NULL,
           enabled INTEGER NOT NULL, max_depth INTEGER NOT NULL, created_at TEXT NOT NULL,
           UNIQUE(workspace_id, canonical_path))
projects(id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, canonical_path TEXT NOT NULL,
         display_name TEXT NOT NULL, classification TEXT NOT NULL,
         confidence REAL NOT NULL, registered_at TEXT NOT NULL,
         UNIQUE(workspace_id, canonical_path))
project_facets(project_id TEXT NOT NULL, facet TEXT NOT NULL, adapter_id TEXT NOT NULL,
               confidence REAL NOT NULL, evidence_json TEXT NOT NULL,
               PRIMARY KEY(project_id, facet, adapter_id))
tools(id TEXT PRIMARY KEY, product_id TEXT NOT NULL, executable_path TEXT NOT NULL,
      version TEXT, health TEXT NOT NULL, capabilities_json TEXT NOT NULL,
      probed_at TEXT NOT NULL, UNIQUE(product_id, executable_path))
devices(id TEXT PRIMARY KEY, transport TEXT NOT NULL, address TEXT NOT NULL,
        display_name TEXT NOT NULL, health TEXT NOT NULL, metadata_json TEXT NOT NULL,
        observed_at TEXT NOT NULL, UNIQUE(transport, address))
tasks(id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, project_id TEXT,
      goal TEXT NOT NULL, status TEXT NOT NULL, authority TEXT NOT NULL,
      plan_json TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)
task_events(id TEXT PRIMARY KEY, task_id TEXT NOT NULL, from_status TEXT,
            to_status TEXT NOT NULL, event_type TEXT NOT NULL,
            payload_json TEXT NOT NULL, created_at TEXT NOT NULL)
evidence(id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, project_id TEXT,
         task_id TEXT, kind TEXT NOT NULL, confidence TEXT NOT NULL,
         source TEXT NOT NULL, content_path TEXT, summary_json TEXT NOT NULL,
         sha256 TEXT, created_at TEXT NOT NULL)
confirmations(id TEXT PRIMARY KEY, task_id TEXT NOT NULL, capability_id TEXT NOT NULL,
              target_hash TEXT NOT NULL, input_hash TEXT NOT NULL, token_hash TEXT NOT NULL,
              expires_at TEXT NOT NULL, consumed_at TEXT)
ai_profiles(id TEXT PRIMARY KEY, name TEXT NOT NULL, provider_type TEXT NOT NULL,
            endpoint TEXT, model TEXT NOT NULL, secret_ref TEXT,
            capabilities_json TEXT NOT NULL, enabled INTEGER NOT NULL)
adapter_settings(adapter_id TEXT PRIMARY KEY, enabled INTEGER NOT NULL,
                 settings_json TEXT NOT NULL, updated_at TEXT NOT NULL)
remote_nodes(id TEXT PRIMARY KEY, name TEXT NOT NULL, endpoint TEXT NOT NULL,
             public_key TEXT NOT NULL, trust_state TEXT NOT NULL,
             capabilities_json TEXT NOT NULL, last_seen_at TEXT)
```

Never store plaintext secrets or plaintext confirmation tokens. JSON columns are
validated before insertion and decoded through one serialization module.

---

# Phase 0: Baseline, Isolation, and Migration Guardrails

**Outcome:** A reproducible development baseline and ownership protections before new
production code exists.

**Files:**
- Modify: `.gitignore`
- Create: `docs/platform/migration.md`
- Create: `tests/unit/platform/test_repository_boundaries.py`

### Task 0.1: Create the isolated worktree

- [ ] Add `.worktrees/` to `.gitignore` if project-local worktrees are selected.
- [ ] Commit that ignore rule alone.
- [ ] Create `feature/universal-rd-platform` from current `main`.
- [ ] Confirm `git status --short` is empty in the new worktree.
- [ ] Confirm the root worktree and independent `embeddedskills/` worktree are unchanged.

Commands:

```powershell
git check-ignore -q .worktrees
git worktree add .worktrees\universal-rd-platform -b feature/universal-rd-platform
git -C .worktrees\universal-rd-platform status --short
git -C embeddedskills status --short
```

### Task 0.2: Capture baseline quality evidence

- [ ] Run Python version and dependency checks.
- [ ] Run focused lint, type checking, normal tests, package validation, and nextboard
  validation without hardware.
- [ ] Save exact results in `docs/platform/migration.md` under `Baseline 2026-08-12`.

Commands:

```powershell
python --version
ruff check tools/ tests/
mypy tools/ --config-file mypy.ini
pytest tests/ -v
python nextboard/tests/validate.py
python plugins/hardware-development-butler/scripts/validate_package.py
```

### Task 0.3: Add repository boundary tests

Write failing tests that assert:

```python
def test_embeddedskills_remains_gitignored() -> None:
    assert git_check_ignore("embeddedskills/")

def test_generated_plugin_files_match_packager_manifest() -> None:
    assert package_manifest_has_no_unowned_source_files()
```

Implement only the test helpers required to inspect Git metadata. Phase gate: all
baseline failures are either fixed in scoped commits or documented as pre-existing.

---

# Phase 1: Domain Kernel, Errors, Serialization, and Persistence

**Outcome:** Stable types and a versioned local catalog usable without GUI, AI, or
hardware.

**Files:**
- Create: `tools/platform/__init__.py`
- Create: `tools/platform/models.py`
- Create: `tools/platform/errors.py`
- Create: `tools/platform/serialization.py`
- Create: `tools/platform/paths.py`
- Create: `tools/platform/persistence.py`
- Create: `tools/platform/migrations/__init__.py`
- Create: `tools/platform/migrations/v001_initial.py`
- Create: `tests/unit/platform/test_models.py`
- Create: `tests/unit/platform/test_serialization.py`
- Create: `tests/unit/platform/test_persistence.py`

### Task 1.1: Define immutable domain records

Test first for stable UUID5 path IDs, canonical Windows path handling, multi-facet
projects, enum serialization, UTC timestamps, and invalid task transitions.

Required records: `Workspace`, `ScanRoot`, `Project`, `ProjectFacet`, `Tool`, `Device`,
`Task`, `TaskEvent`, `Evidence`, `Confirmation`, `AIProfile`, `RemoteNode`,
`CapabilityDescriptor`, and the supporting enums in Section 4.

Focused command:

```powershell
pytest tests/unit/platform/test_models.py -v --no-cov
```

### Task 1.2: Normalize errors and envelopes

Test these exact mappings:

| Exception/input | Error code | Retryable |
| --- | --- | --- |
| missing path | `resource-not-found` | false |
| permission error | `permission-denied` | false |
| subprocess timeout | `tool-timeout` | true |
| adapter unsupported | `capability-unsupported` | false |
| stale confirmation | `confirmation-stale` | false |
| disconnected device | `device-disconnected` | true |
| invalid JSON/schema | `invalid-input` | false |

`ResultEnvelope.to_dict()` must never serialize exception objects or secret-like keys.

### Task 1.3: Implement state paths and SQLite migrations

Inject `state_dir` everywhere. `default_state_dir()` is the only function that reads
platform environment variables. Tests use `tmp_path` and verify migrations are
idempotent, rollback on failure, enforce foreign keys, normalize duplicate scan roots,
and round-trip every Phase 1 record.

Phase verification:

```powershell
pytest tests/unit/platform/test_models.py tests/unit/platform/test_serialization.py tests/unit/platform/test_persistence.py -v --no-cov
ruff check tools/platform tests/unit/platform
mypy tools/platform --config-file mypy.ini
```

Phase gate: a temporary catalog can create, close, reopen, and list one workspace with
projects and task history. Commit `feat: add workbench domain and storage kernel`.

---

# Phase 2: Versioned Adapter SDK and Registry

**Outcome:** Platform-specific capabilities plug into the kernel without hard-coded UI
or service branches.

**Files:**
- Create: `tools/platform/contracts.py`
- Create: `tools/platform/registry.py`
- Create: `tools/platform/adapters/__init__.py`
- Create: `tools/platform/adapters/builtin.py`
- Create: `tests/unit/platform/test_registry.py`
- Create: `tests/contract/adapters/test_adapter_contract.py`
- Create: `tests/fixtures/platform/reference_adapter.py`

### Task 2.1: Implement adapter protocols

Test the Section 4 contract plus:

- duplicate `adapter_id` is rejected;
- contract versions other than `1` are rejected with a normalized diagnostic;
- a failing adapter cannot prevent healthy adapters from detecting;
- matches sort by confidence descending, priority descending, adapter ID ascending;
- capability IDs are globally unique as `<adapter_id>.<operation>`;
- every non-automatic capability declares dry-run and confirmation behavior.

### Task 2.2: Implement registry lifecycle

`AdapterRegistry` exposes `register`, `unregister`, `list_adapters`, `health`,
`detect_projects`, `detect_tools`, `detect_devices`, `capabilities`, and `invoke`.
Invocation returns `CapabilityResult`; it never raises adapter exceptions across the
application boundary.

### Task 2.3: Add a reference adapter and reusable contract suite

Create a fixture adapter with `detect` and read-only `inspect` capability. The contract
suite is parametrized so every built-in and third-party adapter can call:

```python
assert_adapter_contract(adapter, temporary_context)
```

Phase verification:

```powershell
pytest tests/unit/platform/test_registry.py tests/contract/adapters/test_adapter_contract.py -v --no-cov
```

Phase gate: register two adapters, isolate one failure, invoke the healthy capability,
and serialize its result. Commit `feat: add versioned adapter sdk`.

---

# Phase 3: Project, Tool, and Device Discovery

**Outcome:** Safe, bounded, explainable discovery of user projects, installed tools,
SDK/IDE exclusions, and connected endpoints.

**Files:**
- Create: `tools/platform/discovery/exclusions.py`
- Create: `tools/platform/discovery/projects.py`
- Create: `tools/platform/discovery/tools.py`
- Create: `tools/platform/discovery/devices.py`
- Create: `tests/unit/platform/test_project_discovery.py`
- Create: `tests/unit/platform/test_tool_discovery.py`
- Create: `tests/unit/platform/test_device_discovery.py`
- Create: `tests/fixtures/platform/discovery/` fixture tree

### Task 3.1: Implement staged project discovery

Rules:

- scan only user-selected roots;
- default max depth `5`, max directories `20000`, max candidates `1000`;
- do not follow symlink/junction directories;
- exclude VCS, virtual environments, dependencies, builds, package caches, IDE installs,
  SDK roots, generated packages, and vendor sample collections;
- stop at strong project roots but permit explicitly recognized multi-project containers;
- return exclusions with path, reason, detector, and whether a user override is allowed;
- never treat the process working directory as the selected project;
- support multi-facet projects.

Initial marker facets:

| Facet | Required evidence |
| --- | --- |
| `stm32` | `.ioc`, `.uvprojx`, STM32 startup/linker evidence |
| `cmake-cpp` | `CMakeLists.txt` or `CMakePresets.json` plus source/build markers |
| `python` | `pyproject.toml`, `requirements.txt`, or importable application layout |
| `maixcam` | MaixPy/MaixCAM application manifest or known API imports |
| `openmv` | user script with OpenMV sensor/image APIs, outside installation tree |
| `eda` | KiCad/Altium/LCSC/JLCEDA schematic, PCB, BOM, or manufacturing files |
| `documentation` | manuals/datasheets linked to another facet; not sufficient alone by default |

### Task 3.2: Verify executable identity

Candidate sources: PATH, configured paths, Windows uninstall/application metadata, and
conservative known locations. Probe with argument arrays, `shell=False`, timeout,
bounded output, and no writes.

Mandatory regression: `D:\STM32CubeMX\jre\bin\jlink.exe` identifies as Java image
linker and never receives `flash` or `debug-probe` capabilities. SEGGER J-Link requires
vendor output. Filename-only matches remain `unverified`.

### Task 3.3: Discover devices without opening destructive sessions

Read-only enumeration covers serial ports, configured CAN interfaces, debug probe
enumeration when supported, and configured network endpoints. Discovery must not send
CAN frames, open long serial sessions, scan networks, reset probes, or attach debuggers.

Phase verification:

```powershell
pytest tests/unit/platform/test_project_discovery.py tests/unit/platform/test_tool_discovery.py tests/unit/platform/test_device_discovery.py -v --no-cov
```

Phase gate: fixture scan classifies all initial facets, explains every exclusion, and
rejects the Java `jlink` false positive. Commit `feat: discover projects tools and devices`.

---

# Phase 4: Workspace Services and CLI

**Outcome:** A complete headless workflow for creating workspaces, scanning, reviewing,
registering, inspecting, and listing resources.

**Files:**
- Create: `tools/platform/services/__init__.py`
- Create: `tools/platform/services/workspace_service.py`
- Create: `tools/platform/services/settings_service.py`
- Modify: `tools/hardware_butler.py`
- Create: `tests/unit/platform/test_workspace_service.py`
- Create: `tests/integration/platform/test_workspace_cli.py`
- Modify: `tests/unit/test_hardware_butler_guide.py`

### Task 4.1: Implement `WorkspaceService`

Public methods:

```python
create_workspace(name, scan_roots) -> Workspace
list_workspaces() -> list[Workspace]
update_scan_roots(workspace_id, roots) -> Workspace
discover(workspace_id, *, refresh_tools=True, refresh_devices=True) -> DiscoverySession
list_candidates(workspace_id, session_id) -> list[ProjectCandidate]
register_project(workspace_id, session_id, candidate_id) -> Project
ignore_candidate(workspace_id, session_id, candidate_id, reason) -> None
inspect_project(workspace_id, project_id) -> InspectionResult
list_projects(workspace_id) -> list[Project]
```

Discovery sessions expire when scan roots change. Registration rechecks that the path
is under an enabled scan root and still has matching evidence.

### Task 4.2: Add CLI group without breaking legacy commands

Commands:

```text
hardware-butler workspace create --name NAME --root PATH [--root PATH] --json
hardware-butler workspace list --json
hardware-butler workspace scan --workspace ID --json
hardware-butler workspace register --workspace ID --session ID --candidate ID --json
hardware-butler workspace ignore --workspace ID --session ID --candidate ID --reason TEXT --json
hardware-butler workspace inspect --workspace ID --project ID --json
hardware-butler workspace projects --workspace ID --json
hardware-butler workspace tools --workspace ID --json
hardware-butler workspace devices --workspace ID --json
```

All accept optional `--state-dir` for testability. `main(argv)` must return an integer
exit code instead of calling `sys.exit` internally; the module entry point may raise
`SystemExit(main())`.

### Task 4.3: Preserve compatibility

Keep `guide`, `doctor`, `auto`, `next-step`, `workbench`, and all advanced commands.
Update `guide` to prefer workspace onboarding while documenting the single-project
compatibility path.

Phase verification:

```powershell
pytest tests/unit/platform/test_workspace_service.py tests/integration/platform/test_workspace_cli.py tests/unit/test_hardware_butler_guide.py tests/unit/test_hardware_butler_cli_errors.py -v --no-cov
python tools/hardware_butler.py workspace --help
```

Phase gate: a clean temporary state directory completes create -> scan -> register ->
inspect from CLI JSON. Commit `feat: add workspace application services and cli`.

---

# Phase 5: Task Engine, Evidence Store, and Safety Orchestration

**Outcome:** Every operation becomes an auditable task with typed plans, authority,
confirmation, execution status, evidence, and recovery.

**Files:**
- Create: `tools/platform/tasks/policies.py`
- Create: `tools/platform/tasks/planner.py`
- Create: `tools/platform/tasks/engine.py`
- Create: `tools/platform/tasks/executor.py`
- Create: `tools/platform/evidence/redaction.py`
- Create: `tools/platform/evidence/store.py`
- Create: `tools/platform/evidence/export.py`
- Create: `tools/platform/services/task_service.py`
- Modify: `tools/hardware_action_plan.py`
- Modify: `tools/hardware_action_executor.py`
- Modify: `tools/hardware_action_audit.py`
- Create: `tests/unit/platform/test_task_engine.py`
- Create: `tests/unit/platform/test_evidence_store.py`
- Create: `tests/unit/platform/test_safety_policy.py`
- Create: `tests/integration/platform/test_task_execution.py`

### Task 5.1: Implement deterministic task planning

The planner accepts a registered capability and validated inputs. It produces ordered
steps, expected evidence, rollback limitations, target binding, and an authority level.
AI text is not accepted as a command or argument list.

Valid transitions:

```text
draft -> planned
planned -> running | awaiting-confirmation | blocked | cancelled
awaiting-confirmation -> running | blocked | cancelled
running -> succeeded | failed | cancelled | blocked
```

Every transition writes one `task_events` row in the same transaction as task status.

### Task 5.2: Implement append-only evidence

Evidence payload files live under `<state>/evidence/<workspace>/<task>/`. Metadata is
stored in SQLite. Use SHA-256, atomic writes, size limits, UTF-8 replacement for tool
output, and redaction for keys matching `token`, `secret`, `password`, `api_key`,
`authorization`, and adapter-declared sensitive fields.

### Task 5.3: Unify existing safety gates

Wrap current action plan/audit/executor behavior; do not replace its token logic without
equivalent regression coverage. Confirmations bind task ID, capability ID, target,
adapter, artifact hash, normalized input hash, expiry, and single-use token hash.

Authority behavior:

- automatic: inspect, analyze, environment probe, safe build in known output paths;
- confirmed: source/config writes, dependency install, flash, erase, reset, debug;
- high-risk: actuators, broad device writes, unsafe electrical assumptions, destructive
  batches; require adapter interlock evidence plus elevated confirmation.

### Task 5.4: Add cancellation, timeouts, and recovery

The shared executor uses `shell=False`, creates a process group where supported,
terminates children on cancellation, caps captured output, and records raw output only
after redaction. Resume is allowed only when a capability declares idempotence or a
resume strategy.

Phase verification:

```powershell
pytest tests/unit/platform/test_task_engine.py tests/unit/platform/test_evidence_store.py tests/unit/platform/test_safety_policy.py tests/integration/platform/test_task_execution.py tests/unit/test_safety_sanity.py tests/unit/test_value_safety_paths.py -v --no-cov
```

Phase gate: automatic inspection runs; flash cannot run without a current confirmation;
changed artifact/input rejects the token; simulated action remains labeled simulated.
Commit `feat: add task evidence and safety orchestration`.

---

# Phase 6: Provider-Neutral AI Configuration and Routing

**Outcome:** Users configure their own models; the platform works fully without AI and
never gives a model direct execution authority.

**Files:**
- Create: `tools/platform/ai/contracts.py`
- Create: `tools/platform/ai/profiles.py`
- Create: `tools/platform/ai/router.py`
- Create: `tools/platform/ai/openai_compatible.py`
- Create: `tools/platform/ai/local_http.py`
- Create: `tools/platform/migrations/v002_ai_profiles.py`
- Modify: `tools/platform/services/settings_service.py`
- Create: `tests/unit/platform/test_ai_profiles.py`
- Create: `tests/unit/platform/test_ai_router.py`
- Create: `tests/integration/platform/test_ai_optional.py`

### Task 6.1: Implement secret references

Prefer OS credential storage through optional `keyring`. Store only a `secret_ref` in
SQLite. If keyring is unavailable, disable persistent credentials by default; allow an
explicit environment-variable reference. Never create a plaintext fallback silently.

### Task 6.2: Implement provider contracts

Support an OpenAI-compatible JSON protocol and a generic local HTTP profile. A profile
contains endpoint, model, timeout, capability flags, and secret reference. Validate
URLs, disallow credentials embedded in URLs, and redact authentication headers.

### Task 6.3: Implement bounded AI roles

AI may summarize evidence, explain diagnostics, rank registered capabilities, and fill
typed plan fields. The router validates output against schema, rejects unknown
capability IDs/arguments, and falls back to deterministic behavior on timeout, invalid
JSON, missing profile, or provider failure.

Test with fake local providers only. Development may use the active Codex environment
for manual evaluation, but no developer key or provider selection is committed.

Phase verification:

```powershell
pytest tests/unit/platform/test_ai_profiles.py tests/unit/platform/test_ai_router.py tests/integration/platform/test_ai_optional.py -v --no-cov
```

Phase gate: all core acceptance flows pass with zero AI profiles; a fake profile can
summarize evidence but cannot inject a shell command. Commit `feat: add provider neutral ai routing`.

---

# Phase 7: Modular Desktop Workbench

**Outcome:** A coherent, approachable PyQt desktop application using the same services
as CLI, while preserving legacy advanced workflows during migration.

**Files:**
- Create the `gui/app_context.py`, `gui/navigation.py`, `gui/workers.py`, `gui/viewmodels/`,
  `gui/views/`, and `gui/dialogs/` files listed in Section 3 as behavior is implemented.
- Modify: `gui/hardware_agent_ui.py`
- Create: `tests/gui/test_workspace_viewmodel.py`
- Create: `tests/gui/test_task_viewmodel.py`
- Create: `tests/gui/test_settings_viewmodel.py`
- Create: `tests/gui/test_desktop_smoke.py`

### Task 7.1: Extract display-independent view models

View models depend on `WorkspaceService`, `TaskService`, and `SettingsService`, never
on subprocesses. Tests run without a display and cover empty workspace, discovery
results, task confirmation, failure recovery, tool health, AI-disabled state, and
evidence lookup.

### Task 7.2: Build the navigation shell

Primary navigation: Home, Projects, Tasks, Devices, Evidence, Settings. Keep existing
advanced tabs reachable under an `Advanced` area until their capabilities are migrated.
Do not create cards inside cards or oversized marketing content. Use compact operational
layouts, existing Qt styling, stable table dimensions, clear status colors, icons for
familiar actions, and tooltips for unfamiliar icons.

### Task 7.3: Implement first-run workspace setup

Flow: choose state/workspace name -> select scan roots -> review tools and project
candidates -> include/exclude candidates -> register -> run first inspection. Users
may cancel and return later. The default target is never the NextBoard repository.

### Task 7.4: Implement background work and confirmations

All scan/tool/task operations run through reusable workers. Disable only the active
control, support cancellation, stream progress, and distinguish blocked, failed,
cancelled, simulated, and succeeded. Confirmation dialog shows exact capability,
target, input summary, side effects, rollback limits, expiry, and evidence gaps.

### Task 7.5: Visual verification

Run the desktop app and capture Playwright/desktop screenshots where the environment
supports it. Verify 1366x768, 1920x1080, and a narrow 1024x768 window; confirm no text
overlap, clipped buttons, nested-card composition, or blank primary view.

Phase verification:

```powershell
pytest tests/gui -v --no-cov
python -c "import gui.hardware_agent_ui"
python gui/hardware_agent_ui.py
```

Phase gate: a new user completes first-run discovery and reaches a registered project;
an expert reaches legacy tools; no UI thread blocks during scans. Commit
`feat: add modular desktop workbench`.

---

# Phase 8: Initial Full-Stack Capability Adapters

**Outcome:** The universal kernel becomes useful for the user's real D-drive workflows
without making any one platform the core.

**Files:**
- Create built-in adapter files listed in Section 3.
- Create matching tests under `tests/contract/adapters/`.
- Create sanitized fixtures under `tests/fixtures/platform/adapters/`.
- Modify legacy modules only when adapter tests prove a missing stable API.

### Task 8.1: STM32 and firmware adapter

Wrap `project_scanner`, `cube_detect`, `cubemx_ioc_summary`, `build_plan`,
`config_proposal`, firmware planning/patching, Keil/GCC/EIDE discovery, J-Link/OpenOCD/
probe-rs health, and existing safety plans.

Capabilities:

```text
stm32.inspect             automatic
stm32.plan-build          automatic
stm32.build               automatic or confirmed when outputs escape build root
stm32.propose-config      automatic
stm32.patch-config        confirmed
stm32.plan-firmware       automatic
stm32.patch-firmware      confirmed
stm32.plan-flash          automatic
stm32.flash               confirmed
stm32.debug               confirmed
stm32.observe             confirmed when opening hardware sessions
```

Real execution remains blocked unless the concrete backend identity, connected target,
artifact hash, electrical evidence required by that adapter, recovery plan, environment
flag, and confirmation token all validate.

### Task 8.2: Generic C/C++ and Python adapters

CMake adapter detects presets/generators, plans configure/build/test, confines output to
approved build roots, and classifies logs. Python adapter detects environment metadata,
offers read-only inspection/test discovery, and requires confirmation before dependency
installation or source modification. Do not execute arbitrary project scripts during
detection.

### Task 8.3: MaixCAM and OpenMV adapters

Detect user applications separately from installed IDE/SDK content. Initial operations:
inspect project, identify entry point and board hints, validate syntax/import layout,
index vision assets/models, collect logs, and create run/deploy plans. Real device upload
or run must use a verified tool/device adapter and confirmed task.

Validate using `D:\maixcam_E12_TASK1_ONLY` and user-selected Maix/OpenMV projects, but
commit only minimal synthetic fixtures.

### Task 8.4: EDA/BOM/document adapter

Wrap `nextboard/` hardware solution workflows and existing document/evidence modules.
First mature scope is detection, indexing, BOM normalization, schematic/PCB artifact
association, constraint/risk reports, and evidence-backed reviews. Do not implement
automatic PCB edits, ordering, purchasing, or guessed component parameters.

Every critical component fact must cite datasheet/distributor evidence and pass
`nextboard` verification gates.

### Task 8.5: Serial, CAN, network, SSH, and terminal adapters

Wrap `embeddedskills` as an external runtime through `runtime_context`. Read-only scan
and short bounded observation can be automatic only when the underlying script is
read-only. Send/transmit/connect/capture actions use confirmed or high-risk authority as
appropriate. Network discovery never expands beyond explicitly configured targets.

Phase verification:

```powershell
pytest tests/contract/adapters tests/integration/platform -v --no-cov
python nextboard/tests/validate.py
python tools/hardware_butler.py doctor --root tests/fixtures/cubemx-basic --json
```

Additionally run each affected `embeddedskills` script in dry-run/simulation mode and
require JSON `status` to be honest. Phase gate: at least one STM32 fixture, one generic
project, one Maix/OpenMV fixture, and one EDA fixture complete inspect -> plan -> safe
result -> evidence. Commit `feat: connect initial rd platform adapters`.

---

# Phase 9: Plugin SDK, Packaging, and Third-Party Extension

**Outcome:** New platforms such as ESP32, Arduino, RISC-V, FPGA, Linux boards,
instruments, and mechanical controllers can be added without changing the kernel.

**Files:**
- Create: `tools/platform/plugin_manifest.py`
- Create: `tools/platform/plugin_loader.py`
- Create: `docs/platform/adapter-sdk.md`
- Create: `examples/adapters/hello_board/`
- Modify: `tools/package_hardware_butler_plugin.py`
- Create: `tests/unit/platform/test_plugin_loader.py`
- Create: `tests/contract/adapters/test_reference_package.py`

### Task 9.1: Define plugin manifest

Use a declarative `nextboard-adapter.json` containing ID, contract version,
implementation version, Python entry point, platform support, declared capabilities,
minimum NextBoard version, and package hash. Loading code is never fetched from the
network automatically.

### Task 9.2: Implement trusted local loading

Search explicit user plugin directories only. Validate manifest and contract before
import. A broken plugin is quarantined in diagnostics, not allowed to crash startup.
Unsigned/untrusted plugins require explicit user enablement; plugin settings and trust
state are local.

### Task 9.3: Build one reference adapter package

The example adapter detects a synthetic `hello-board.json` project and exposes one
automatic inspect operation. Include complete tests and documentation so another AI can
clone the pattern for ESP32/FPGA without reading kernel internals.

### Task 9.4: Update distributed Codex plugin safely

Teach the package builder to include `tools/platform/` and generated manifests. Never
hand-edit copied source under `plugins/hardware-development-butler/scripts/tools/`.
Run package sync tests and validate the packaged CLI in an isolated temp directory.

Phase gate: install the reference adapter locally, discover its project, invoke it,
disable it, and survive a deliberately broken plugin. Commit
`feat: add adapter sdk packaging and diagnostics`.

---

# Phase 10: Local API, Web-Ready Boundary, and Remote Nodes

**Outcome:** The desktop remains local-first while stable interfaces permit a future Web
console and explicitly trusted remote execution nodes.

**Files:**
- Create: `tools/platform/api/schemas.py`
- Create: `tools/platform/api/auth.py`
- Create: `tools/platform/api/local_server.py`
- Create: `tools/platform/remote/protocol.py`
- Create: `tools/platform/remote/node_agent.py`
- Create: `tools/platform/remote/scheduler.py`
- Create: `tools/platform/migrations/v003_remote_nodes.py`
- Create: `tests/unit/platform/test_api_schemas.py`
- Create: `tests/integration/platform/test_local_api.py`
- Create: `tests/integration/platform/test_remote_protocol.py`
- Create: `docs/platform/remote-nodes.md`

### Task 10.1: Freeze serializable service schemas

Expose workspace/project/tool/device/task/evidence/settings operations through versioned
request/response schemas. API schemas map to domain types but do not leak SQLite rows,
filesystem handles, exceptions, confirmation tokens, or provider secrets.

### Task 10.2: Implement loopback-only local API

Default bind is `127.0.0.1` on an ephemeral/configured port. Require a randomly generated
local session credential stored outside logs. Reject non-loopback binding unless the
user explicitly configures TLS and authentication. Add rate limits and request size
limits before accepting task inputs.

### Task 10.3: Define remote node trust and protocol

Nodes advertise identity, versions, adapters, capabilities, health, and resource limits.
Pairing is explicit with public-key fingerprint confirmation. The coordinator sends
typed capability requests, never arbitrary shell strings. High-risk confirmation is
performed at the controlling client and revalidated by the node.

### Task 10.4: Implement scheduling conservatively

The scheduler selects only trusted healthy nodes with exact capability and adapter
contract matches. Local execution remains the default. Network loss marks task state
unknown/blocked until reconciled; it never retries a non-idempotent hardware action
automatically.

Phase verification:

```powershell
pytest tests/unit/platform/test_api_schemas.py tests/integration/platform/test_local_api.py tests/integration/platform/test_remote_protocol.py -v --no-cov
```

Phase gate: a loopback client lists workspaces; a fake paired node executes a read-only
fixture capability; arbitrary command injection and stale confirmations are rejected.
Commit `feat: add local api and remote node protocol`.

---

# Phase 11: Reliability, Performance, Security, and Migration

**Outcome:** Existing users can upgrade safely, large disks remain responsive, and core
trust boundaries have adversarial coverage.

**Files:**
- Create: `tools/platform/migration_legacy.py`
- Create: `tests/performance/test_discovery_budget.py`
- Create: `tests/security/test_path_and_command_boundaries.py`
- Create: `tests/security/test_secret_redaction.py`
- Create: `tests/security/test_confirmation_replay.py`
- Create: `tests/integration/platform/test_legacy_migration.py`
- Modify: `docs/platform/migration.md`
- Create: `docs/platform/safety-model.md`
- Create: `docs/platform/workspace-data.md`

### Task 11.1: Migrate legacy project state

Read `.hardware-butler/project-state.json` and existing inspection directories without
deleting or rewriting them. Import references into the catalog, attach provenance
`legacy-import`, and make repeated imports idempotent. Provide dry-run report and an
explicit confirmation before any migration writes.

### Task 11.2: Establish performance budgets

On a synthetic tree of 20,000 directories and 100,000 files, staged discovery must
honor configured limits, emit partial results with a scan-limit exclusion, remain
cancellable, and avoid loading full file contents. Set measurable budgets from baseline
hardware; document machine and observed results rather than inventing universal timing.

### Task 11.3: Add security regression suite

Cover path traversal, symlink/junction escape, malicious filenames, shell metacharacters,
oversized output, poisoned plugin manifests, secret-like fields, confirmation replay,
expired tokens, changed artifact hashes, remote node impersonation, and API non-loopback
binding. Run `pip audit` when available and record unavailable tooling honestly.

### Task 11.4: Crash recovery and backups

Test SQLite interruption, evidence atomic-write failure, cancelled scans, killed tool
processes, and restart with a running task. On restart, running tasks become
`blocked` with recovery guidance unless an adapter supplies a verified reconciliation
method. Provide catalog backup/export and restore validation.

Phase gate: legacy state imports without data loss, security suite passes, interrupted
tasks recover honestly, and bounded discovery respects limits. Commit
`feat: harden platform migration and recovery`.

---

# Phase 12: Beta Integration, Packaging, and Acceptance

**Outcome:** A distributable Beta foundation that a beginner can start, an expert can
automate, and a maintainer can extend and verify before broader product domains are
added in Phases 13-17.

**Files:**
- Modify: `README.md`
- Modify: `docs/START_HERE.md`
- Modify: `docs/COMMANDS.md`
- Modify: `docs/ARCHITECTURE_MAP.md`
- Modify: `docs/INSTALL.md`
- Modify: `docs/RELEASE_PROCESS.md`
- Create remaining `docs/platform/*.md` files from Section 3
- Modify: `pyproject.toml`
- Modify: `tools/build_workbench_exe.py`
- Modify: `tools/release_verify.py`
- Modify: `tools/package_hardware_butler_plugin.py`
- Create: `tests/acceptance/test_universal_workbench.py`

### Task 12.1: Rewrite public product entry points accurately

Describe NextBoard as a universal local-first R&D workbench, not an STM32-only agent.
Show the actual first five-minute workflow, initial supported adapters, optional AI,
safety levels, data location, and extension path. Clearly separate available, limited,
planned, simulated, and hardware-verified capabilities.

### Task 12.2: Package CLI, GUI, platform kernel, migrations, and adapters

Ensure wheels and Windows GUI bundle include migration modules, built-in adapters,
icons/assets, and no user catalog or credentials. Test installed-package execution in a
fresh temp environment. Regenerate the Codex plugin through the packager and validate
its manifest and runtime resolution.

### Task 12.3: Run the complete automated gate

```powershell
ruff check tools/ tests/ gui/
mypy tools/ --config-file mypy.ini
pytest tests/ -v
python nextboard/tests/validate.py
python plugins/hardware-development-butler/scripts/validate_package.py
python tools/release_verify.py
```

Expected: all non-hardware tests pass. Hardware tests are separate and never silently
skipped inside the release report.

### Task 12.4: Run real D-drive acceptance matrix

Use user-selected roots and sanitize stored evidence:

| Scenario | Expected result |
| --- | --- |
| STM32 fixture/project | detect CubeMX/Keil/CMake facets, inspect, plan build, archive evidence |
| `D:\电赛准备\26\mock-problems\2026-control\...` | detect real CMake projects without scanning unrelated disk content |
| `D:\maixcam_E12_TASK1_ONLY` | detect MaixCAM and STM32 facets as one multi-facet project or linked projects based on root structure |
| `D:\openmv` installation | classify installation/SDK content as excluded, not a user project |
| user OpenMV script | classify user project and create inspect/run plan |
| `D:\STM32CubeMX\jre\bin\jlink.exe` | classify as Java jlink, never SEGGER |
| serial/CAN/network adapters | enumerate only; transmit/connect requires confirmation |
| no AI profile | all deterministic onboarding/build/diagnostic flows remain usable |
| fake or user-configured AI | explanation works; unknown command/capability is rejected |

### Task 12.5: Hardware-in-the-loop acceptance

Only when the user provides actual targets and approves execution, run
`pytest tests/hardware -v --run-hardware --target <mcu> --port <port>` plus adapter-
specific flash/debug/observe checks. Record board, probe, firmware hash, voltage/current
evidence, backend identity, confirmation, outcome, and recovery. Absence of hardware is
reported `not-run`.

### Task 12.6: Beta decision

Mark the platform foundation Beta only when:

- all automated gates pass;
- migration dry-run and restore are verified;
- capability matrix matches reality;
- GUI screenshots show no overlap at required sizes;
- no plaintext secrets/tokens appear in repo, package, logs, or fixtures;
- root and `embeddedskills` ownership boundaries remain intact;
- changelog lists breaking changes, migrations, known limitations, and rollback;
- version is updated consistently in `pyproject.toml`, package metadata, GUI, plugin,
  and docs.

Commit `docs: complete universal platform beta workflow`. Do not describe this gate as
the mature 1.0 product: concrete platform breadth, instruments, Web/cloud, multi-agent
collaboration, and product operations are completed in the following phases. Do not
push, publish, tag, or create a remote release without explicit user approval.

---

# Phase 13: Concrete MCU, FPGA, Linux, and Edge Platform Adapters

**Outcome:** The product is demonstrably broader than STM32 and vision boards, with
maintained adapters for representative ecosystems rather than empty extension points.

**Files:**
- Create: `tools/platform/adapters/esp_idf.py`
- Create: `tools/platform/adapters/arduino.py`
- Create: `tools/platform/adapters/platformio.py`
- Create: `tools/platform/adapters/riscv.py`
- Create: `tools/platform/adapters/fpga.py`
- Create: `tools/platform/adapters/linux_board.py`
- Create: `tests/contract/adapters/test_esp_idf_adapter.py`
- Create: `tests/contract/adapters/test_arduino_platformio_adapters.py`
- Create: `tests/contract/adapters/test_riscv_adapter.py`
- Create: `tests/contract/adapters/test_fpga_adapter.py`
- Create: `tests/contract/adapters/test_linux_board_adapter.py`
- Create: `tests/fixtures/platform/adapters/esp-idf/`
- Create: `tests/fixtures/platform/adapters/arduino/`
- Create: `tests/fixtures/platform/adapters/riscv/`
- Create: `tests/fixtures/platform/adapters/fpga/`
- Create: `tests/fixtures/platform/adapters/linux-board/`
- Create: `docs/platform/supported-platforms.md`

### Task 13.1: ESP-IDF adapter

Detect `CMakeLists.txt`, `sdkconfig`, component manifests, partitions, and `idf.py`
identity. Provide inspect, target/config summary, build plan, build, flash plan, monitor
plan, and size diagnostics. Build is automatic only within a registered build directory;
flash and monitor are confirmed and require exact port/target binding.

Contract acceptance:

```text
esp-idf.inspect       automatic
esp-idf.build         automatic
esp-idf.plan-flash    automatic
esp-idf.flash         confirmed
esp-idf.monitor       confirmed
esp-idf.erase-flash   high-risk
```

### Task 13.2: Arduino CLI and PlatformIO adapters

Arduino adapter verifies `arduino-cli`, board FQBN, libraries, and sketch root before
compile/upload. PlatformIO adapter detects `platformio.ini`, environments, frameworks,
boards, and build targets. Dependency installation and upload require confirmation.
Never infer a board or port solely from an old build cache.

### Task 13.3: RISC-V adapter

Support generic CMake/Make RISC-V GCC projects plus toolchain identity, ELF inspection,
OpenOCD/probe-rs plan creation, and target-specific adapter metadata. Initial hardware
validation selects one available RISC-V fixture or board; unsupported vendor SDKs are
reported accurately and still retain generic build/inspect capability.

### Task 13.4: FPGA adapter

Detect Verilog/SystemVerilog/VHDL projects and vendor manifests for at least one
available toolchain. Provide source/top/constraint discovery, lint/synthesis plan,
resource/timing report indexing, bitstream evidence, and confirmed programming plan.
Simulation and synthesis are structurally distinct from physical programming. Tool
licenses and headless availability are health diagnostics, not assumed.

### Task 13.5: Linux board and SBC adapter

Support local Linux projects and explicitly configured SSH targets. Capabilities include
system profile, build/package plan, file synchronization preview, service/log inspection,
deployment plan, and rollback plan. Remote execution requires paired target identity,
host-key verification, scoped command templates, and confirmation. No arbitrary AI-
generated SSH command is accepted.

### Task 13.6: Platform breadth gate

For each ecosystem, run reusable adapter contracts, a synthetic fixture workflow, and
one real tool probe when installed. At least four of the five adapter families must
complete inspect -> plan -> safe execution/evidence in CI or reproducible local tests;
missing proprietary tools must produce explicit `unavailable`, not false passes.

Verification:

```powershell
pytest tests/contract/adapters/test_esp_idf_adapter.py tests/contract/adapters/test_arduino_platformio_adapters.py tests/contract/adapters/test_riscv_adapter.py tests/contract/adapters/test_fpga_adapter.py tests/contract/adapters/test_linux_board_adapter.py -v --no-cov
```

Commit `feat: add maintained cross-platform rd adapters`.

---

# Phase 14: Laboratory Instruments, Industrial Protocols, and Motion Control

**Outcome:** The platform can safely coordinate measurement and controlled physical
systems through concrete, testable adapters with simulation-first workflows.

**Files:**
- Create: `tools/platform/instruments/contracts.py`
- Create: `tools/platform/instruments/scpi.py`
- Create: `tools/platform/instruments/visa.py`
- Create: `tools/platform/instruments/modbus.py`
- Create: `tools/platform/instruments/motion.py`
- Create: `tools/platform/instruments/interlocks.py`
- Create: `tools/platform/adapters/instruments.py`
- Create: `tools/platform/adapters/industrial.py`
- Create: `tests/unit/platform/test_scpi_policy.py`
- Create: `tests/unit/platform/test_modbus_policy.py`
- Create: `tests/unit/platform/test_motion_interlocks.py`
- Create: `tests/integration/platform/test_instrument_simulators.py`
- Create: `tests/hardware/test_lab_instruments.py`
- Create: `docs/platform/instruments-and-motion.md`

### Task 14.1: SCPI and VISA instrument support

Implement discovery and typed command templates for oscilloscopes, power supplies,
electronic loads, DMMs, and signal generators. Start with `*IDN?`, bounded queries,
measurement capture, waveform/screenshot evidence, and configuration snapshots. Output
enable, voltage/current changes, arbitrary waveform upload, calibration, and reset are
confirmed or high-risk based on adapter policy.

### Task 14.2: Instrument safety profiles

Each registered instrument has model identity, channel capabilities, configured limits,
load expectations, and safe-off behavior. Commands are typed operations such as
`SetPowerChannel(voltage_v, current_a, output_enabled)` rather than free-form SCPI.
Validate units, ranges, slew constraints, channel, and target identity before encoding.

### Task 14.3: Modbus and industrial protocol support

Support read-only register maps, polling plans, decoded evidence, and confirmed writes
for explicitly configured Modbus TCP/RTU targets. Register type, width, endianness,
scale, unit, allowed range, and write authority come from a user-approved device profile.
No broad network scan or guessed register writes.

### Task 14.4: Motion-control contract and interlocks

Define typed operations for home, jog, absolute/relative move, stop, enable, and status.
Real motion is high-risk unless an adapter proves configured travel limits, units,
velocity/acceleration limits, emergency stop state, homing state, target identity, and a
working stop command. Require simulation/digital-twin preview, dry-run path, explicit
operator confirmation, bounded timeout, and continuous cancellation/stop handling.

### Task 14.5: Simulator-first integration tests

Build deterministic SCPI, Modbus, and motion simulators. Test disconnection, malformed
responses, over-limit setpoints, stale device identity, emergency-stop activation,
timeout, cancellation, and evidence capture. Hardware tests remain opt-in and must use
user-approved bench profiles.

Verification:

```powershell
pytest tests/unit/platform/test_scpi_policy.py tests/unit/platform/test_modbus_policy.py tests/unit/platform/test_motion_interlocks.py tests/integration/platform/test_instrument_simulators.py -v --no-cov
```

Phase gate: simulated measurement and motion workflows complete end to end; every
physical write path is blocked without a registered safety profile and confirmation.
Commit `feat: add instruments industrial and motion workflows`.

---

# Phase 15: Production Web Console, Cloud Services, Accounts, and Synchronization

**Outcome:** A complete optional Web/cloud product complements local-first desktop use
without making cloud connectivity mandatory.

**Files:**
- Create: `web/` frontend application using the repository-selected framework
- Create: `server/` authenticated API service
- Create: `tools/platform/cloud/sync.py`
- Create: `tools/platform/cloud/conflicts.py`
- Create: `tools/platform/cloud/permissions.py`
- Create: `tests/e2e/web/`
- Create: `tests/integration/platform/test_cloud_sync.py`
- Create: `tests/security/test_tenant_isolation.py`
- Create: `docs/platform/web-and-cloud.md`

### Task 15.1: Freeze product API and authentication model

Version the API, generate client types from schemas, and define users, organizations,
workspaces, roles, service identities, sessions, and audit events. Roles: owner, admin,
engineer, operator, reviewer, and viewer. Hardware execution additionally requires a
local/node confirmation; cloud role alone is never sufficient.

### Task 15.2: Build the actual Web console

Implement authenticated workspace, project, task, device, evidence, adapter, node, team,
and settings views. Match desktop operational density and workflows. Include live task
progress, confirmation routing, evidence preview/download, node health, search, filters,
empty/loading/error/offline states, responsive layout, keyboard accessibility, and no
marketing landing page as the signed-in primary experience.

### Task 15.3: Implement opt-in synchronization

Synchronize metadata, settings selected by policy, task summaries, and chosen evidence.
Source trees and large binaries remain local unless explicitly included. Use version
vectors or equivalent conflict metadata; surface conflicts instead of last-writer-wins
loss. Support pause, resume, retry, offline queue, export, and account disconnect.

### Task 15.4: Tenant isolation and secret boundaries

Enforce organization/workspace authorization at every server query. Provider secrets,
node private keys, local confirmation tokens, and raw hardware credentials never sync.
Add tenant-isolation, IDOR, session expiry, CSRF/CORS, rate-limit, upload validation, and
audit-log tests.

### Task 15.5: Deployment and operations

Provide development, self-hosted, and managed deployment configurations; health/readiness
checks; database migrations; backup/restore; structured logs; metrics; and rollback.
Do not choose or deploy a paid external service without user approval. Keep local-only
mode fully supported and visible in tests.

Verification includes backend tests, browser E2E, accessibility scans, responsive
screenshots, tenant security tests, and an offline local-only regression. Phase gate:
two test users in separate organizations cannot access each other's data; one user can
move between desktop and Web task history without syncing secrets/source by default.
Commit `feat: add production web and cloud collaboration`.

---

# Phase 16: Multi-Agent Orchestration and Team Collaboration

**Outcome:** Complex R&D goals can be decomposed among specialized agents and humans
with review, budgets, provenance, and the same safety gates as manual tasks.

**Files:**
- Create: `tools/platform/agents/contracts.py`
- Create: `tools/platform/agents/roles.py`
- Create: `tools/platform/agents/orchestrator.py`
- Create: `tools/platform/agents/review.py`
- Create: `tools/platform/agents/budgets.py`
- Create: `tools/platform/agents/memory.py`
- Create: `tests/unit/platform/test_agent_orchestrator.py`
- Create: `tests/unit/platform/test_agent_review.py`
- Create: `tests/integration/platform/test_multi_agent_workflow.py`
- Create: `docs/platform/multi-agent.md`

### Task 16.1: Define agent roles and permissions

Initial roles: project explorer, firmware engineer, hardware architect, vision engineer,
host/cloud engineer, lab operator, safety reviewer, and release reviewer. Each role has
read scopes, allowed proposal types, disallowed capabilities, model profile selection,
time/token/tool budgets, and required reviewers.

### Task 16.2: Implement goal decomposition into typed work items

The orchestrator decomposes a goal into dependency-linked tasks that reference registered
projects, capabilities, evidence, expected outputs, and acceptance tests. Agents propose
plans and artifacts; they never receive blanket shell or hardware authority.

### Task 16.3: Add independent review and conflict resolution

Mutating code/config proposals require test evidence. Hardware plans require safety
review. Conflicting conclusions are retained with provenance and surfaced to a human;
the orchestrator does not conceal disagreement. Require review before merging agent
outputs into an executable task plan.

### Task 16.4: Add resumable execution and audit

Persist agent runs, prompts after redaction, model/provider identity, tool calls,
artifacts, decisions, costs/usage when available, failures, handoffs, and approvals.
Resume only from committed task state; do not replay non-idempotent hardware operations.

### Task 16.5: Human collaboration

Implement comments, assignments, review requests, approval queues, task ownership,
notifications, and audit history in desktop/Web clients. Notifications must not expose
secrets or proprietary evidence content.

Phase gate: a cross-domain fixture goal is decomposed, analyzed by at least three fake
role agents, reviewed, converted into tasks, and completed in simulation while a
malicious agent command and unauthorized hardware action are rejected. Commit
`feat: add governed multi-agent collaboration`.

---

# Phase 17: Product Operations, Updates, Supportability, and Quality SLOs

**Outcome:** The product can be installed, upgraded, diagnosed, supported, and improved
without requiring its author to manually repair each machine.

**Files:**
- Create: `tools/platform/updates.py`
- Create: `tools/platform/diagnostics.py`
- Create: `tools/platform/telemetry.py`
- Create: `tools/platform/support_bundle.py`
- Create: `tests/integration/platform/test_upgrade_paths.py`
- Create: `tests/unit/platform/test_support_bundle_redaction.py`
- Create: `tests/performance/test_product_slos.py`
- Create: `docs/platform/support.md`
- Create: `docs/platform/quality-slos.md`
- Create: `docs/platform/privacy.md`

### Task 17.1: Installer, updater, and rollback

Produce signed/versioned installation artifacts where the release environment permits.
Support clean install, in-place upgrade, migration preview, backup, rollback to the
previous compatible version, uninstall that preserves user data by default, and a
portable local mode. Failed update must leave the prior runnable version intact.

### Task 17.2: Diagnostics and support bundles

Add one-click/CLI diagnostics for version, schema, adapters, tools, devices, node health,
permissions, recent normalized failures, and package integrity. Support bundles are
previewable, redact secrets/tokens/usernames/private paths where configured, exclude
source files by default, and require explicit user creation.

### Task 17.3: Privacy-preserving product analytics

Telemetry is off by default. If explicitly enabled, collect only documented coarse
events and performance/error aggregates; never collect source, prompts, evidence body,
device payloads, secrets, or absolute paths. Provide local event preview, retention,
export, and delete controls.

### Task 17.4: Define and enforce quality SLOs

Measure on a documented reference machine:

- cold desktop startup and workspace render;
- cancellation response for scans/tasks;
- discovery throughput and memory bound;
- task/event persistence latency;
- crash-free automated workflow rate;
- API availability under integration load;
- sync recovery after network interruption;
- installer/upgrade success across supported Windows versions.

Set release thresholds from measured Beta baselines, record machine and dataset, and
fail release verification when a threshold regresses beyond its documented tolerance.

### Task 17.5: Support and compatibility policy

Publish supported OS/Python/tool versions, adapter support levels, deprecation windows,
database migration policy, plugin compatibility matrix, security reporting path, backup
expectations, and release channels (stable/beta). Automate checks that docs and package
metadata agree.

Phase gate: clean install, upgrade from Beta, forced failed migration rollback, support
bundle generation, telemetry-off validation, and quality SLO suite all pass. Commit
`feat: add product updates diagnostics and quality gates`.

---

# Phase 18: Mature Product 1.0 Release and End-to-End Qualification

**Outcome:** A supportable NextBoard 1.0 product, not merely an extensible technical
foundation.

**Files:**
- Modify all release/version files from Phase 12
- Create: `docs/platform/1.0-qualification.md`
- Create: `docs/platform/known-limitations.md`
- Create: `tests/acceptance/test_product_1_0.py`
- Create: `tests/acceptance/test_beginner_journey.py`
- Create: `tests/acceptance/test_professional_journey.py`
- Create: `tests/acceptance/test_team_journey.py`

### Task 18.1: Run persona journeys

Beginner journey: install -> create workspace -> discover a project -> inspect -> receive
clear next action -> build/diagnose -> find evidence, without CLI knowledge.

Professional journey: configure multiple roots/tools/models -> run repeatable CLI/API
workflow -> review plan -> execute confirmed hardware simulation/approved bench action ->
export evidence -> create a custom adapter.

Team journey: create organization -> assign task -> coordinate agents/humans -> review
and approve -> execute on trusted node -> inspect audit/evidence -> recover from failure.

### Task 18.2: Run domain qualification matrix

Qualify STM32, ESP-IDF, Arduino/PlatformIO, one RISC-V path, one FPGA path, Linux/SBC,
MaixCAM/OpenMV, generic Python/CMake, EDA/BOM review, serial, CAN, network/SSH, SCPI/VISA,
Modbus, and motion simulation. Each domain must state support level and pass its contract;
domains requiring unavailable proprietary tools may be `limited` but cannot be called
fully supported.

### Task 18.3: Run security, privacy, recovery, and compatibility gates

Execute all unit/integration/contract/E2E/security/performance/package tests; clean-
machine installer tests; upgrade and rollback; backup/restore; secret scan; tenant
isolation; confirmation replay; plugin quarantine; node trust; offline operation; and
crash recovery. Resolve every severity-1/2 issue and document accepted lower-severity
limitations with owner and target release.

### Task 18.4: Conduct controlled hardware qualification

Use only available, user-approved lab hardware. For each tested target, record exact
device/probe/instrument identity, versions, artifacts, electrical limits, confirmation,
result, and recovery. Untested hardware is labeled unverified. Demonstrate emergency
stop/cancellation for any approved motion test before normal motion qualification.

### Task 18.5: Final product truth audit

Cross-check GUI, CLI help, API schema, adapter metadata, README, capability matrix,
installer, plugin package, changelog, privacy statement, and known limitations. Every
visible claim must map to a passing test or an explicitly labeled support level.

### Task 18.6: 1.0 release gate

1.0 is eligible only when:

- beginner, professional, and team journeys pass;
- local-only mode, optional cloud mode, and no-AI mode all pass;
- required quality SLOs pass on documented machines;
- supported adapter families pass contracts and qualification;
- installer, upgrade, rollback, backup, restore, and uninstall pass;
- no unresolved severity-1/2 correctness, safety, security, or data-loss issue remains;
- simulation, limited, unverified, and hardware-verified states are truthful everywhere;
- support, privacy, security, migration, and known-limitations docs are complete;
- release artifacts contain no credentials, user state, private paths, or proprietary
  fixtures;
- explicit user approval is obtained before tag, push, publication, or deployment.

Commit `release: qualify NextBoard 1.0` only after the complete verification output is
fresh. Publication remains a separate user-approved external action.

---

## 6. Cross-Phase Testing Matrix

| Risk | Required test level | Required phases |
| --- | --- | --- |
| Domain/state transition | unit | 1, 5 |
| SQLite migration/rollback | unit + integration | 1, 6, 10, 11, 15, 17, 18 |
| Adapter compatibility | reusable contract | 2, 8, 9, 13, 14, 18 |
| SDK/IDE false positives | fixture + real read-only acceptance | 3, 12, 18 |
| Command construction | unit with argument arrays | 3, 5, 8, 13, 14 |
| Secret/token leakage | unit + security scan | 5, 6, 10, 11, 12, 15, 16, 17, 18 |
| Hardware authority bypass | adversarial integration | 5, 8, 10, 11, 13, 14, 16, 18 |
| GUI responsiveness | view-model + UI smoke | 7, 12, 15, 18 |
| Web accessibility/responsiveness | browser E2E + screenshots | 15, 18 |
| Tenant and role isolation | integration + security | 15, 16, 18 |
| Multi-agent governance | deterministic fake-agent integration | 16, 18 |
| Instrument and motion interlocks | simulator + opt-in hardware | 14, 18 |
| Installer/update/rollback | clean-machine acceptance | 12, 17, 18 |
| Backup/restore/data retention | integration + disaster recovery | 11, 15, 17, 18 |
| Quality SLO regression | performance benchmark | 11, 17, 18 |
| Legacy CLI regression | existing suite | 4 onward |
| Plugin package drift | package validation | 9, 12, 13, 14, 18 |
| Real hardware | opt-in hardware tests | 8, 12, 13, 14, 18 |

## 7. Definition of Done for Every Phase

A phase is complete only when all statements are true:

- production behavior was preceded by a focused failing test;
- focused tests pass;
- relevant legacy regressions pass;
- Ruff and mypy pass for changed Python modules;
- errors are normalized and evidence is sanitized;
- documentation describes only behavior that exists;
- `git diff --check` is clean;
- `git status --short` contains only intended files;
- independent `embeddedskills` changes are unchanged unless explicitly owned;
- one scoped commit exists with a meaningful message;
- the phase gate has been demonstrated and recorded.

## 8. Global Acceptance Criteria

The mature 1.0 product is accepted only after Phase 18 when:

1. A new user creates a local workspace, selects roots, reviews candidates, registers a
   project, runs inspection/build or deterministic diagnosis, and finds all evidence
   from the desktop UI without knowing CLI commands.
2. An expert performs the equivalent workflow through stable JSON CLI/API contracts.
3. STM32, ESP-IDF, Arduino/PlatformIO, generic RISC-V, at least one FPGA flow,
   Linux/SBC, CMake C/C++, Python, MaixCAM/OpenMV, EDA documents, serial, CAN,
   network/SSH, SCPI/VISA, Modbus, and motion simulation coexist without platform
   assumptions in the kernel and have explicit support levels.
4. Tool identity is evidence-based and the Java `jlink.exe` regression is fixed.
5. AI is entirely user-configured and optional; disabling it preserves core behavior.
6. Mutating and hardware actions cannot bypass typed plans, policy, fresh confirmation,
   target/artifact binding, and audit evidence.
7. Simulation and real hardware outcomes are visibly and structurally distinct.
8. Installed SDK/IDE trees do not flood the project catalog, while explicit user
   overrides remain possible and explainable.
9. Existing CLI capabilities and `nextboard` validation continue to work.
10. Third-party adapters can be installed, diagnosed, disabled, and upgraded without
    editing kernel or GUI code.
11. Local API and trusted nodes exchange typed capability requests, never arbitrary
    remote shell commands.
12. Packaging contains no user state or secrets and passes clean-install validation.
13. Desktop and Web clients implement equivalent primary workflows with accessible,
    responsive, non-blocking interfaces and complete empty/loading/error/offline states.
14. Optional cloud synchronization preserves local-first operation, excludes source and
    secrets by default, surfaces conflicts, and enforces tenant/role isolation.
15. Multi-agent work is bounded by roles, budgets, evidence, independent review, human
    approvals, and the same capability/safety system as manual work.
16. Instrument, industrial, and motion actions use typed operations, configured limits,
    interlocks, simulation, cancellation, confirmation, and audit rather than raw model
    commands.
17. Clean install, upgrade, failed-upgrade rollback, backup/restore, uninstall, portable
    mode, diagnostics, and redacted support bundle workflows pass on supported systems.
18. Telemetry remains off by default, is inspectable/deletable when enabled, and never
    includes source, prompts, evidence bodies, device payloads, secrets, or absolute
    paths.
19. Beginner, professional, and team end-to-end journeys pass against packaged builds,
    not only source checkouts.
20. No severity-1/2 correctness, safety, security, privacy, or data-loss issue remains;
    lower-severity limitations are documented with support level and ownership.

### Product Completion Levels

| Gate | Meaning | May be called mature product? |
| --- | --- | --- |
| Phase 4 | Headless workspace foundation | No |
| Phase 8 | Useful local multi-domain alpha | No |
| Phase 12 | Installable Beta foundation | No |
| Phase 14 | Broad hardware/lab Beta | No |
| Phase 16 | Collaborative platform release candidate | Not yet |
| Phase 17 | Operationally supportable release candidate | Not yet |
| Phase 18 | Qualified NextBoard 1.0 | Yes, only if every Phase 18 gate passes |

## 9. Explicitly Prohibited Shortcuts

- Do not rewrite the application in another framework before the kernel and contracts
  are stable.
- Do not add platform `if/elif` chains to GUI or services; use adapter metadata.
- Do not make whole-drive scanning the default.
- Do not identify tools solely by executable filename.
- Do not use AI output as raw shell, Python, SQL, device, CAN, serial, or network input.
- Do not weaken confirmation because a task originated from AI or a trusted plugin.
- Do not commit API keys, local catalogs, D-drive paths, hardware tokens, or proprietary
  project contents.
- Do not manually maintain the plugin's copied source tree.
- Do not claim broad ESP32/FPGA/Linux/instrument support until concrete adapters pass the
  same contract and acceptance gates.
- Do not call Phase 12 or any earlier milestone the finished mature product.
- Do not make cloud accounts, telemetry, or AI providers mandatory for local workflows.
- Do not expose raw SCPI, Modbus writes, motion commands, SSH commands, or agent-generated
  command strings as a shortcut around typed capabilities.
- Do not declare 1.0 while installer rollback, data restore, support diagnostics,
  beginner/professional/team journeys, or severity-1/2 findings remain incomplete.
- Do not publish or push as part of implementation without explicit user approval.

## 10. Handoff Prompt for Another AI

Use this exact instruction with the plan:

```text
Implement NextBoard according to docs/UNIVERSAL_RD_PLATFORM_MASTER_IMPLEMENTATION_PLAN.md.
Read AGENTS.md and the approved design first. Work in an isolated Git worktree. Execute
only one numbered phase at a time through Phase 18, using TDD and the listed verification commands. At
each phase gate, report changed files, tests, unresolved risks, and the next phase; do
not begin the next phase until the current gate passes. Preserve the independent dirty
embeddedskills repository and never bypass hardware safety gates. Phase 12 is Beta, not
the finished product; only Phase 18 may qualify mature 1.0. Do not push, publish, operate
real hardware, or deploy paid cloud resources without explicit user approval.
```
