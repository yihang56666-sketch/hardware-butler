#!/usr/bin/env python3
"""NextBoard skill structure and content consistency validator.

Works directly on the repo source tree — no installation required.
Can also point at an installed copy to verify installation completeness.

Usage:
    python3 tests/validate.py                     # validate repo root
    python3 tests/validate.py /path/to/NextBoard  # validate a specific path
    python3 tests/validate.py --installed          # validate ~/.claude/skills/hardware-solution
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

# ── colour helpers ──────────────────────────────────────────────────
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"

pass_count = 0
fail_count = 0
warn_count = 0


def ok(msg):
    global pass_count
    pass_count += 1
    print(f"  {GREEN}PASS{RESET}  {msg}")


def fail(msg):
    global fail_count
    fail_count += 1
    print(f"  {RED}FAIL{RESET}  {msg}")


def warn(msg):
    global warn_count
    warn_count += 1
    print(f"  {YELLOW}WARN{RESET}  {msg}")


def _valid_bash(path: str | None) -> bool:
    """Return True for a real bash executable, excluding Windows launcher stubs."""
    if not path:
        return False
    return Path(path).is_file() and "WindowsApps" not in path


def _find_windows_bash() -> str | None:
    """Find Git Bash on Windows even when PATH resolves bash to the WSL launcher."""
    candidates: list[Path] = []
    for name in ("bash", "bash.exe"):
        found = shutil.which(name)
        if found:
            candidates.append(Path(found))

    git = shutil.which("git") or shutil.which("git.exe")
    if git:
        git_path = Path(git)
        git_root = git_path.parent.parent if git_path.parent.name.lower() == "cmd" else git_path.parent
        candidates.extend([
            git_root / "bin" / "bash.exe",
            git_root / "usr" / "bin" / "bash.exe",
        ])

    for env_name in ("ProgramFiles", "ProgramFiles(x86)"):
        base = os.environ.get(env_name)
        if base:
            candidates.extend([
                Path(base) / "Git" / "bin" / "bash.exe",
                Path(base) / "Git" / "usr" / "bin" / "bash.exe",
            ])

    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate).lower()
        if key in seen:
            continue
        seen.add(key)
        path = str(candidate)
        if _valid_bash(path):
            return path
    return None


# ── Layer 1: structure completeness ─────────────────────────────────
REQUIRED_REFS = [
    "design-workflow.md",
    "domestic-sources.md",
    "download-sources.md",
    "output-template.md",
    "review-checklists.md",
    "sourcing-and-risk.md",
    "verification-gates.md",
]

GATE_HEADERS = [
    "Gate 1",
    "Gate 2",
    "Gate 3",
    "Gate 4",
    "Gate 5",
    "Gate 6",
]

# output-template.md required sections (mapped from Gate 4 checks)
OUTPUT_TEMPLATE_SECTIONS = [
    "系统框图",       # or "推荐系统框图"
    "接口",           # "接口与信号规划"
    "电源树",         # "电源树与功耗预算"
    "PCB",            # "PCB 与结构约束"
    "验证计划",
    "风险清单",
    "原理图",         # "模块原理图"
    "已确定",
    "待确认",
    "高风险",
    "门控记录",
    "证据定位",
]

REVIEWER_DIMENSIONS = [
    "Completeness",
    "Risk Identification",
    "Implementability",
    "Cost Reasonableness",
    "Validation Coverage",
]

# anti-pattern vague phrases from SKILL.md
VAGUE_PHRASES = [
    r"选择合适的",
    r"使用低功耗方案",
    r"选用主流",
    r"采用常见",
]

PLACEHOLDER_PATTERNS = [
    r"待补充",
    r"\bTBD\b",
    r"\bxxx\b",
    r"\bTODO\b",
]

# ── platform config files that must carry a consistent version ─────
PLATFORM_CONFIG_FILES = [
    ".claude-plugin/plugin.json",
    ".codex-plugin/plugin.json",
    ".cursor-plugin/plugin.json",
]

PLATFORM_ENTRY_FILES = [
    "CLAUDE.md",
    "AGENTS.md",
]

REPO_META_FILES = [
    ".version-bump.json",
    ".github/PULL_REQUEST_TEMPLATE.md",
]


def check_structure(root: Path, installed: bool):
    """Layer 1: all expected files exist."""
    print("\n── Layer 1: Structure completeness ──")

    skill_dir = root / "skills" / "hardware-solution" if not installed else root
    skill_md = skill_dir / "SKILL.md"
    refs_dir = skill_dir / "references"

    if skill_md.is_file():
        ok("SKILL.md exists")
    else:
        fail(f"SKILL.md missing at {skill_md}")

    for ref in REQUIRED_REFS:
        p = refs_dir / ref
        if p.is_file():
            ok(f"references/{ref} exists")
        else:
            fail(f"references/{ref} missing")

    for relative in ("scripts/md_to_pdf.py", "agents/openai.yaml"):
        if (skill_dir / relative).is_file():
            ok(f"{relative} exists")
        else:
            fail(f"{relative} missing")

    if not installed:
        agent = root / "agents" / "hardware-reviewer.md"
        if agent.is_file():
            ok("agents/hardware-reviewer.md exists")
        else:
            fail("agents/hardware-reviewer.md missing")

        hook_script = root / "hooks" / "session-start"
        if hook_script.is_file():
            ok("hooks/session-start exists")
            if os.access(hook_script, os.X_OK):
                ok("hooks/session-start is executable")
            else:
                fail("hooks/session-start is not executable")
        else:
            fail("hooks/session-start missing")

    return skill_dir


# ── Layer 1b: hook JSON output ──────────────────────────────────────
def check_hook_output(root: Path):
    """Layer 1b: hook produces valid JSON."""
    print("\n── Layer 1b: Hook output ──")
    hook = root / "hooks" / "session-start"
    if not hook.is_file():
        warn("hooks/session-start not found, skipping hook test")
        return
    env = {**os.environ, "CLAUDE_PLUGIN_ROOT": str(root)}
    cmd = [str(hook)]
    if os.name == "nt":
        bash = _find_windows_bash()
        if bash:
            cmd = [bash, str(hook)]
        else:
            warn("bash not available on Windows, skipping hook test")
            return
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=5, env=env, encoding="utf-8", errors="replace"
        )
        if result.returncode != 0:
            fail(f"hook exited with code {result.returncode}: {result.stderr.strip()}")
            return
        data = json.loads(result.stdout)
        ok("hook output is valid JSON")
        # check that some context string exists
        ctx = data.get("additionalContext") or data.get("hookSpecificOutput", {}).get("additionalContext") or ""
        if "hardware-solution" in ctx:
            ok("hook mentions hardware-solution skill")
        else:
            fail("hook output missing hardware-solution reference")
    except json.JSONDecodeError:
        fail(f"hook output is not valid JSON: {result.stdout[:200]}")
    except Exception as e:
        fail(f"hook execution error: {e}")


# ── Layer 2: content consistency ────────────────────────────────────

def check_cross_references(skill_dir: Path):
    """Check local link targets in the skill and its first-party references."""
    print("\n── Layer 2a: Cross-references ──")
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        fail("cannot check cross-references: SKILL.md missing")
        return
    documents = [skill_md, *sorted((skill_dir / "references").glob("*.md"))]
    for document in documents:
        text = document.read_text(encoding="utf-8")
        links = re.findall(r'\[.*?\]\((.*?)\)', text)
        for link in links:
            parsed = urlsplit(link)
            if parsed.scheme or parsed.netloc or not parsed.path:
                continue
            target = (document.parent / unquote(parsed.path)).resolve()
            if target.is_file():
                ok(f"{document.name} link resolves: {link}")
            else:
                fail(f"broken link in {document.name}: {link}")


def check_gates_nonempty(skill_dir: Path):
    """Layer 2b: every Gate in verification-gates.md has checklist items."""
    print("\n── Layer 2b: Verification gates ──")
    vg = skill_dir / "references" / "verification-gates.md"
    if not vg.is_file():
        fail("verification-gates.md missing")
        return
    text = vg.read_text(encoding="utf-8")
    for gate in GATE_HEADERS:
        pattern = rf"##\s+{gate}.*?\n(.*?)(?=\n## |\Z)"
        m = re.search(pattern, text, re.DOTALL)
        if not m:
            fail(f"{gate} section not found")
            continue
        items = re.findall(r"- \[.\]", m.group(1))
        if items:
            ok(f"{gate} has {len(items)} check items")
        else:
            fail(f"{gate} has no checklist items")


def check_output_template_sections(skill_dir: Path):
    """Layer 2c: output-template covers Gate 4 required sections."""
    print("\n── Layer 2c: Output template vs Gate 4 ──")
    ot = skill_dir / "references" / "output-template.md"
    if not ot.is_file():
        fail("output-template.md missing")
        return
    text = ot.read_text(encoding="utf-8")
    for section in OUTPUT_TEMPLATE_SECTIONS:
        if section in text:
            ok(f"output template contains '{section}'")
        else:
            fail(f"output template missing '{section}'")


def check_reviewer_dimensions(root: Path, installed: bool):
    """Layer 2d: reviewer agent covers all 5 dimensions."""
    print("\n── Layer 2d: Reviewer dimensions ──")
    agent = (root.parents[1] if installed else root) / "agents" / "hardware-reviewer.md"
    if not agent.is_file():
        fail("hardware-reviewer.md missing")
        return
    text = agent.read_text(encoding="utf-8")
    for dim in REVIEWER_DIMENSIONS:
        if dim in text:
            ok(f"reviewer covers '{dim}'")
        else:
            fail(f"reviewer missing dimension '{dim}'")


def check_antipatterns(skill_dir: Path):
    """Layer 3a: reference docs should not contain vague phrases."""
    print("\n── Layer 3a: Anti-pattern detection ──")
    refs_dir = skill_dir / "references"
    if not refs_dir.is_dir():
        fail("references/ directory missing")
        return
    found_any = False
    for md in sorted(refs_dir.glob("*.md")):
        text = md.read_text(encoding="utf-8")
        for phrase in VAGUE_PHRASES:
            matches = re.findall(phrase, text)
            if matches:
                found_any = True
                fail(f"{md.name} contains vague phrase: '{matches[0]}'")
    if not found_any:
        ok("no vague phrases found in reference docs")


def _strip_quoted(text: str) -> str:
    """Remove content inside quotes/brackets so rule descriptions aren't flagged."""
    # remove "…" "…" '…' 「…」 and （…）
    text = re.sub(r'[""「].*?[""」]', '', text)
    text = re.sub(r"'.*?'", '', text)
    text = re.sub(r'（.*?）', '', text)
    return text


