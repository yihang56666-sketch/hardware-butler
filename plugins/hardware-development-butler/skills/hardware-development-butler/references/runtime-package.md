# Runtime Package

The plugin vendors a runnable workspace under:

```text
plugins/hardware-development-butler/scripts/
  tools/
  embeddedskills/
  nextboard/
  agents/
  .codex/
  tests/
  docs/
```

The skill wrapper is:

```text
plugins/hardware-development-butler/skills/hardware-development-butler/scripts/run_hardware_butler.py
```

Validation commands from the repository root:

```powershell
python plugins\hardware-development-butler\scripts\tools\hardware_butler.py capabilities --json
python plugins\hardware-development-butler\scripts\tests\validate_hardware_butler.py
python <user-home>/.codex/skills/.system/skill-creator/scripts/quick_validate.py plugins/hardware-development-butler/skills/hardware-development-butler
python <user-home>/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py plugins/hardware-development-butler
```

If the official plugin validator reports missing `yaml`, install PyYAML in the active Python environment or use the local package validator as a structural fallback.
