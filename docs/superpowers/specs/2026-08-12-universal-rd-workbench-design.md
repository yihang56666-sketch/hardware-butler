# NextBoard Universal R&D Workbench Design

Date: 2026-08-12
Status: Approved design

## 1. Purpose

NextBoard will evolve from an STM32-oriented Hardware Butler into a local-first,
extensible software and hardware R&D workbench. The product must help a user move
from an unregistered real project to an evidence-backed result through one coherent
workflow:

1. discover installed tools, devices, and candidate projects;
2. register them in a workspace;
3. understand project structure and environment health;
4. turn a user goal into a reviewable task plan;
5. execute permitted steps through capability adapters;
6. retain logs, artifacts, decisions, and recovery guidance as evidence.

The first release is a local desktop application with a CLI-compatible application
service. Its interfaces must allow later Web consoles, remote execution nodes, and
cloud coordination without requiring a rewrite of the domain model.

## 2. Product Principles

- **Universal core, concrete adapters.** STM32, MaixCAM, and OpenMV are initial
  adapters and validation projects, not assumptions embedded in the core.
- **Useful without AI.** Discovery, inspection, builds, deterministic diagnostics,
  safety checks, and fixed workflows continue to work when no model is configured.
- **User-owned AI configuration.** Providers, endpoints, model names, and credentials
  are configured by the user. The repository contains no personal key or mandatory
  provider.
- **Evidence before action.** Recommendations and execution plans cite project,
  environment, manual, or runtime evidence and label uncertain conclusions.
- **Progressive authority.** Read-only work can run automatically. Mutating or
  physical actions require increasingly strong review and confirmation.
- **Local data ownership.** Project metadata, task history, and evidence are local by
  default. Remote synchronization is opt-in and outside the first release.
- **Preserve existing value.** Existing `tools/`, `nextboard/`, and `embeddedskills/`
  capabilities are wrapped behind stable interfaces rather than replaced wholesale.

## 3. Scope

### 3.1 First Release

The first implementation cycle delivers a universal platform skeleton and one real
end-to-end workflow. It includes:

- workspace creation and persistence;
- configurable scan roots and project registration;
- tool discovery with executable identity validation;
- classification of user projects, installed SDKs, bundled examples, and unrelated
  directories;
- project adapters for STM32/CubeMX, CMake C/C++, generic Python, MaixCAM, OpenMV,
  and EDA/BOM document discovery;
- tool adapters for Keil, Arm GCC, CMake, Ninja, EIDE, J-Link, and OpenOCD where the
  corresponding runtime is genuinely installed;
- communication capability descriptors for serial, CAN, and network workflows;
- a task engine spanning inspect, analyze, build, diagnose, plan, confirm, execute,
  and archive;
- an evidence store for reports, logs, artifacts, provenance, and task transitions;
- a modular desktop workbench for projects, tasks, devices, evidence, and settings;
- existing CLI behavior retained through the same application services;
- a provider-neutral AI configuration and routing boundary;
- safety-gated real execution when an adapter implements and validates it.

### 3.2 Deferred Capabilities

The following are extension targets, not first-release promises:

- ESP32, Arduino, RISC-V, FPGA, and Linux board adapters;
- deep schematic or PCB editing and EDA ordering automation;
- autonomous mechanical motion or laboratory instrument control;
- Web console, cloud accounts, collaboration, and remote node scheduling;
- fleet provisioning and unattended high-risk hardware actions;
- a marketplace or automatic installation of third-party adapters.

The first release defines interfaces for these capabilities but does not implement
empty UI controls that imply they already work.

## 4. Chosen Architecture

Three approaches were considered:

1. continue adding behavior directly to the current GUI;
2. build a plugin-oriented local workbench around an application kernel;
3. replace the application immediately with a distributed Web platform.

Approach 2 is selected. It reuses proven Python code and provides clear extension
boundaries while avoiding premature cloud infrastructure. Direct GUI expansion
would preserve the current fragmentation, while an immediate distributed rewrite
would delay usable hardware workflows and increase migration risk.

```text
Desktop UI -----------+
CLI ------------------+--> Application Services
Future local Web API -+          |
                                 +--> Registry and Discovery
                                 +--> Task and Workflow Engine
                                 +--> AI Router
                                 +--> Safety Policy Engine
                                 +--> Evidence Store
                                          |
                                          +--> Capability Adapters
                                               |- project adapters
                                               |- tool adapters
                                               |- device/transport adapters
                                               `- future remote-node adapters
