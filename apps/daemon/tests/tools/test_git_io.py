from pathlib import Path

from omnimac_daemon.tools.git_io import run_git


async def _init(repo: Path) -> None:
    await run_git(repo, ["init"])
    await run_git(repo, ["config", "user.email", "t@t.test"])
    await run_git(repo, ["config", "user.name", "T"])


async def test_run_git_captures_output(tmp_path: Path) -> None:
    await _init(tmp_path)
    r = await run_git(tmp_path, ["status", "--porcelain=v1", "--branch"])
    assert r.returncode == 0 and "##" in r.stdout


async def test_run_git_nonzero_not_raised(tmp_path: Path) -> None:
    r = await run_git(tmp_path, ["status"])  # not a repo
    assert r.returncode != 0 and r.stdout == ""
