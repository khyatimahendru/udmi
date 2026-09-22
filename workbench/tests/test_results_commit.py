"""Tests for results commit (Layer 4), exercised against real git repositories.

Every repository in this module is a genuine `git init` under `tmp_path`,
including a real bare repository used as a push remote, so branch selection,
branch creation, pathspec restriction, and pushing are verified end to end
rather than mocked. Nothing here touches the real UDMI checkout.
"""

import json
import os
import subprocess

import pytest

from workbench.server.results_commit import CommitError, build_message, commit, preview

DEVICE_ID = "AHU-1"
TEST_NAME = "system_mode"


def _run(cwd, *args):
    result = subprocess.run(["git", "-C", str(cwd), *args],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, f"git {' '.join(args)} failed: {result.stderr}"
    return result.stdout.strip()


def _run_bare(git_dir, *args):
    """Inspects a bare repository; `--git-dir` avoids safe.bareRepository rules."""
    result = subprocess.run(["git", f"--git-dir={git_dir}", *args],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, f"git {' '.join(args)} failed: {result.stderr}"
    return result.stdout.strip()


def _write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)


def _make_site_model(site_dir, device_id=DEVICE_ID):
    """Creates the minimum layout that discovery.resolve_site_model accepts."""
    _write(os.path.join(site_dir, "cloud_iot_config.json"),
           json.dumps({"site_name": "TEST", "registry_id": "ZZ-TRI-FECTA"}))
    _write(os.path.join(site_dir, "devices", device_id, "metadata.json"),
           json.dumps({"version": "1.5.0"}))


def _write_results(site_dir, device_id=DEVICE_ID, content="RESULT pass system_mode\n"):
    _write(os.path.join(site_dir, "out", "devices", device_id, "tests", TEST_NAME,
                        "RESULT.log"), content)


def _init_repo(path):
    """Initialises a real git repository with a local commit identity."""
    os.makedirs(path, exist_ok=True)
    subprocess.run(["git", "init", "-b", "main", str(path)],
                   capture_output=True, text=True, check=True, timeout=30)
    _run(path, "config", "user.name", "Workbench Test")
    _run(path, "config", "user.email", "workbench@example.com")
    return str(path)


@pytest.fixture
def site_repo(tmp_path):
    """A real git repo holding a site model, with one committed baseline file."""
    repo = tmp_path / "lab-site"
    _init_repo(repo)
    _make_site_model(str(repo))
    _run(repo, "add", "-A")
    _run(repo, "commit", "-m", "baseline site model")
    _write_results(str(repo))
    return str(repo)


@pytest.fixture
def udmi_root(tmp_path):
    """A directory standing in for the UDMI checkout, used as the path base."""
    root = tmp_path / "udmi-root"
    root.mkdir()
    return str(root)


def test_preview_non_repo_is_blocked(tmp_path, udmi_root):
    site = tmp_path / "plain-site"
    _make_site_model(str(site))
    _write_results(str(site))

    plan = preview(udmi_root, str(site), DEVICE_ID)

    assert plan["committable"] is False
    assert "not inside a git repository" in plan["reason"]
    assert plan["repo"] is None
    assert plan["path"] is None
    assert plan["repo_is_udmi"] is False
    assert plan["branches"] == []
    assert plan["remotes"] == []
    assert "Source: UDMI Workbench sequencer run" in plan["default_message"]


def test_preview_missing_results_dir_is_blocked(site_repo, udmi_root):
    plan = preview(udmi_root, site_repo, "NO-SUCH-DEVICE")

    assert plan["committable"] is False
    assert "No results directory" in plan["reason"]
    # Repository facts are still determinable from the site directory.
    assert plan["repo"] == os.path.realpath(site_repo)
    assert plan["current_branch"] == "main"


def test_preview_blocks_udmi_repo(tmp_path):
    """A site model living inside the UDMI checkout itself is hard-blocked."""
    udmi = tmp_path / "udmi"
    _init_repo(udmi)
    site = udmi / "sites" / "udmi_site_model"
    _make_site_model(str(site))
    _write_results(str(site))

    plan = preview(str(udmi), "sites/udmi_site_model", DEVICE_ID)

    assert plan["repo_is_udmi"] is True
    assert plan["committable"] is False
    assert "UDMI checkout" in plan["reason"]
    assert "sites/udmi_site_model" in plan["reason"]
    assert plan["repo"] == os.path.realpath(str(udmi))
    assert plan["path"] == os.path.join("sites", "udmi_site_model", "out", "devices",
                                        DEVICE_ID, "tests")
    assert plan["current_branch"] == "main"


def test_commit_against_udmi_repo_makes_no_git_write(tmp_path):
    udmi = tmp_path / "udmi"
    _init_repo(udmi)
    site = udmi / "sites" / "udmi_site_model"
    _make_site_model(str(site))
    _run(udmi, "add", "-A")
    _run(udmi, "commit", "-m", "udmi baseline")
    _write_results(str(site))

    before_head = _run(udmi, "rev-parse", "HEAD")
    before_branch = _run(udmi, "rev-parse", "--abbrev-ref", "HEAD")
    before_status = _run(udmi, "status", "--porcelain")

    with pytest.raises(CommitError) as excinfo:
        commit(str(udmi), "sites/udmi_site_model", DEVICE_ID,
               branch="results", create_branch=True, push=True, remote="origin")

    assert "UDMI checkout" in str(excinfo.value)
    assert _run(udmi, "rev-parse", "HEAD") == before_head
    assert _run(udmi, "rev-parse", "--abbrev-ref", "HEAD") == before_branch
    assert _run(udmi, "status", "--porcelain") == before_status
    assert _run(udmi, "for-each-ref", "--format=%(refname:short)", "refs/heads") == "main"


def test_preview_reports_branches_remotes_and_current(site_repo, udmi_root, tmp_path):
    _run(site_repo, "branch", "archive")
    remote_path = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(remote_path)],
                   capture_output=True, text=True, check=True, timeout=30)
    _run(site_repo, "remote", "add", "origin", str(remote_path))
    _run(site_repo, "remote", "add", "backup", str(remote_path))

    plan = preview(udmi_root, site_repo, DEVICE_ID)

    assert plan["committable"] is True
    assert plan["reason"] is None
    assert plan["current_branch"] == "main"
    assert plan["branches"] == ["archive", "main"]
    assert plan["remotes"] == ["backup", "origin"]
    assert plan["change_count"] == len(plan["changes"]) == 1
    assert plan["repo_is_udmi"] is False