def check_placeholders(skill_dir: Path):
    """Layer 3b: no stale placeholders in non-template reference docs."""
    print("\n── Layer 3b: Placeholder detection ──")
    refs_dir = skill_dir / "references"
    if not refs_dir.is_dir():
        fail("references/ directory missing")
        return
    # output-template.md is allowed to have empty cells
    skip = {"output-template.md"}
    found_any = False
    for md in sorted(refs_dir.glob("*.md")):
        if md.name in skip:
            continue
        text = md.read_text(encoding="utf-8")
        cleaned = _strip_quoted(text)
        for pat in PLACEHOLDER_PATTERNS:
            matches = re.findall(pat, cleaned, re.IGNORECASE)
            if matches:
                found_any = True
                fail(f"{md.name} contains placeholder: '{matches[0]}'")
    # also check SKILL.md
    skill_md = skill_dir / "SKILL.md"
    if skill_md.is_file():
        text = skill_md.read_text(encoding="utf-8")
        cleaned = _strip_quoted(text)
        for pat in PLACEHOLDER_PATTERNS:
            matches = re.findall(pat, cleaned, re.IGNORECASE)
            if matches:
                found_any = True
                fail(f"SKILL.md contains placeholder: '{matches[0]}'")
    if not found_any:
        ok("no stale placeholders found")


