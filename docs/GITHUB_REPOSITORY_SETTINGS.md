# GitHub Repository Settings

Suggested settings for the public repository page.

## About

Description:

```text
A safety-first embedded hardware copilot that turns board evidence, CubeMX projects, firmware plans, and bench bring-up into clear, gated next steps.
```

Homepage:

```text
https://github.com/yihang56666-sketch/hardware-butler#readme
```

Topics:

```text
embedded, hardware, stm32, cubemx, firmware, freertos, jlink, openocd, probe-rs, serial, can, safety, codex-plugin
```

Optional GitHub CLI commands:

```powershell
gh repo edit yihang56666-sketch/hardware-butler `
  --description "A safety-first embedded hardware copilot that turns board evidence, CubeMX projects, firmware plans, and bench bring-up into clear, gated next steps." `
  --homepage "https://github.com/yihang56666-sketch/hardware-butler#readme"

gh repo edit yihang56666-sketch/hardware-butler `
  --add-topic embedded `
  --add-topic hardware `
  --add-topic stm32 `
  --add-topic cubemx `
  --add-topic firmware `
  --add-topic freertos `
  --add-topic jlink `
  --add-topic openocd `
  --add-topic probe-rs `
  --add-topic serial `
  --add-topic can `
  --add-topic safety `
  --add-topic codex-plugin
```

## Features

Recommended:

- Enable Issues.
- Enable Discussions only if you want public Q&A.
- Enable Dependabot alerts and security updates.
- Keep Actions enabled for pull requests and pushes to `main`.

## Branch Protection

For `main`, require:

- Pull request before merge.
- Status checks from the `CI` workflow.
- Conversation resolution before merge.

If the repository starts private and becomes public later, re-run the clean
candidate tree smoke test after the visibility change.