def test_commit_uses_custom_message_verbatim(site_repo, udmi_root):
    result = commit(udmi_root, site_repo, DEVICE_ID, message="Lab run 42 results")

    assert result["status"] == "COMMITTED"
    assert result["message"] == "Lab run 42 results"
    assert _run(site_repo, "log", "-1", "--pretty=%B").strip() == "Lab run 42 results"
    assert result["branch"] == "main"
    assert result["branch_created"] is False
    assert result["pushed"] is False
    assert result["remote"] is None
    assert result["push_output"] is None
    assert result["revision"].startswith(result["short_revision"])


def test_commit_without_message_uses_generated_default(site_repo, udmi_root):
    result = commit(udmi_root, site_repo, DEVICE_ID,
                    summary={"pass": 3, "fail": 1}, project_spec="//mqtt/localhost:18833")

    body = _run(site_repo, "log", "-1", "--pretty=%B")
    assert result["message"].startswith(f"Sequencer results for {DEVICE_ID}")
    assert f"Device: {DEVICE_ID}" in body
    assert f"Site model: {site_repo}" in body
    assert "Source: UDMI Workbench sequencer run" in body
    assert "Project spec: //mqtt/localhost:18833" in body
    assert "Results: 3 pass, 1 fail" in body


def test_commit_creates_and_switches_branch(site_repo, udmi_root):
    result = commit(udmi_root, site_repo, DEVICE_ID, branch="results/run-1",
                    create_branch=True)

    assert result["branch"] == "results/run-1"
    assert result["branch_created"] is True
    assert _run(site_repo, "rev-parse", "--abbrev-ref", "HEAD") == "results/run-1"
    assert _run(site_repo, "rev-parse", "results/run-1") == result["revision"]


