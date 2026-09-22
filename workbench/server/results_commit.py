"""Commit sequencer results to version control (Layer 4).

Implements b/541129051: after a sequencer run the lab needs the results
committed for historical tracking, with a message identifying the device, the
fact that it was a sequencer run, and that it originated from Workbench.

Design decisions:
  * Commits are ONLY ever made in response to an explicit user action. There is
    no automatic or implicit commit path.
  * Only the one device's results directory is staged and committed. Unrelated
    working-tree changes are never swept in.
  * Every precondition failure (not a repo, path missing, path ignored, nothing
    to commit, identity unset) is reported explicitly rather than worked around.

Prohibition on committing to the UDMI checkout:
  The Workbench must never commit to, switch branches in, or push the UDMI
  repository itself. When the results directory resolves to a git repository
  whose root is the UDMI checkout, the whole feature is hard-blocked:
  `preview` reports `repo_is_udmi: True` with `committable: False`, and
  `commit` raises `CommitError` before any git write is attempted.
  `sites/udmi_site_model` is a fixture of the UDMI repo, not a lab site model;
  results are only committable for site models kept in their own repository
  outside the UDMI checkout.
"""

from datetime import datetime, timezone
import os
import subprocess
from typing import Any, Dict, List, Optional

from workbench.server.logger import SERVER_LOGGER

GIT_TIMEOUT_SECONDS = 30


class CommitError(Exception):
    """Raised when results cannot be committed. Carries an actionable message."""


def _git(repo: str, *args: str) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            ["git", "-C", repo, *args],
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except FileNotFoundError as exc:
        raise CommitError("git executable not found on PATH.") from exc
    except subprocess.TimeoutExpired as exc:
        raise CommitError(f"git {' '.join(args)} timed out after {GIT_TIMEOUT_SECONDS}s.") from exc


def _repo_root(path: str) -> Optional[str]:
    """Returns the git repository root containing `path`, or None if untracked."""
    result = _git(path, "rev-parse", "--show-toplevel")
    if result.returncode != 0:
        return None
    return os.path.realpath(result.stdout.strip())


def _current_branch(repo: str) -> Optional[str]:
    """Returns the checked-out branch name, or None when HEAD is detached."""
    result = _git(repo, "symbolic-ref", "--quiet", "--short", "HEAD")
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _branches(repo: str) -> List[str]:
    result = _git(repo, "for-each-ref", "--format=%(refname:short)", "refs/heads")
    if result.returncode != 0:
        return []
    return sorted(line.strip() for line in result.stdout.splitlines() if line.strip())


def _remotes(repo: str) -> List[str]:
    result = _git(repo, "remote")
    if result.returncode != 0:
        return []
    return sorted(line.strip() for line in result.stdout.splitlines() if line.strip())


def _locate(udmi_root: str, site_model: str, device_id: str) -> tuple:
    """Returns the (site directory, results directory) pair for one device."""
    from workbench.server.discovery import resolve_site_model

    site_dir = resolve_site_model(udmi_root, site_model)
    return site_dir, os.path.join(site_dir, "out", "devices", device_id, "tests")


def build_message(
    device_id: str,
    site_model: str,
    summary: Optional[Dict[str, Any]] = None,
    project_spec: Optional[str] = None,
) -> str:
    """Builds the commit message required by b/541129051."""
    lines = [
        f"Sequencer results for {device_id}",
        "",
        f"Device: {device_id}",
        f"Site model: {site_model}",
        "Source: UDMI Workbench sequencer run",
        f"Recorded: {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
    ]
    if project_spec:
        lines.append(f"Project spec: {project_spec}")
    if summary:
        counts = ", ".join(
            f"{summary[key]} {key}"
            for key in ("pass", "fail", "skip")
            if isinstance(summary.get(key), int)
        )
        if counts:
            lines.append(f"Results: {counts}")
    return "\n".join(lines) + "\n"


