from __future__ import annotations

import re
from pathlib import Path

import pytest

from tools.github_launch_audit import EXPECTED_DESCRIPTION, EXPECTED_HOMEPAGE, EXPECTED_TOPICS

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_root_install_and_release_metadata_point_to_the_hardware_butler_repository() -> None:
    from tools.github_launch_audit import DEFAULT_REPOSITORY

    repository = "yihang56666-sketch/hardware-butler"
    assert DEFAULT_REPOSITORY == repository
    metadata = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    install = (REPO_ROOT / "docs" / "INSTALL.md").read_text(encoding="utf-8")
    assert f'Repository = "https://github.com/{repository}"' in metadata
    assert f"git clone https://github.com/{repository}.git" in install
    assert "cd hardware-butler" in install


def test_root_community_files_are_present() -> None:
    if not (REPO_ROOT / ".github").is_dir():
        pytest.skip("GitHub community files are only required in the root repository")

    for relative in (
        "LICENSE",
        "SECURITY.md",
        "CONTRIBUTING.md",
        "SUPPORT.md",
        "CODE_OF_CONDUCT.md",
        ".github/pull_request_template.md",
        ".github/ISSUE_TEMPLATE/bug_report.yml",
        ".github/ISSUE_TEMPLATE/feature_request.yml",
        ".github/ISSUE_TEMPLATE/hardware_safety.yml",
    ):
        assert (REPO_ROOT / relative).is_file()


def test_code_of_conduct_mentions_hardware_safety() -> None:
    path = REPO_ROOT / "CODE_OF_CONDUCT.md"
    if not path.exists():
        pytest.skip("code of conduct is only required in the root repository")

    text = path.read_text(encoding="utf-8")

    assert "safety" in text.lower()
    assert "hardware" in text.lower()
    assert "SECURITY.md" in text


def test_release_note_config_covers_launch_labels() -> None:
    config_path = REPO_ROOT / ".github" / "release.yml"
    if not config_path.exists():
        pytest.skip("release note config is only required in the root GitHub repository")

    text = config_path.read_text(encoding="utf-8")

    assert "changelog:" in text
    assert "Safety And Hardware Gates" in text
    assert "User Workflows" in text
    assert "Documentation" in text
    assert "Other Changes" in text
    for label in ("safety", "hardware", "enhancement", "documentation", "bug", "dependencies", "chore"):
        assert f"- {label}" in text
    assert '- "*"' in text


def test_launch_repository_settings_match_audit_constants() -> None:
    settings_text = (REPO_ROOT / "docs" / "GITHUB_REPOSITORY_SETTINGS.md").read_text(encoding="utf-8")
    readme_text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    pyproject_text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert EXPECTED_DESCRIPTION in settings_text
    assert EXPECTED_DESCRIPTION in readme_text
    assert f'description = "{EXPECTED_DESCRIPTION}"' in pyproject_text
    assert EXPECTED_HOMEPAGE in settings_text
    assert f'--description "{EXPECTED_DESCRIPTION}"' in settings_text
    assert f'--homepage "{EXPECTED_HOMEPAGE}"' in settings_text

    match = re.search(r"Topics:\n\n```text\n(?P<topics>[^`]+)\n```", settings_text)
    assert match is not None
    documented_topics = {topic.strip() for topic in match.group("topics").split(",")}

    assert documented_topics == EXPECTED_TOPICS
    for topic in EXPECTED_TOPICS:
        assert f"--add-topic {topic}" in settings_text