# ── Layer 4: multi-platform config consistency ─────────────────────

def check_platform_configs(root: Path):
    """Layer 4a: all platform config files exist."""
    print("\n── Layer 4a: Platform config files ──")
    for rel in PLATFORM_CONFIG_FILES:
        p = root / rel
        if p.is_file():
            ok(f"{rel} exists")
        else:
            fail(f"{rel} missing")

    for rel in PLATFORM_ENTRY_FILES:
        p = root / rel
        if p.is_file():
            ok(f"{rel} exists")
        else:
            fail(f"{rel} missing")

    for rel in REPO_META_FILES:
        p = root / rel
        if p.is_file():
            ok(f"{rel} exists")
        else:
            fail(f"{rel} missing")


def check_version_consistency(root: Path):
    """Layer 4b: all platform config JSON files share the same version."""
    print("\n── Layer 4b: Version consistency ──")
    versions = {}
    for rel in PLATFORM_CONFIG_FILES:
        p = root / rel
        if not p.is_file():
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            v = data.get("version")
            if v:
                versions[rel] = v
                ok(f"{rel} version: {v}")
            else:
                fail(f"{rel} missing version field")
        except json.JSONDecodeError:
            fail(f"{rel} is not valid JSON")

    unique = set(versions.values())
    if len(unique) == 1:
        ok(f"all platform configs share version {unique.pop()}")
    elif len(unique) > 1:
        fail(f"version mismatch across configs: {versions}")

    # also check hooks-cursor.json exists
    hc = root / "hooks" / "hooks-cursor.json"
    if hc.is_file():
        ok("hooks/hooks-cursor.json exists")
    else:
        fail("hooks/hooks-cursor.json missing")


