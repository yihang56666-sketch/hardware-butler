#!/usr/bin/env bash
set -euo pipefail

# NextBoard plugin installer
# Guides the user through choosing global or project-level installation.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

GREEN='\033[92m'
YELLOW='\033[93m'
RED='\033[91m'
BOLD='\033[1m'
RESET='\033[0m'

info()  { printf "${GREEN}%s${RESET}\n" "$*"; }
warn()  { printf "${YELLOW}%s${RESET}\n" "$*"; }
error() { printf "${RED}%s${RESET}\n" "$*"; }

usage() {
  cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Options:
  --global            Global install (copy skill/agent to ~/.claude or ~/.codex)
  --project <path>    Project-level install (copy plugin files into target project)
  --platform <name>   Target platform: claude (default) or codex
  --uninstall         Remove global installation
  --uninstall-project <path>  Remove project-level installation
  --status            Show current installation status
  -h, --help          Show this help

Without options, runs in interactive mode.
EOF
}

# ── detection ───────────────────────────────────────────────────────

detect_claude_global() {
  [ -f "$HOME/.claude/skills/hardware-solution/SKILL.md" ]
}

detect_claude_agent() {
  [ -f "$HOME/.claude/agents/hardware-reviewer.md" ]
}

detect_codex_global() {
  [ -f "$HOME/.codex/skills/hardware-solution/SKILL.md" ]
}

show_status() {
  echo ""
  printf "${BOLD}NextBoard installation status:${RESET}\n"
  echo ""

  if detect_claude_global; then
    info "  Claude Code skill:  installed"
  else
    warn "  Claude Code skill:  not installed"
  fi

  if detect_claude_agent; then
    info "  Claude Code agent:  installed"
  else
    warn "  Claude Code agent:  not installed"
  fi

  if detect_codex_global; then
    info "  Codex skill:        installed"
  else
    warn "  Codex skill:        not installed"
  fi

  echo ""
  echo "  Tip: use 'claude --plugin-dir $REPO_ROOT' to load plugin for a single session."
  echo ""
}

# ── install actions ─────────────────────────────────────────────────

install_global_claude() {
  mkdir -p "$HOME/.claude/skills"
  rm -rf "$HOME/.claude/skills/hardware-solution"
  cp -r "$REPO_ROOT/skills/hardware-solution" "$HOME/.claude/skills/"
  info "Skill installed to ~/.claude/skills/hardware-solution"

  mkdir -p "$HOME/.claude/agents"
  cp "$REPO_ROOT/agents/hardware-reviewer.md" "$HOME/.claude/agents/"
  info "Reviewer document installed to ~/.claude/agents/hardware-reviewer.md"

  echo ""
  warn "Hooks are not available in global mode (requires plugin context)."
  info "Restart your Claude Code session to activate."
}

install_global_codex() {
  mkdir -p "$HOME/.codex/skills"
  rm -rf "$HOME/.codex/skills/hardware-solution"
  cp -r "$REPO_ROOT/skills/hardware-solution" "$HOME/.codex/skills/"
  info "Skill installed to ~/.codex/skills/hardware-solution"

  mkdir -p "$HOME/.codex/agents"
  cp "$REPO_ROOT/agents/hardware-reviewer.md" "$HOME/.codex/agents/"
  info "Agent installed to ~/.codex/agents/hardware-reviewer.md"

  echo ""
  warn "Codex does not support hooks. Skill and agent are available, hooks require --plugin-dir mode."
  info "Restart your Codex session to activate."
}

get_version() {
  # read version from plugin.json
  local pjson="$REPO_ROOT/.claude-plugin/plugin.json"
  if command -v python3 &>/dev/null && [ -f "$pjson" ]; then
    python3 -c "import json; print(json.load(open('$pjson'))['version'])" 2>/dev/null || echo "unknown"
  else
    echo "unknown"
  fi
}

