from pathlib import Path

import pytest

from thoth_daemon.tools.git_io import run_git
from thoth_daemon.tools.git_tools import GitAdd, GitCommit, GitDiff, GitLog, GitStatus


async def _repo(tmp_path: Path) -> Path:
    await run_git(tmp_path, ["init"])
    await run_git(tmp_path, ["config", "user.email", "t@t.test"])
    await run_git(tmp_path, ["config", "user.name", "T"])
    return tmp_path


async def test_status_untracked_then_add_commit_log(tmp_path: Path) -> None:
    await _repo(tmp_path)
    (tmp_path / "a.txt").write_text("hi")

    st = GitStatus()
    out = await st.run(st.input_model(cwd=str(tmp_path)), dry_run=False)
    assert "a.txt" in out.untracked and out.clean is False

    add = GitAdd()
    await add.run(add.input_model(cwd=str(tmp_path), paths=["a.txt"]), dry_run=False)
    st2 = await st.run(st.input_model(cwd=str(tmp_path)), dry_run=False)
    assert "a.txt" in st2.staged

    commit = GitCommit()
    cout = await commit.run(commit.input_model(cwd=str(tmp_path), message="add a"), dry_run=False)
    assert len(cout.sha) == 40

    log = GitLog()
    lout = await log.run(log.input_model(cwd=str(tmp_path)), dry_run=False)
    assert lout.commits and lout.commits[0].subject == "add a"


async def test_log_empty_repo_is_empty(tmp_path: Path) -> None:
    await _repo(tmp_path)
    log = GitLog()
    out = await log.run(log.input_model(cwd=str(tmp_path)), dry_run=False)
    assert out.commits == []


async def test_diff_staged_shows_patch(tmp_path: Path) -> None:
    await _repo(tmp_path)
    (tmp_path / "a.txt").write_text("hi\n")
    add = GitAdd()
    await add.run(add.input_model(cwd=str(tmp_path), paths=["a.txt"]), dry_run=False)
    diff = GitDiff()
    out = await diff.run(diff.input_model(cwd=str(tmp_path), staged=True), dry_run=False)
    assert "a.txt" in out.diff


async def test_status_non_repo_raises(tmp_path: Path) -> None:
    st = GitStatus()
    with pytest.raises(RuntimeError):
        await st.run(st.input_model(cwd=str(tmp_path)), dry_run=False)


async def test_commit_nothing_staged_raises(tmp_path: Path) -> None:
    await _repo(tmp_path)
    commit = GitCommit()
    with pytest.raises(RuntimeError):
        await commit.run(commit.input_model(cwd=str(tmp_path), message="empty"), dry_run=False)


def test_read_tools_are_r0_and_diff_redacted() -> None:
    assert GitStatus().default_risk.value == "R0"
    assert GitDiff.redaction_fields == ["diff"]
    assert GitAdd().default_risk.value == "R1"
    assert GitCommit().default_risk.value == "R1"


def test_add_requested_scope_includes_path_args(tmp_path: Path) -> None:
    from thoth_daemon.security.paths import expand_and_resolve

    add = GitAdd()
    scope = add.requested_scope(add.input_model(cwd=str(tmp_path), paths=["sub/x"]))
    assert str(tmp_path) in scope.paths
    assert str(expand_and_resolve(str(tmp_path / "sub" / "x"))) in scope.paths
