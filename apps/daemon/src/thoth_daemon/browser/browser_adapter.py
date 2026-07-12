"""Browser automation via Playwright (headless Chromium). Fetches a page's
visible text — the domain allowlist is enforced upstream by the scope enforcer
(browser tools declare requested_scope(domains=[host])). Playwright is imported
lazily so this module imports without the package/browsers present.

Chosen over the Node "Playwright MCP" server (ADR-018): Python-native, no extra
process, verifiable now, same safety contract, swappable behind this protocol."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

_MAX_TEXT = 64 * 1024


@dataclass
class PageContent:
    url: str
    title: str
    text: str
    truncated: bool


class BrowserAdapter(Protocol):
    async def fetch(self, url: str, timeout_s: float) -> PageContent: ...


class PlaywrightBrowser:
    """Real headless-Chromium adapter. Launches a fresh browser per call
    (stateless — no cookies/session carried between fetches)."""

    async def fetch(self, url: str, timeout_s: float) -> PageContent:
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                page = await browser.new_page()
                await page.goto(url, wait_until="domcontentloaded", timeout=int(timeout_s * 1000))
                title = await page.title()
                body = await page.inner_text("body")
            finally:
                await browser.close()
        truncated = len(body) > _MAX_TEXT
        return PageContent(url=url, title=title, text=body[:_MAX_TEXT], truncated=truncated)


class MockBrowser:
    """In-memory adapter for tests: url -> (title, text)."""

    def __init__(self, pages: dict[str, tuple[str, str]] | None = None) -> None:
        self._pages = pages or {}

    async def fetch(self, url: str, timeout_s: float) -> PageContent:
        if url not in self._pages:
            raise RuntimeError(f"mock: no page for {url}")
        title, text = self._pages[url]
        return PageContent(url=url, title=title, text=text, truncated=False)


def default_browser() -> BrowserAdapter:
    return PlaywrightBrowser()
