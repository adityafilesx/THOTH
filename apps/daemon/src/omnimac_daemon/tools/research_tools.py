"""Research tools combining web scraping and summarization."""

from __future__ import annotations

from typing import ClassVar
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict

from omnimac_daemon.browser.browser_adapter import BrowserAdapter, default_browser
from omnimac_daemon.core.focus import FocusPolicy
from omnimac_daemon.inference.base import InferenceProvider, InferenceRequest
from omnimac_daemon.schemas import ResourceScope, RiskLevel, VerificationStrategy
from omnimac_daemon.security.paths import expand_and_resolve
from omnimac_daemon.tools.base import ToolDefinition
from omnimac_daemon.tools.fs_io import atomic_write
from omnimac_daemon.tools.registry import ToolRegistry


class BrowserResearchAndSaveIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str
    topic: str
    dest_path: str


class BrowserResearchAndSaveOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str
    topic: str
    dest_path: str
    written: bool
    bytes: int


class BrowserResearchAndSave(ToolDefinition[BrowserResearchAndSaveIn, BrowserResearchAndSaveOut]):
    name = "browser_research_and_save"
    description = "Read a web page, summarize it using local AI, and save it to an approved path."
    focus_policy = FocusPolicy.DO_NOT_STEAL_FOCUS
    input_model = BrowserResearchAndSaveIn
    output_model = BrowserResearchAndSaveOut
    default_risk = RiskLevel.R2
    timeout_s = 120.0
    supports_dry_run = True
    verification = VerificationStrategy.STATE_PROBE
    # topic and dest_path are retained; actual content logic isn't passed here anyway
    redaction_fields: ClassVar[list[str]] = []

    def __init__(
        self,
        inference_provider: InferenceProvider,
        browser_adapter: BrowserAdapter | None = None,
    ) -> None:
        super().__init__()
        self._inference = inference_provider
        self._browser = browser_adapter or default_browser()

    def requested_scope(self, args: BrowserResearchAndSaveIn) -> ResourceScope:
        host = urlparse(args.url).hostname or ""
        return ResourceScope(domains=[host], paths=[args.dest_path])

    async def run(self, args: BrowserResearchAndSaveIn, dry_run: bool) -> BrowserResearchAndSaveOut:
        scheme = urlparse(args.url).scheme
        if scheme not in ("http", "https"):
            raise ValueError(f"unsupported url scheme: {scheme!r}")

        p = expand_and_resolve(args.dest_path)

        if dry_run:
            return BrowserResearchAndSaveOut(
                url=args.url,
                topic=args.topic,
                dest_path=str(p),
                written=False,
                bytes=0,
            )

        # 1. Fetch content
        pc = await self._browser.fetch(args.url, 30.0)

        # 2. Summarize
        prompt = f"Please summarize the following web page content focusing on the topic: '{args.topic}'.\n\nTitle: {pc.title}\n\nContent:\n{pc.text}"
        req = InferenceRequest(prompt=prompt, system="You are a helpful research assistant.", timeout_s=90.0)
        res = await self._inference.generate(req)

        data = res.text.encode("utf-8")

        # 3. Write
        atomic_write(p, data)
        if p.read_bytes() != data:
            raise OSError(f"write verification failed for {p}")

        return BrowserResearchAndSaveOut(
            url=args.url,
            topic=args.topic,
            dest_path=str(p),
            written=True,
            bytes=len(data),
        )


def register_research_tools(
    registry: ToolRegistry,
    inference_provider: InferenceProvider,
    browser_adapter: BrowserAdapter | None = None,
) -> None:
    registry.register(
        BrowserResearchAndSave(
            inference_provider=inference_provider,
            browser_adapter=browser_adapter,
        )
    )
