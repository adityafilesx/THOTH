"""Dedicated git workflow tools (Phase 3 slice 5). Structured, scoped git
operations: reads at R0, add/commit at R1. Gated by the slice-1 scope enforcer
via requested_scope (repo cwd + add path args). See ADR-015."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from omnimac_daemon.schemas import ResourceScope, RiskLevel, VerificationStrategy
from omnimac_daemon.security.paths import expand_and_resolve
from omnimac_daemon.tools.base import ToolDefinition
from omnimac_daemon.tools.git_io import run_git
from omnimac_daemon.tools.registry import ToolRegistry


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _Out(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _resolve_repo(cwd: str) -> Path:
    p = expand_and_resolve(cwd)
    if not p.is_dir():
        raise NotADirectoryError(f"cwd is not a directory: {p}")
    return p


# --- git_status (R0) -------------------------------------------------------
class GitStatusIn(_In):
    cwd: str


class GitStatusOut(_Out):
    cwd: str
    branch: str
    staged: list[str]
    unstaged: list[str]
    untracked: list[str]
    clean: bool


class GitStatus(ToolDefinition[GitStatusIn, GitStatusOut]):
    name = "git_status"
    description = "Structured git status of an approved repository (read-only)."
    input_model = GitStatusIn
    output_model = GitStatusOut
    default_risk = RiskLevel.R0
    verification = VerificationStrategy.NONE_READONLY

    def requested_scope(self, args: GitStatusIn) -> ResourceScope:
        return ResourceScope(paths=[args.cwd])

    async def run(self, args: GitStatusIn, dry_run: bool) -> GitStatusOut:
        cwd = _resolve_repo(args.cwd)
        r = await run_git(cwd, ["status", "--porcelain=v1", "--branch"])
        if r.returncode != 0:
            raise RuntimeError(r.stderr.strip() or "git status failed")
        branch = ""
        staged: list[str] = []
        unstaged: list[str] = []
        untracked: list[str] = []
        for line in r.stdout.splitlines():
            if line.startswith("## "):
                rest = line[3:]
                branch = rest[len("No commits yet on ") :] if rest.startswith("No commits yet on ") else rest.split("...")[0].split(" ")[0]
                continue
            if not line:
                continue
            code, name = line[:2], line[3:]
            if code == "??":
                untracked.append(name)
                continue
            if code[0] not in (" ", "?"):
                staged.append(name)
            if code[1] not in (" ", "?"):
                unstaged.append(name)
        return GitStatusOut(
            cwd=str(cwd),
            branch=branch,
            staged=staged,
            unstaged=unstaged,
            untracked=untracked,
            clean=not (staged or unstaged or untracked),
        )


# --- git_log (R0) ----------------------------------------------------------
class GitCommitInfo(_Out):
    sha: str
    subject: str
    author: str


class GitLogIn(_In):
    cwd: str
    max_count: int = Field(default=20, gt=0, le=1000)


class GitLogOut(_Out):
    cwd: str
    commits: list[GitCommitInfo]


class GitLog(ToolDefinition[GitLogIn, GitLogOut]):
    name = "git_log"
    description = "Recent commits of an approved repository (read-only)."
    input_model = GitLogIn
    output_model = GitLogOut
    default_risk = RiskLevel.R0
    verification = VerificationStrategy.NONE_READONLY

    def requested_scope(self, args: GitLogIn) -> ResourceScope:
        return ResourceScope(paths=[args.cwd])

    async def run(self, args: GitLogIn, dry_run: bool) -> GitLogOut:
        cwd = _resolve_repo(args.cwd)
        r = await run_git(cwd, ["log", f"--max-count={args.max_count}", "--pretty=format:%H%x1f%s%x1f%an"])
        if r.returncode != 0:
            if "does not have any commits" in r.stderr or "bad default revision" in r.stderr:
                return GitLogOut(cwd=str(cwd), commits=[])
            raise RuntimeError(r.stderr.strip() or "git log failed")
        commits = []
        for line in r.stdout.splitlines():
            parts = line.split("\x1f")
            if len(parts) == 3:
                commits.append(GitCommitInfo(sha=parts[0], subject=parts[1], author=parts[2]))
        return GitLogOut(cwd=str(cwd), commits=commits)


# --- git_diff (R0) ---------------------------------------------------------
class GitDiffIn(_In):
    cwd: str
    staged: bool = False


class GitDiffOut(_Out):
    cwd: str
    diff: str
    truncated: bool


class GitDiff(ToolDefinition[GitDiffIn, GitDiffOut]):
    name = "git_diff"
    description = "Unified diff of an approved repository (read-only)."
    input_model = GitDiffIn
    output_model = GitDiffOut
    default_risk = RiskLevel.R0
    verification = VerificationStrategy.NONE_READONLY
    redaction_fields: ClassVar[list[str]] = ["diff"]

    def requested_scope(self, args: GitDiffIn) -> ResourceScope:
        return ResourceScope(paths=[args.cwd])

    async def run(self, args: GitDiffIn, dry_run: bool) -> GitDiffOut:
        cwd = _resolve_repo(args.cwd)
        r = await run_git(cwd, ["diff", "--cached"] if args.staged else ["diff"])
        if r.returncode != 0:
            raise RuntimeError(r.stderr.strip() or "git diff failed")
        return GitDiffOut(cwd=str(cwd), diff=r.stdout, truncated=r.truncated)


# --- git_add (R1) ----------------------------------------------------------
class GitAddIn(_In):
    cwd: str
    paths: list[str] = Field(min_length=1)


class GitAddOut(_Out):
    cwd: str
    added: list[str]


class GitAdd(ToolDefinition[GitAddIn, GitAddOut]):
    name = "git_add"
    description = "Stage approved paths in an approved repository."
    input_model = GitAddIn
    output_model = GitAddOut
    default_risk = RiskLevel.R1
    verification = VerificationStrategy.STATE_PROBE

    def requested_scope(self, args: GitAddIn) -> ResourceScope:
        tokens = []
        for p in args.paths:
            base = p if p.startswith(("~", "/")) else str(Path(args.cwd) / p)
            tokens.append(str(expand_and_resolve(base)))
        return ResourceScope(paths=[args.cwd, *tokens])

    async def run(self, args: GitAddIn, dry_run: bool) -> GitAddOut:
        cwd = _resolve_repo(args.cwd)
        r = await run_git(cwd, ["add", "--", *args.paths])
        if r.returncode != 0:
            raise RuntimeError(r.stderr.strip() or "git add failed")
        return GitAddOut(cwd=str(cwd), added=list(args.paths))


# --- git_commit (R1) -------------------------------------------------------
class GitCommitIn(_In):
    cwd: str
    message: str


class GitCommitOut(_Out):
    cwd: str
    sha: str
    message: str


class GitCommit(ToolDefinition[GitCommitIn, GitCommitOut]):
    name = "git_commit"
    description = "Commit staged changes in an approved repository."
    input_model = GitCommitIn
    output_model = GitCommitOut
    default_risk = RiskLevel.R1
    verification = VerificationStrategy.STATE_PROBE

    def requested_scope(self, args: GitCommitIn) -> ResourceScope:
        return ResourceScope(paths=[args.cwd])

    async def run(self, args: GitCommitIn, dry_run: bool) -> GitCommitOut:
        cwd = _resolve_repo(args.cwd)
        r = await run_git(cwd, ["commit", "-m", args.message])
        if r.returncode != 0:
            raise RuntimeError(r.stderr.strip() or r.stdout.strip() or "git commit failed")
        head = await run_git(cwd, ["rev-parse", "HEAD"])
        if head.returncode != 0:
            raise RuntimeError("commit verification failed")
        return GitCommitOut(cwd=str(cwd), sha=head.stdout.strip(), message=args.message)


def register_git_tools(registry: ToolRegistry) -> None:
    for tool in (GitStatus(), GitLog(), GitDiff(), GitAdd(), GitCommit()):
        registry.register(tool)
