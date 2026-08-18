from unittest.mock import AsyncMock, MagicMock

import pytest

from omnimac_daemon.inference.base import InferenceResult
from omnimac_daemon.schemas import RiskLevel
from omnimac_daemon.tools.research_tools import BrowserResearchAndSave, BrowserResearchAndSaveIn


@pytest.fixture
def mock_browser():
    browser = AsyncMock()
    page_content = MagicMock()
    page_content.title = "Test Page"
    page_content.text = "This is a test web page content."
    page_content.truncated = False
    browser.fetch.return_value = page_content
    return browser


@pytest.fixture
def mock_inference():
    inference = AsyncMock()
    res = InferenceResult(text="Summarized content.", model_id="test-model")
    inference.generate.return_value = res
    return inference


@pytest.mark.asyncio
async def test_browser_research_and_save(mock_browser, mock_inference, tmp_path):
    dest = tmp_path / "summary.md"
    tool = BrowserResearchAndSave(inference_provider=mock_inference, browser_adapter=mock_browser)

    assert tool.default_risk == RiskLevel.R2

    args = BrowserResearchAndSaveIn(url="https://example.com/test", topic="Testing", dest_path=str(dest))

    scope = tool.requested_scope(args)
    assert "example.com" in scope.domains
    assert str(dest) in scope.paths

    res = await tool.run(args, dry_run=False)

    assert res.written is True
    assert res.dest_path == str(dest)

    # Verify file content
    assert dest.read_text(encoding="utf-8") == "Summarized content."

    # Verify browser was called
    mock_browser.fetch.assert_called_once_with("https://example.com/test", 30.0)

    # Verify inference was called
    req = mock_inference.generate.call_args[0][0]
    assert "Test Page" in req.prompt
    assert "This is a test web page content" in req.prompt
    assert "Testing" in req.prompt


@pytest.mark.asyncio
async def test_browser_research_and_save_dry_run(mock_browser, mock_inference, tmp_path):
    dest = tmp_path / "summary.md"
    tool = BrowserResearchAndSave(inference_provider=mock_inference, browser_adapter=mock_browser)

    args = BrowserResearchAndSaveIn(url="https://example.com/test", topic="Testing", dest_path=str(dest))

    res = await tool.run(args, dry_run=True)

    assert res.written is False
    assert not dest.exists()
    mock_browser.fetch.assert_not_called()
    mock_inference.generate.assert_not_called()
