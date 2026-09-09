# NextBoard — Hardware Solution Agent

面向硬件产品的PCB方案设计 AI Agent。输入产品需求，输出可评审、可落地的PCB原理图的方案。

## 使用说明

按需求输入:
- 设计一个无人机方案
- 设计一个FOC控制器
- 设计一个记单词的墨水屏卡片

Agent会自动帮你进行需求确认，实时分析国内外各类芯片技术方案，进行器件选型，下载datasheet，输出BOM表，计算价格，输出模块原理图，最终整合成可落地技术方案。

<img width="1049" height="384" alt="PixPin_2026-05-05_09-43-02" src="https://github.com/user-attachments/assets/daf0ba27-03b1-4c48-a646-03a447d6fd28" />

## 功能概览

- 分阶段设计流程：需求冻结 → 架构候选 → 系统分解/选型 → 资料核验 → 约束/验证计划 → 决策/独立评审 → 可选原理图 → 报告
- 三类架构候选对比：国产优先、海外主流、混合折中
- Gate 1–5 为必需验证门，用户请求模块原理图时增加可选 Gate 6；不适用时记录原因
- 独立评审 agent，从完整性、风险、可实施性、成本、验证覆盖 5 个维度打分
- 供应链风险评估与国产替代参考

<img width="3659" height="1458" alt="PixPin_2026-05-05_09-18-28" src="https://github.com/user-attachments/assets/305c73ed-9d26-485b-9a1c-83720c39a806" />

- 产出markdown、datasheet、封装库、pdf方案

<img width="2379" height="1792" alt="PixPin_2026-05-04_21-51-20" src="https://github.com/user-attachments/assets/c2a7e85a-0fca-44e1-9459-f0d3a0c30525" />


## 快速开始

在 Claude Code、Codex 或 Cursor 会话中调用：

```
$hardware-solution
```

输入产品需求即可进入设计流程。

源码的主入口是 [skills/hardware-solution/SKILL.md](skills/hardware-solution/SKILL.md)。`hermes_launcher_gui.py` 是独立的历史 Hermes/日报启动器，含个人本机路径和配置写入逻辑，不是 Hardware Butler GUI，也不是本技能的安装或演示入口。硬件管家源码 GUI 位于父工作区的 `gui/`。

## 安装

安装后需重启 AI IDE 会话，让客户端重新加载 skill 列表。

### AI 安装指引

> 本节供 AI 助手（Claude Code、Codex、Cursor 等）阅读。当用户要求安装本插件时，按以下流程引导。

**第一步：确认当前环境**

运行 `./scripts/install.sh --status` 查看是否已安装。

**第二步：引导用户选择安装方式**

向用户说明三种方式的区别，让用户选择：

| 方式 | 适用场景 | 可用组件 | 限制 |
|------|---------|---------|------|
| 全局安装 | 希望所有项目都能用 | skill + agent | hooks 不生效 |
| --plugin-dir | 开发调试或临时使用 | skill + agent + hooks | 每次启动需指定路径 |
| Marketplace | 正式分发 | skill + agent + hooks | 需要 GitHub 访问 |

**第三步：执行安装**

用户选择后，运行对应命令：

```bash
# 全局安装（Claude Code，含 agent）
./scripts/install.sh --global --platform claude

# 全局安装（Codex，skill + agent）
./scripts/install.sh --global --platform codex

# --plugin-dir（单次会话加载，skill + agent + hooks 全部可用）
claude --plugin-dir /path/to/NextBoard

# Marketplace 安装
claude plugin marketplace add LeoKemp223/NextBoard
claude plugin install nextboard-hardware-solution
```

如果 `scripts/install.sh` 不可用（例如用户未克隆本仓库），按下方"手动安装"章节的命令执行。

**第四步：验证**

安装完成后提醒用户重启会话，然后调用 `$hardware-solution` 验证是否生效。

### 交互式安装

```bash
git clone <NextBoard-repo-url>
cd NextBoard
./scripts/install.sh
```

脚本会显示当前安装状态，引导你选择安装方式。

### 手动安装

#### 方式一：全局安装

从 NextBoard 仓库复制文件到全局目录，所有项目都能使用 `$hardware-solution`。

```bash
git clone <NextBoard-repo-url>
cd NextBoard
```

Claude Code：

```bash
# 完整源码安装（skill + reviewer 文档）
mkdir -p "$HOME/.claude/skills"
rm -rf "$HOME/.claude/skills/hardware-solution"
cp -r skills/hardware-solution "$HOME/.claude/skills/"

# reviewer 是技能相对链接所需内容，不应遗漏
mkdir -p "$HOME/.claude/agents"
cp agents/hardware-reviewer.md "$HOME/.claude/agents/"
```

Codex：

```bash
mkdir -p "$HOME/.codex/skills"
rm -rf "$HOME/.codex/skills/hardware-solution"
cp -r skills/hardware-solution "$HOME/.codex/skills/"

mkdir -p "$HOME/.codex/agents"
cp agents/hardware-reviewer.md "$HOME/.codex/agents/"
```

> 全局安装的局限：hooks 无法生效（缺少插件上下文）。

reviewer Markdown 的复制不保证目标客户端已注册可调度 agent。客户端支持独立 agent 时使用它；否则按文档五维自检并明确标为非独立，待人工复核，不能把自检算作 Gate 5 PASS。

#### 方式二：--plugin-dir（推荐开发调试）

直接从 NextBoard 仓库加载插件，skill + agent + hooks 全部可用，无需复制文件。

```bash
claude --plugin-dir /path/to/NextBoard
```

每次启动 Claude Code 时需要指定 `--plugin-dir` 参数。

#### 方式三：Marketplace 安装

通过 Claude Code 插件市场安装，适合正式分发。

