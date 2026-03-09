"""URL preview connector.

Fetches metadata (title, description, OGP) from a property listing URL.
This is NOT a scraper — it only reads standard HTML meta tags that any
link previewer (Slack, Twitter, etc.) would read.

For SUUMO URLs, it also attempts to extract structured data from
the page title which typically follows a known format.
"""

from __future__ import annotations

import logging
import re
from typing import Any

import httpx

from app.connectors.base import BaseConnector, ConnectorResult

logger = logging.getLogger(__name__)

# User-Agent mimicking a standard browser link previewer
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; HomeDecisionOS/0.1; +https://github.com/home-decision-os)"
    ),
}


class URLPreviewConnector(BaseConnector):
    """Extracts metadata from a property listing URL."""

    @property
    def name(self) -> str:
        return "URL Preview"

    async def fetch(self, url: str, **kwargs: Any) -> ConnectorResult:
        """Fetch URL and extract metadata.

        Parameters
        ----------
        url : str
            Property listing URL (SUUMO, LIFULL HOME'S, etc.)
        """
        if not url:
            return ConnectorResult(success=False, source=self.name, errors=["URL is empty"])

        try:
            async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
                resp = await client.get(url, headers=HEADERS)
                resp.raise_for_status()
                html = resp.text
        except Exception as e:
            logger.error("URL fetch error: %s", e)
            return ConnectorResult(success=False, source=self.name, errors=[str(e)])

        meta = _extract_meta(html, url)
        return ConnectorResult(success=True, source=self.name, data=meta)


def _extract_meta(html: str, url: str) -> dict[str, Any]:
    """Extract OGP and basic meta tags from HTML."""
    data: dict[str, Any] = {"url": url}

    # <title>
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.DOTALL | re.IGNORECASE)
    if m:
        data["title"] = _clean(m.group(1))

    # OGP tags
    for prop in ("og:title", "og:description", "og:image", "og:site_name"):
        m = re.search(
            rf'<meta\s+(?:property|name)="{prop}"\s+content="([^"]*)"',
            html,
            re.IGNORECASE,
        )
        if not m:
            m = re.search(
                rf'<meta\s+content="([^"]*)"\s+(?:property|name)="{prop}"',
                html,
                re.IGNORECASE,
            )
        if m:
            key = prop.replace("og:", "")
            data[key] = _clean(m.group(1))

    # meta description
    m = re.search(
        r'<meta\s+name="description"\s+content="([^"]*)"', html, re.IGNORECASE
    )
    if m and "description" not in data:
        data["description"] = _clean(m.group(1))

    # SUUMO-specific: try to parse price/area from title
    if "suumo.jp" in url:
        data.update(_parse_suumo_hints(data.get("title", ""), data.get("description", "")))

    return data


def _parse_suumo_hints(title: str, description: str) -> dict[str, Any]:
    """Attempt to extract property hints from SUUMO page title/description.

    SUUMO titles often follow patterns like:
    "物件名 | 3LDK | 65.5㎡ | 3,500万円 | 兵庫県尼崎市..."
    """
    hints: dict[str, Any] = {}
    combined = f"{title} {description}"

    # Price: 3,500万円 or 3500万円
    m = re.search(r"([\d,]+)\s*万円", combined)
    if m:
        price_man = int(m.group(1).replace(",", ""))
        hints["hint_price_jpy"] = price_man * 10_000

    # Area: 65.5㎡ or 65.50m²
    m = re.search(r"([\d.]+)\s*[㎡m²]", combined)
    if m:
        hints["hint_floor_area_sqm"] = float(m.group(1))

    # Layout: 3LDK, 2LDK etc.
    m = re.search(r"\b(\d[LDKS]{1,4})\b", combined, re.IGNORECASE)
    if m:
        hints["hint_layout"] = m.group(1).upper()

    # Walking minutes: 徒歩5分
    m = re.search(r"徒歩\s*(\d+)\s*分", combined)
    if m:
        hints["hint_walking_minutes"] = int(m.group(1))

    # Station: ○○駅
    m = re.search(r"「?([^」\s]{2,6})駅」?", combined)
    if m:
        hints["hint_station_name"] = m.group(1)

    return hints


def _clean(s: str) -> str:
    """Clean HTML entities and whitespace."""
    s = re.sub(r"&amp;", "&", s)
    s = re.sub(r"&lt;", "<", s)
    s = re.sub(r"&gt;", ">", s)
    s = re.sub(r"&quot;", '"', s)
    s = re.sub(r"&#\d+;", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s
