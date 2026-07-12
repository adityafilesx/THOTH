import pytest

from thoth_daemon.browser.browser_adapter import MockBrowser, PlaywrightBrowser
from thoth_daemon.schemas import ResourceScope, RiskLevel, ToolInvocation
from thoth_daemon.tools.browser_tools import BrowserRead, register_browser_tools
from thoth_daemon.tools.registry import ToolRegistry

PAGES = {"https://docs.python.org/3/": ("Python docs", "Welcome to Python")}


async def test_browser_read_returns_text() -> None:
    tool = BrowserRead(MockBrowser(PAGES))
    out = await tool.run(tool.input_model(url="https://docs.python.org/3/"), dry_run=False)
    assert out.title == "Python docs" and "Welcome" in out.text


async def test_browser_read_dry_run_no_navigation() -> None:
    tool = BrowserRead(MockBrowser({}))  # empty; would error if it navigated
    out = await tool.run(tool.input_model(url="https://x.example/"), dry_run=True)
    assert out.text == "[dry-run]"


async def test_browser_read_rejects_non_http_scheme() -> None:
    tool = BrowserRead(MockBrowser(PAGES))
    with pytest.raises(ValueError):
        await tool.run(tool.input_model(url="file:///etc/hosts"), dry_run=False)


def test_requested_scope_is_the_host() -> None:
    tool = BrowserRead(MockBrowser())
    assert tool.requested_scope(tool.input_model(url="https://docs.python.org/3/")).domains == [
        "docs.python.org"
    ]


def _inv(url: str) -> ToolInvocation:
    return ToolInvocation(
        task_id="t",
        step_id="s",
        tool_name="browser_read",
        arguments={"url": url},
        effective_risk=RiskLevel.R1,
    )


async def test_backstop_refuses_ungranted_domain() -> None:
    reg = ToolRegistry()
    register_browser_tools(reg, adapter=MockBrowser(PAGES))
    result = await reg.execute(
        _inv("https://evil.example/"), ResourceScope(domains=["docs.python.org"])
    )
    assert not result.ok and "scope violation" in (result.error or "")


async def test_backstop_allows_granted_domain_text_masked() -> None:
    reg = ToolRegistry()
    register_browser_tools(reg, adapter=MockBrowser(PAGES))
    result = await reg.execute(
        _inv("https://docs.python.org/3/"), ResourceScope(domains=["docs.python.org"])
    )
    assert result.ok
    assert result.output is not None and result.output["text"] == "[REDACTED]"  # web text masked


async def test_real_playwright_reads_data_url() -> None:
    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            b = await p.chromium.launch(headless=True)
            await b.close()
    except Exception as exc:
        pytest.skip(f"chromium not launchable: {exc}")

    pc = await PlaywrightBrowser().fetch(
        "data:text/html,<title>T</title><body><h1>hello thoth</h1></body>", 15.0
    )
    assert "hello thoth" in pc.text
