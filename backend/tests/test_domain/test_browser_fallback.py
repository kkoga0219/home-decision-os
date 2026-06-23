"""Tests for the headless-browser fallback wiring (no real browser needed)."""

import asyncio

from app.connectors import browser_fetch
from app.connectors.suumo_search import _looks_like_challenge


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class TestChallengeDetector:
    def test_empty_is_challenge(self):
        assert _looks_like_challenge("")

    def test_no_listing_markup_is_challenge(self):
        assert _looks_like_challenge("<html><body>bot check</body></html>")

    def test_real_page_not_challenge(self):
        html = '<div class="property_unit"><dl><dt>販売価格</dt></dl></div>'
        assert not _looks_like_challenge(html)


class TestBrowserFetchGuard:
    def test_returns_none_when_playwright_missing(self, monkeypatch):
        """If Playwright import fails, fetch_html degrades to None, no raise."""

        real_import = __import__

        def fake_import(name, *args, **kwargs):
            if name.startswith("playwright"):
                raise ImportError("playwright not installed")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr("builtins.__import__", fake_import)
        result = _run(browser_fetch.fetch_html("https://example.com"))
        assert result is None

    def test_playwright_available_returns_bool(self):
        # Just ensure it never raises and returns a bool.
        assert isinstance(browser_fetch.playwright_available(), bool)
