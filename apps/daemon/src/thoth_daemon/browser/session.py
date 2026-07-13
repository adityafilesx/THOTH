"""Stateful browser session for interaction tools (Phase 4 slice 4).

The read-only ``BrowserAdapter`` (browser_adapter.py) stays stateless; this
module adds a SESSION — one live page whose state persists across tool
calls — behind the swappable ``BrowserSession`` protocol.

Safety design:
- All page-derived text (titles, element text, values) is UNTRUSTED
  (WEB_UNTRUSTED). It is returned as plain data and scanned by the
  injection guard downstream; nothing in this layer interprets it.
- Form submission is TWO-PHASE: ``prepare_submission`` captures exactly
  what would be submitted (action URL + full field map) WITHOUT
  submitting and returns a single-use submission id; ``submit`` refuses
  unknown ids, consumed ids, and submissions whose form state changed
  since preparation (recapture + compare). There is no one-shot submit.
- ``PlaywrightSession`` is the real implementation (headless Chromium,
  lazy imports). Its interactive paths are exercised offline against a
  file:// fixture where Playwright is installed; anything beyond that is
  pending live verification. ``MockBrowserSession`` is a deterministic
  in-memory DOM used by unit tests.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol
from uuid import uuid4


@dataclass(frozen=True)
class PageState:
    url: str
    title: str
    text: str
    selectors: tuple[str, ...]


@dataclass(frozen=True)
class ElementInfo:
    selector: str
    tag: str
    text: str
    value: str | None


@dataclass(frozen=True)
class PreparedSubmission:
    submission_id: str
    form_selector: str
    action_url: str
    fields: dict[str, str]


class SubmissionError(Exception):
    """Unknown, consumed, or stale (form changed) submission."""


class BrowserSession(Protocol):
    async def open(self, url: str, timeout_s: float) -> PageState: ...
    async def state(self) -> PageState: ...
    async def find(self, selector: str) -> list[ElementInfo]: ...
    async def click(self, selector: str, timeout_s: float) -> PageState: ...
    async def fill(self, selector: str, value: str) -> PageState: ...
    async def select(self, selector: str, option: str) -> PageState: ...
    async def download(self, url: str, dest_dir: str, timeout_s: float) -> str: ...
    async def screenshot(self, dest_path: str) -> str: ...
    async def prepare_submission(self, form_selector: str) -> PreparedSubmission: ...
    async def submit(self, submission_id: str, timeout_s: float) -> PageState: ...


class _SubmissionLedger:
    """Single-use prepared submissions with staleness detection."""

    def __init__(self) -> None:
        self._prepared: dict[str, PreparedSubmission] = {}
        self._consumed: set[str] = set()

    def add(self, prepared: PreparedSubmission) -> None:
        self._prepared[prepared.submission_id] = prepared

    def take(self, submission_id: str, current_fields: dict[str, str]) -> PreparedSubmission:
        if submission_id in self._consumed:
            raise SubmissionError("submission already consumed (single-use)")
        prepared = self._prepared.get(submission_id)
        if prepared is None:
            raise SubmissionError("unknown submission id; call browser_prepare_submission first")
        if current_fields != prepared.fields:
            raise SubmissionError("form state changed since preparation; re-prepare and re-approve")
        self._consumed.add(submission_id)
        return prepared


# ---------------------------------------------------------------------- mock


@dataclass
class MockElement:
    tag: str = "div"
    text: str = ""
    value: str | None = None
    options: list[str] = field(default_factory=list)
    navigates_to: str | None = None  # for links/buttons
    form: str | None = None  # form selector this element belongs to
    name: str | None = None  # form field name


@dataclass
class MockPage:
    title: str
    text: str
    elements: dict[str, MockElement] = field(default_factory=dict)
    forms: dict[str, str] = field(default_factory=dict)  # form selector -> action url


class MockBrowserSession:
    """Deterministic in-memory DOM. MOCK — used by unit tests."""

    def __init__(self, pages: dict[str, MockPage]) -> None:
        self._pages = pages
        self._url: str | None = None
        self._ledger = _SubmissionLedger()
        self.submitted: list[PreparedSubmission] = []
        self.downloads: list[tuple[str, str]] = []
        self.screenshots: list[str] = []

    # -- helpers -----------------------------------------------------------
    def _page(self) -> MockPage:
        if self._url is None:
            raise RuntimeError("no page open")
        return self._pages[self._url]

    def _state(self) -> PageState:
        page = self._page()
        assert self._url is not None
        return PageState(
            url=self._url,
            title=page.title,
            text=page.text,
            selectors=tuple(page.elements.keys()),
        )

    def _form_fields(self, form_selector: str) -> dict[str, str]:
        page = self._page()
        return {
            el.name or sel: el.value or ""
            for sel, el in page.elements.items()
            if el.form == form_selector
        }

    # -- protocol ------------------------------------------------------------
    async def open(self, url: str, timeout_s: float) -> PageState:
        if url not in self._pages:
            raise RuntimeError(f"mock: no page for {url}")
        self._url = url
        return self._state()

    async def state(self) -> PageState:
        return self._state()

    async def find(self, selector: str) -> list[ElementInfo]:
        page = self._page()
        out = []
        for sel, el in page.elements.items():
            if sel == selector or selector in el.text:
                out.append(ElementInfo(selector=sel, tag=el.tag, text=el.text, value=el.value))
        return out

    async def click(self, selector: str, timeout_s: float) -> PageState:
        el = self._page().elements.get(selector)
        if el is None:
            raise RuntimeError(f"mock: no element {selector}")
        if el.navigates_to:
            self._url = el.navigates_to
        return self._state()

    async def fill(self, selector: str, value: str) -> PageState:
        el = self._page().elements.get(selector)
        if el is None:
            raise RuntimeError(f"mock: no element {selector}")
        el.value = value
        return self._state()

    async def select(self, selector: str, option: str) -> PageState:
        el = self._page().elements.get(selector)
        if el is None:
            raise RuntimeError(f"mock: no element {selector}")
        if option not in el.options:
            raise RuntimeError(f"mock: option {option!r} not in {el.options}")
        el.value = option
        return self._state()

    async def download(self, url: str, dest_dir: str, timeout_s: float) -> str:
        path = f"{dest_dir}/mock-download.bin"
        self.downloads.append((url, path))
        return path

    async def screenshot(self, dest_path: str) -> str:
        self.screenshots.append(dest_path)
        return dest_path

    async def prepare_submission(self, form_selector: str) -> PreparedSubmission:
        page = self._page()
        if form_selector not in page.forms:
            raise RuntimeError(f"mock: no form {form_selector}")
        prepared = PreparedSubmission(
            submission_id=str(uuid4()),
            form_selector=form_selector,
            action_url=page.forms[form_selector],
            fields=self._form_fields(form_selector),
        )
        self._ledger.add(prepared)
        return prepared

    async def submit(self, submission_id: str, timeout_s: float) -> PageState:
        # Locate the prepared form to recapture current fields.
        prepared_meta = self._ledger._prepared.get(submission_id)
        current = (
            self._form_fields(prepared_meta.form_selector) if prepared_meta is not None else {}
        )
        prepared = self._ledger.take(submission_id, current)
        self.submitted.append(prepared)
        # Navigate to the form's action URL if it is a known page.
        if prepared.action_url in self._pages:
            self._url = prepared.action_url
        return self._state()


# ------------------------------------------------------------------ playwright


class PlaywrightSession:
    """Real stateful session over headless Chromium. Lazy start; the page
    persists across calls. Interaction beyond the file:// fixture tests is
    pending live verification."""

    def __init__(self) -> None:
        self._pw: Any = None
        self._browser: Any = None
        self._page: Any = None
        self._ledger = _SubmissionLedger()

    async def _ensure(self) -> Any:
        if self._page is None:
            from playwright.async_api import async_playwright

            self._pw = await async_playwright().start()
            self._browser = await self._pw.chromium.launch(headless=True)
            self._page = await self._browser.new_page()
        return self._page

    async def close(self) -> None:
        if self._browser is not None:
            await self._browser.close()
        if self._pw is not None:
            await self._pw.stop()
        self._pw = self._browser = self._page = None

    async def _snapshot(self) -> PageState:
        page = await self._ensure()
        title = await page.title()
        text = await page.inner_text("body")
        selectors = await page.eval_on_selector_all("[id]", "els => els.map(e => '#' + e.id)")
        return PageState(
            url=page.url, title=title, text=text[: 64 * 1024], selectors=tuple(selectors)
        )

    async def open(self, url: str, timeout_s: float) -> PageState:
        page = await self._ensure()
        await page.goto(url, wait_until="domcontentloaded", timeout=int(timeout_s * 1000))
        return await self._snapshot()

    async def state(self) -> PageState:
        return await self._snapshot()

    async def find(self, selector: str) -> list[ElementInfo]:
        page = await self._ensure()
        out: list[ElementInfo] = []
        for handle in await page.query_selector_all(selector):
            tag = await handle.evaluate("e => e.tagName.toLowerCase()")
            text = (await handle.inner_text()) if tag not in ("input", "select") else ""
            value = await handle.evaluate("e => 'value' in e ? e.value : null")
            out.append(ElementInfo(selector=selector, tag=tag, text=text, value=value))
        return out

    async def click(self, selector: str, timeout_s: float) -> PageState:
        page = await self._ensure()
        await page.click(selector, timeout=int(timeout_s * 1000))
        return await self._snapshot()

    async def fill(self, selector: str, value: str) -> PageState:
        page = await self._ensure()
        await page.fill(selector, value)
        return await self._snapshot()

    async def select(self, selector: str, option: str) -> PageState:
        page = await self._ensure()
        await page.select_option(selector, option)
        return await self._snapshot()

    async def download(self, url: str, dest_dir: str, timeout_s: float) -> str:
        page = await self._ensure()
        async with page.expect_download(timeout=int(timeout_s * 1000)) as info:
            await page.goto(url)
        download = await info.value
        path = f"{dest_dir}/{download.suggested_filename}"
        await download.save_as(path)
        return path

    async def screenshot(self, dest_path: str) -> str:
        page = await self._ensure()
        await page.screenshot(path=dest_path)
        return dest_path

    async def _capture_fields(self, form_selector: str) -> tuple[str, dict[str, str]]:
        page = await self._ensure()
        action = await page.eval_on_selector(form_selector, "f => f.action")
        fields = await page.eval_on_selector(
            form_selector,
            "f => Object.fromEntries([...f.elements].filter(e => e.name)"
            ".map(e => [e.name, e.value]))",
        )
        return str(action), dict(fields)

    async def prepare_submission(self, form_selector: str) -> PreparedSubmission:
        action, fields = await self._capture_fields(form_selector)
        prepared = PreparedSubmission(
            submission_id=str(uuid4()),
            form_selector=form_selector,
            action_url=action,
            fields=fields,
        )
        self._ledger.add(prepared)
        return prepared

    async def submit(self, submission_id: str, timeout_s: float) -> PageState:
        prepared_meta = self._ledger._prepared.get(submission_id)
        current: dict[str, str] = {}
        if prepared_meta is not None:
            _, current = await self._capture_fields(prepared_meta.form_selector)
        prepared = self._ledger.take(submission_id, current)
        page = await self._ensure()
        await page.eval_on_selector(prepared.form_selector, "f => f.submit()")
        await page.wait_for_load_state("domcontentloaded", timeout=int(timeout_s * 1000))
        return await self._snapshot()


def default_browser_session() -> BrowserSession:
    return PlaywrightSession()