```bash
# 添加 NextBoard marketplace
claude plugin marketplace add LeoKemp223/NextBoard

# 安装插件
claude plugin install nextboard-hardware-solution
```

### 更新

```bash
# 全局安装：pull 后重新执行安装
cd NextBoard && git pull
./scripts/install.sh --global --platform claude

# --plugin-dir：pull 即可，下次启动自动加载最新版
cd NextBoard && git pull
```

### 卸载

```bash
# 全局卸载
./scripts/install.sh --uninstall

# 项目级卸载
./scripts/install.sh --uninstall-project /path/to/your-project

# 或手动卸载全局安装
rm -rf "$HOME/.claude/skills/hardware-solution"
rm -f "$HOME/.claude/agents/hardware-reviewer.md"
rm -rf "$HOME/.codex/skills/hardware-solution"
rm -f "$HOME/.codex/agents/hardware-reviewer.md"
```

项目级卸载仅移除指定项目 `.codex/skills/hardware-solution` 和 `.codex/agents/hardware-reviewer.md`，拒绝通过符号链接/重定向目录删除。不会删除通用 `skills/`、`agents/`、`hooks/`、`.claude-plugin/`、旧 `.nextboard/` 或改写 `.gitignore`；历史文件需人工确认归属后处理。

## 项目结构

```
NextBoard/
├── skills/hardware-solution/
│   ├── SKILL.md                        # 技能入口，定义工作流和输出原则
│   └── references/
│       ├── design-workflow.md           # 分阶段设计与交付流程
│       ├── output-template.md           # 方案输出标准结构
│       ├── verification-gates.md        # 5 道必需门控 + 可选 Gate 6
│       ├── download-sources.md          # 项目来源登记的只读模板
│       ├── review-checklists.md         # 原理图/PCB/BOM/方案评审清单
│       ├── sourcing-and-risk.md         # 供应链风险评估指南
│       └── domestic-sources.md          # 国产芯片与元器件参考
├── agents/
│   └── hardware-reviewer.md             # 独立评审 agent（增强安装）
├── hooks/
│   ├── hooks.json                       # Claude Code 会话启动 hook 配置
│   └── session-start                    # 会话启动提醒脚本
├── scripts/
│   └── install.sh                       # 交互式安装/卸载脚本
├── tests/
│   └── validate.py                      # 结构与内容一致性验证脚本
├── .claude-plugin/                      # Claude Code 插件配置
├── .codex-plugin/                       # Codex 插件配置
├── .cursor-plugin/                      # Cursor 插件配置
├── CLAUDE.md                            # Claude Code / 通用 AI 会话项目指令
└── AGENTS.md                            # Cursor Agent Mode / 通用 Agent 指令
```

## 验证

修改 skill 或 reference 文档后，运行验证脚本检查结构完整性和内容一致性：

```bash
# 验证仓库源文件
python3 tests/validate.py

# 验证已安装的副本
python3 tests/validate.py --installed

# 验证 Codex 全局安装，或指定隔离副本
python3 tests/validate.py --installed --platform codex
python3 tests/validate.py /path/to/.codex/skills/hardware-solution --installed
```

验证覆盖源码静态结构和内容检查：

| 层 | 内容 |
|---|---|
| 结构完整性 | 文件存在、hook 可执行、hook 输出合法 JSON |
| 内容一致性 | SKILL.md 与 reference 中本地链接的目标文件存在、Gate 非空、输出模板包含决策/门控证据、reviewer 覆盖 5 维度 |
| 反模式检测 | reference 文档无模糊措辞、无残留占位符 |
| 平台配置 | 清单存在、配置版本一致、版本更新目标存在 |

安装校验还检查 PDF 脚本、`agents/openai.yaml` 和 reviewer 文档。它不验证远程 URL、标题锚点、价格/库存、datasheet 参数、EDA 文件、客户端实际加载、PDF 渲染或实机结果；这些仍需逐门记录实际证据。`docs/hardware/stm32-quadrotor/` 是历史待核草案，不是通过门控的设计示例。

## Hooks 说明

`hooks/hooks.json` 与 `hooks/hooks-cursor.json` 提供对应客户端的会话 hook 配置。全局复制安装不启用 hooks。脚本输出合法 JSON 不代表目标客户端已经加载；插件加载方式须在相应客户端单独验证。

手动验证 hook 输出：

```bash
CLAUDE_PLUGIN_ROOT="$PWD" hooks/session-start | python3 -m json.tool
```

## 输出质量要求

- 器件参数必须来自数据手册或分销商页面，禁止凭记忆
- 每个关键选择必须说明取舍，不能只列器件
- 风险清单不能为空，高风险项必须有验证动作
- 正式方案必须通过 Gate 1–5；用户请求原理图时增加可选 Gate 6，未通过只能标注待核草案

## 贡献规范

- 修改 skill 或 reference 文档需提供修改前后的对比说明
- 新增参考文档需在 SKILL.md 流程部分添加引用入口
- 不接受没有实际硬件设计场景验证的修改
- 提交前运行 `python3 tests/validate.py` 确保验证通过

## 平台支持

| 平台 | 配置文件 | 全局安装 | 项目级插件 |
|------|---------|---------|-----------|
| Claude Code | `.claude-plugin/plugin.json` | skill + agent | skill + agent + hooks |
| Codex | `.codex-plugin/plugin.json` | skill + reviewer 文档 | 清单/客户端加载兼容性需另行验证 |
| Cursor | `.cursor-plugin/plugin.json` | skill（手动 cp） | skill + agent + hooks |

## License

MIT


感谢 LinuxDo 社区的支持！
[![LinuxDo](https://img.shields.io/badge/LinuxDo-社区支持-blue)](https://linux.do/)
