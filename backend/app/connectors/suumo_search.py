"""SUUMO area search connector.

Fetches property listings from SUUMO's search results page for a given area.
Parses listing cards to extract basic property info without visiting each
individual property page (much faster).

Supported search modes:
1. By station name (e.g. 塚口) → searches chuko mansion listings
2. By city (e.g. 尼崎市) → searches by city code
3. By direct SUUMO search URL
"""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import quote

import httpx

from app.connectors.base import BaseConnector, ConnectorResult

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}

# City code mapping for SUUMO search URLs (兵庫県)
CITY_CODES: dict[str, str] = {
    "尼崎市": "sc_amagasaki",
    "西宮市": "sc_nishinomiya",
    "神戸市": "sc_kobe",
    "芦屋市": "sc_ashiya",
    "伊丹市": "sc_itami",
    "宝塚市": "sc_takarazuka",
    "川西市": "sc_kawanishi",
}

# Station name → SUUMO search keyword mapping
STATION_SEARCH_AREAS: dict[str, str] = {
    "塚口": "sc_amagasaki",
    "武庫之荘": "sc_amagasaki",
    "立花": "sc_amagasaki",
    "尼崎": "sc_amagasaki",
    "園田": "sc_amagasaki",
    "西宮北口": "sc_nishinomiya",
    "夙川": "sc_nishinomiya",
    "甲子園": "sc_nishinomiya",
    "三宮": "sc_kobe",
    "六甲道": "sc_kobe",
    "住吉": "sc_kobe",
    "芦屋": "sc_ashiya",
    "伊丹": "sc_itami",
}


class SuumoSearchConnector(BaseConnector):
    """Search SUUMO for property listings in a given area."""

    @property
    def name(self) -> str:
        return "SUUMO物件検索"

    async def fetch(
        self,
        station_name: str = "",
        city_name: str = "",
        search_url: str = "",
        max_pages: int = 2,
        **kwargs: Any,
    ) -> ConnectorResult:
        """Fetch property listings from SUUMO.

        Parameters
        ----------
        station_name : str
            Station name to search near (e.g. "塚口")
        city_name : str
            City name (e.g. "尼崎市")
        search_url : str
            Direct SUUMO search URL (overrides station/city)
        max_pages : int
            Maximum number of pages to fetch (default 2, ~40 listings)
        """
        # Determine search URL
        if search_url:
            base_url = search_url
        elif station_name and station_name in STATION_SEARCH_AREAS:
            area_code = STATION_SEARCH_AREAS[station_name]
            base_url = f"https://suumo.jp/ms/chuko/hyogo/{area_code}/"
        elif city_name and city_name in CITY_CODES:
            area_code = CITY_CODES[city_name]
            base_url = f"https://suumo.jp/ms/chuko/hyogo/{area_code}/"
        else:
            # Fallback: keyword search
            keyword = station_name or city_name
            if not keyword:
                return ConnectorResult(
                    success=False,
                    source=self.name,
                    errors=["検索条件を指定してください (station_name or city_name)"],
                )
            base_url = f"https://suumo.jp/ms/chuko/hyogo/sc_amagasaki/?rn={quote(keyword)}"

        all_listings: list[dict[str, Any]] = []
        errors: list[str] = []

        try:
            async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
                for page in range(1, max_pages + 1):
                    url = base_url if page == 1 else f"{base_url}?page={page}"
                    logger.info("Fetching SUUMO page %d: %s", page, url)

                    resp = await client.get(url, headers=HEADERS)
                    if resp.status_code != 200:
                        errors.append(f"Page {page}: HTTP {resp.status_code}")
                        break

                    listings = _parse_listing_page(resp.text)
                    if not listings:
                        break  # No more results

                    all_listings.extend(listings)

        except Exception as e:
            logger.error("SUUMO search error: %s", e)
            return ConnectorResult(
                success=False,
                source=self.name,
                errors=[f"SUUMO検索エラー: {str(e)}"],
            )

        return ConnectorResult(
            success=True,
            source=self.name,
            data={
                "search_url": base_url,
                "total_found": len(all_listings),
                "listings": all_listings,
            },
            errors=errors,
        )