```

The desktop UI and CLI are clients of application services. They must not call
tool-specific subprocesses or parse project formats directly.

## 5. Domain Model

The core uses six stable aggregate types.

### 5.1 Workspace

A workspace is the user's local catalog and operating context. It owns scan roots,
registered projects, user preferences, task history, and references to evidence. A
workspace may contain projects from unrelated directories and technology stacks.

### 5.2 Project

A project is a user-controlled source or design root. Its descriptor contains:

- stable identifier and canonical root path;
- display name and lifecycle state;
- one or more detected facets, such as firmware, vision, host application, PCB, or
  documentation;
- adapter matches with confidence and evidence;
- associated tools, devices, tasks, and artifacts;
- ignored subtrees and classification reasons.

A project can have multiple facets. A robot repository, for example, may contain
STM32 firmware, a Python vision application, and PCB files without being forced into
one platform category.

### 5.3 Tool

A tool represents a verified installed capability, not merely a matching filename.
Its identity includes executable path, product identity, version, discovery source,
supported operations, and health. Discovery probes must distinguish namesakes, such
as Java's `jlink.exe` and SEGGER J-Link.

### 5.4 Device

A device represents an attached or configured execution target or transport endpoint.
It may be a debug probe, serial port, CAN interface, network target, board, instrument,
or future remote node. Device descriptors expose capabilities and connection state;
they do not embed vendor command construction in the core.

### 5.5 Task

A task is a persisted state machine created from a user goal or deterministic command.
It contains inputs, selected capabilities, ordered steps, permissions, status,
timestamps, and evidence references. Core states are:

```text
draft -> planned -> awaiting_confirmation -> running -> succeeded
                                      |          |       |
                                      |          +-----> failed
                                      +---------------> cancelled