def udmi_repo_reason(repo: str) -> str:
    """The single copy of the hard block message for the UDMI checkout."""
    return (
        f"The results directory is inside the UDMI checkout itself ({repo}). "
        "The Workbench never commits to, switches branches in, or pushes the UDMI "
        "repository. Committing sequencer results is only supported for site models "
        "kept in their own repository outside the UDMI checkout; "
        "'sites/udmi_site_model' is a fixture of the UDMI repo, not a lab site model."
    )


def preview(udmi_root: str, site_model: str, device_id: str) -> Dict[str, Any]:
    """Reports exactly what a commit would do, including any blocking reason.

    Every key is always present so the UI can render a fully explained disabled
    dialog; values are populated as far as they can be determined even when the
    commit is blocked.
    """
    site_dir, results_dir = _locate(udmi_root, site_model, device_id)

    state: Dict[str, Any] = {
        "committable": False,
        "reason": None,
        "repo": None,
        "path": None,
        "changes": [],
        "change_count": 0,
        "repo_is_udmi": False,
        "current_branch": None,
        "branches": [],
        "remotes": [],
        "default_message": build_message(device_id, site_model),
    }

    # The site model directory is guaranteed to exist by resolve_site_model, so
    # repository facts stay discoverable even when no results were recorded yet.
    probe = results_dir if os.path.isdir(results_dir) else site_dir

    repo = _repo_root(probe)
    if repo:
        state["repo"] = repo
        state["path"] = os.path.relpath(results_dir, repo)
        state["repo_is_udmi"] = repo == os.path.realpath(udmi_root)
        state["current_branch"] = _current_branch(repo)
        state["branches"] = _branches(repo)
        state["remotes"] = _remotes(repo)

    if not os.path.isdir(results_dir):
        state["reason"] = (
            f"No results directory at {results_dir}. Run a sequence before committing."
        )
        return state

    if not repo:
        state["reason"] = (
            f"'{results_dir}' is not inside a git repository, so results cannot be "
            "committed. Site models tracked for historical results must be version "
            "controlled."
        )
        return state

    if state["repo_is_udmi"]:
        state["reason"] = udmi_repo_reason(repo)
        return state

    relative = state["path"]
    if _git(repo, "check-ignore", "-q", relative).returncode == 0:
        state["reason"] = (
            f"'{relative}' is excluded by .gitignore in {repo}, so results cannot be "
            "committed. Un-ignore the results path in that repository first."
        )
        return state

    status = _git(repo, "status", "--porcelain", "--", relative)
    if status.returncode != 0:
        raise CommitError(f"git status failed: {status.stderr.strip()}")
    state["changes"] = [line[3:] for line in status.stdout.splitlines() if line.strip()]
    state["change_count"] = len(state["changes"])

    if not state["changes"]:
        state["reason"] = f"No uncommitted changes under '{relative}'. Nothing to commit."
        return state

    state["committable"] = True
    return state


def _validate_new_branch(repo: str, branch: str, existing: List[str]) -> None:
    """Fails unless `branch` is a valid, unused local branch name."""
    if branch.startswith("-"):
        raise CommitError(f"Invalid branch name '{branch}': names may not start with '-'.")
    if _git(repo, "check-ref-format", "--branch", branch).returncode != 0:
        raise CommitError(
            f"Invalid branch name '{branch}': rejected by git check-ref-format."
        )
    if branch in existing:
        raise CommitError(
            f"Branch '{branch}' already exists in {repo}. Choose a different name, or "
            "commit onto the existing branch without requesting branch creation."
        )


def _select_branch(repo: str, plan: Dict[str, Any], branch: Optional[str],
                   create_branch: bool) -> Dict[str, Any]:
    """Puts the repository on the requested branch, or fails explicitly."""
    current = plan["current_branch"]
    if create_branch:
        if not branch:
            raise CommitError("Branch creation requested but no 'branch' name was given.")
        _validate_new_branch(repo, branch, plan["branches"])
        result = _git(repo, "switch", "-c", branch)
        if result.returncode != 0:
            raise CommitError(
                f"git switch -c {branch} failed: {(result.stderr or result.stdout).strip()}"
            )
        return {"branch": branch, "branch_created": True}

    if branch and branch != current:
        if branch not in plan["branches"]:
            raise CommitError(
                f"Branch '{branch}' does not exist in {repo}. Existing branches: "
                f"{', '.join(plan['branches']) or '(none)'}. Request branch creation to "
                "make a new one."
            )
        result = _git(repo, "switch", branch)
        if result.returncode != 0:
            raise CommitError(
                f"git switch {branch} failed: {(result.stderr or result.stdout).strip()}"
            )
        return {"branch": branch, "branch_created": False}

    if not current:
        raise CommitError(
            f"HEAD is detached in {repo}. Specify a branch to commit the results onto."
        )
    return {"branch": current, "branch_created": False}