install_project() {
  local project_path="$1"
  local platform="${2:-claude}"

  if [ ! -d "$project_path" ]; then
    error "Project path does not exist: $project_path"
    exit 1
  fi

  local version
  version="$(get_version)"

  case "$platform" in
    codex)
      info "NextBoard $version — project-level install (Codex) → $project_path"
      echo ""

      mkdir -p "$project_path/.codex/skills"
      rm -rf "$project_path/.codex/skills/hardware-solution"
      cp -r "$REPO_ROOT/skills/hardware-solution" "$project_path/.codex/skills/"
      info "Skill installed to $project_path/.codex/skills/hardware-solution"

      mkdir -p "$project_path/.codex/agents"
      cp "$REPO_ROOT/agents/hardware-reviewer.md" "$project_path/.codex/agents/"
      info "Agent installed to $project_path/.codex/agents/hardware-reviewer.md"

      echo ""
      info "Restart your Codex session in this project to activate."
      warn "Hooks not available in Codex."
      ;;
    claude)
      info "NextBoard $version — project-level plugin (Claude Code)"
      echo ""
      echo "  Claude Code 不支持从项目目录自动加载插件。"
      echo "  请使用以下方式之一在该项目中启用 NextBoard："
      echo ""
      printf "  ${BOLD}方式 1：--plugin-dir（推荐，每次启动时指定）${RESET}\n"
      echo ""
      echo "    cd $project_path"
      echo "    claude --plugin-dir $REPO_ROOT"
      echo ""
      printf "  ${BOLD}方式 2：全局安装（所有项目可用）${RESET}\n"
      echo ""
      echo "    $0 --global --platform claude"
      echo ""
      printf "  ${BOLD}方式 3：Marketplace 安装（需要 GitHub 访问）${RESET}\n"
      echo ""
      echo "    claude plugin marketplace add LeoKemp223/NextBoard"
      echo "    claude plugin install nextboard-hardware-solution"
      echo ""
      ;;
    *)
      error "Unknown platform: $platform"
      exit 1
      ;;
  esac
}

uninstall_project() {
  if [ -z "$1" ] || [ ! -d "$1" ]; then
    error "An existing project directory is required."
    return 1
  fi
  local project_path
  project_path="$(cd -- "$1" && pwd -P)"
  if [ "$project_path" = "/" ]; then
    error "Refusing to uninstall from a filesystem root."
    return 1
  fi
  local codex_dir="$project_path/.codex"
  local skill_dir="$codex_dir/skills/hardware-solution"
  local reviewer="$codex_dir/agents/hardware-reviewer.md"
  local target
  for target in "$codex_dir" "$codex_dir/skills" "$codex_dir/agents" "$skill_dir" "$reviewer"; do
    if [ -L "$target" ]; then
      error "Refusing to uninstall through a symbolic link: $target"
      return 1
    fi
    if [ -d "$target" ]; then
      local resolved
      resolved="$(cd -- "$target" && pwd -P)"
      if [ "$resolved" != "$target" ]; then
        error "Refusing to uninstall through a redirected directory: $target"
        return 1
      fi
    fi
  done
  local found=false
  if [ -d "$skill_dir" ]; then
    rm -rf -- "$skill_dir"
    found=true
  fi
  if [ -f "$reviewer" ]; then
    rm -f -- "$reviewer"
    found=true
  fi

  if [ "$found" = "false" ]; then
    warn "No project-level installation found in $project_path"
    return
  fi

  info "Removed only the named NextBoard Codex skill and reviewer document."
  warn "Legacy .nextboard, .claude-plugin, skills, agents, hooks and .gitignore are preserved; review ownership manually."
  info "If using --plugin-dir, no further cleanup needed."
}

# ── uninstall ───────────────────────────────────────────────────────

