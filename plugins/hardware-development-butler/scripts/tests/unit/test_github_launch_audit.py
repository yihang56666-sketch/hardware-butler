from __future__ import annotations

import json
import subprocess

from tools import github_launch_audit


def _repo_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "description": github_launch_audit.EXPECTED_DESCRIPTION,
        "homepage": github_launch_audit.EXPECTED_HOMEPAGE,
        "topics": sorted(github_launch_audit.EXPECTED_TOPICS),
    }
    payload.update(overrides)
    return payload


def _workflow_run(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "status": "completed",
        "conclusion": "success",
        "head_sha": "abc",
        "html_url": "https://github.com/yihang56666-sketch/hardware-butler/actions/runs/1",
    }
    payload.update(overrides)
    return payload


def test_build_report_is_ok_when_remote_metadata_and_ci_match() -> None:
    report = github_launch_audit.build_report(
        owner=github_launch_audit.DEFAULT_OWNER,
        repo=github_launch_audit.DEFAULT_REPO,
        branch="main",
        workflow="ci.yml",
        local_sha="abc",
        remote_sha="abc",
        repository=_repo_payload(),
        workflow_run=_workflow_run(),
        remote="origin",
    )

    assert report.status == "ok"
    assert {check.name for check in report.checks} == {
        "remote.head",
        "repo.description",
        "repo.homepage",
        "repo.topics",
        "ci.main",
    }
    assert all(check.next_action == "No action required." for check in report.checks)


def test_build_report_uses_owner_repo_homepage() -> None:
    homepage = github_launch_audit.expected_homepage("yihang56666-sketch", "hardware-agent")

    report = github_launch_audit.build_report(
        owner="yihang56666-sketch",
        repo="hardware-agent",
        branch="main",
        workflow="ci.yml",
        local_sha="abc",
        remote_sha="abc",
        repository=_repo_payload(homepage=homepage),
        workflow_run=_workflow_run(),
        remote="origin",
    )

    checks = {check.name: check for check in report.checks}

    assert report.repository == "yihang56666-sketch/hardware-agent"
    assert checks["repo.homepage"].status == "ok"
    assert checks["repo.homepage"].details["expected"] == homepage


def test_build_report_reports_push_metadata_and_ci_gaps() -> None:
    report = github_launch_audit.build_report(
        owner=github_launch_audit.DEFAULT_OWNER,
        repo=github_launch_audit.DEFAULT_REPO,
        branch="main",
        workflow="ci.yml",
        local_sha="local",
        remote_sha="remote",
        repository=_repo_payload(description="old", homepage="", topics=["hardware"]),
        workflow_run=_workflow_run(status="completed", conclusion="failure"),
        remote="origin",
    )

    errors = {check.name: check for check in report.checks if check.status == "error"}

    assert report.status == "error"
    assert set(errors) == {"remote.head", "repo.description", "repo.homepage", "repo.topics", "ci.main"}
    assert "push is still required" in errors["remote.head"].message
    assert "git push origin main" in errors["remote.head"].next_action
    assert "GitHub About description" in errors["repo.description"].next_action
    assert "GitHub About homepage" in errors["repo.homepage"].next_action
    assert "stm32" in errors["repo.topics"].details["missing"]
    assert "stm32" in errors["repo.topics"].next_action
    assert "fix the failing CI" in errors["ci.main"].next_action


def test_build_report_can_include_push_permission_preflight() -> None:
    push_check = github_launch_audit.AuditCheck(
        name="git.push",
        status="error",
        message="git push --dry-run origin main failed",
        next_action="Fix credentials.",
        details={"command": "git push --dry-run origin main"},
    )

    report = github_launch_audit.build_report(
        owner=github_launch_audit.DEFAULT_OWNER,
        repo=github_launch_audit.DEFAULT_REPO,
        branch="main",
        workflow="ci.yml",
        local_sha="abc",
        remote_sha="abc",
        repository=_repo_payload(),
        workflow_run=_workflow_run(),
        remote="origin",
        push_check=push_check,
    )

    assert report.status == "error"
    assert [check.name for check in report.checks] == [
        "remote.head",
        "git.push",
        "repo.description",
        "repo.homepage",
        "repo.topics",
        "ci.main",
    ]


