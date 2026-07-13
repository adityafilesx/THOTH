"""MOCK tools — Phase 2 only.

These are clearly-marked mocks (docs/TOOL_CONTRACTS.md §6). They operate on
in-memory fixtures, have NO real side effects, and exist solely to exercise
the safety core end-to-end. THOTH cannot control the computer with these.
Real adapters (macOS/browser/shell/filesystem) arrive in Phase 3.
"""

import asyncio
from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from thoth_daemon.core.focus import FocusPolicy
from thoth_daemon.schemas import RiskLevel, VerificationStrategy
from thoth_daemon.tools.base import ToolDefinition
from thoth_daemon.tools.registry import ToolRegistry


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _Out(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- mock_read_file (R0) -------------------------------------------------
class ReadFileIn(_In):
    path: str


class ReadFileOut(_Out):
    path: str
    content: str
    lines: int


class MockReadFile(ToolDefinition[ReadFileIn, ReadFileOut]):
    name = "mock_read_file"
    description = "MOCK: read an approved file (in-memory fixture)."
    input_model = ReadFileIn
    output_model = ReadFileOut
    default_risk = RiskLevel.R0
    verification = VerificationStrategy.OUTPUT_ASSERTION

    async def run(self, args: ReadFileIn, dry_run: bool) -> ReadFileOut:
        content = f"# mock contents of {args.path}\nline 1\nline 2\n"
        return ReadFileOut(path=args.path, content=content, lines=content.count("\n"))


# --- mock_list_dir (R0) --------------------------------------------------
class ListDirIn(_In):
    path: str


class ListDirOut(_Out):
    path: str
    entries: list[str]


class MockListDir(ToolDefinition[ListDirIn, ListDirOut]):
    name = "mock_list_dir"
    description = "MOCK: list a directory (in-memory fixture)."
    input_model = ListDirIn
    output_model = ListDirOut
    default_risk = RiskLevel.R0
    verification = VerificationStrategy.NONE_READONLY

    async def run(self, args: ListDirIn, dry_run: bool) -> ListDirOut:
        return ListDirOut(path=args.path, entries=["README.md", "src", "tests"])


# --- mock_open_app (R1) --------------------------------------------------
class OpenAppIn(_In):
    app: str


class OpenAppOut(_Out):
    app: str
    opened: bool


class MockOpenApp(ToolDefinition[OpenAppIn, OpenAppOut]):
    name = "mock_open_app"
    description = "MOCK: open/focus an approved application (no real launch)."
    focus_policy = FocusPolicy.KEEP_NEW_FOCUS
    input_model = OpenAppIn
    output_model = OpenAppOut
    default_risk = RiskLevel.R1
    verification = VerificationStrategy.STATE_PROBE

    def __init__(self) -> None:
        super().__init__()
        self.side_effect_count = 0

    async def run(self, args: OpenAppIn, dry_run: bool) -> OpenAppOut:
        if not dry_run:
            self.side_effect_count += 1
        return OpenAppOut(app=args.app, opened=not dry_run)


# --- mock_edit_file (R1) -------------------------------------------------
class EditFileIn(_In):
    path: str
    content: str


class EditFileOut(_Out):
    path: str
    written: bool
    bytes: int


class MockEditFile(ToolDefinition[EditFileIn, EditFileOut]):
    name = "mock_edit_file"
    description = "MOCK: write a file in an approved repo (in-memory only)."
    input_model = EditFileIn
    output_model = EditFileOut
    default_risk = RiskLevel.R1
    supports_dry_run = True
    verification = VerificationStrategy.OUTPUT_ASSERTION

    def __init__(self) -> None:
        super().__init__()
        self.side_effect_count = 0
        self._store: dict[str, str] = {}

    async def run(self, args: EditFileIn, dry_run: bool) -> EditFileOut:
        if not dry_run:
            self._store[args.path] = args.content
            self.side_effect_count += 1
        return EditFileOut(
            path=args.path,
            written=not dry_run,
            bytes=len(args.content.encode()),
        )


# --- mock_send_email (R2) ------------------------------------------------
class SendEmailIn(_In):
    recipient: str
    subject: str
    body: str


class SendEmailOut(_Out):
    recipient: str
    subject: str
    body: str
    sent: bool


class MockSendEmail(ToolDefinition[SendEmailIn, SendEmailOut]):
    name = "mock_send_email"
    description = "MOCK: send an email (external side effect; never really sent)."
    input_model = SendEmailIn
    output_model = SendEmailOut
    default_risk = RiskLevel.R2
    verification = VerificationStrategy.OUTPUT_ASSERTION
    redaction_fields: ClassVar[list[str]] = ["recipient", "body"]

    async def run(self, args: SendEmailIn, dry_run: bool) -> SendEmailOut:
        return SendEmailOut(
            recipient=args.recipient,
            subject=args.subject,
            body=args.body,
            sent=not dry_run,
        )


# --- mock_git_push (R2) --------------------------------------------------
class GitPushIn(_In):
    remote: str
    branch: str


class GitPushOut(_Out):
    remote: str
    branch: str
    pushed: bool


class MockGitPush(ToolDefinition[GitPushIn, GitPushOut]):
    name = "mock_git_push"
    description = "MOCK: push commits to a remote (external side effect)."
    input_model = GitPushIn
    output_model = GitPushOut
    default_risk = RiskLevel.R2
    verification = VerificationStrategy.OUTPUT_ASSERTION

    async def run(self, args: GitPushIn, dry_run: bool) -> GitPushOut:
        return GitPushOut(remote=args.remote, branch=args.branch, pushed=not dry_run)


# --- mock_delete_dir (R3) ------------------------------------------------
class DeleteDirIn(_In):
    path: str


class DeleteDirOut(_Out):
    path: str
    deleted: bool


class MockDeleteDir(ToolDefinition[DeleteDirIn, DeleteDirOut]):
    name = "mock_delete_dir"
    description = "MOCK: delete a directory (destructive; blocked by default)."
    input_model = DeleteDirIn
    output_model = DeleteDirOut
    default_risk = RiskLevel.R3
    verification = VerificationStrategy.STATE_PROBE

    async def run(self, args: DeleteDirIn, dry_run: bool) -> DeleteDirOut:
        # Reachable only if policy is bypassed; a test asserts it never is.
        return DeleteDirOut(path=args.path, deleted=not dry_run)


# --- mock_flaky (R1) -----------------------------------------------------
class FlakyIn(_In):
    fail_times: int = 1


class FlakyOut(_Out):
    attempts: int
    succeeded: bool


class MockFlaky(ToolDefinition[FlakyIn, FlakyOut]):
    name = "mock_flaky"
    description = "MOCK: fails the first N calls, then succeeds (recovery tests)."
    input_model = FlakyIn
    output_model = FlakyOut
    default_risk = RiskLevel.R1
    verification = VerificationStrategy.OUTPUT_ASSERTION

    def __init__(self) -> None:
        super().__init__()
        self._calls = 0

    async def run(self, args: FlakyIn, dry_run: bool) -> FlakyOut:
        self._calls += 1
        if self._calls <= args.fail_times:
            raise RuntimeError(f"transient failure (attempt {self._calls})")
        return FlakyOut(attempts=self._calls, succeeded=True)


# --- mock_slow (R0) ------------------------------------------------------
class SlowIn(_In):
    sleep_s: float = 5.0


class SlowOut(_Out):
    slept_s: float


class MockSlow(ToolDefinition[SlowIn, SlowOut]):
    name = "mock_slow"
    description = "MOCK: sleeps past its timeout (timeout/cancellation tests)."
    input_model = SlowIn
    output_model = SlowOut
    default_risk = RiskLevel.R0
    timeout_s = 0.2
    verification = VerificationStrategy.NONE_READONLY

    async def run(self, args: SlowIn, dry_run: bool) -> SlowOut:
        await asyncio.sleep(args.sleep_s)
        return SlowOut(slept_s=args.sleep_s)


def build_registry() -> ToolRegistry:
    registry = ToolRegistry()
    for tool in (
        MockReadFile(),
        MockListDir(),
        MockOpenApp(),
        MockEditFile(),
        MockSendEmail(),
        MockGitPush(),
        MockDeleteDir(),
        MockFlaky(),
        MockSlow(),
    ):
        registry.register(tool)
    return registry
