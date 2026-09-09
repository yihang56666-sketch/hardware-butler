# Install

Hardware Butler is best used as a source workspace. That keeps the CLI, GUI,
docs, tests, Codex plugin runtime, and embedded backend mirror together.

## Recommended: Source Workspace

```powershell
git clone https://github.com/yihang56666-sketch/hardware-butler.git
cd hardware-butler
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
python tools\hardware_butler.py guide --root <project-root>
```

Then check the environment:

```powershell
python tools\hardware_butler.py doctor --root <project-root> --json
```

`doctor` should report an `embeddedskills.runtime` check. It tells you which
backend runtime path is active.

## Editable CLI Install

For local command aliases:

```powershell
pip install -e .
hardware-butler guide --root <project-root>
butler guide --root <project-root>
```

The editable install still uses this source checkout, so the packaged plugin
runtime mirror remains discoverable.

## GUI Install

Install the desktop workbench extras only when you want the PyQt UI:

```powershell
pip install -e ".[ui]"
python gui\hardware_agent_ui.py
```

## Contributor Install

For full repository verification, install the development requirements. This
keeps the quick start small while still giving maintainers the lint, typecheck,
and test dependencies used by CI.

```powershell
pip install -r requirements-dev.txt
```

For every optional integration in one environment:

```powershell
pip install -r requirements-all.txt
```

Most users should prefer targeted extras instead:

```powershell
pip install -e ".[ui]"
pip install -e ".[hardware]"
pip install -e ".[ai]"
```

## embeddedskills Runtime Choices

The backend runtime is resolved in this order:

1. `HW_BUTLER_EMBEDDEDSKILLS_ROOT`, for an external checkout.
2. Root `embeddedskills/`, for local development or a future submodule.
3. `plugins/hardware-development-butler/scripts/embeddedskills/`, the packaged
   plugin runtime mirror.

Use an external checkout when you want to work directly on the backend repo:

```powershell
$env:HW_BUTLER_EMBEDDEDSKILLS_ROOT="<path-to-embeddedskills>"
python tools\hardware_butler.py doctor --root <project-root> --json
```

When regenerating the plugin runtime, `python tools\package_hardware_butler_plugin.py`
uses the same source preference for `embeddedskills`: environment override first,
root checkout second, and the existing packaged mirror as a clean-clone fallback.
That keeps a GitHub checkout usable even when the root `embeddedskills/` directory
is intentionally not tracked.

## Verification Install

Before publishing a branch, use the release verifier:

```powershell
python tools\release_verify.py
```

For quick iteration on the no-hardware demo and plugin mirror:

```powershell
python tools\release_verify.py --profile quick
```

The main individual checks are:

```powershell
ruff check tools/ tests/
mypy tools/ --config-file mypy.ini
pytest tests/ -v --basetemp=.tmp-pytest-current
python tests\validate_hardware_butler.py
python tools\package_hardware_butler_plugin.py
python plugins\hardware-development-butler\scripts\validate_package.py
```

## Package-Only Caveat

The GitHub project is currently source-workspace first. A wheel install provides
the Python CLI packages, but hardware backend scripts should be supplied by a
source checkout or `HW_BUTLER_EMBEDDEDSKILLS_ROOT`. This avoids accidentally
shipping an ignored, dirty root-level `embeddedskills/` checkout inside a wheel.