uninstall_global() {
  local removed=false

  if detect_claude_global; then
    rm -rf "$HOME/.claude/skills/hardware-solution"
    info "Removed Claude Code skill"
    removed=true
  fi

  if detect_claude_agent; then
    rm -f "$HOME/.claude/agents/hardware-reviewer.md"
    info "Removed Claude Code agent"
    removed=true
  fi

  if detect_codex_global; then
    rm -rf "$HOME/.codex/skills/hardware-solution"
    rm -f "$HOME/.codex/agents/hardware-reviewer.md"
    info "Removed Codex skill and agent"
    removed=true
  fi

  if [ "$removed" = "false" ]; then
    warn "No global installation found."
  else
    info "Uninstall complete. Restart your session."
  fi
}

# ── interactive mode ────────────────────────────────────────────────

interactive() {
  echo ""
  printf "${BOLD}NextBoard Hardware Solution — Installer${RESET}\n"
  echo ""

  show_status

  printf "${BOLD}Choose installation method:${RESET}\n"
  echo ""
  echo "  1) Global install — copy skill/agent to home directory, all projects can use"
  echo "     Components: skill + reviewer document (Claude Code and Codex)"
  echo "     Limitation: hooks not available"
  echo ""
  echo "  2) Project-level usage — show how to load plugin in a specific project"
  echo "     Uses --plugin-dir or marketplace install"
  echo ""
  echo "  3) Show current status"
  echo "  4) Uninstall global installation"
  echo "  5) Uninstall project-level installation"
  echo "  q) Quit"
  echo ""

  read -rp "Select [1-5/q]: " choice

  case "$choice" in
    1)
      echo ""
      printf "${BOLD}Target platform:${RESET}\n"
      echo "  1) Claude Code (skill + agent)"
      echo "  2) Codex (skill + reviewer document)"
      echo ""
      read -rp "Select [1-2]: " platform

      case "$platform" in
        1)
          install_global_claude
          ;;
        2)
          install_global_codex
          ;;
        *)
          error "Invalid choice"
          exit 1
          ;;
      esac
      ;;
    2)
      echo ""
      read -rp "Target project path: " project_path
      if [ -z "$project_path" ]; then
        error "Project path is required."
        exit 1
      fi
      # expand ~ if present
      project_path="${project_path/#\~/$HOME}"
      install_project "$project_path"
      ;;
    3)
      show_status
      ;;
    4)
      uninstall_global
      ;;
    5)
      echo ""
      read -rp "Target project path: " project_path
      if [ -z "$project_path" ]; then
        error "Project path is required."
        exit 1
      fi
      project_path="${project_path/#\~/$HOME}"
      uninstall_project "$project_path"
      ;;
    q|Q)
      exit 0
      ;;
    *)
      error "Invalid choice"
      exit 1
      ;;
  esac
}

# ── CLI entry ───────────────────────────────────────────────────────

if [ $# -eq 0 ]; then
  interactive
  exit 0
fi

MODE=""
PLATFORM="claude"
PROJECT_PATH=""
UNINSTALL_PROJECT_PATH=""

while [ $# -gt 0 ]; do
  case "$1" in
    --global)     MODE="global"; shift ;;
    --project)    MODE="project"; PROJECT_PATH="$2"; shift 2 ;;
    --platform)   PLATFORM="$2"; shift 2 ;;
    --uninstall)  MODE="uninstall"; shift ;;
    --uninstall-project) MODE="uninstall-project"; UNINSTALL_PROJECT_PATH="$2"; shift 2 ;;
    --status)     show_status; exit 0 ;;
    -h|--help)    usage; exit 0 ;;
    *)            error "Unknown option: $1"; usage; exit 1 ;;
  esac
done

case "$MODE" in
  global)
    case "$PLATFORM" in
      claude) install_global_claude true ;;
      codex)  install_global_codex ;;
      *)      error "Unknown platform: $PLATFORM"; exit 1 ;;
    esac
    ;;
  project)
    install_project "$PROJECT_PATH" "$PLATFORM"
    ;;
  uninstall)
    uninstall_global
    ;;
  uninstall-project)
    uninstall_project "$UNINSTALL_PROJECT_PATH"
    ;;
  *)
    error "No mode specified. Use --global, --project <path>, or --uninstall."
    usage
    exit 1
    ;;
esac