def check_version_bump_config(root: Path):
    """Layer 4c: .version-bump.json references valid files."""
    print("\n── Layer 4c: Version bump config ──")
    vb = root / ".version-bump.json"
    if not vb.is_file():
        fail(".version-bump.json missing")
        return
    try:
        cfg = json.loads(vb.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        fail(".version-bump.json is not valid JSON")
        return
    files = cfg.get("files", [])
    if not files:
        fail(".version-bump.json has no files entries")
        return
    for entry in files:
        p = root / entry["path"]
        if p.is_file():
            ok(f"bump target exists: {entry['path']}")
        else:
            fail(f"bump target missing: {entry['path']}")

    bump_script = root / "scripts" / "bump-version.sh"
    if bump_script.is_file():
        ok("scripts/bump-version.sh exists")
        if os.access(bump_script, os.X_OK):
            ok("scripts/bump-version.sh is executable")
        else:
            fail("scripts/bump-version.sh is not executable")
    else:
        fail("scripts/bump-version.sh missing")


# ── main ────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Validate NextBoard skill structure and content")
    default_root = Path(__file__).resolve().parents[1]
    parser.add_argument(
        "root",
        nargs="?",
        default=None,
        help=f"repo root or skill directory (default: {default_root})",
    )
    parser.add_argument("--installed", action="store_true",
                        help="validate an installed skill directory; explicit root takes precedence")
    parser.add_argument("--platform", choices=("claude", "codex"), default="claude",
                        help="default installation directory when --installed is used without root")
    args = parser.parse_args()

    if args.installed:
        root = Path(args.root).expanduser().resolve() if args.root else Path.home() / f".{args.platform}" / "skills" / "hardware-solution"
        installed = True
    else:
        root = Path(args.root).expanduser().resolve() if args.root else default_root
        installed = False

    print(f"Validating: {root}")
    print(f"Mode: {'installed copy' if installed else 'repo source'}")
    print("Scope: static source structure/content only; not datasheet, EDA, hardware, or release certification.")

    skill_dir = check_structure(root, installed)

    if not installed:
        check_hook_output(root)

    check_cross_references(skill_dir)
    check_gates_nonempty(skill_dir)
    check_output_template_sections(skill_dir)
    check_reviewer_dimensions(root, installed)
    check_antipatterns(skill_dir)
    check_placeholders(skill_dir)

    if not installed:
        check_platform_configs(root)
        check_version_consistency(root)
        check_version_bump_config(root)

    # summary
    print(f"\n{'─' * 40}")
    total = pass_count + fail_count + warn_count
    print(f"Total: {total}  {GREEN}PASS: {pass_count}{RESET}  {RED}FAIL: {fail_count}{RESET}  {YELLOW}WARN: {warn_count}{RESET}")
    if fail_count > 0:
        print(f"\n{RED}Validation failed.{RESET}")
        sys.exit(1)
    else:
        print(f"\n{GREEN}All static checks passed; design gates still require recorded evidence and review.{RESET}")
        sys.exit(0)


if __name__ == "__main__":
    main()
