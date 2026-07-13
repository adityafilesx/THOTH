"""Browser tool (Phase 3 slice 7). Read the visible text of an approved web
page. The domain allowlist is enforced by the slice-1 scope enforcer via
requested_scope(domains=[host]); page text is untrusted (WEB_UNTRUSTED) and
redacted from the persisted record. Read-only — no clicking/forms/downloads."""

from __future__ import annotations

from typing import ClassVar
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict

from thoth_daemon.browser.browser_adapter import BrowserAdapter, default_browser
from thoth_daemon.core.focus import FocusPolicy
from thoth_daemon.schemas import ResourceScope, RiskLevel, VerificationStrategy
from thoth_daemon.tools.base import ToolDefinition
from thoth_daemon.tools.registry import ToolRegistry


class BrowserReadIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str


class BrowserReadOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str
    title: str
    text: str
    truncated: bool


class BrowserRead(ToolDefinition[BrowserReadIn, BrowserReadOut]):
    name = "browser_read"
    description = "Read the visible text of an approved web page (read-only)."
    focus_policy = FocusPolicy.DO_NOT_STEAL_FOCUS
    input_model = BrowserReadIn
    output_model = BrowserReadOut
    default_risk = RiskLevel.R1
    timeout_s = 30.0
    verification = VerificationStrategy.OUTPUT_ASSERTION
    redaction_fields: ClassVar[list[str]] = ["text"]

    def __init__(self, adapter: BrowserAdapter | None = None) -> None:
        super().__init__()
        self._browser = adapter or default_browser()

    def requested_scope(self, args: BrowserReadIn) -> ResourceScope:
        host = urlparse(args.url).hostname or ""
        return ResourceScope(domains=[host])

    async def run(self, args: BrowserReadIn, dry_run: bool) -> BrowserReadOut:
        scheme = urlparse(args.url).scheme
        if scheme not in ("http", "https"):
            raise ValueError(f"unsupported url scheme: {scheme!r}")
        if dry_run:
            return BrowserReadOut(url=args.url, title="", text="[dry-run]", truncated=False)
        pc = await self._browser.fetch(args.url, self.timeout_s)
        return BrowserReadOut(url=pc.url, title=pc.title, text=pc.text, truncated=pc.truncated)


def register_browser_tools(registry: ToolRegistry, adapter: BrowserAdapter | None = None) -> None:
    registry.register(BrowserRead(adapter or default_browser()))
