"""Headless-browser HTML fetcher (Playwright).

Some portals (notably SUUMO, and athome's price rendering) gate their pages
behind JavaScript / anti-bot checks: a plain HTTP request returns HTTP 200 but
the body is a challenge/interstitial page with no listings. Rendering the page
in a real browser defeats this.

This module is an *optional* dependency: Playwright is imported lazily so the
rest of the app keeps working without it. If Playwright (or its browser
binary) is unavailable, ``fetch_html`` returns ``None`` and callers fall back
to their normal HTTP path.

Install:
    pip install ".[browser]"
    python -m playwright install --with-deps chromium
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# Light stealth: hide the most obvious headless/automation signals.
_STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'languages', {get: () => ['ja-JP', 'ja', 'en-US', 'en']});
Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
window.chrome = window.chrome || {runtime: {}};
"""

# Module-level flag so we only warn once about a missing dependency.
_unavailable_logged = False


def playwright_available() -> bool:
    """True if the Playwright Python package is importable."""
    try:
        import playwright.async_api  # noqa: F401

        return True
    except Exception:
        return False


async def fetch_html(
    url: str,
    *,
    wait_selector: str | None = None,
    wait_for_text: str | None = None,
    wait_ms: int = 1500,
    timeout_ms: int = 30000,
    user_agent: str = _DEFAULT_UA,
    proxy: str = "",
) -> str | None:
    """Render ``url`` in headless Chromium and return the HTML.

    Returns ``None`` (never raises) if Playwright is unavailable or the page
    could not be rendered, so callers can fall back gracefully.

    Parameters
    ----------
    wait_selector :
        If given, wait for this CSS selector to appear before reading content.
    wait_for_text :
        If given, poll the page content until this substring appears (used to
        wait out JS anti-bot challenges that reload into the real page, e.g.
        athome's Imperva "認証中" gate → wait for "bukkenList").
    wait_ms :
        Extra settle time after load (lazy content).
    proxy :
        Optional proxy URL (e.g. residential proxy) to bypass datacenter-IP
        blocks.
    """
    global _unavailable_logged

    try:
        from playwright.async_api import async_playwright
    except Exception:
        if not _unavailable_logged:
            logger.warning(
                "Playwright is not installed; browser fallback disabled. "
                'Install with: pip install ".[browser]" '
                "&& python -m playwright install --with-deps chromium"
            )
            _unavailable_logged = True
        return None

    launch_kwargs: dict = {
        "headless": True,
        "args": [
            "--no-sandbox",
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
        ],
    }
    if proxy:
        launch_kwargs["proxy"] = {"server": proxy}

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(**launch_kwargs)
            try:
                context = await browser.new_context(
                    user_agent=user_agent,
                    locale="ja-JP",
                    viewport={"width": 1366, "height": 900},
                    extra_http_headers={
                        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
                    },
                )
                await context.add_init_script(_STEALTH_JS)
                page = await context.new_page()
                await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                if wait_selector:
                    try:
                        await page.wait_for_selector(wait_selector, timeout=timeout_ms)
                    except Exception:
                        pass
                if wait_for_text:
                    await _poll_for_text(page, wait_for_text, timeout_ms)
                if wait_ms:
                    await page.wait_for_timeout(wait_ms)
                return await page.content()
            finally:
                await browser.close()
    except Exception as exc:  # noqa: BLE001 - degrade gracefully
        logger.warning("Browser fetch failed for %s: %s", url, exc)
        return None


async def _poll_for_text(page, text: str, timeout_ms: int) -> None:
    """Poll page content until ``text`` appears (anti-bot reload), best-effort."""
    import time

    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        try:
            if text in await page.content():
                return
        except Exception:
            pass
        await page.wait_for_timeout(1000)
