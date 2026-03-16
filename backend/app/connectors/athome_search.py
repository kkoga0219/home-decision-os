"""athome.co.jp search connector.

Fetches used-mansion listings from athome.co.jp.
HTML structure (confirmed 2026-03):
  - div.card-box                   → each listing card
  - .title-wrap__title-text        → building name + floor + layout
  - span.property-price            → price (万円)
  - .property-detail-table__block  → label/value pairs
    - strong → label (交通, 所在地, 間取り, 築年月, 専有面積)
    - span   → value
  - a[href*="/mansion/"]           → detail URL
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

# City → athome URL slug
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
    "京都市": ("kyoto", "kyoto-city"),
    "横浜市": ("kanagawa", "yokohama-city"),
    "川崎市": ("kanagawa", "kawasaki-city"),
    "名古屋市": ("aichi", "nagoya-city"),
    "福岡市": ("fukuoka", "fukuoka-city"),
    "札幌市": ("hokkaido", "sapporo-city"),
    "仙台市": ("miyagi", "sendai-city"),
}

# Prefecture slugs for athome
_PREF_SLUGS: dict[str, str] = {
    "北海道": "hokkaido", "宮城県": "miyagi",
    "東京都": "tokyo", "神奈川県": "kanagawa",
    "埼玉県": "saitama", "千葉県": "chiba",
    "愛知県": "aichi", "大阪府": "osaka",
    "京都府": "kyoto", "兵庫県": "hyogo",
    "福岡県": "fukuoka", "広島県": "hiroshima",
    "奈良県": "nara", "滋賀県": "shiga",
}


class AthomeSearchConnector(BaseConnector):
    """Search athome.co.jp for used mansion listings."""

    @property
    def name(self) -> str:
        return "athome"

    async def fetch(
        self,
        station_name: str = "",
        city_name: str = "",
        prefecture: str = "",
        max_pages: int = 2,
        **kwargs: Any,
    ) -> ConnectorResult:
        """Fetch listings from athome."""
        base_url = self._resolve_url(
            station_name=station_name,
            city_name=city_name,
            prefecture=prefecture,
        )
        if not base_url:
            return ConnectorResult(
                success=False,
                source=self.name,
                errors=["athome: 検索条件不足"],
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
                        "Fetching athome page %d: %s", page, url,
                    )
                    resp = await client.get(
                        url, headers=HEADERS,
                    )
                    if resp.status_code != 200:
                        errors.append(
                            f"athome page {page}: "
                            f"HTTP {resp.status_code}"
                        )
                        break

                    listings = _parse_athome_page(resp.text)
                    if not listings:
                        break
                    all_listings.extend(listings)

        except Exception as e:
            logger.error("athome search error: %s", e)
            return ConnectorResult(
                success=False,
                source=self.name,
                errors=[f"athome検索エラー: {e!s}"],
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
        base = "https://www.athome.co.jp/mansion/chuko"

        # City lookup
        if city_name and city_name in _CITY_SLUGS:
            pref, city = _CITY_SLUGS[city_name]
            return f"{base}/{pref}/{city}/list/"

        # Prefecture + keyword
        pref_slug = _PREF_SLUGS.get(prefecture, "")
        keyword = station_name or city_name
        if pref_slug and keyword:
            return (
                f"{base}/{pref_slug}/list/"
                f"?keyword={quote(keyword)}"
            )
        if pref_slug:
            return f"{base}/{pref_slug}/list/"
        if keyword:
            return (
                f"{base}/list/"
                f"?keyword={quote(keyword)}"
            )
        return None


# -------------------------------------------------------------------
# HTML parsing
# -------------------------------------------------------------------

def _parse_athome_page(html: str) -> list[dict[str, Any]]:
    """Parse athome listing page."""
    listings: list[dict[str, Any]] = []

    # Split by card-box boundaries
    chunks = re.split(
        r'<div\s+class="card-box(?:\s|")', html,
    )

    for chunk in chunks[1:]:
        listing = _parse_athome_card(chunk)
        if listing:
            listings.append(listing)

    return listings


def _parse_athome_card(chunk: str) -> dict[str, Any] | None:
    """Parse a single athome listing card."""
    info: dict[str, Any] = {
        "source": "athome",
        "parse_method": "structured",
    }

    # Building name: .title-wrap__title-text
    m = re.search(
        r'class="title-wrap__title-text"[^>]*>(.*?)</div>',
        chunk,
        re.DOTALL,
    )
    if m:
        name = _strip_tags(m.group(1)).strip()
        if name:
            info["name"] = name

    # Price: span.property-price
    m = re.search(
        r'class="property-price"[^>]*>([\d,.]+)\s*万円',
        chunk,
    )
    if m:
        try:
            info["price_jpy"] = (
                int(m.group(1).replace(",", "")) * 10_000
            )
            info["price_text"] = f"{m.group(1)}万円"
        except ValueError:
            pass

    # Detail URL: a[href*="/mansion/"]
    m = re.search(
        r'href="((?:https?://www\.athome\.co\.jp)?'
        r'/mansion/\d+/?)"',
        chunk,
    )
    if m:
        url = m.group(1)
        if not url.startswith("http"):
            url = f"https://www.athome.co.jp{url}"
        info["url"] = url

    # Parse property-detail-table__block fields
    fields = _extract_detail_blocks(chunk)

    # 交通
    access = fields.get("交通", "")
    if access:
        info["access"] = access
        sm = re.search(r"「([^」]+)」\s*駅", access)
        if sm:
            info["station_name"] = sm.group(1)
        else:
            sm = re.search(r"(\S+)駅", access)
            if sm:
                info["station_name"] = sm.group(1)
        sm = re.search(r"徒歩(\d+)分", access)
        if sm:
            info["walking_minutes"] = int(sm.group(1))
        sm = re.search(r"^(\S+線)\s", access)
        if sm:
            info["line_name"] = sm.group(1)

    # 所在地
    addr = fields.get("所在地", "")
    if addr:
        info["address"] = addr

    # 間取り
    layout = fields.get("間取り", "")
    if layout:
        lm = re.search(r"(\d[LDKSR０-９]{1,4})", layout)
        if lm:
            info["layout"] = (
                lm.group(1)
                .replace("０", "0").replace("１", "1")
                .replace("２", "2").replace("３", "3")
                .replace("４", "4").replace("５", "5")
                .replace("Ｌ", "L").replace("Ｄ", "D")
                .replace("Ｋ", "K").replace("Ｓ", "S")
                .replace("Ｒ", "R")
            )

    # 専有面積
    area = fields.get("専有面積", "")
    if area:
        am = re.search(r"([\d.]+)\s*m", area)
        if am:
            info["floor_area_sqm"] = float(am.group(1))

    # 築年月
    built = fields.get("築年月", "")
    if built:
        info["built_date"] = built
        bm = re.search(r"(\d{4})年", built)
        if bm:
            info["built_year"] = int(bm.group(1))
        # 築N年 pattern
        bm = re.search(r"築(\d+)年", built)
        if bm and "built_year" not in info:
            from datetime import date
            info["age_years"] = int(bm.group(1))

    if "price_jpy" in info or "name" in info:
        return info
    return None


def _extract_detail_blocks(html: str) -> dict[str, str]:
    """Extract label-value pairs from athome detail blocks.

    Structure: .property-detail-table__block > strong + span
    """
    fields: dict[str, str] = {}

    for m in re.finditer(
        r'class="property-detail-table__block[^"]*"[^>]*>'
        r'.*?<strong[^>]*>(.*?)</strong>'
        r'.*?<span[^>]*>(.*?)</span>',
        html,
        re.DOTALL,
    ):
        label = _strip_tags(m.group(1)).strip()
        value = _strip_tags(m.group(2)).strip()
        if label and value and label not in fields:
            fields[label] = value

    return fields


def _strip_tags(html: str) -> str:
    """Remove HTML tags."""
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()
