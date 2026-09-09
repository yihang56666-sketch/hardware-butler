import os
import subprocess
from pathlib import Path

import package_hardware_butler_plugin as packager
import pytest


def _directory_link(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        if os.name != "nt":
            pytest.skip("directory links are not available")
        subprocess.run(["cmd.exe", "/c", "mklink", "/J", str(link), str(target)], check=True, capture_output=True)


def test_packaging_omits_private_state_and_prunes_runtime_temp_folders(tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    candidates = {
        "tool.py": "public source",
        ".env": "fake secret",
        "credentials.json": "fake credentials",
        ".tmp-pytest-runtime/subdir/result.txt": "test residue",
        ".tmp-core-audit-fixture/data.txt": "test residue",
        ".claude/settings.local.json": "local settings",
        "private.pem": "fake private key",
        "__pycache__/ignored.pyc": "cache",
    }
    for relative, content in candidates.items():
        path = source / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    packager.copy_tree(source, target)
    assert sorted(path.relative_to(target).as_posix() for path in target.rglob("*") if path.is_file()) == ["tool.py"]


def test_packaging_rejects_source_links_instead_of_copying_external_content(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    private = tmp_path / "outside"
    private.mkdir()
    (private / "external.txt").write_text("not part of the package", encoding="utf-8")
    _directory_link(source / "linked", private)
    with pytest.raises(ValueError, match="link|outside"):
        packager.copy_tree(source, tmp_path / "target")


def test_clearing_managed_payload_cannot_follow_a_runtime_link_outside_plugin(tmp_path: Path, monkeypatch) -> None:
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    private = tmp_path / "private"
    private.mkdir()
    sentinel = private / "sentinel.txt"
    sentinel.write_text("keep", encoding="utf-8")
    _directory_link(runtime / "tools", private)
    monkeypatch.setattr(packager, "RUNTIME_ROOT", runtime)
    monkeypatch.setattr(packager, "MANAGED_RUNTIME_ITEMS", {"tools"})
    with pytest.raises(ValueError, match="outside|link"):
        packager.clear_managed_runtime_payload()
    assert sentinel.read_text(encoding="utf-8") == "keep"


def test_copy_file_does_not_follow_an_existing_destination_link(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_text("new content", encoding="utf-8")
    private = tmp_path / "private.txt"
    private.write_text("keep", encoding="utf-8")
    destination = tmp_path / "destination.txt"
    try:
        destination.symlink_to(private)
    except OSError:
        pytest.skip("symbolic link creation is not available")
    with pytest.raises(ValueError, match="link|outside"):
        packager.copy_file(source, destination)
    assert private.read_text(encoding="utf-8") == "keep"


def test_packaging_rejects_machine_specific_path_text(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "source"
    docs = source / "docs"
    docs.mkdir(parents=True)
    (docs / "public.md").write_text("# Public guide\nUse `<repo-root>` paths only.\n", encoding="utf-8")
    (docs / "local-path.md").write_text("Install at " + "D:" + chr(92) + "private" + chr(92) + "hardware-butler\n", encoding="utf-8")
    (docs / "username.md").write_text("Set C:" + chr(92) + "Users" + chr(92) + "private-user" + chr(92) + "config\n", encoding="utf-8")

    captured: list[Path] = []

    def reject_copied_path(path: Path, destination: Path) -> None:
        captured.append(path)

    monkeypatch.setattr(packager, "copy_file", reject_copied_path)
    monkeypatch.setattr(packager, "PUBLIC_RUNTIME_DOCS", {"public.md", "local-path.md", "username.md"})
    with pytest.raises(ValueError, match="(?i)machine-specific path"):
        packager.copy_public_docs(source / "docs", tmp_path / "runtime" / "docs")


def test_packaging_does_not_copy_unlisted_historical_docs(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "source" / "docs"
    source.mkdir(parents=True)
    copied: list[Path] = []
    for name in {"public.md", "private-audit.md"}:
        (source / name).write_text(f"# {name}\n", encoding="utf-8")

    def record_copy(path: Path, destination: Path) -> None:
        copied.append(path)

    monkeypatch.setattr(packager, "copy_file", record_copy)
    monkeypatch.setattr(packager, "PUBLIC_RUNTIME_DOCS", {"public.md"})
    packager.copy_public_docs(source, tmp_path / "runtime" / "docs")
    assert [path.name for path in copied] == ["public.md"]


def test_packaging_rejects_machine_specific_paths_in_runtime_source(tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    (source / "tool.py").write_text(
        'KNOWN_TOOL = Path("D:' + chr(92) + 'private' + chr(92) + 'tool.exe")\n',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="(?i)machine-specific path"):
        packager.copy_tree(source, target)
    assert not target.exists()


def test_packaging_allows_https_urls_that_contain_drive_like_substrings(tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    (source / "provider.py").write_text(
        'RESOURCE_URL = "https://www.st.com/en/search.html#q={part}"\n',
        encoding="utf-8",
    )

    packager.copy_tree(source, target)
    assert (target / "provider.py").read_text(encoding="utf-8") == (
        'RESOURCE_URL = "https://www.st.com/en/search.html#q={part}"\n'
    )


def test_packaging_allows_regexes_that_contain_non_drive_colons(tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    (source / "parser.py").write_text(
        'serial_number = re.search(r"S/N:\\\\s+(\\\\d+)", stdout)\\n',
        encoding="utf-8",
    )

    packager.copy_tree(source, target)
    assert (target / "parser.py").exists()


def test_packaging_rejects_machine_specific_paths_in_embedded_skill_text(tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    skill = source / "eide" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("Use toolchain `K:" + chr(92) + "Keil" + chr(92) + "ARMCLANG`.\n", encoding="utf-8")

    with pytest.raises(ValueError, match="(?i)machine-specific path"):
        packager.copy_tree(source, target)
