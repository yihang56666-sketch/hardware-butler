"""Read-only checks for the GitHub launch state."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OWNER = "yihang56666-sketch"
DEFAULT_REPO = "hardware-butler"
DEFAULT_BRANCH = "main"
DEFAULT_WORKFLOW = "ci.yml"
EXPECTED_DESCRIPTION = (
    "A safety-first embedded hardware copilot that turns board evidence, CubeMX projects, "
    "firmware plans, and bench bring-up into clear, gated next steps."
)
EXPECTED_TOPICS = frozenset(
    {
        "embedded",
        "hardware",
        "stm32",
        "cubemx",
        "firmware",
        "freertos",
        "jlink",
        "openocd",
        "probe-rs",
        "serial",
        "can",
        "safety",
        "codex-plugin",
    }
)
DEFAULT_REPOSITORY = f"{DEFAULT_OWNER}/{DEFAULT_REPO}"


def expected_homepage(owner: str, repo: str) -> str:
    return f"https://github.com/{owner}/{repo}#readme"


def expected_homepage_for_repository(repository: str) -> str:
    return f"https://github.com/{repository}#readme"


EXPECTED_HOMEPAGE = expected_homepage(DEFAULT_OWNER, DEFAULT_REPO)

Status = Literal["ok", "error"]


class GitHubApiError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class AuditCheck:
    name: str
    status: Status
    message: str
    next_action: str
    details: dict[str, Any]


@dataclass(frozen=True)
class AuditReport:
    schema_version: int
    status: Status
    repository: str
    branch: str
    checks: list[AuditCheck]


def _run_git(args: tuple[str, ...]) -> str:
    result = subprocess.run(
        ("git", *args),
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"git {' '.join(args)} failed with exit code {result.returncode}")
    return result.stdout.strip()


def _run_git_push_dry_run(remote: str, branch: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ("git", "push", "--dry-run", remote, branch),
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )


def local_head() -> str:
    return _run_git(("rev-parse", "HEAD"))


def remote_head(remote: str, branch: str) -> str:
    output = _run_git(("ls-remote", remote, f"refs/heads/{branch}"))
    if not output:
        raise RuntimeError(f"remote branch not found: {remote}/{branch}")
    return output.split()[0]


def _request_json(url: str, *, token: str | None = None) -> dict[str, Any]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "hardware-butler-launch-audit",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise GitHubApiError(f"GitHub API returned HTTP {exc.code} for {url}: {body}", status_code=exc.code) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"GitHub API request failed for {url}: {exc.reason}") from exc
    loaded = json.loads(payload)
    if not isinstance(loaded, dict):
        raise RuntimeError(f"GitHub API returned non-object JSON for {url}")
    return loaded


def fetch_repository(owner: str, repo: str, *, token: str | None = None) -> dict[str, Any]:
    return _request_json(f"https://api.github.com/repos/{owner}/{repo}", token=token)


def fetch_latest_workflow_run(
    owner: str,
    repo: str,
    workflow: str,
    branch: str,
    *,
    token: str | None = None,
) -> dict[str, Any] | None:
    url = (
        f"https://api.github.com/repos/{owner}/{repo}/actions/workflows/{workflow}/runs"
        f"?branch={branch}&per_page=1"
    )
    try:
        payload = _request_json(url, token=token)
    except GitHubApiError as exc:
        if exc.status_code == 404:
            return None
        raise
    runs = payload.get("workflow_runs")
    if not isinstance(runs, list) or not runs:
        return None
    first = runs[0]
    if not isinstance(first, dict):
        raise RuntimeError("GitHub API returned malformed workflow_runs entry")
    return first


def _normalize_topic(value: object) -> str:
    return str(value).strip().lower()


def check_heads(local_sha: str, remote_sha: str, *, remote: str, branch: str) -> AuditCheck:
    if local_sha == remote_sha:
        return AuditCheck(
            name="remote.head",
            status="ok",
            message=f"{remote}/{branch} matches local HEAD.",
            next_action="No action required.",
            details={"local": local_sha, "remote": remote_sha},
        )
    return AuditCheck(
        name="remote.head",
        status="error",
        message=f"{remote}/{branch} does not match local HEAD; push is still required.",
        next_action=f"Push local commits with `git push {remote} {branch}`, then wait for CI on {branch}.",
        details={"local": local_sha, "remote": remote_sha},
    )


def check_push_permission(remote: str, branch: str) -> AuditCheck:
    command = f"git push --dry-run {remote} {branch}"
    try:
        result = _run_git_push_dry_run(remote, branch)
    except subprocess.TimeoutExpired as exc:
        return AuditCheck(
            name="git.push",
            status="error",
            message=f"{command} timed out before Git reported whether push is authorized.",
            next_action="Check Git Credential Manager prompts or network access, then rerun this dry-run push check.",
            details={"command": command, "timeout_seconds": exc.timeout},
        )

    stdout = result.stdout.strip()
    stderr = result.stderr.strip()
    details: dict[str, Any] = {
        "command": command,
        "returncode": result.returncode,
        "stdout": stdout,
        "stderr": stderr,
    }
    output = f"{stdout}\n{stderr}".strip()
    if result.returncode == 0:
        return AuditCheck(
            name="git.push",
            status="ok",
            message=f"{command} completed successfully; Git credentials can push to {remote}/{branch}.",
            next_action="No action required.",
            details=details,
        )

    permission_match = re.search(r"Permission to (?P<repository>\S+) denied to (?P<account>[^.\s]+)", output)
    if permission_match:
        details["repository"] = permission_match.group("repository")
        details["account"] = permission_match.group("account")
        return AuditCheck(
            name="git.push",
            status="error",
            message=(
                f"{command} was rejected because GitHub account {details['account']} "
                f"does not have push access to {details['repository']}."
            ),
            next_action=(
                f"Grant {details['account']} write access, switch Git credentials to an account with access, "
                "or change `origin` to a repository owned by the authenticated account; then rerun this check."
            ),
            details=details,
        )

    return AuditCheck(
        name="git.push",
        status="error",
        message=f"{command} failed; Git could not prove push access to {remote}/{branch}.",
        next_action="Fix the Git remote or credentials, then rerun this dry-run push check.",
        details=details,
    )


def check_repository_metadata(
    repository: dict[str, Any],
    *,
    homepage_expected: str = EXPECTED_HOMEPAGE,
) -> list[AuditCheck]:
    checks: list[AuditCheck] = []
    description = str(repository.get("description") or "")
    checks.append(
        AuditCheck(
            name="repo.description",
            status="ok" if description == EXPECTED_DESCRIPTION else "error",
            message="Repository description matches launch settings."
            if description == EXPECTED_DESCRIPTION
            else "Repository description does not match launch settings.",
            next_action="No action required."
            if description == EXPECTED_DESCRIPTION
            else "Set the GitHub About description to the expected value in docs/GITHUB_REPOSITORY_SETTINGS.md.",
            details={"actual": description, "expected": EXPECTED_DESCRIPTION},
        )
    )

    homepage = str(repository.get("homepage") or "")
    checks.append(
        AuditCheck(
            name="repo.homepage",
            status="ok" if homepage == homepage_expected else "error",
            message="Repository homepage matches launch settings."
            if homepage == homepage_expected
            else "Repository homepage does not match launch settings.",
            next_action="No action required."
            if homepage == homepage_expected
            else "Set the GitHub About homepage to the expected value in docs/GITHUB_REPOSITORY_SETTINGS.md.",
            details={"actual": homepage, "expected": homepage_expected},
        )
    )

    raw_topics = repository.get("topics", [])
    topic_values = raw_topics if isinstance(raw_topics, list) else []
    actual_topics = {_normalize_topic(topic) for topic in topic_values}
    missing_topics = sorted(EXPECTED_TOPICS - actual_topics)
    checks.append(
        AuditCheck(
            name="repo.topics",
            status="ok" if not missing_topics else "error",
            message="Repository topics include the launch topic set."
            if not missing_topics
            else "Repository topics are missing launch topics.",
            next_action="No action required."
            if not missing_topics
            else f"Add these GitHub repository topics: {', '.join(missing_topics)}.",
            details={"actual": sorted(actual_topics), "missing": missing_topics, "expected": sorted(EXPECTED_TOPICS)},
        )
    )
    return checks


def check_workflow_run(
    workflow_run: dict[str, Any] | None,
    *,
    workflow: str,
    branch: str,
    expected_sha: str | None = None,
) -> AuditCheck:
    if workflow_run is None:
        return AuditCheck(
            name="ci.main",
            status="error",
            message=f"No {workflow} workflow run found on {branch}.",
            next_action=f"Push {branch}, wait for the {workflow} GitHub Actions run, then rerun this audit.",
            details={},
        )
    status = str(workflow_run.get("status") or "")
    conclusion = str(workflow_run.get("conclusion") or "")
    html_url = str(workflow_run.get("html_url") or "")
    head_sha = str(workflow_run.get("head_sha") or "")
    details = {"status": status, "conclusion": conclusion, "html_url": html_url}
    if head_sha:
        details["head_sha"] = head_sha
    if expected_sha:
        details["expected_sha"] = expected_sha
    if status == "completed" and conclusion == "success" and expected_sha and not head_sha:
        return AuditCheck(
            name="ci.main",
            status="error",
            message=f"Latest {workflow} run on {branch} does not expose its commit SHA.",
            next_action=(
                "Open the workflow run, confirm which commit it tested, wait for a successful run "
                f"for {expected_sha}, then rerun this audit."
            ),
            details=details,
        )
    if status == "completed" and conclusion == "success" and expected_sha and head_sha != expected_sha:
        return AuditCheck(
            name="ci.main",
            status="error",
            message=f"Latest {workflow} run on {branch} does not match expected commit.",
            next_action=(
                f"Push {branch} if needed, wait for {workflow} to run for {expected_sha}, "
                "then rerun this audit."
            ),
            details=details,
        )
    if status == "completed" and conclusion == "success":
        return AuditCheck(
            name="ci.main",
            status="ok",
            message=f"Latest {workflow} run on {branch} completed successfully.",
            next_action="No action required.",
            details=details,
        )
    return AuditCheck(
        name="ci.main",
        status="error",
        message=f"Latest {workflow} run on {branch} is not a successful completed run.",
        next_action="Open the workflow run, fix the failing CI result, wait for a successful rerun, then rerun this audit.",
        details=details,
    )


def build_report(
    *,
    owner: str,
    repo: str,
    branch: str,
    workflow: str,
    local_sha: str,
    remote_sha: str,
    repository: dict[str, Any],
    workflow_run: dict[str, Any] | None,
    remote: str,
    push_check: AuditCheck | None = None,
) -> AuditReport:
    repository_name = f"{owner}/{repo}"
    checks = [
        check_heads(local_sha, remote_sha, remote=remote, branch=branch),
        *check_repository_metadata(repository, homepage_expected=expected_homepage(owner, repo)),
        check_workflow_run(workflow_run, workflow=workflow, branch=branch, expected_sha=local_sha),
    ]
    if push_check is not None:
        checks.insert(1, push_check)
    status: Status = "ok" if all(check.status == "ok" for check in checks) else "error"
    return AuditReport(
        schema_version=1,
        status=status,
        repository=repository_name,
        branch=branch,
        checks=checks,
    )


def build_runtime_error_report(*, owner: str, repo: str, branch: str, error: str) -> AuditReport:
    return AuditReport(
        schema_version=1,
        status="error",
        repository=f"{owner}/{repo}",
        branch=branch,
        checks=[
            AuditCheck(
                name="audit.runtime",
                status="error",
                message=error,
                next_action=(
                    "Check network access, GitHub availability, the configured remote/branch, "
                    "and any required credentials, then rerun this audit."
                ),
                details={"error": error},
            )
        ],
    )


def configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-only GitHub launch-state audit.")
    parser.add_argument("--owner", default=DEFAULT_OWNER, help="GitHub repository owner")
    parser.add_argument("--repo", default=DEFAULT_REPO, help="GitHub repository name")
    parser.add_argument("--remote", default="origin", help="Git remote name to compare against local HEAD")
    parser.add_argument("--branch", default=DEFAULT_BRANCH, help="Branch expected to contain local HEAD")
    parser.add_argument("--workflow", default=DEFAULT_WORKFLOW, help="Workflow file name to verify on the branch")
    parser.add_argument("--print-settings", action="store_true", help="print expected GitHub About settings and exit")
    parser.add_argument(
        "--check-push",
        action="store_true",
        help="include a `git push --dry-run` credential/permission preflight in the audit",
    )
    parser.add_argument(
        "--check-push-only",
        action="store_true",
        help="only run the `git push --dry-run` credential/permission preflight",
    )
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    return parser.parse_args(argv)


def build_metadata_command(repository: str) -> str:
    homepage = expected_homepage_for_repository(repository)
    return "\n".join(
        (
            f"gh repo edit {repository} `",
            f'  --description "{EXPECTED_DESCRIPTION}" `',
            f'  --homepage "{homepage}"',
        )
    )


def build_topics_command(repository: str, topics: list[str]) -> str:
    lines = [f"gh repo edit {repository} `"]
    for index, topic in enumerate(topics):
        suffix = " `" if index < len(topics) - 1 else ""
        lines.append(f"  --add-topic {topic}{suffix}")
    return "\n".join(lines)


def build_settings_commands(repository: str) -> list[str]:
    return [build_metadata_command(repository), build_topics_command(repository, sorted(EXPECTED_TOPICS))]


def build_github_cli_commands(report: AuditReport) -> list[str]:
    failed_checks = {check.name: check for check in report.checks if check.status == "error"}
    commands: list[str] = []

    if "repo.description" in failed_checks or "repo.homepage" in failed_checks:
        commands.append(build_metadata_command(report.repository))

    topics_check = failed_checks.get("repo.topics")
    if topics_check is not None:
        raw_missing = topics_check.details.get("missing", sorted(EXPECTED_TOPICS))
        missing_topics = sorted(str(topic) for topic in raw_missing) if isinstance(raw_missing, list) else sorted(EXPECTED_TOPICS)
        if missing_topics:
            commands.append(build_topics_command(report.repository, missing_topics))

    return commands


def build_settings_payload(repository: str) -> dict[str, Any]:
    return {
        "repository": repository,
        "description": EXPECTED_DESCRIPTION,
        "homepage": expected_homepage_for_repository(repository),
        "topics": sorted(EXPECTED_TOPICS),
        "commands": build_settings_commands(repository),
    }


def print_settings(*, repository: str, as_json: bool) -> None:
    payload = build_settings_payload(repository)
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    print(f"GitHub launch settings: {repository}")
    print(f"Description: {EXPECTED_DESCRIPTION}")
    print(f"Homepage: {payload['homepage']}")
    print(f"Topics: {', '.join(sorted(EXPECTED_TOPICS))}")
    print()
    print("Suggested GitHub CLI commands:")
    for command in payload["commands"]:
        print(command)


def print_report(report: AuditReport, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(asdict(report), ensure_ascii=False, indent=2))
        return
    print(f"GitHub launch audit: {report.repository}@{report.branch}")
    print(f"Status: {report.status}")
    for check in report.checks:
        print(f"- [{check.status}] {check.name}: {check.message}")
        if check.status == "error":
            print(f"  next: {check.next_action}")
    commands = build_github_cli_commands(report)
    if commands:
        print()
        print("Suggested GitHub CLI commands:")
        for command in commands:
            print(command)


def main(argv: list[str] | None = None) -> int:
    configure_stdio()
    args = parse_args(argv)
    if args.print_settings:
        print_settings(repository=f"{args.owner}/{args.repo}", as_json=args.json)
        return 0
    if args.check_push_only:
        push_only_check = check_push_permission(args.remote, args.branch)
        report = AuditReport(
            schema_version=1,
            status=push_only_check.status,
            repository=f"{args.owner}/{args.repo}",
            branch=args.branch,
            checks=[push_only_check],
        )
        print_report(report, as_json=args.json)
        return 0 if report.status == "ok" else 1

    token = os.environ.get("GITHUB_TOKEN") or None
    try:
        push_check: AuditCheck | None = check_push_permission(args.remote, args.branch) if args.check_push else None
        report = build_report(
            owner=args.owner,
            repo=args.repo,
            branch=args.branch,
            workflow=args.workflow,
            local_sha=local_head(),
            remote_sha=remote_head(args.remote, args.branch),
            repository=fetch_repository(args.owner, args.repo, token=token),
            workflow_run=fetch_latest_workflow_run(args.owner, args.repo, args.workflow, args.branch, token=token),
            remote=args.remote,
            push_check=push_check,
        )
    except RuntimeError as exc:
        report = build_runtime_error_report(owner=args.owner, repo=args.repo, branch=args.branch, error=str(exc))
        print_report(report, as_json=args.json)
        return 2
    print_report(report, as_json=args.json)
    return 0 if report.status == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