def _parse_listing_page(html: str) -> list[dict[str, Any]]:
    """Parse a SUUMO search results page and extract listing cards.

    SUUMO listing pages contain property cards with structured info.
    We parse the full page text and extract repeating patterns.
    """
    listings: list[dict[str, Any]] = []

    # Extract individual property links
    # Pattern: /ms/chuko/PREFECTURE/CITY/nc_DIGITS/
    detail_links = re.findall(
        r'href="(https?://suumo\.jp/ms/chuko/[^"]*nc_\d+/[^"]*)"', html
    )
    if not detail_links:
        # Try relative links
        detail_links = [
            f"https://suumo.jp{link}"
            for link in re.findall(r'href="(/ms/chuko/[^"]*nc_\d+/[^"]*)"', html)
        ]

    # Deduplicate
    seen_urls: set[str] = set()
    unique_links: list[str] = []
    for link in detail_links:
        # Normalize URL
        clean = link.split("?")[0]
        if clean not in seen_urls:
            seen_urls.add(clean)
            unique_links.append(clean)

    # Try to parse property cards from the HTML
    # SUUMO uses various div structures; we'll parse text blocks between property links
    # Each listing card typically contains: name, price, station/access, area, layout, age

    # Strategy: split the HTML by property detail links, parse each chunk
    # If that fails, fall back to parsing the full text for repeating patterns

    # First attempt: parse structured data from repeated HTML patterns
    # Look for property name patterns in the raw HTML
    card_blocks = _split_into_cards(html, unique_links)

    for i, (url, card_html) in enumerate(card_blocks):
        listing = _parse_card(card_html, url)
        if listing:
            listings.append(listing)

    # If card parsing yielded nothing, try text-based extraction
    if not listings and unique_links:
        for url in unique_links[:20]:  # Max 20
            listings.append({
                "url": url,
                "name": f"物件 {len(listings) + 1}",
                "parse_method": "link_only",
            })

    return listings


def _split_into_cards(html: str, urls: list[str]) -> list[tuple[str, str]]:
    """Split HTML into chunks, one per property listing."""
    cards: list[tuple[str, str]] = []

    # Find positions of each URL in the HTML
    positions: list[tuple[int, str]] = []
    for url in urls:
        # Search for the URL or its relative form
        rel_url = url.replace("https://suumo.jp", "")
        pos = html.find(rel_url)
        if pos == -1:
            pos = html.find(url)
        if pos >= 0:
            positions.append((pos, url))

    positions.sort(key=lambda x: x[0])

    # Extract chunks between consecutive URLs (with some look-back)
    for i, (pos, url) in enumerate(positions):
        start = max(0, pos - 2000)  # Look back for card start
        if i + 1 < len(positions):
            end = positions[i + 1][0]
        else:
            end = min(pos + 3000, len(html))
        cards.append((url, html[start:end]))

    return cards


def _parse_card(card_html: str, url: str) -> dict[str, Any] | None:
    """Parse a single property card chunk."""
    text = _strip_tags(card_html)
    info: dict[str, Any] = {"url": url, "parse_method": "card"}

    # Property name: look for text near the URL or in heading-like elements
    # Try to find the property/mansion name
    m = re.search(r'class="[^"]*property[_-]?name[^"]*"[^>]*>([^<]+)', card_html, re.IGNORECASE)
    if not m:
        m = re.search(r'<h[23][^>]*>([^<]{3,40})</h[23]>', card_html)
    if not m:
        # Try from text: first substantial text before price
        _name_re = (
            r'([ぁ-んァ-ヶ一-龠Ａ-Ｚａ-ｚ\w]{2,30}'
            r'(?:マンション|レジデンス|ハウス|タワー|コート|パーク'
            r'|プラウド|グラン|ルネ|ライオンズ|サーパス|エスリード'
            r'|ワコーレ|アドリーム|ジオ|ブランズ))'
        )
        m = re.search(_name_re, text)
    if m:
        info["name"] = m.group(1).strip()

    # Price
    m = re.search(r"([\d,]+)\s*万円", text)
    if m:
        info["price_jpy"] = int(m.group(1).replace(",", "")) * 10_000
        info["price_text"] = m.group(0)

    # Layout
    m = re.search(r"(\d[LDKSR]{1,4})", text, re.IGNORECASE)
    if m:
        info["layout"] = m.group(1).upper()

    # Area
    m = re.search(r"([\d.]+)\s*[㎡m²]", text)
    if m:
        info["floor_area_sqm"] = float(m.group(1))

    # Station / walking
    m = re.search(r"「?([^」\s]{2,8})」?駅", text)
    if m:
        info["station_name"] = m.group(1)
    m = re.search(r"徒歩\s*(\d+)\s*分", text)
    if m:
        info["walking_minutes"] = int(m.group(1))

    # Built year
    m = re.search(r"築(\d+)年", text)
    if m:
        info["age_years"] = int(m.group(1))
    m = re.search(r"(\d{4})年\d{0,2}月?築", text)
    if m:
        info["built_year"] = int(m.group(1))

    # Floor
    m = re.search(r"(\d+)階", text)
    if m:
        info["floor"] = m.group(0)

    # Only return if we got at least a price or name
    if "price_jpy" in info or "name" in info:
        return info

    return None


def _strip_tags(html: str) -> str:
    """Remove HTML tags, collapse whitespace."""
    text = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()