def _push(repo: str, branch: str, remote: str, remotes: List[str]) -> str:
    """Pushes `branch` to `remote`, setting upstream on first push."""
    if remote not in remotes:
        raise CommitError(
            f"Remote '{remote}' is not configured in {repo}. Available remotes: "
            f"{', '.join(remotes) or '(none)'}."
        )
    upstream = _git(repo, "rev-parse", "--abbrev-ref", "--symbolic-full-name",
                    f"{branch}@{{upstream}}")
    args = ["push"] + (["--set-upstream"] if upstream.returncode != 0 else []) + [remote, branch]
    result = _git(repo, *args)
    if result.returncode != 0:
        raise CommitError(
            f"git {' '.join(args)} failed: {(result.stderr or result.stdout).strip()}"
        )
    return (result.stderr or result.stdout).strip()


def commit(
    udmi_root: str,
    site_model: str,
    device_id: str,
    *,
    message: Optional[str] = None,
    branch: Optional[str] = None,
    create_branch: bool = False,
    push: bool = False,
    remote: Optional[str] = None,
    summary: Optional[Dict[str, Any]] = None,
    project_spec: Optional[str] = None,
    correlation_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Stages and commits one device's sequencer results. User-initiated only."""
    if not site_model:
        raise CommitError("Missing required field: 'site_model'")
    if not device_id:
        raise CommitError("Missing required field: 'device_id'")
    if push and not remote:
        raise CommitError("Push requested but no 'remote' was given.")

    # Single enforcement point: nothing below runs for a blocked repository,
    # including the UDMI checkout itself.
    plan = preview(udmi_root, site_model, device_id)
    if not plan["committable"]:
        raise CommitError(plan["reason"])

    repo = plan["repo"]
    relative = plan["path"]
    final_message = (
        message
        if message and message.strip()
        else build_message(device_id, site_model, summary, project_spec)
    )

    selection = _select_branch(repo, plan, branch, create_branch)

    staged = _git(repo, "add", "--", relative)
    if staged.returncode != 0:
        raise CommitError(f"git add failed: {staged.stderr.strip()}")

    # Restricting the commit to this pathspec keeps unrelated staged work out.
    committed = _git(repo, "commit", "-m", final_message, "--", relative)
    if committed.returncode != 0:
        detail = (committed.stderr or committed.stdout).strip()
        if "user.email" in detail or "user.name" in detail:
            raise CommitError(
                "git identity is not configured in this repository. Set user.name and "
                f"user.email before committing results. Git reported: {detail}"
            )
        raise CommitError(f"git commit failed: {detail}")

    revision = _git(repo, "rev-parse", "HEAD").stdout.strip()
    push_output = _push(repo, selection["branch"], remote, plan["remotes"]) if push else None

    SERVER_LOGGER.info(
        "ResultsCommit",
        "results.committed",
        correlation_id=correlation_id,
        context={"deviceId": device_id, "siteModel": site_model},
        details={"repo": repo, "path": relative, "revision": revision,
                 "fileCount": plan["change_count"], "branch": selection["branch"],
                 "branchCreated": selection["branch_created"], "pushed": bool(push),
                 "remote": remote if push else None},
    )

    return {
        "status": "COMMITTED",
        "repo": repo,
        "path": relative,
        "revision": revision,
        "short_revision": revision[:12],
        "message": final_message,
        "files": plan["changes"],
        "file_count": plan["change_count"],
        "branch": selection["branch"],
        "branch_created": selection["branch_created"],
        "pushed": bool(push),
        "remote": remote if push else None,
        "push_output": push_output,
    }
