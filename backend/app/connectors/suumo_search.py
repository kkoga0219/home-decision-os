"""SUUMO area search connector.

Fetches property listings from SUUMO's search results page for a given area.
Parses listing cards using SUUMO's actual HTML structure:
  - .property_unit          → each listing card
  - .property_unit-title    → headline (not always the building name)
  - .property_unit-body dl  → structured fields (物件名, 販売価格, 所在地, etc.)
  - .property_unit-body a   → detail page link

Supported search modes:
1. By station/keyword (any area in Japan)
2. By city (mapped to SUUMO sc_ codes)
3. By prefecture + keyword (dynamic)
4. By direct SUUMO search URL
"""

from __future__ import annotations

import asyncio
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
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Cache-Control": "no-cache",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}

_MAX_RETRIES = 2
_RETRY_DELAY = 2.0  # seconds

# ---------------------------------------------------------------------------
# Prefecture → SUUMO URL slug
# ---------------------------------------------------------------------------
PREFECTURE_SLUGS: dict[str, str] = {
    "北海道": "hokkaido", "青森県": "aomori", "岩手県": "iwate",
    "宮城県": "miyagi", "秋田県": "akita", "山形県": "yamagata",
    "福島県": "fukushima", "茨城県": "ibaraki", "栃木県": "tochigi",
    "群馬県": "gunma", "埼玉県": "saitama", "千葉県": "chiba",
    "東京都": "tokyo", "神奈川県": "kanagawa", "新潟県": "niigata",
    "富山県": "toyama", "石川県": "ishikawa", "福井県": "fukui",
    "山梨県": "yamanashi", "長野県": "nagano", "岐阜県": "gifu",
    "静岡県": "shizuoka", "愛知県": "aichi", "三重県": "mie",
    "滋賀県": "shiga", "京都府": "kyoto", "大阪府": "osaka",
    "兵庫県": "hyogo", "奈良県": "nara", "和歌山県": "wakayama",
    "鳥取県": "tottori", "島根県": "shimane", "岡山県": "okayama",
    "広島県": "hiroshima", "山口県": "yamaguchi",
    "徳島県": "tokushima", "香川県": "kagawa",
    "愛媛県": "ehime", "高知県": "kochi",
    "福岡県": "fukuoka", "佐賀県": "saga", "長崎県": "nagasaki",
    "熊本県": "kumamoto", "大分県": "oita",
    "宮崎県": "miyazaki", "鹿児島県": "kagoshima",
    "沖縄県": "okinawa",
}

# Short names without 県/府/都/道 → full name
_PREF_SHORT: dict[str, str] = {}
for _full in PREFECTURE_SLUGS:
    _short = _full.rstrip("都道府県")
    _PREF_SHORT[_short] = _full

