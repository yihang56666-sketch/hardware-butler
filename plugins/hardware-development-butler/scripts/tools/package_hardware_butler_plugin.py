"""Package the hardware butler runtime into the repo-local Codex plugin."""

from __future__ import annotations

import os
import re
import shutil
import stat
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = REPO_ROOT / "plugins" / "hardware-development-butler"
RUNTIME_ROOT = PLUGIN_ROOT / "scripts"

EXCLUDED_DIRS = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".tmp-pytest",
    ".tmp-plugin-smoke",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
    ".venv",
    "venv",
    ".hardware-butler",
    ".claude",
    "output",
}
EXCLUDED_DOC_RUNTIME_DIRS = {"inspections", "chip"}
EXCLUDED_RUNTIME_PARTS = {("tests", "tmp")}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".pem", ".key", ".pfx", ".p12", ".sqlite", ".sqlite3", ".db"}
EXCLUDED_PRIVATE_FILES = {".env", "credentials.json", "auth.json", "settings.local.json"}
MANAGED_RUNTIME_ITEMS = {
    ".codex",
    "AGENTS.md",
    "CHANGELOG.md",
    "README.md",
    "agents",
    "conftest.py",
    "docs",
    "embeddedskills",
    "nextboard",
    "pyproject.toml",
    "requirements-all.txt",
    "requirements-dev.txt",
    "requirements.txt",
    "tests",
    "tools",
}
MANAGED_PLUGIN_SKILLS = {
    "chip-bringup",
}
PUBLIC_RUNTIME_DOCS = {
    "ARCHITECTURE_MAP.md",
    "AUTO_WORKFLOW_GUI.md",
    "BEGINNER_GUIDE.md",
    "COMMANDS.md",
    "FEATURES_AND_USAGE.md",
    "GITHUB_LAUNCH_CHECKLIST.md",
    "GITHUB_REPOSITORY_SETTINGS.md",
    "HARDWARE_UNDERSTANDING.md",
    "HR_PROJECT_GUIDE.md",
    "INSTALL.md",
    "OPEN_SOURCE_INTEGRATION.md",
    "PROGRESS.md",
    "PROJECT_PORTFOLIO_AUDIT.md",
    "README.md",
    "REAL_BOARD_DAY_RUNBOOK.md",
    "RELEASE_PROCESS.md",
    "START_HERE.md",
    "VS_TRADITIONAL_WORKFLOW.md",
    "WORKBENCH_FEATURE_COVERAGE.md",
    "WORKBENCH_TUTORIAL.md",
    "WORKFLOW_RUNNER_DESIGN.md",
}
MACHINE_PATH_PATTERN = re.compile(
    r"(?<![A-Za-z/\\])[A-Za-z]:[\\/]+(?:Users[\\/]+)?[^`|\s]*", re.IGNORECASE
)
ENV_EMBEDDEDSKILLS_ROOT = "HW_BUTLER_EMBEDDEDSKILLS_ROOT"
EMBEDDEDSKILLS_REQUIRED_FILES = (
    "safety_gate.py",
    "safety_cli.py",
    "workflow/scripts/workflow_run.py",
)


def should_ignore(path: Path) -> bool:
    if path.name in EXCLUDED_DIRS:
        return True
    if path.suffix.lower() in EXCLUDED_SUFFIXES:
        return True
    if path.name.lower() in EXCLUDED_PRIVATE_FILES:
        return True
    if path.name.startswith(".tmp") or path.name.endswith(".tmp"):
        return True
    if path.name.startswith(".env.") and path.name not in {".env.example", ".env.sample", ".env.template"}:
        return True
    return False


def reject_path_links(path: Path) -> None:
    for candidate in (path.absolute(), *path.absolute().parents):
        try:
            metadata = candidate.lstat()
        except FileNotFoundError:
            continue
        attributes = getattr(metadata, "st_file_attributes", 0)
        if stat.S_ISLNK(metadata.st_mode) or attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
            raise ValueError(f"Package paths must not contain a link or reparse point: {candidate}")


def require_contained_path(path: Path, root: Path) -> None:
    reject_path_links(root)
    reject_path_links(path)
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"Package path is outside the managed root: {path}")


def copy_tree(src: Path, dst: Path) -> None:
    reject_path_links(src)
    reject_path_links(dst)

    files: list[tuple[Path, Path]] = []

    def collect_files(current: Path) -> None:
        for path in sorted(current.iterdir()):
            if should_ignore(path):
                continue
            rel = path.relative_to(src)
            if (src.name, *rel.parts[:1]) in EXCLUDED_RUNTIME_PARTS:
                continue
            if src.name == "docs" and rel.parts and rel.parts[0] in EXCLUDED_DOC_RUNTIME_DIRS:
                continue
            reject_path_links(path)
            if path.is_dir():
                collect_files(path)
            elif path.is_file():
                assert_public_file(path)
                files.append((path, rel))

    collect_files(src)
    for source, rel in files:
        target = dst / rel
        require_contained_path(target, dst)
        copy_file(source, target)


