"""Real, scoped filesystem tools (Phase 3 slice 3). Unlike the mocks these
touch the actual disk — but only within approved scope, enforced by the
ScopeEnforcer gate + registry backstop via requested_scope()."""

from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from omnimac_daemon.schemas import ResourceScope, RiskLevel, VerificationStrategy
from omnimac_daemon.security.paths import expand_and_resolve
from omnimac_daemon.tools.base import ToolDefinition
from omnimac_daemon.tools.fs_io import atomic_write, read_text_capped
from omnimac_daemon.tools.registry import ToolRegistry


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _Out(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- fs_read_file (R0) ---------------------------------------------------
class FsReadFileIn(_In):
    path: str
    max_bytes: int = Field(default=1_048_576, gt=0)


class FsReadFileOut(_Out):
    path: str
    content: str
    bytes: int
    truncated: bool


class FsReadFile(ToolDefinition[FsReadFileIn, FsReadFileOut]):
    name = "fs_read_file"
    description = "Read an approved text file from disk (scoped, size-capped)."
    input_model = FsReadFileIn
    output_model = FsReadFileOut
    default_risk = RiskLevel.R0
    verification = VerificationStrategy.NONE_READONLY
    redaction_fields: ClassVar[list[str]] = ["content"]

    def requested_scope(self, args: FsReadFileIn) -> ResourceScope:
        return ResourceScope(paths=[args.path])

    async def run(self, args: FsReadFileIn, dry_run: bool) -> FsReadFileOut:
        p = expand_and_resolve(args.path)
        text, n, truncated = read_text_capped(p, args.max_bytes)
        return FsReadFileOut(path=str(p), content=text, bytes=n, truncated=truncated)


# --- fs_list_dir (R0) ----------------------------------------------------
class FsEntry(_Out):
    name: str
    is_dir: bool


class FsListDirIn(_In):
    path: str


class FsListDirOut(_Out):
    path: str
    entries: list[FsEntry]


class FsListDir(ToolDefinition[FsListDirIn, FsListDirOut]):
    name = "fs_list_dir"
    description = "List an approved directory from disk (scoped)."
    input_model = FsListDirIn
    output_model = FsListDirOut
    default_risk = RiskLevel.R0
    verification = VerificationStrategy.NONE_READONLY

    def requested_scope(self, args: FsListDirIn) -> ResourceScope:
        return ResourceScope(paths=[args.path])

    async def run(self, args: FsListDirIn, dry_run: bool) -> FsListDirOut:
        p = expand_and_resolve(args.path)
        if not p.is_dir():
            raise NotADirectoryError(f"{p} is not a directory")
        entries: list[FsEntry] = []
        for child in sorted(p.iterdir(), key=lambda c: c.name):
            try:
                entries.append(FsEntry(name=child.name, is_dir=child.is_dir()))
            except OSError:
                continue
        return FsListDirOut(path=str(p), entries=entries)


# --- fs_stat (R0) --------------------------------------------------------
class FsStatIn(_In):
    path: str


class FsStatOut(_Out):
    path: str
    exists: bool
    is_file: bool
    is_dir: bool
    size: int


class FsStat(ToolDefinition[FsStatIn, FsStatOut]):
    name = "fs_stat"
    description = "Stat an approved path (existence/type/size); read-only probe."
    input_model = FsStatIn
    output_model = FsStatOut
    default_risk = RiskLevel.R0
    verification = VerificationStrategy.NONE_READONLY

    def requested_scope(self, args: FsStatIn) -> ResourceScope:
        return ResourceScope(paths=[args.path])

    async def run(self, args: FsStatIn, dry_run: bool) -> FsStatOut:
        p = expand_and_resolve(args.path)
        if not p.exists():
            return FsStatOut(path=str(p), exists=False, is_file=False, is_dir=False, size=0)
        return FsStatOut(path=str(p), exists=True, is_file=p.is_file(), is_dir=p.is_dir(), size=p.stat().st_size)


# --- fs_write_file (R1) --------------------------------------------------
class FsWriteFileIn(_In):
    path: str
    content: str


class FsWriteFileOut(_Out):
    path: str
    written: bool
    bytes: int


class FsWriteFile(ToolDefinition[FsWriteFileIn, FsWriteFileOut]):
    name = "fs_write_file"
    description = "Write/overwrite an approved file (scoped, atomic, self-verified)."
    input_model = FsWriteFileIn
    output_model = FsWriteFileOut
    default_risk = RiskLevel.R1
    supports_dry_run = True
    verification = VerificationStrategy.STATE_PROBE
    redaction_fields: ClassVar[list[str]] = ["content"]

    def requested_scope(self, args: FsWriteFileIn) -> ResourceScope:
        return ResourceScope(paths=[args.path])

    async def run(self, args: FsWriteFileIn, dry_run: bool) -> FsWriteFileOut:
        p = expand_and_resolve(args.path)
        data = args.content.encode("utf-8")
        if dry_run:
            return FsWriteFileOut(path=str(p), written=False, bytes=len(data))
        atomic_write(p, data)
        if p.read_bytes() != data:  # read-back self-verification (real state probe)
            raise OSError(f"write verification failed for {p}")
        return FsWriteFileOut(path=str(p), written=True, bytes=len(data))


def register_fs_tools(registry: ToolRegistry) -> None:
    for tool in (FsReadFile(), FsListDir(), FsWriteFile(), FsStat()):
        registry.register(tool)