# ---------------------------------------------------------------------------
# City code mapping (prefecture_slug, sc_code)
# Covers major cities; unknown cities use keyword fallback
# ---------------------------------------------------------------------------
CITY_DB: dict[str, tuple[str, str]] = {
    # --- 兵庫県 ---
    "尼崎市": ("hyogo", "sc_amagasaki"),
    "西宮市": ("hyogo", "sc_nishinomiya"),
    "神戸市": ("hyogo", "sc_kobe"),
    "芦屋市": ("hyogo", "sc_ashiya"),
    "伊丹市": ("hyogo", "sc_itami"),
    "宝塚市": ("hyogo", "sc_takarazuka"),
    "川西市": ("hyogo", "sc_kawanishi"),
    "明石市": ("hyogo", "sc_akashi"),
    "姫路市": ("hyogo", "sc_himeji"),
    "加古川市": ("hyogo", "sc_kakogawa"),
    "三田市": ("hyogo", "sc_sanda"),
    # --- 大阪府 ---
    "大阪市": ("osaka", "sc_osaka"),
    "堺市": ("osaka", "sc_sakai"),
    "豊中市": ("osaka", "sc_toyonaka"),
    "吹田市": ("osaka", "sc_suita"),
    "茨木市": ("osaka", "sc_ibaraki"),
    "高槻市": ("osaka", "sc_takatsuki"),
    "枚方市": ("osaka", "sc_hirakata"),
    "東大阪市": ("osaka", "sc_higashiosaka"),
    "八尾市": ("osaka", "sc_yao"),
    "池田市": ("osaka", "sc_ikeda"),
    "箕面市": ("osaka", "sc_minoo"),
    "守口市": ("osaka", "sc_moriguchi"),
    "寝屋川市": ("osaka", "sc_neyagawa"),
    "門真市": ("osaka", "sc_kadoma"),
    "岸和田市": ("osaka", "sc_kishiwada"),
    # --- 京都府 ---
    "京都市": ("kyoto", "sc_kyoto"),
    "宇治市": ("kyoto", "sc_uji"),
    "長岡京市": ("kyoto", "sc_nagaokakyo"),
    # --- 東京都 ---
    "千代田区": ("tokyo", "sc_chiyoda"),
    "中央区": ("tokyo", "sc_chuo"),
    "港区": ("tokyo", "sc_minato"),
    "新宿区": ("tokyo", "sc_shinjuku"),
    "渋谷区": ("tokyo", "sc_shibuya"),
    "品川区": ("tokyo", "sc_shinagawa"),
    "目黒区": ("tokyo", "sc_meguro"),
    "世田谷区": ("tokyo", "sc_setagaya"),
    "大田区": ("tokyo", "sc_ota"),
    "杉並区": ("tokyo", "sc_suginami"),
    "豊島区": ("tokyo", "sc_toshima"),
    "板橋区": ("tokyo", "sc_itabashi"),
    "練馬区": ("tokyo", "sc_nerima"),
    "北区": ("tokyo", "sc_kita"),
    "足立区": ("tokyo", "sc_adachi"),
    "江東区": ("tokyo", "sc_koto"),
    "墨田区": ("tokyo", "sc_sumida"),
    "台東区": ("tokyo", "sc_taito"),
    "文京区": ("tokyo", "sc_bunkyo"),
    "荒川区": ("tokyo", "sc_arakawa"),
    "中野区": ("tokyo", "sc_nakano"),
    "八王子市": ("tokyo", "sc_hachioji"),
    "町田市": ("tokyo", "sc_machida"),
    "武蔵野市": ("tokyo", "sc_musashino"),
    "三鷹市": ("tokyo", "sc_mitaka"),
    "府中市": ("tokyo", "sc_fuchu"),
    "調布市": ("tokyo", "sc_chofu"),
    # --- 神奈川県 ---
    "横浜市": ("kanagawa", "sc_yokohama"),
    "川崎市": ("kanagawa", "sc_kawasaki"),
    "相模原市": ("kanagawa", "sc_sagamihara"),
    "藤沢市": ("kanagawa", "sc_fujisawa"),
    "鎌倉市": ("kanagawa", "sc_kamakura"),
    # --- 埼玉県 ---
    "さいたま市": ("saitama", "sc_saitama"),
    "川口市": ("saitama", "sc_kawaguchi"),
    "所沢市": ("saitama", "sc_tokorozawa"),
    "川越市": ("saitama", "sc_kawagoe"),
    # --- 千葉県 ---
    "千葉市": ("chiba", "sc_chiba"),
    "船橋市": ("chiba", "sc_funabashi"),
    "市川市": ("chiba", "sc_ichikawa"),
    "松戸市": ("chiba", "sc_matsudo"),
    "柏市": ("chiba", "sc_kashiwa"),
    # --- 愛知県 ---
    "名古屋市": ("aichi", "sc_nagoya"),
    # --- 福岡県 ---
    "福岡市": ("fukuoka", "sc_fukuoka"),
    "北九州市": ("fukuoka", "sc_kitakyushu"),
    # --- 広島県 ---
    "広島市": ("hiroshima", "sc_hiroshima"),
    # --- 宮城県 ---
    "仙台市": ("miyagi", "sc_sendai"),
    # --- 北海道 ---
    "札幌市": ("hokkaido", "sc_sapporo"),
}

