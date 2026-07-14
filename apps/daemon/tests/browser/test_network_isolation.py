"""Offline mode blocks external browser I/O before any adapter is called."""

import pytest

from thoth_daemon.browser.browser_adapter import PageContent
from thoth_daemon.browser.session import PageState
from thoth_daemon.inference import IsolationViolation
from thoth_daemon.tools.browser_interaction_tools import BrowserOpen, OpenIn
from thoth_daemon.tools.browser_tools import BrowserRead, BrowserReadIn


class _RecordingBrowser:
    def __init__(self) -> None:
        self.urls: list[str] = []

    async def fetch(self, url: str, timeout_s: float) -> PageContent:
        del timeout_s
        self.urls.append(url)
        return PageContent(url=url, title="unexpected", text="unexpected", truncated=False)


class _RecordingSession:
    def __init__(self) -> None:
        self.urls: list[str] = []

    async def open(self, url: str, timeout_s: float) -> PageState:
        del timeout_s
        self.urls.append(url)
        return PageState(url=url, title="unexpected", text="unexpected", selectors=())


async def test_offline_browser_read_rejects_external_url_before_adapter() -> None:
    adapter = _RecordingBrowser()
    tool = BrowserRead(adapter, network_isolation=True)

    with pytest.raises(IsolationViolation, match="not loopback"):
        await tool.run(BrowserReadIn(url="https://example.com"), dry_run=False)
    assert adapter.urls == []


async def test_offline_interactive_open_rejects_external_url_before_session() -> None:
    session = _RecordingSession()
    tool = BrowserOpen(session, network_isolation=True)  # type: ignore[arg-type]

    with pytest.raises(IsolationViolation, match="not loopback"):
        await tool.run(OpenIn(url="https://example.com"), dry_run=False)
    assert session.urls == []


async def test_offline_browser_allows_loopback_for_local_services() -> None:
    adapter = _RecordingBrowser()
    tool = BrowserRead(adapter, network_isolation=True)

    result = await tool.run(BrowserReadIn(url="http://127.0.0.1:7710/health"), dry_run=False)
    assert result.url == "http://127.0.0.1:7710/health"
    assert adapter.urls == ["http://127.0.0.1:7710/health"]