def test_check_push_permission_reports_github_account_mismatch(monkeypatch) -> None:
    def fake_push_dry_run(remote: str, branch: str) -> subprocess.CompletedProcess[str]:
        assert remote == "origin"
        assert branch == "main"
        return subprocess.CompletedProcess(
            args=("git", "push", "--dry-run", remote, branch),
            returncode=1,
            stdout="",
            stderr=(
                "remote: Permission to LeoKemp223/NextBoard.git denied to yihang56666-sketch.\n"
                "fatal: unable to access 'https://github.com/LeoKemp223/NextBoard.git/': "
                "The requested URL returned error: 403\n"
            ),
        )

    monkeypatch.setattr(github_launch_audit, "_run_git_push_dry_run", fake_push_dry_run)

    check = github_launch_audit.check_push_permission("origin", "main")

    assert check.status == "error"
    assert check.name == "git.push"
    assert "yihang56666-sketch does not have push access" in check.message
    assert "LeoKemp223/NextBoard.git" in check.message
    assert "Grant yihang56666-sketch write access" in check.next_action
    assert "switch Git credentials" in check.next_action
    assert check.details["account"] == "yihang56666-sketch"
    assert check.details["repository"] == "LeoKemp223/NextBoard.git"
    assert check.details["returncode"] == 1


def test_check_push_permission_ok(monkeypatch) -> None:
    def fake_push_dry_run(remote: str, branch: str) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=("git", "push", "--dry-run", remote, branch),
            returncode=0,
            stdout="Everything up-to-date\n",
            stderr="",
        )

    monkeypatch.setattr(github_launch_audit, "_run_git_push_dry_run", fake_push_dry_run)

    check = github_launch_audit.check_push_permission("origin", "main")

    assert check.status == "ok"
    assert "Git credentials can push" in check.message
    assert check.next_action == "No action required."


def test_build_report_reports_stale_ci_commit() -> None:
    report = github_launch_audit.build_report(
        owner=github_launch_audit.DEFAULT_OWNER,
        repo=github_launch_audit.DEFAULT_REPO,
        branch="main",
        workflow="ci.yml",
        local_sha="new-sha",
        remote_sha="new-sha",
        repository=_repo_payload(),
        workflow_run=_workflow_run(head_sha="old-sha"),
        remote="origin",
    )

    errors = {check.name: check for check in report.checks if check.status == "error"}

    assert report.status == "error"
    assert set(errors) == {"ci.main"}
    assert "does not match expected commit" in errors["ci.main"].message
    assert errors["ci.main"].details["expected_sha"] == "new-sha"


def test_missing_workflow_run_is_error() -> None:
    check = github_launch_audit.check_workflow_run(None, workflow="ci.yml", branch="main")

    assert check.status == "error"
    assert "No ci.yml workflow run found" in check.message
    assert "wait for the ci.yml GitHub Actions run" in check.next_action


def test_workflow_run_must_match_expected_commit() -> None:
    check = github_launch_audit.check_workflow_run(
        _workflow_run(head_sha="old-sha"),
        workflow="ci.yml",
        branch="main",
        expected_sha="new-sha",
    )

    assert check.status == "error"
    assert "does not match expected commit" in check.message
    assert "new-sha" in check.next_action
    assert check.details["head_sha"] == "old-sha"
    assert check.details["expected_sha"] == "new-sha"


def test_human_report_prints_next_actions_for_errors(capsys) -> None:
    report = github_launch_audit.build_report(
        owner=github_launch_audit.DEFAULT_OWNER,
        repo=github_launch_audit.DEFAULT_REPO,
        branch="main",
        workflow="ci.yml",
        local_sha="local",
        remote_sha="remote",
        repository=_repo_payload(description="old", homepage="", topics=["hardware"]),
        workflow_run=None,
        remote="origin",
    )

    github_launch_audit.print_report(report, as_json=False)

    output = capsys.readouterr().out
    assert "next: Push local commits with `git push origin main`" in output
    assert "next: Set the GitHub About description" in output
    assert "next: Add these GitHub repository topics" in output
    assert "Suggested GitHub CLI commands:" in output
    assert "gh repo edit yihang56666-sketch/hardware-butler `" in output
    assert f'--description "{github_launch_audit.EXPECTED_DESCRIPTION}"' in output
    assert f'--homepage "{github_launch_audit.EXPECTED_HOMEPAGE}"' in output
    assert "--add-topic stm32" in output