def test_create_branch_on_existing_name_fails(site_repo, udmi_root):
    _run(site_repo, "branch", "existing")
    head = _run(site_repo, "rev-parse", "HEAD")

    with pytest.raises(CommitError, match="already exists"):
        commit(udmi_root, site_repo, DEVICE_ID, branch="existing", create_branch=True)

    assert _run(site_repo, "rev-parse", "HEAD") == head
    assert _run(site_repo, "rev-parse", "--abbrev-ref", "HEAD") == "main"


def test_create_branch_with_invalid_ref_name_fails(site_repo, udmi_root):
    with pytest.raises(CommitError) as excinfo:
        commit(udmi_root, site_repo, DEVICE_ID, branch="bad name~1", create_branch=True)

    assert "bad name~1" in str(excinfo.value)
    assert _run(site_repo, "rev-parse", "--abbrev-ref", "HEAD") == "main"


def test_switch_to_missing_branch_fails(site_repo, udmi_root):
    with pytest.raises(CommitError) as excinfo:
        commit(udmi_root, site_repo, DEVICE_ID, branch="nope")

    assert "does not exist" in str(excinfo.value)
    assert "main" in str(excinfo.value)
    assert _run(site_repo, "rev-parse", "--abbrev-ref", "HEAD") == "main"


def test_switch_to_existing_branch(site_repo, udmi_root):
    _run(site_repo, "branch", "archive")

    result = commit(udmi_root, site_repo, DEVICE_ID, branch="archive")

    assert result["branch"] == "archive"
    assert result["branch_created"] is False
    assert _run(site_repo, "rev-parse", "--abbrev-ref", "HEAD") == "archive"


def test_commit_only_stages_the_device_pathspec(site_repo, udmi_root):
    unrelated = os.path.join(site_repo, "devices", DEVICE_ID, "metadata.json")
    _write(unrelated, json.dumps({"version": "1.5.1"}))

    commit(udmi_root, site_repo, DEVICE_ID)

    dirty = _run(site_repo, "status", "--porcelain")
    assert "devices/AHU-1/metadata.json" in dirty
    assert "out/devices" not in dirty


def test_push_to_real_bare_remote(site_repo, udmi_root, tmp_path):
    remote_path = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", str(remote_path)],
                   capture_output=True, text=True, check=True, timeout=30)
    _run(site_repo, "remote", "add", "origin", str(remote_path))

    result = commit(udmi_root, site_repo, DEVICE_ID, branch="results/push",
                    create_branch=True, push=True, remote="origin")

    assert result["pushed"] is True
    assert result["remote"] == "origin"
    assert result["push_output"]
    assert _run_bare(remote_path, "rev-parse", "results/push") == result["revision"]
    assert TEST_NAME in _run_bare(remote_path, "ls-tree", "-r", "--name-only",
                                  "results/push")


def test_push_to_unconfigured_remote_fails(site_repo, udmi_root, tmp_path):
    remote_path = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", str(remote_path)],
                   capture_output=True, text=True, check=True, timeout=30)
    _run(site_repo, "remote", "add", "origin", str(remote_path))

    with pytest.raises(CommitError) as excinfo:
        commit(udmi_root, site_repo, DEVICE_ID, push=True, remote="upstream")

    message = str(excinfo.value)
    assert "upstream" in message
    assert "origin" in message
    # The commit itself succeeded before the push was rejected; nothing reached
    # the remote.
    assert _run_bare(remote_path, "for-each-ref", "refs/heads") == ""


def test_preview_blocks_when_nothing_changed(site_repo, udmi_root):
    commit(udmi_root, site_repo, DEVICE_ID)

    plan = preview(udmi_root, site_repo, DEVICE_ID)

    assert plan["committable"] is False
    assert "Nothing to commit" in plan["reason"]
    assert plan["change_count"] == 0


def test_preview_blocks_ignored_results(site_repo, udmi_root):
    _write(os.path.join(site_repo, ".gitignore"), "out/\n")

    plan = preview(udmi_root, site_repo, DEVICE_ID)

    assert plan["committable"] is False
    assert ".gitignore" in plan["reason"]


def test_build_message_omits_absent_optional_fields():
    message = build_message(DEVICE_ID, "sites/lab")

    assert "Project spec:" not in message
    assert "Results:" not in message
    assert message.endswith("\n")
