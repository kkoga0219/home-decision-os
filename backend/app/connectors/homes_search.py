"""LIFULL HOME'S search connector.

Fetches used-mansion listings from homes.co.jp.
HTML structure (confirmed 2026-03):
  - div.mod-listKks            → each listing card
  - a.prg-detailLink span.bukkenName → building name
  - th.price + td.price span.num     → price (万円)
  - th.address + td.address          → address
  - th.traffic + td.traffic          → station/access
  - th.space + td.space              → area + layout
  - a.prg-detailLink[href]           → detail URL
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

# Prefecture slug mapping for HOME'S URLs
_PREF_SLUGS: dict[str, str] = {
    "北海道": "hokkaido", "宮城県": "miyagi",
    "東京都": "tokyo", "神奈川県": "kanagawa",
    "埼玉県": "saitama", "千葉県": "chiba",
    "愛知県": "aichi", "大阪府": "osaka",
    "京都府": "kyoto", "兵庫県": "hyogo",
    "福岡県": "fukuoka", "広島県": "hiroshima",
    "奈良県": "nara", "滋賀県": "shiga",
}

# City → HOME'S URL slug
_CITY_SLUGS: dict[str, tuple[str, str]] = {
    "尼崎市": ("hyogo", "amagasaki-city"),
    "西宮市": ("hyogo", "nishinomiya-city"),
    "神戸市": ("hyogo", "kobe-city"),
    "芦屋市": ("hyogo", "ashiya-city"),
    "伊丹市": ("hyogo", "itami-city"),
    "宝塚市": ("hyogo", "takarazuka-city"),
    "大阪市": ("osaka", "osaka-city"),
    "豊中市": ("osaka", "toyonaka-city"),
    "吹田市": ("osaka", "suita-city"),
    "堺市": ("osaka", "sakai-city"),
    "茨木市": ("osaka", "ibaraki-city"),
    "高槻市": ("osaka", "takatsuki-city"),
    "京都市": ("kyoto", "kyoto-city"),
    "横浜市": ("kanagawa", "yokohama-city"),
    "川崎市": ("kanagawa", "kawasaki-city"),
    "名古屋市": ("aichi", "nagoya-city"),
    "福岡市": ("fukuoka", "fukuoka-city"),
    "札幌市": ("hokkaido", "sapporo-city"),
    "仙台市": ("miyagi", "sendai-city"),
}


class HomesSearchConnector(BaseConnector):
    """Search LIFULL HOME'S for used mansion listings."""

    @property
    def name(self) -> str:
        return "LIFULL HOME'S"

    async def fetch(
        self,
        station_name: str = "",
        city_name: str = "",
        prefecture: str = "",
        max_pages: int = 2,
        **kwargs: Any,
    ) -> ConnectorResult:
        """Fetch listings from HOME'S."""
        base_url = self._resolve_url(
            station_name=station_name,
            city_name=city_name,
            prefecture=prefecture,
        )
        if not base_url:
            return ConnectorResult(
                success=False,
                source=self.name,
                errors=["HOME'S: 検索条件不足"],
            )

        all_listings: list[dict[str, Any]] = []
        errors: list[str] = []

        try:
            async with httpx.AsyncClient(
                timeout=20, follow_redirects=True,
            ) as client:
                for page in range(1, max_pages + 1):
                    if page == 1:
                        url = base_url
                    else:
                        sep = "&" if "?" in base_url else "?"
                        url = f"{base_url}{sep}page={page}"

                    logger.info(
                        "Fetching HOME'S page %d: %s", page, url,
                    )
                    resp = await client.get(
                        url, headers=HEADERS,
                    )
                    if resp.status_code != 200:
                        errors.append(
                            f"HOME'S page {page}: "
                            f"HTTP {resp.status_code}"
                        )
                        break

                    listings = _parse_homes_page(resp.text)
                    if not listings:
                        break
                    all_listings.extend(listings)

        except Exception as e:
            logger.error("HOME'S search error: %s", e)
            return ConnectorResult(
                success=False,
                source=self.name,
                errors=[f"HOME'S検索エラー: {e!s}"],
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

    @staticmethod
    def _resolve_url(
        station_name: str = "",
        city_name: str = "",
        prefecture: str = "",
    ) -> str | None:
        # City lookup
        if city_name and city_name in _CITY_SLUGS:
            pref, city = _CITY_SLUGS[city_name]
            return (
                f"https://www.homes.co.jp/mansion/chuko/"
                f"{pref}/{city}/list/"
            )

        # Prefecture + keyword
        pref_slug = _PREF_SLUGS.get(prefecture, "")
        keyword = station_name or city_name
        if pref_slug and keyword:
            return (
                f"https://www.homes.co.jp/mansion/chuko/"
                f"{pref_slug}/list/"
                f"?keyword={quote(keyword)}"
            )
        if pref_slug:
            return (
                f"https://www.homes.co.jp/mansion/chuko/"
                f"{pref_slug}/list/"
            )
        if keyword:
            return (
                f"https://www.homes.co.jp/mansion/chuko/"
                f"list/?keyword={quote(keyword)}"
            )
        return None


# -------------------------------------------------------------------
# HTML parsing
# -------------------------------------------------------------------

def _parse_homes_page(html: str) -> list[dict[str, Any]]:
    """Parse HOME'S listing page."""
    listings: list[dict[str, Any]] = []

    # Split by listing card boundaries
    chunks = re.split(
        r'<div\s+class="[^"]*mod-listKks[^"]*"', html,
    )

    for chunk in chunks[1:]:
        listing = _parse_homes_card(chunk)
        if listing:
            listings.append(listing)

    return listings


def _parse_homes_card(chunk: str) -> dict[str, Any] | None:
    """Parse a single HOME'S listing card."""
    info: dict[str, Any] = {
        "source": "homes",
        "parse_method": "structured",
    }

    # Building name: span.bukkenName
    m = re.search(
        r'class="bukkenName"[^>]*>([^<]+)<', chunk,
    )
    if m:
        info["name"] = m.group(1).strip()

    # Detail URL: a.prg-detailLink or /mansion/b-XXXXX/
    m = re.search(
        r'href="((?:https?://www\.homes\.co\.jp)?'
        r'/mansion/b-[^"]+)"',
        chunk,
    )
    if m:
        url = m.group(1)
        if not url.startswith("http"):
            url = f"https://www.homes.co.jp{url}"
        info["url"] = url

    # Price: td.price span.num → N万円
    m = re.search(
        r'class="price"[^>]*>.*?'
        r'class="num"[^>]*>([\d,]+)</span>\s*万円',
        chunk,
        re.DOTALL,
    )
    if m:
        try:
            info["price_jpy"] = (
                int(m.group(1).replace(",", "")) * 10_000
            )
            info["price_text"] = f"{m.group(1)}万円"
        except ValueError:
            pass

    # Address: td.address
    m = re.search(
        r'class="address"[^>]*>([^<]+)<', chunk,
    )
    if m:
        info["address"] = m.group(1).strip()

    # Station/access: td.traffic
    m = re.search(
        r'class="traffic"[^>]*>([^<]+)<', chunk,
    )
    if m:
        access = m.group(1).strip()
        info["access"] = access
        # Parse station name
        sm = re.search(r"(\S+)駅", access)
        if sm:
            info["station_name"] = sm.group(1)
        # Walking minutes
        sm = re.search(r"徒歩(\d+)分", access)
        if sm:
            info["walking_minutes"] = int(sm.group(1))
        # Line name
        sm = re.search(r"^(\S+線)\s", access)
        if sm:
            info["line_name"] = sm.group(1)

    # Floor area + layout: td.space
    m = re.search(
        r'class="space"[^>]*>(.*?)</td>',
        chunk,
        re.DOTALL,
    )
    if m:
        space_html = _strip_tags(m.group(1))
        # Area: 70.81m²
        am = re.search(r"([\d.]+)\s*m", space_html)
        if am:
            info["floor_area_sqm"] = float(am.group(1))
        # Layout: 4DK, 3LDK etc.
        lm = re.search(r"(\d[LDKSR]{1,4})", space_html)
        if lm:
            info["layout"] = lm.group(1)

    if "price_jpy" in info or "name" in info:
        return info
    return None


def _strip_tags(html: str) -> str:
    """Remove HTML tags."""
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()
