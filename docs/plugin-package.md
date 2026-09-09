# Hardware Development Butler Plugin Package

插件包位置：

```text
plugins/hardware-development-butler/
```

包内包含：

- `.codex-plugin/plugin.json`: Codex 插件 manifest。
- `skills/hardware-development-butler/SKILL.md`: 触发说明和工作流。
- `skills/hardware-development-butler/agents/openai.yaml`: skill UI 元数据。
- `skills/hardware-development-butler/scripts/run_hardware_butler.py`: 从 skill 调用包内 CLI 的 wrapper。
- `skills/chip-bringup/SKILL.md`: 芯片资料检索、手册总结、CubeMX/引脚配置、FreeRTOS 实现和硬件安全门控。
- `scripts/tools/`: 硬件管家 CLI 运行时。
- `scripts/embeddedskills/`: Keil/GCC/EIDE、J-Link/OpenOCD/probe-rs、串口、CAN、网络和 workflow skill 工具。
- `scripts/nextboard/`: 硬件设计/评审知识层。
- `scripts/tests/`: 可重复验证 fixture。

直接使用：

```powershell
python plugins\hardware-development-butler\skills\hardware-development-butler\scripts\run_hardware_butler.py capabilities --json
python plugins\hardware-development-butler\skills\hardware-development-butler\scripts\run_hardware_butler.py doctor --root <project-root> --json
python plugins\hardware-development-butler\skills\hardware-development-butler\scripts\run_hardware_butler.py onboard --root <project-root> --out-dir docs\inspections\<project-name> --json
```

校验：

```powershell
python plugins\hardware-development-butler\scripts\validate_package.py
python plugins\hardware-development-butler\scripts\tests\validate_hardware_butler.py
python <user-home>/.codex/skills/.system/skill-creator/scripts/quick_validate.py plugins/hardware-development-butler/skills/hardware-development-butler
python <user-home>/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py plugins/hardware-development-butler
```

官方 `quick_validate.py` 和 `validate_plugin.py` 依赖 PyYAML；如果当前 Python 缺少 `yaml`，先给验证环境安装 `PyYAML`，或只跑包内的 `validate_package.py` 做结构检查。

重新同步运行时：

```powershell
python tools\package_hardware_butler_plugin.py
```

安全边界：

- 默认只做项目发现、文档生成、配置提案和日志诊断。
- `run-plan --phase build-discovery` 只执行硬 allowlist 内的安全发现命令。
- build、flash、erase、debug 控制、CAN 发送、网络扫描都需要后续单独显式确认。
- wrapper 会把 `HARDWARE_BUTLER_WORKSPACE_ROOT` 设置为当前调用目录，包内 runtime 只允许向当前 workspace 写报告。
