# Hardware Butler Configuration

本项目现在支持配置文件和环境变量配置。

## 配置文件位置（按优先级）

1. `HW_BUTLER_CONFIG` 环境变量指定的文件
2. 当前目录的 `.hardware-butler.json`
3. 用户目录的 `~/.hardware-butler/config.json`

## 配置文件格式

```json
{
  "workspace": {
    "root": ".",
    "allowed_roots": ["."],
    "chip_cache_dir": "~/.hardware-butler/chip-cache"
  },
  "tools": {
    "jlink": "C:/Program Files/SEGGER/JLink/JLink.exe",
    "openocd": "C:/openocd/bin/openocd.exe",
    "probe_rs": null,
    "keil_uvision": "C:/Keil/UV4/UV4.exe"
  },
  "logging": {
    "level": "INFO",
    "file": "~/.hardware-butler/butler.log"
  }
}
```

## 环境变量

- `HW_BUTLER_ROOT`: 工作区根目录（优先于配置文件中的 workspace.root）
- `HW_BUTLER_CONFIG`: 配置文件路径
- `HW_BUTLER_LOG_LEVEL`: 日志级别（DEBUG/INFO/WARNING/ERROR）

## 快速开始

### 创建项目级配置

```bash
cp .hardware-butler.json.template .hardware-butler.json
# 编辑 .hardware-butler.json
```

### 创建用户级配置

```bash
mkdir -p ~/.hardware-butler
cp .hardware-butler.json.template ~/.hardware-butler/config.json
# 编辑 ~/.hardware-butler/config.json
```

### 使用环境变量

```bash
# Windows PowerShell
$env:HW_BUTLER_ROOT = "<repo-root>"
$env:HW_BUTLER_LOG_LEVEL = "DEBUG"

# Linux/macOS
export HW_BUTLER_ROOT="/home/user/hardware-agent"
export HW_BUTLER_LOG_LEVEL="DEBUG"
```
