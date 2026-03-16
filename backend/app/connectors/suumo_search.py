"""SUUMO area search connector.

Fetches property listings from SUUMO's search results page for a given area.
Parses listing cards using SUUMO's actual HTML structure:
  - .property_unit          → each listing card
  - .property_unit-title    → headline (not always the building name)
  - .property_unit-body dl  → structured fields (物件名, 販売価格, 所在地, etc.)
  - .property_unit-body a   → detail page link

Supported search modes:
1. By station name (e.g. 塚口) → searches chuko mansion listings
2. By city (e.g. 尼崎市) → searches by city code
3. By direct SUUMO search URL
"""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import quote, urlencode

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
        price_min: int | None = None,
        price_max: int | None = None,
        area_min: float | None = None,
        walking_max: int | None = None,
        age_max: int | None = None,
        stations: list[str] | None = None,
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
        price_min, price_max : int | None
            Price range in 万円
        area_min : float | None
            Minimum floor area (㎡)
        walking_max : int | None
            Maximum walking minutes from station
        age_max : int | None
            Maximum building age in years
        stations : list[str] | None
            Search multiple stations (overrides station_name)
        """
        # If multiple stations, aggregate results
        if stations and len(stations) > 1:
            return await self._fetch_multi_station(
                stations=stations,
                city_name=city_name,
                max_pages=max_pages,
                price_min=price_min,
                price_max=price_max,
                area_min=area_min,
                walking_max=walking_max,
                age_max=age_max,
            )

        # Determine search URL
        if search_url:
            base_url = search_url
        elif station_name and station_name in STATION_SEARCH_AREAS:
            area_code = STATION_SEARCH_AREAS[station_name]
            base_url = (
                f"https://suumo.jp/ms/chuko/hyogo/{area_code}/"
            )
        elif city_name and city_name in CITY_CODES:
            area_code = CITY_CODES[city_name]
            base_url = (
                f"https://suumo.jp/ms/chuko/hyogo/{area_code}/"
            )
        else:
            keyword = station_name or city_name
            if not keyword:
                return ConnectorResult(
                    success=False,
                    source=self.name,
                    errors=["検索条件を指定してください"],
                )
            base_url = (
                f"https://suumo.jp/ms/chuko/hyogo/sc_amagasaki/"
                f"?rn={quote(keyword)}"
            )

        # Append SUUMO-native query filters
        filter_qs = _build_suumo_qs(
            price_min=price_min,
            price_max=price_max,
            area_min=area_min,
            walking_max=walking_max,
            age_max=age_max,
        )
        if filter_qs:
            sep = "&" if "?" in base_url else "?"
            base_url = f"{base_url}{sep}{filter_qs}"

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
                    logger.info("Fetching SUUMO page %d: %s", page, url)

                    resp = await client.get(url, headers=HEADERS)
                    if resp.status_code != 200:
                        errors.append(
                            f"Page {page}: HTTP {resp.status_code}"
                        )
                        break

                    listings = _parse_listing_page(resp.text)
                    if not listings:
                        break

                    all_listings.extend(listings)

        except Exception as e:
            logger.error("SUUMO search error: %s", e)
            return ConnectorResult(
                success=False,
                source=self.name,
                errors=[f"SUUMO検索エラー: {e!s}"],
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

    async def _fetch_multi_station(
        self,
        stations: list[str],
        city_name: str = "",
        max_pages: int = 1,
        **filter_kwargs: Any,
    ) -> ConnectorResult:
        """Aggregate results from multiple station searches."""
        all_listings: list[dict[str, Any]] = []
        errors: list[str] = []
        search_urls: list[str] = []
        seen_urls: set[str] = set()

        for stn in stations[:5]:  # cap at 5 stations
            result = await self.fetch(
                station_name=stn,
                city_name=city_name,
                max_pages=max_pages,
                stations=[],  # prevent recursion
                **filter_kwargs,
            )
            if result.success:
                url = result.data.get("search_url", "")
                if url:
                    search_urls.append(url)
                for ls in result.data.get("listings", []):
                    u = ls.get("url", "")
                    if u and u not in seen_urls:
                        seen_urls.add(u)
                        all_listings.append(ls)
            errors.extend(result.errors)

        return ConnectorResult(
            success=True,
            source=self.name,
            data={
                "search_url": search_urls[0] if search_urls else "",
                "total_found": len(all_listings),
                "listings": all_listings,
            },
            errors=errors,
        )


# ---------------------------------------------------------------------------
# SUUMO query-string builder
# ---------------------------------------------------------------------------

# SUUMO price codes (万円 → code for the pc1/pc2 parameter)
_PRICE_CODES: list[tuple[int, str]] = [
    (300, "0300"), (400, "0400"), (500, "0500"),
    (600, "0600"), (700, "0700"), (800, "0800"),
    (900, "0900"), (1000, "1000"), (1500, "1500"),
    (2000, "2000"), (2500, "2500"), (3000, "3000"),
    (3500, "3500"), (4000, "4000"), (4500, "4500"),
    (5000, "5000"), (6000, "6000"), (7000, "7000"),
    (8000, "8000"), (9000, "9000"), (10000, "10000"),
]

# Walking-minutes codes
_WALK_CODES: dict[int, str] = {
    1: "01", 3: "03", 5: "05", 7: "07",
    10: "10", 15: "15", 20: "20",
}

# Age codes (築年数)
_AGE_CODES: dict[int, str] = {
    1: "01", 3: "03", 5: "05", 7: "07",
    10: "10", 15: "15", 20: "20", 25: "25", 30: "30",
}

# Area codes (㎡)
_AREA_CODES: dict[int, str] = {
    20: "20", 25: "25", 30: "30", 40: "40",
    50: "50", 60: "60", 70: "70", 80: "80",
    90: "90", 100: "100",
}


def _nearest_code(
    value: int | float,
    code_map: list[tuple[int, str]] | dict[int, str],
    mode: str = "le",
) -> str | None:
    """Find nearest SUUMO code ≤ or ≥ value."""
    if isinstance(code_map, dict):
        keys = sorted(code_map.keys())
        if mode == "le":
            best = None
            for k in keys:
                if k <= value:
                    best = code_map[k]
            return best
        else:  # ge
            for k in keys:
                if k >= value:
                    return code_map[k]
            return None
    else:  # list of tuples
        if mode == "le":
            best = None
            for v, c in code_map:
                if v <= value:
                    best = c
            return best
        else:
            for v, c in code_map:
                if v >= value:
                    return c
            return None


def _build_suumo_qs(
    *,
    price_min: int | None = None,
    price_max: int | None = None,
    area_min: float | None = None,
    walking_max: int | None = None,
    age_max: int | None = None,
) -> str:
    """Build SUUMO-compatible query string for search filters.

    Returns empty string if no filters applicable.
    """
    params: list[tuple[str, str]] = []

    if price_min is not None:
        code = _nearest_code(price_min, _PRICE_CODES, "le")
        if code:
            params.append(("pc1", code))
    if price_max is not None:
        code = _nearest_code(price_max, _PRICE_CODES, "ge")
        if code:
            params.append(("pc2", code))
    if area_min is not None:
        code = _nearest_code(area_min, _AREA_CODES, "le")
        if code:
            params.append(("as1", code))
    if walking_max is not None:
        code = _nearest_code(walking_max, _WALK_CODES, "ge")
        if code:
            params.append(("wk", code))
    if age_max is not None:
        code = _nearest_code(age_max, _AGE_CODES, "ge")
        if code:
            params.append(("kz", code))

    if not params:
        return ""
    return urlencode(params)


# ---------------------------------------------------------------------------
# HTML parsing – based on SUUMO's actual DOM structure
# ---------------------------------------------------------------------------

def _parse_listing_page(html: str) -> list[dict[str, Any]]:
    """Parse a SUUMO search results page.

    SUUMO structure (confirmed 2026-03):
      .property_unit
        .property_unit-header
          h2.property_unit-title  ← headline (promotional, NOT building name)
        .property_unit-body
          dl: dt="物件名"  dd="武庫之荘パークハイツ"   ← building name
          dl: dt="販売価格" dd="1180万円"
          dl: dt="所在地"  dd="兵庫県尼崎市南武庫之荘３-36-16"
          dl: dt="沿線・駅" dd='阪急神戸線「武庫之荘」徒歩4分'
          table.dottable-fix:
            dl: dt="専有面積" dd="46.05m2（13.93坪）（壁芯）"
            dl: dt="間取り"  dd="1LDK"
          dl: dt="バルコニー" dd="1m2"
          dl: dt="築年月"   dd="1978年11月"
          a[href*="/ms/chuko/"] ← detail page URL
    """
    listings: list[dict[str, Any]] = []

    # Split HTML by property_unit boundaries
    # Each card starts with <div class="property_unit...">
    card_chunks = re.split(
        r'<div\s+class="property_unit(?:\s|")', html,
    )

    for chunk in card_chunks[1:]:  # skip before first card
        listing = _parse_property_unit(chunk)
        if listing:
            listings.append(listing)

    return listings


def _parse_property_unit(chunk: str) -> dict[str, Any] | None:
    """Parse a single property_unit chunk into a listing dict."""
    info: dict[str, Any] = {"parse_method": "structured"}

    # --- Detail page URL ---
    m = re.search(
        r'href="(/ms/chuko/[^"]*nc_\d+/[^"]*)"', chunk,
    )
    if m:
        info["url"] = f"https://suumo.jp{m.group(1)}"
    else:
        m2 = re.search(
            r'href="(https?://suumo\.jp/ms/chuko/[^"]*nc_\d+/[^"]*)"',
            chunk,
        )
        if m2:
            info["url"] = m2.group(1)

    # --- Parse all dl > dt/dd pairs (the core structured data) ---
    fields = _extract_dl_fields(chunk)

    # 物件名 (building/mansion name)
    if "物件名" in fields:
        info["name"] = fields["物件名"]

    # 販売価格
    if "販売価格" in fields:
        price_text = fields["販売価格"]
        info["price_text"] = price_text
        m = re.search(r"([\d,]+)\s*万円", price_text)
        if m:
            info["price_jpy"] = (
                int(m.group(1).replace(",", "")) * 10_000
            )

    # 所在地
    if "所在地" in fields:
        info["address"] = fields["所在地"]

    # 沿線・駅 → station name + walking minutes
    access = fields.get("沿線・駅", "")
    if access:
        info["access"] = access
        # 「武庫之荘」 or 「塚口」 etc.
        m = re.search(r"「([^」]+)」", access)
        if m:
            info["station_name"] = m.group(1)
        # 徒歩N分
        m = re.search(r"徒歩(\d+)分", access)
        if m:
            info["walking_minutes"] = int(m.group(1))
        # 路線名
        m = re.search(r"^([^「]+?)「", access)
        if m:
            info["line_name"] = m.group(1).strip()

    # 専有面積
    area_text = fields.get("専有面積", "")
    if area_text:
        m = re.search(r"([\d.]+)\s*m", area_text)
        if m:
            info["floor_area_sqm"] = float(m.group(1))

    # 間取り
    if "間取り" in fields:
        info["layout"] = fields["間取り"].strip()

    # 築年月
    built_text = fields.get("築年月", "")
    if built_text:
        info["built_date"] = built_text
        m = re.search(r"(\d{4})年", built_text)
        if m:
            info["built_year"] = int(m.group(1))

    # バルコニー
    balcony_text = fields.get("バルコニー", "")
    if balcony_text:
        m = re.search(r"([\d.]+)\s*m", balcony_text)
        if m:
            info["balcony_sqm"] = float(m.group(1))

    # --- Fallback: if no 物件名 from dl, try from title ---
    if "name" not in info:
        m = re.search(
            r'class="property_unit-title[^"]*"[^>]*>(.*?)</h',
            chunk,
            re.DOTALL,
        )
        if m:
            title_text = _strip_tags(m.group(1)).strip()
            # Title is often promotional; try to extract building name
            name = _extract_building_name_from_title(title_text)
            if name:
                info["name"] = name
            else:
                info["headline"] = title_text[:80]

    # Only return if we got useful data
    if "price_jpy" in info or "name" in info:
        return info

    return None


def _extract_dl_fields(html: str) -> dict[str, str]:
    """Extract all dt/dd pairs from dl elements in a chunk.

    Handles SUUMO's structure where each property field is a
    <dl><dt>label</dt><dd>value</dd></dl>.
    """
    fields: dict[str, str] = {}

    # Match <dl>...<dt>LABEL</dt>...<dd>VALUE</dd>...</dl>
    for m in re.finditer(
        r"<dl[^>]*>\s*<dt[^>]*>(.*?)</dt>\s*<dd[^>]*>(.*?)</dd>",
        html,
        re.DOTALL,
    ):
        label = _strip_tags(m.group(1)).strip()
        value = _strip_tags(m.group(2)).strip()
        if label and value:
            # Keep first occurrence of each label (most relevant)
            if label not in fields:
                fields[label] = value

    return fields


def _extract_building_name_from_title(title: str) -> str | None:
    """Try to extract a building name from a promotional title.

    SUUMO titles are often like:
    "頭金０円ローン可【本日見学可】阪急武庫之荘駅徒歩4分 リフォーム物件"
    These are NOT building names. We skip these.

    Real building names look like:
    "武庫之荘パークハイツ" "プラウド塚口" "グランドメゾン武庫之荘"
    """
    # If the title contains promotional keywords, it's not a name
    promo_keywords = [
        "頭金", "ローン", "見学", "リフォーム", "リノベ",
        "即入居", "駅徒歩", "新価格", "値下", "オープン",
        "ペット", "角部屋", "最上階", "フル",
    ]
    if any(kw in title for kw in promo_keywords):
        return None

    # Check if it looks like a building name (contains typical suffixes)
    name_suffixes = [
        "マンション", "レジデンス", "ハウス", "タワー", "コート",
        "パーク", "プラウド", "グラン", "ルネ", "ライオンズ",
        "サーパス", "エスリード", "ワコーレ", "アドリーム",
        "ジオ", "ブランズ", "ハイツ", "パレス", "メゾン",
        "シャトー", "ロイヤル", "コスモ", "ダイアパレス",
        "朝日プラザ", "藤和", "ネオ", "セレッソ",
    ]
    if any(s in title for s in name_suffixes):
        return title.strip()

    # If short enough and looks like a proper name, keep it
    if len(title) <= 25 and not re.search(r"[！!？?。]", title):
        return title.strip()

    return None


def _strip_tags(html: str) -> str:
    """Remove HTML tags, collapse whitespace."""
    text = re.sub(
        r"<script[^>]*>.*?</script>", " ",
        html, flags=re.DOTALL | re.IGNORECASE,
    )
    text = re.sub(
        r"<style[^>]*>.*?</style>", " ",
        text, flags=re.DOTALL | re.IGNORECASE,
    )
    text = re.sub(r"<sup[^>]*>.*?</sup>", "", text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()