def test_print_settings_does_not_contact_git_or_github(monkeypatch, capsys) -> None:
    def fail_if_called(*args: object, **kwargs: object) -> object:
        raise AssertionError("offline settings output should not inspect git or GitHub")

    monkeypatch.setattr(github_launch_audit, "local_head", fail_if_called)
    monkeypatch.setattr(github_launch_audit, "remote_head", fail_if_called)
    monkeypatch.setattr(github_launch_audit, "fetch_repository", fail_if_called)
    monkeypatch.setattr(github_launch_audit, "fetch_latest_workflow_run", fail_if_called)

    exit_code = github_launch_audit.main(["--print-settings"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "GitHub launch settings: yihang56666-sketch/hardware-butler" in output
    assert github_launch_audit.EXPECTED_DESCRIPTION in output
    assert github_launch_audit.EXPECTED_HOMEPAGE in output
    assert "Suggested GitHub CLI commands:" in output
    assert "--add-topic stm32" in output


def test_print_settings_json(monkeypatch, capsys) -> None:
    def fail_if_called(*args: object, **kwargs: object) -> object:
        raise AssertionError("offline settings output should not inspect git or GitHub")

    monkeypatch.setattr(github_launch_audit, "local_head", fail_if_called)
    monkeypatch.setattr(github_launch_audit, "remote_head", fail_if_called)
    monkeypatch.setattr(github_launch_audit, "fetch_repository", fail_if_called)
    monkeypatch.setattr(github_launch_audit, "fetch_latest_workflow_run", fail_if_called)

    exit_code = github_launch_audit.main(["--print-settings", "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["repository"] == "yihang56666-sketch/hardware-butler"
    assert payload["description"] == github_launch_audit.EXPECTED_DESCRIPTION
    assert payload["homepage"] == github_launch_audit.EXPECTED_HOMEPAGE
    assert payload["topics"] == sorted(github_launch_audit.EXPECTED_TOPICS)
    assert any("--description" in command for command in payload["commands"])


def test_print_settings_json_uses_custom_owner_repo_homepage(monkeypatch, capsys) -> None:
    def fail_if_called(*args: object, **kwargs: object) -> object:
        raise AssertionError("offline settings output should not inspect git or GitHub")

    monkeypatch.setattr(github_launch_audit, "local_head", fail_if_called)
    monkeypatch.setattr(github_launch_audit, "remote_head", fail_if_called)
    monkeypatch.setattr(github_launch_audit, "fetch_repository", fail_if_called)
    monkeypatch.setattr(github_launch_audit, "fetch_latest_workflow_run", fail_if_called)

    exit_code = github_launch_audit.main(
        ["--owner", "yihang56666-sketch", "--repo", "hardware-agent", "--print-settings", "--json"]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["repository"] == "yihang56666-sketch/hardware-agent"
    assert payload["homepage"] == "https://github.com/yihang56666-sketch/hardware-agent#readme"
    assert any(
        '--homepage "https://github.com/yihang56666-sketch/hardware-agent#readme"' in command
        for command in payload["commands"]
    )


def test_check_push_only_does_not_contact_github(monkeypatch, capsys) -> None:
    def fail_if_called(*args: object, **kwargs: object) -> object:
        raise AssertionError("push-only check should not inspect GitHub API state")

    monkeypatch.setattr(github_launch_audit, "fetch_repository", fail_if_called)
    monkeypatch.setattr(github_launch_audit, "fetch_latest_workflow_run", fail_if_called)
    monkeypatch.setattr(
        github_launch_audit,
        "check_push_permission",
        lambda remote, branch: github_launch_audit.AuditCheck(
            name="git.push",
            status="ok",
            message=f"git push --dry-run {remote} {branch} completed",
            next_action="No action required.",
            details={"command": f"git push --dry-run {remote} {branch}"},
        ),
    )

    exit_code = github_launch_audit.main(["--check-push-only", "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["status"] == "ok"
    assert payload["checks"][0]["name"] == "git.push"


def test_runtime_errors_are_structured_json(monkeypatch, capsys) -> None:
    def raise_network_error() -> str:
        raise RuntimeError("fatal: unable to access remote")

    monkeypatch.setattr(github_launch_audit, "local_head", raise_network_error)

    exit_code = github_launch_audit.main(["--json"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert payload["status"] == "error"
    assert payload["checks"][0]["name"] == "audit.runtime"
    assert "fatal: unable to access remote" in payload["checks"][0]["message"]
    assert "Check network access" in payload["checks"][0]["next_action"]


def test_workflow_404_is_treated_as_missing_run(monkeypatch) -> None:
    def raise_not_found(url: str, *, token: str | None = None) -> dict[str, object]:
        raise github_launch_audit.GitHubApiError(f"missing: {url}", status_code=404)

    monkeypatch.setattr(github_launch_audit, "_request_json", raise_not_found)

    run = github_launch_audit.fetch_latest_workflow_run("LeoKemp223", "NextBoard", "ci.yml", "main")

    assert run is None