# Station → (prefecture_slug, city_sc_code)
# Common stations; for unlisted ones, keyword search is used
STATION_DB: dict[str, tuple[str, str]] = {
    # --- 兵庫県 (阪急神戸線・宝塚線 etc.) ---
    "塚口": ("hyogo", "sc_amagasaki"),
    "武庫之荘": ("hyogo", "sc_amagasaki"),
    "立花": ("hyogo", "sc_amagasaki"),
    "尼崎": ("hyogo", "sc_amagasaki"),
    "園田": ("hyogo", "sc_amagasaki"),
    "西宮北口": ("hyogo", "sc_nishinomiya"),
    "夙川": ("hyogo", "sc_nishinomiya"),
    "甲子園": ("hyogo", "sc_nishinomiya"),
    "三宮": ("hyogo", "sc_kobe"),
    "六甲道": ("hyogo", "sc_kobe"),
    "住吉": ("hyogo", "sc_kobe"),
    "芦屋": ("hyogo", "sc_ashiya"),
    "伊丹": ("hyogo", "sc_itami"),
    "宝塚": ("hyogo", "sc_takarazuka"),
    "川西能勢口": ("hyogo", "sc_kawanishi"),
    "三田": ("hyogo", "sc_sanda"),
    "明石": ("hyogo", "sc_akashi"),
    "姫路": ("hyogo", "sc_himeji"),
    # --- 大阪府 ---
    "梅田": ("osaka", "sc_osaka"),
    "難波": ("osaka", "sc_osaka"),
    "天王寺": ("osaka", "sc_osaka"),
    "新大阪": ("osaka", "sc_osaka"),
    "本町": ("osaka", "sc_osaka"),
    "心斎橋": ("osaka", "sc_osaka"),
    "淀屋橋": ("osaka", "sc_osaka"),
    "天満橋": ("osaka", "sc_osaka"),
    "京橋": ("osaka", "sc_osaka"),
    "十三": ("osaka", "sc_osaka"),
    "江坂": ("osaka", "sc_suita"),
    "千里中央": ("osaka", "sc_toyonaka"),
    "豊中": ("osaka", "sc_toyonaka"),
    "池田": ("osaka", "sc_ikeda"),
    "箕面": ("osaka", "sc_minoo"),
    "茨木": ("osaka", "sc_ibaraki"),
    "高槻": ("osaka", "sc_takatsuki"),
    "枚方市": ("osaka", "sc_hirakata"),
    "堺": ("osaka", "sc_sakai"),
    # --- 京都府 ---
    "京都": ("kyoto", "sc_kyoto"),
    "四条": ("kyoto", "sc_kyoto"),
    "河原町": ("kyoto", "sc_kyoto"),
    "烏丸": ("kyoto", "sc_kyoto"),
    "宇治": ("kyoto", "sc_uji"),
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
        prefecture: str = "",
        max_pages: int = 3,
        price_min: int | None = None,
        price_max: int | None = None,
        area_min: float | None = None,
        walking_max: int | None = None,
        age_max: int | None = None,
        stations: list[str] | None = None,
        property_type: str = "mansion",
        **kwargs: Any,
    ) -> ConnectorResult:
        """Fetch property listings from SUUMO.

        Parameters
        ----------
        station_name : str
            Station name (any station in Japan)
        city_name : str
            City name (e.g. "尼崎市", "大阪市", "世田谷区")
        search_url : str
            Direct SUUMO search URL (overrides everything)
        prefecture : str
            Prefecture name (e.g. "兵庫県", "大阪府")
            Used with keyword search for unlisted stations
        max_pages : int
            Maximum number of pages to fetch (default 3)
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
        property_type : str
            "mansion" (中古マンション, default) or "house" (中古戸建て)
        """
        # If multiple stations, aggregate results
        if stations and len(stations) > 1:
            return await self._fetch_multi_station(
                stations=stations,
                city_name=city_name,
                prefecture=prefecture,
                max_pages=max_pages,
                price_min=price_min,
                price_max=price_max,
                area_min=area_min,
                walking_max=walking_max,
                age_max=age_max,
                property_type=property_type,
            )

        # Build search URL dynamically
        base_url = self._resolve_search_url(
            search_url=search_url,
            station_name=station_name,
            city_name=city_name,
            prefecture=prefecture,
            property_type=property_type,
        )
        if base_url is None:
            return ConnectorResult(
                success=False,
                source=self.name,
                errors=["検索条件を指定してください"],
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
                timeout=25,
                follow_redirects=True,
                http2=False,
            ) as client:
                for page in range(1, max_pages + 1):
                    if page == 1:
                        url = base_url
                    else:
                        sep = "&" if "?" in base_url else "?"
                        url = f"{base_url}{sep}page={page}"

                    # Add per-page delay to avoid rate-limiting
                    if page > 1:
                        await asyncio.sleep(1.0)

                    html = await self._fetch_page_with_retry(
                        client, url, page, errors,
                    )
                    if html is None:
                        break

                    listings = _parse_listing_page(html)
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

    @staticmethod
    async def _fetch_page_with_retry(
        client: httpx.AsyncClient,
        url: str,
        page: int,
        errors: list[str],
    ) -> str | None:
        """Fetch a single page with retry on 202/429."""
        for attempt in range(_MAX_RETRIES):
            logger.info(
                "Fetching SUUMO page %d (attempt %d): %s",
                page, attempt + 1, url,
            )
            headers = {**HEADERS, "Referer": "https://suumo.jp/"}
            resp = await client.get(url, headers=headers)

            if resp.status_code == 200:
                return resp.text

            if resp.status_code in (202, 429, 503):
                logger.warning(
                    "SUUMO page %d: HTTP %d, retrying in %.1fs",
                    page, resp.status_code, _RETRY_DELAY,
                )
                await asyncio.sleep(_RETRY_DELAY)
                continue

            errors.append(
                f"SUUMO page {page}: HTTP {resp.status_code}"
            )
            return None

        # All retries exhausted — try to parse last response anyway
        if resp.status_code in (200, 202):
            logger.info(
                "SUUMO page %d: using response despite HTTP %d",
                page, resp.status_code,
            )
            return resp.text

        errors.append(
            f"SUUMO page {page}: HTTP {resp.status_code} after "
            f"{_MAX_RETRIES} retries"
        )
        return None

    @staticmethod
    def _resolve_search_url(
        *,
        search_url: str = "",
        station_name: str = "",
        city_name: str = "",
        prefecture: str = "",
        property_type: str = "mansion",
    ) -> str | None:
        """Build a SUUMO search URL from location params.

        Resolution order:
        1. Direct URL (search_url)
        2. Station DB lookup (exact match)
        3. City DB lookup (exact match)
        4. Prefecture + keyword (dynamic)
        5. Keyword search on prefecture index page
        """
        if search_url:
            return search_url

        # SUUMO uses a different path segment per property type:
        #   中古マンション → /ms/chuko/   中古戸建て → /chukoikkodate/
        seg = "chukoikkodate" if property_type == "house" else "ms/chuko"
        base = f"https://suumo.jp/{seg}"

        # Resolve prefecture slug
        pref_slug = ""
        if prefecture:
            pref_slug = PREFECTURE_SLUGS.get(prefecture, "")
            if not pref_slug:
                full = _PREF_SHORT.get(
                    prefecture.rstrip("都道府県"), "",
                )
                if full:
                    pref_slug = PREFECTURE_SLUGS[full]

        # Station lookup
        if station_name and station_name in STATION_DB:
            ps, sc = STATION_DB[station_name]
            return f"{base}/{ps}/{sc}/?rn={quote(station_name)}"

        # City lookup
        if city_name and city_name in CITY_DB:
            ps, sc = CITY_DB[city_name]
            return f"{base}/{ps}/{sc}/"

        # Dynamic: prefecture + keyword
        keyword = station_name or city_name
        if not keyword:
            # Prefecture-level browse (all listings)
            if pref_slug:
                return f"{base}/{pref_slug}/"
            return None

        # Use prefecture if known, else nationwide keyword search
        if pref_slug:
            return f"{base}/{pref_slug}/?rn={quote(keyword)}"

        # Default: search nationwide via keyword (SUUMO redirects)
        return f"{base}/?rn={quote(keyword)}"

    async def _fetch_multi_station(
        self,
        stations: list[str],
        city_name: str = "",
        prefecture: str = "",
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
                prefecture=prefecture,
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