def assert_public_file(path: Path) -> None:
    """Reject machine-specific paths in any text file entering the plugin."""
    data = path.read_bytes()
    if b"\0" in data:
        return
    text = data.decode("utf-8", errors="replace")
    for line_number, line in enumerate(text.splitlines(), start=1):
        if MACHINE_PATH_PATTERN.search(line):
            raise ValueError(
                f"Machine-specific path in public package text: {path}:{line_number}: {line.strip()}"
            )


def copy_file(src: Path, dst: Path) -> None:
    reject_path_links(src)
    reject_path_links(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def assert_public_text(path: Path) -> None:
    """Reject machine-specific paths before files enter the public plugin mirror."""
    text = path.read_text(encoding="utf-8", errors="replace")
    for line_number, line in enumerate(text.splitlines(), start=1):
        if MACHINE_PATH_PATTERN.search(line):
            raise ValueError(
                f"Machine-specific path in public package text: {path}:{line_number}: {line.strip()}"
            )


def copy_public_docs(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for name in sorted(PUBLIC_RUNTIME_DOCS):
        source_doc = source / name
        if not source_doc.exists():
            continue
        reject_path_links(source_doc)
        assert_public_text(source_doc)
        copy_file(source_doc, destination / name)


def clear_managed_runtime_payload(preserve: set[str] | None = None) -> None:
    preserve = preserve or set()
    for name in MANAGED_RUNTIME_ITEMS:
        if name not in preserve:
            require_contained_path(RUNTIME_ROOT / name, RUNTIME_ROOT)
    for name in MANAGED_RUNTIME_ITEMS:
        if name in preserve:
            continue
        target = RUNTIME_ROOT / name
        if target.is_dir():
            clear_runtime_directory(target)
        elif target.exists():
            target.unlink()


def clear_runtime_directory(path: Path) -> None:
    """Remove packaged files while leaving local test/cache state alone."""
    require_contained_path(path, RUNTIME_ROOT)
    for child in path.iterdir():
        if should_ignore(child):
            continue
        require_contained_path(child, RUNTIME_ROOT)
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def sync_project_skills() -> list[str]:
    copied = []
    for name in MANAGED_PLUGIN_SKILLS:
        src = REPO_ROOT / ".agents" / "skills" / name
        dst = PLUGIN_ROOT / "skills" / name
        if not src.exists():
            continue
        reject_path_links(src)
        require_contained_path(dst, PLUGIN_ROOT / "skills")
        if dst.exists():
            shutil.rmtree(dst)
        copy_tree(src, dst)
        copied.append(f"skills/{name}/")
    return copied


def embeddedskills_available(root: Path) -> bool:
    """Return True when a directory has the minimum embeddedskills runtime."""
    return all((root / rel).is_file() for rel in EMBEDDEDSKILLS_REQUIRED_FILES)


def resolve_embeddedskills_source() -> tuple[Path, str]:
    """Find the source used for the packaged embeddedskills runtime."""
    if override := os.getenv(ENV_EMBEDDEDSKILLS_ROOT):
        root = Path(override).expanduser().resolve()
        if embeddedskills_available(root):
            return root, "environment"

    root_checkout = REPO_ROOT / "embeddedskills"
    if embeddedskills_available(root_checkout):
        return root_checkout, "workspace"

    packaged_runtime = RUNTIME_ROOT / "embeddedskills"
    if embeddedskills_available(packaged_runtime):
        return packaged_runtime, "plugin-runtime"

    raise FileNotFoundError(
        "No embeddedskills runtime found. Provide a root embeddedskills/ checkout, "
        f"set {ENV_EMBEDDEDSKILLS_ROOT}, or restore the packaged plugin mirror."
    )


def package_runtime() -> list[str]:
    copied: list[str] = []
    RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    embeddedskills_src, embeddedskills_source = resolve_embeddedskills_source()
    preserve = {"embeddedskills"} if embeddedskills_src == RUNTIME_ROOT / "embeddedskills" else set()
    clear_managed_runtime_payload(preserve=preserve)

    for name in ("tools", "tests", "agents", ".codex", "nextboard"):
        copy_tree(REPO_ROOT / name, RUNTIME_ROOT / name)
        copied.append(f"{name}/")

    if "embeddedskills" in preserve:
        copied.append(f"embeddedskills/ (preserved from {embeddedskills_source})")
    else:
        copy_tree(embeddedskills_src, RUNTIME_ROOT / "embeddedskills")
        copied.append(f"embeddedskills/ (from {embeddedskills_source})")

    copy_public_docs(REPO_ROOT / "docs", RUNTIME_ROOT / "docs")
    copied.extend(f"docs/{name}" for name in sorted(PUBLIC_RUNTIME_DOCS) if (REPO_ROOT / "docs" / name).exists())

    for name in (
        "README.md",
        "AGENTS.md",
        "CHANGELOG.md",
        "pyproject.toml",
        "requirements.txt",
        "requirements-dev.txt",
        "requirements-all.txt",
        "conftest.py",
    ):
        copy_file(REPO_ROOT / name, RUNTIME_ROOT / name)
        copied.append(name)

    copied.extend(sync_project_skills())
    return copied


def main() -> None:
    copied = package_runtime()
    print(f"Packaged runtime into {RUNTIME_ROOT}")
    for item in copied:
        print(f"- {item}")


if __name__ == "__main__":
    main()
