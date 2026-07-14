"""Browser interaction tools (Phase 4 slice 4).

Nine tools over an injected stateful BrowserSession. Navigation and
mutation are R1; ACTUAL form submission is R2 (explicit approval) and is
only reachable through the two-phase prepare/submit flow — there is no
one-shot submit. Domain scope is declared per navigation
(requested_scope(domains=[host])); downloads and screenshots also declare
the destination path. All page-derived text is UNTRUSTED (WEB_UNTRUSTED)
and is returned as inert data; the injection guard scans it downstream.
Password-like field values are masked by the standard redaction layer at
every serialization boundary.
"""

from __future__ import annotations

from typing import ClassVar
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field

from thoth_daemon.browser.session import (
    BrowserSession,
    PageState,
    default_browser_session,
)
from thoth_daemon.core.focus import FocusPolicy
from thoth_daemon.inference.isolation import NetworkIsolationGuard
from thoth_daemon.schemas import ResourceScope, RiskLevel, VerificationStrategy
from thoth_daemon.tools.base import ToolDefinition
from thoth_daemon.tools.registry import ToolRegistry


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _Out(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PageView(_Out):
    url: str
    title: str
    text: str
    selectors: list[str]


def _view(state: PageState) -> PageView:
    return PageView(
        url=state.url, title=state.title, text=state.text, selectors=list(state.selectors)
    )


def _host(url: str) -> str:
    return urlparse(url).hostname or ""


async def _require_on_page(session: BrowserSession, current_url: str) -> None:
    """The scope anchor (args.current_url) must describe the session's ACTUAL
    page — otherwise the scope check was anchored on a lie (slice 11)."""
    state = await session.state()
    if _host(state.url) != _host(current_url):
        raise ValueError(
            f"current_url host {_host(current_url)!r} does not match the session's "
            f"actual page host {_host(state.url)!r}"
        )


def _require_http(url: str) -> None:
    scheme = urlparse(url).scheme
    if scheme not in ("http", "https", "file"):
        raise ValueError(f"unsupported url scheme: {scheme!r}")


class _SessionTool:
    def __init__(
        self,
        session: BrowserSession | None = None,
        *,
        network_isolation: bool = False,
    ) -> None:
        super().__init__()
        self._session = session or default_browser_session()
        self._network = NetworkIsolationGuard(isolation=network_isolation)

    def _require_network(self, url: str) -> None:
        self._network.check(url)


# -- browser_open (R1) --------------------------------------------------------
class OpenIn(_In):
    url: str


class BrowserOpen(_SessionTool, ToolDefinition[OpenIn, PageView]):
    name = "browser_open"
    description = "Open an approved URL in the interactive session."
    focus_policy = FocusPolicy.KEEP_NEW_FOCUS
    input_model = OpenIn
    output_model = PageView
    default_risk = RiskLevel.R1
    timeout_s = 30.0
    supports_dry_run = True
    verification = VerificationStrategy.OUTPUT_ASSERTION
    redaction_fields: ClassVar[list[str]] = ["text"]

    def requested_scope(self, args: OpenIn) -> ResourceScope:
        return ResourceScope(domains=[_host(args.url)])

    async def run(self, args: OpenIn, dry_run: bool) -> PageView:
        _require_http(args.url)
        self._require_network(args.url)
        if dry_run:
            return PageView(url=args.url, title="", text="[dry-run]", selectors=[])
        return _view(await self._session.open(args.url, self.timeout_s))


# -- browser_find (R0, current page) -------------------------------------------
class FindIn(_In):
    selector: str


class FoundElement(_Out):
    selector: str
    tag: str
    text: str
    value: str | None


class FindOut(_Out):
    matches: list[FoundElement]


class BrowserFind(_SessionTool, ToolDefinition[FindIn, FindOut]):
    name = "browser_find"
    description = "Find elements on the CURRENT page by selector or text (read-only)."
    focus_policy = FocusPolicy.DO_NOT_STEAL_FOCUS
    input_model = FindIn
    output_model = FindOut
    default_risk = RiskLevel.R0
    verification = VerificationStrategy.NONE_READONLY
    redaction_fields: ClassVar[list[str]] = ["text"]

    async def run(self, args: FindIn, dry_run: bool) -> FindOut:
        found = await self._session.find(args.selector)
        return FindOut(
            matches=[
                FoundElement(selector=e.selector, tag=e.tag, text=e.text, value=e.value)
                for e in found
            ]
        )


# -- browser_click (R1) ----------------------------------------------------------
class ClickIn(_In):
    selector: str
    current_url: str  # scope anchor: the page the click happens on


class BrowserClick(_SessionTool, ToolDefinition[ClickIn, PageView]):
    name = "browser_click"
    description = "Click an element on the current approved page."
    focus_policy = FocusPolicy.DO_NOT_STEAL_FOCUS
    input_model = ClickIn
    output_model = PageView
    default_risk = RiskLevel.R1
    timeout_s = 15.0
    supports_dry_run = True
    verification = VerificationStrategy.OUTPUT_ASSERTION
    redaction_fields: ClassVar[list[str]] = ["text"]

    def requested_scope(self, args: ClickIn) -> ResourceScope:
        return ResourceScope(domains=[_host(args.current_url)])

    async def run(self, args: ClickIn, dry_run: bool) -> PageView:
        if dry_run:
            state = await self._session.state()
            return _view(state)
        await _require_on_page(self._session, args.current_url)
        return _view(await self._session.click(args.selector, self.timeout_s))


# -- browser_fill (R1) -------------------------------------------------------------
class FillIn(_In):
    selector: str
    value: str
    current_url: str


class BrowserFill(_SessionTool, ToolDefinition[FillIn, PageView]):
    name = "browser_fill"
    description = "Type a value into a field on the current approved page (no submit)."
    focus_policy = FocusPolicy.DO_NOT_STEAL_FOCUS
    input_model = FillIn
    output_model = PageView
    default_risk = RiskLevel.R1
    supports_dry_run = True
    verification = VerificationStrategy.OUTPUT_ASSERTION
    redaction_fields: ClassVar[list[str]] = ["text", "value"]

    def requested_scope(self, args: FillIn) -> ResourceScope:
        return ResourceScope(domains=[_host(args.current_url)])

    async def run(self, args: FillIn, dry_run: bool) -> PageView:
        if dry_run:
            return _view(await self._session.state())
        await _require_on_page(self._session, args.current_url)
        return _view(await self._session.fill(args.selector, args.value))


# -- browser_select (R1) --------------------------------------------------------------
class SelectIn(_In):
    selector: str
    option: str
    current_url: str


class BrowserSelect(_SessionTool, ToolDefinition[SelectIn, PageView]):
    name = "browser_select"
    description = "Choose an option in a select element on the current approved page."
    focus_policy = FocusPolicy.DO_NOT_STEAL_FOCUS
    input_model = SelectIn
    output_model = PageView
    default_risk = RiskLevel.R1
    supports_dry_run = True
    verification = VerificationStrategy.OUTPUT_ASSERTION
    redaction_fields: ClassVar[list[str]] = ["text"]

    def requested_scope(self, args: SelectIn) -> ResourceScope:
        return ResourceScope(domains=[_host(args.current_url)])

    async def run(self, args: SelectIn, dry_run: bool) -> PageView:
        if dry_run:
            return _view(await self._session.state())
        await _require_on_page(self._session, args.current_url)
        return _view(await self._session.select(args.selector, args.option))


# -- browser_download (R1) --------------------------------------------------------------
class DownloadIn(_In):
    url: str
    dest_dir: str


class DownloadOut(_Out):
    path: str


class BrowserDownload(_SessionTool, ToolDefinition[DownloadIn, DownloadOut]):
    name = "browser_download"
    description = "Download a file from an approved domain into an approved directory."
    focus_policy = FocusPolicy.DO_NOT_STEAL_FOCUS
    input_model = DownloadIn
    output_model = DownloadOut
    default_risk = RiskLevel.R1
    timeout_s = 60.0
    supports_dry_run = True
    verification = VerificationStrategy.STATE_PROBE

    def requested_scope(self, args: DownloadIn) -> ResourceScope:
        return ResourceScope(domains=[_host(args.url)], paths=[args.dest_dir])

    async def run(self, args: DownloadIn, dry_run: bool) -> DownloadOut:
        _require_http(args.url)
        if dry_run:
            return DownloadOut(path=f"{args.dest_dir}/[dry-run]")
        return DownloadOut(
            path=await self._session.download(args.url, args.dest_dir, self.timeout_s)
        )


# -- browser_screenshot (R1) ---------------------------------------------------------------
class ScreenshotIn(_In):
    dest_path: str


class ScreenshotOut(_Out):
    path: str


class BrowserScreenshot(_SessionTool, ToolDefinition[ScreenshotIn, ScreenshotOut]):
    name = "browser_screenshot"
    description = "Screenshot the current page into an approved path."
    focus_policy = FocusPolicy.DO_NOT_STEAL_FOCUS
    input_model = ScreenshotIn
    output_model = ScreenshotOut
    default_risk = RiskLevel.R1
    supports_dry_run = True
    verification = VerificationStrategy.STATE_PROBE

    def requested_scope(self, args: ScreenshotIn) -> ResourceScope:
        return ResourceScope(paths=[args.dest_path])

    async def run(self, args: ScreenshotIn, dry_run: bool) -> ScreenshotOut:
        if dry_run:
            return ScreenshotOut(path="[dry-run]")
        return ScreenshotOut(path=await self._session.screenshot(args.dest_path))


# -- browser_prepare_submission (R1) ----------------------------------------------------------
class PrepareIn(_In):
    form_selector: str
    current_url: str


class PrepareOut(_Out):
    submission_id: str
    form_selector: str
    action_url: str
    # Exactly what would be submitted. Sensitive keys (password etc.) are
    # masked by the redaction layer at serialization boundaries.
    fields: dict[str, str]


class BrowserPrepareSubmission(_SessionTool, ToolDefinition[PrepareIn, PrepareOut]):
    name = "browser_prepare_submission"
    description = (
        "Capture exactly what a form WOULD submit (action URL + field map) "
        "without submitting; returns a single-use submission id."
    )
    focus_policy = FocusPolicy.DO_NOT_STEAL_FOCUS
    input_model = PrepareIn
    output_model = PrepareOut
    default_risk = RiskLevel.R1
    verification = VerificationStrategy.OUTPUT_ASSERTION

    def requested_scope(self, args: PrepareIn) -> ResourceScope:
        return ResourceScope(domains=[_host(args.current_url)])

    async def run(self, args: PrepareIn, dry_run: bool) -> PrepareOut:
        await _require_on_page(self._session, args.current_url)
        prepared = await self._session.prepare_submission(args.form_selector)
        return PrepareOut(
            submission_id=prepared.submission_id,
            form_selector=prepared.form_selector,
            action_url=prepared.action_url,
            fields=prepared.fields,
        )


# -- browser_submit (R2 — explicit approval) -----------------------------------------------------
class SubmitIn(_In):
    submission_id: str = Field(min_length=8)
    action_url: str  # scope anchor + shown to the approver


class BrowserSubmit(_SessionTool, ToolDefinition[SubmitIn, PageView]):
    name = "browser_submit"
    description = (
        "Submit a PREVIOUSLY PREPARED form (single-use id). External "
        "side effect — requires explicit approval."
    )
    focus_policy = FocusPolicy.DO_NOT_STEAL_FOCUS
    input_model = SubmitIn
    output_model = PageView
    default_risk = RiskLevel.R2
    timeout_s = 30.0
    supports_dry_run = True
    verification = VerificationStrategy.OUTPUT_ASSERTION
    redaction_fields: ClassVar[list[str]] = ["text"]

    def requested_scope(self, args: SubmitIn) -> ResourceScope:
        return ResourceScope(domains=[_host(args.action_url)])

    async def run(self, args: SubmitIn, dry_run: bool) -> PageView:
        if dry_run:
            return _view(await self._session.state())
        return _view(
            await self._session.submit(
                args.submission_id, self.timeout_s, expected_action_url=args.action_url
            )
        )


def register_browser_interaction_tools(
    registry: ToolRegistry,
    session: BrowserSession | None = None,
    *,
    network_isolation: bool = False,
) -> None:
    s = session or default_browser_session()
    for tool in (
        BrowserOpen(s, network_isolation=network_isolation),
        BrowserFind(s, network_isolation=network_isolation),
        BrowserClick(s, network_isolation=network_isolation),
        BrowserFill(s, network_isolation=network_isolation),
        BrowserSelect(s, network_isolation=network_isolation),
        BrowserDownload(s, network_isolation=network_isolation),
        BrowserScreenshot(s, network_isolation=network_isolation),
        BrowserPrepareSubmission(s, network_isolation=network_isolation),
        BrowserSubmit(s, network_isolation=network_isolation),
    ):
        registry.register(tool)
