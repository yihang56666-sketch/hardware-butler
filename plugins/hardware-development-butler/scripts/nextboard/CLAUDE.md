# NextBoard — 项目指令

本文件供 AI 会话使用，面向人类的说明见 README.md。

## 安装引导

当用户提到安装、部署、使用本插件时，先运行 `scripts/install.sh --status` 检查当前安装状态，然后向用户说明三种安装方式的区别，引导用户选择：

- 全局安装：skill（和 agent）复制到 `~/.claude/skills/`（或 `~/.codex/skills/`），所有项目可用，但 hooks 不生效。
- --plugin-dir：`claude --plugin-dir /path/to/NextBoard`，skill + agent + hooks 全部可用，每次启动需指定。
- Marketplace：`claude plugin marketplace add LeoKemp223/NextBoard && claude plugin install nextboard-hardware-solution`，正式分发方式。

用户确认后，运行对应的命令完成安装：

```bash
# 全局安装（Claude Code，含 agent）
scripts/install.sh --global --platform claude

# 全局安装（Codex）
scripts/install.sh --global --platform codex

# --plugin-dir（单次会话，完整功能）
claude --plugin-dir /path/to/NextBoard

# 卸载全局安装
scripts/install.sh --uninstall

# 查看安装状态
scripts/install.sh --status
```

## 核心规则

- 调用 `$hardware-solution` 进入硬件方案设计流程。
- 器件参数必须来自数据手册或分销商页面，禁止凭记忆回答。
- 每个关键选择必须说明取舍，不能只列器件。
- 风险清单不能为空，高风险项必须有验证动作。
- 正式方案须通过 `skills/hardware-solution/references/verification-gates.md` 的 Gate 1–5；用户请求模块原理图时另过可选 Gate 6，否则记录不适用。静态校验不等于方案门控通过，缺证据只交付标注待核的草案。

## 关键文件

- `skills/hardware-solution/SKILL.md` — 技能入口和工作流定义
- `skills/hardware-solution/references/` — 工作流、输出模板、评审清单、供应链风险、验证门控
- `agents/hardware-reviewer.md` — 独立评审 agent（5 维度打分）

## 开发验证

修改 skill 或 reference 后运行：

```bash
python3 tests/validate.py
```

## 贡献规范

- 修改 skill 或 reference 文档需提供修改前后的对比说明。
- 新增参考文档需在 SKILL.md 流程部分添加引用入口。
- 不接受没有实际硬件设计场景验证的修改。
- 提交前确保 `python3 tests/validate.py` 通过。