```

Read-only tasks may move directly from `planned` to `running`. A failed task records
the failing step, normalized error, raw output reference, and safe recovery actions.

### 5.6 Evidence

Evidence is an immutable record or artifact reference with provenance. Types include
scan observations, project files, tool probe results, manuals, plans, command output,
build artifacts, user confirmations, and diagnostic conclusions. Conclusions use
`confirmed`, `inferred`, or `needs_verification` confidence labels.

## 6. Registries and Adapter Contracts

The kernel owns registries for project detectors, tools, devices, actions, workflows,
and optional AI providers. Adapters register descriptors and callable capabilities;
the UI renders registry data rather than hard-coded platform tabs.

Every adapter declares:

- unique ID, semantic contract version, display metadata, and implementation version;
- supported operating systems and required dependencies;
- detection probes that return evidence and confidence;
- capabilities with typed input/output schemas;
- side-effect and risk classification for each capability;
- dry-run support and cancellation behavior;
- normalized failures and recovery hints;
- health-check and diagnostics entry points.

Adapters cannot bypass the task engine or safety policy. Subprocess invocation goes
through a shared runner that captures command, working directory, exit status,
duration, bounded output, and artifact references. Sensitive values are redacted
before persistence.

Initial adapters wrap current code where possible:

- `tools/` supplies discovery, inspection, evidence, plan, and classification logic;
- `embeddedskills/` supplies build, debug probe, transport, and workflow backends;
- `nextboard/` supplies component, BOM, PCB constraint, and report capabilities.

The independent `embeddedskills/` repository and its existing uncommitted files are
treated as externally owned during migration. Initial integration uses public calls
or thin wrappers in the root repository and does not reset, overwrite, or silently
commit that worktree.

## 7. Discovery and Registration

Discovery is staged to avoid slow or misleading whole-disk scans:

1. scan explicitly configured roots and recently opened locations;
2. discover tools from PATH, known installation metadata, and user-provided paths;
3. run cheap directory signatures to find candidate roots;
4. run adapter-specific probes only on candidates;
5. classify candidates as user project, SDK/runtime, bundled sample, generated output,
   or unknown;
6. present new candidates for bulk review before registration.

Default exclusions include dependency caches, build outputs, IDE installations, SDK
trees, virtual environments, and vendor example collections. Users can include or
exclude roots explicitly, and every exclusion exposes a reason. The scanner must not
register the NextBoard repository itself merely because it is the GUI's current
working directory.

D-drive installations and projects found during discovery are validation fixtures,
not hard-coded defaults. Expected useful detections include STM32CubeMX, MaixVision,
OpenMV IDE, representative CMake projects, and the MaixCAM combined project. Installed
OpenMV firmware/SDK content must not flood the project catalog.

## 8. Task Planning and Execution

A user starts from either a command or a goal such as "inspect this project and build
it" or "prepare a safe firmware flash." The application service:

1. loads the workspace and project facets;
2. gathers fresh environment and device evidence;
3. matches required capabilities against healthy adapters;
4. produces a deterministic plan skeleton;
5. optionally asks the configured AI provider to explain, rank, or fill bounded
   decisions using referenced evidence;
6. validates the resulting typed plan;
7. applies safety policy and requests confirmation when required;
8. executes steps with streaming progress and cancellation;
9. archives outputs and recommends the next safe action.

AI output never becomes an executable command directly. It must resolve to registered
capabilities with validated inputs. When no provider is configured or a provider is
unavailable, the deterministic plan and diagnostic pipeline remain operational.

## 9. Safety and Authority

Capabilities are classified into three authority levels.

| Level | Examples | Default behavior |
| --- | --- | --- |
| Automatic | read-only discovery, inspection, environment probes, builds in known output locations | execute after plan validation |
| Confirmed | source/config changes, dependency installation, flash, erase, reset, debug session | show exact target, command summary, changes, rollback limits, then require one-time confirmation |
| High risk | actuator motion, broad device writes, unsafe electrical assumptions, destructive batch actions | require preflight evidence, explicit target binding, elevated confirmation, and adapter-specific interlocks |

Confirmations bind the action, target, adapter, relevant artifact hashes, and expiry.
They are single-use and auditable. A task must be replanned when bound inputs change.
Missing voltage/current/target evidence blocks actions whose adapters declare those
facts mandatory. `unknown` is a valid result; the platform must not invent plausible
hardware parameters.

The first release can perform real hardware actions only when a concrete adapter,
preflight, and safety policy support them. Unsupported actions remain explicitly
blocked with a reason; simulation success is never presented as real execution.

## 10. AI Configuration

The AI layer is provider-neutral. A provider profile includes endpoint, protocol
adapter, model name, capability flags, timeout, and a reference to a locally stored
credential. Credentials use the operating-system credential store when available;
a clearly marked local fallback may be used only with restrictive file permissions.

Provider profiles can be assigned to task classes, with an optional default profile.
The router returns structured responses, usage metadata when available, and normalized
failures. Prompts receive the minimum required evidence and redact secrets and
unrelated file content. Testing uses mocked providers and the active Codex development
environment; no developer credential or fixed production model is committed.

## 11. Persistence

Persistence combines:

- SQLite for workspaces, normalized descriptors, task transitions, adapter health,
  evidence metadata, and schema migrations;
- JSON manifests for portable, human-readable project overrides where appropriate;
- content-addressed or task-addressed files for logs, reports, and build artifact
  references.

The database stores canonical paths and stable IDs but does not copy user source code.
Schema changes use explicit forward migrations. Evidence records are append-only;
retention cleanup removes referenced files only through a deliberate maintenance
operation and records what was removed.

Application services define serializable request and response types so a future local
Web API or remote node can reuse the same contracts. Network transport is not required
in the first release.

## 12. Desktop Information Architecture

The current large PyQt module will be migrated incrementally into focused views and
view models. The initial navigation is:

- **Home:** workspace health, recent projects, active tasks, and recommended actions;
- **Projects:** discovery inbox, registered projects, facets, environment, and actions;
- **Tasks:** plans, confirmation requests, live progress, history, and recovery;
- **Devices:** detected probes and transports with health and capability summaries;
- **Evidence:** searchable reports, logs, artifacts, and provenance;
- **Settings:** scan roots, exclusions, tools, AI providers, safety defaults, and
  adapter health.

The primary first-run experience is the usable workbench, not a marketing page. A
guided discovery flow selects scan roots, reviews detected tools/projects, creates a
workspace, and offers the first inspection task. Expert users can skip the guide and
use dense project and task views. The CLI exposes equivalent operations for automation.

The migration avoids a flag-day GUI rewrite. Existing panels continue to work while
new views move tool calls into application services. The final shell contains
navigation and composition only; project scanning, command execution, and persistence
live outside UI modules.

## 13. Failure Handling

All boundaries return typed results and normalized errors. Errors include category,
human summary, technical detail reference, retryability, affected resource, and safe
recovery actions. Key categories are invalid configuration, missing dependency,
unsupported project, ambiguous detection, permission denied, safety blocked, tool
failure, device disconnected, cancellation, and internal defect.

Partial discovery results remain usable when one probe fails. Task steps are resumable
only when their adapter declares the operation idempotent or provides a verified resume
strategy. A cancelled subprocess is terminated through the shared runner and recorded.
The UI always distinguishes blocked, failed, cancelled, simulated, and successfully
executed states.

## 14. Testing Strategy

Tests scale with the risk of each boundary:

- unit tests for domain state transitions, registry conflicts, path normalization,
  classification, policy decisions, redaction, and schema migration;
- contract tests applied to every adapter implementation;
- fixture tests for STM32/CubeMX, CMake, Python, MaixCAM, OpenMV, and EDA document
  layouts, including SDK and IDE false positives;
- subprocess tests with fake executables and deterministic output;
- integration tests covering discover -> register -> inspect -> build -> archive;
- safety tests proving mutating capabilities cannot bypass confirmation and that stale
  confirmations are rejected;
- GUI tests for first-run discovery, task confirmation, progress, failure recovery,
  keyboard navigation, and representative desktop sizes;
- optional hardware-in-the-loop tests, clearly separated from default CI and requiring
  explicit device configuration.

Existing CLI and fixture tests remain regression gates. Real hardware verification
reports the exact connected target and adapter; absence of lab hardware is reported as
not run, never as a pass.

## 15. Migration Sequence

The approved product direction is delivered through several implementation plans. The
first plan is limited to the foundation and usable local loop:

1. introduce domain models, registries, persistence, and application services;
2. implement staged discovery and registration using existing detectors;
3. wrap representative STM32/CMake, generic Python, MaixCAM/OpenMV, and document
   detection capabilities;
4. implement task planning, safety states, execution records, and evidence archival;
5. add the new workspace/project/task desktop flow and keep CLI compatibility;
6. validate against selected D-drive projects and installed tools;
7. document plugin contracts and add one small reference adapter.

Later plans add deeper device execution, EDA workflows, more platform adapters, remote
nodes, and Web/cloud clients. Each later capability must pass the same adapter contract
and safety model.

## 16. Acceptance Criteria

The first release is accepted when all of the following are demonstrated:

1. A fresh local workspace can scan user-selected D-drive roots and show verified tools
   and candidate projects without registering known IDE/SDK trees as user projects.
2. The user can review candidates, register a project, and see its detected facets,
   required tools, environment health, and evidence.
3. At least one STM32/CMake fixture, one MaixCAM or OpenMV fixture, and one generic
   Python/CMake fixture complete the discovery and inspection flow.
4. A supported fixture completes inspect -> build or deterministic diagnostic ->
   evidence archive through both application services and a user-facing entry point.
5. A mutating or hardware action cannot execute without the required fresh confirmation,
   while read-only and safe build actions can run without unnecessary prompts.
6. Tool identity checks reject the Java `jlink.exe` false positive as SEGGER J-Link.
7. The workbench starts on the user's workspace rather than treating the NextBoard
   repository as the default target.
8. AI profiles are optional, user-configurable, and absent from repository state;
   disabling AI does not break the core workflow.
9. Existing supported CLI behavior and tests remain operational, and new core and
   adapter contract tests pass.
10. Logs, plans, confirmations, results, and failures are traceable from a task without
    exposing configured credentials.

## 17. Compatibility and Ownership Constraints

- Existing user changes, especially within the independent `embeddedskills/` worktree,
  must be preserved.
- Existing command names remain available unless a separately approved migration
  provides deprecation and compatibility behavior.
- Runtime discovery continues to support external, root-local, and packaged
  `embeddedskills` locations.
- No network publishing, pushing, remote execution, credential modification, or paid
  action is part of implementation without separate explicit approval.
