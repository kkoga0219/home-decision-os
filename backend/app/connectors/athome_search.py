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

import asyncio
import json
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
    "北海道": "hokkaido",
    "宮城県": "miyagi",
    "東京都": "tokyo",
    "神奈川県": "kanagawa",
    "埼玉県": "saitama",
    "千葉県": "chiba",
    "愛知県": "aichi",
    "大阪府": "osaka",
    "京都府": "kyoto",
    "兵庫県": "hyogo",
    "福岡県": "fukuoka",
    "広島県": "hiroshima",
    "奈良県": "nara",
    "滋賀県": "shiga",
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
        property_type: str = "mansion",
        use_browser: bool = False,
        **kwargs: Any,
    ) -> ConnectorResult:
        """Fetch listings from athome.

        property_type: "mansion" (中古マンション) or "house" (中古戸建て).
        use_browser: render with a headless browser (Playwright); athome's
            prices are JS-rendered, so this also auto-falls back to the
            browser when the HTTP response lacks listing markup.
        """
        base_url = self._resolve_url(
            station_name=station_name,
            city_name=city_name,
            prefecture=prefecture,
            property_type=property_type,
        )
        if not base_url:
            return ConnectorResult(
                success=False,
                source=self.name,
                errors=["athome: 検索条件不足"],
            )

        all_listings: list[dict[str, Any]] = []
        errors: list[str] = []

        from app.config import settings

        try:
            async with httpx.AsyncClient(
                timeout=25,
                follow_redirects=True,
                http2=False,
                headers=HEADERS,
                proxy=settings.scrape_proxy or None,
            ) as client:
                # Warm-up: athome is behind Imperva bot protection
                # ("認証中" block page). Hitting the top page first sets the
                # `athome_lab` cookie on the shared client, which lets the
                # subsequent list request through over plain HTTP.
                await self._warm_up(client, errors)

                for page in range(1, max_pages + 1):
                    if page == 1:
                        url = base_url
                    else:
                        sep = "&" if "?" in base_url else "?"
                        url = f"{base_url}{sep}page={page}"

                    # Add per-page delay to avoid rate-limiting
                    if page > 1:
                        await asyncio.sleep(1.0)

                    html = await self._get_page_html(
                        client,
                        url,
                        page,
                        errors,
                        use_browser,
                    )
                    if html is None:
                        break

                    listings = _parse_athome_page(html, property_type)
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
    async def _warm_up(
        client: httpx.AsyncClient,
        errors: list[str],
    ) -> None:
        """Acquire athome's anti-bot cookie via the top page."""
        try:
            await client.get(
                "https://www.athome.co.jp/",
                headers={"Referer": "https://www.google.com/"},
            )
            await asyncio.sleep(1.0)
        except Exception as exc:  # noqa: BLE001 - non-fatal warm-up
            logger.info("athome warm-up failed (continuing): %s", exc)

    @staticmethod
    async def _get_page_html(
        client: httpx.AsyncClient,
        url: str,
        page: int,
        errors: list[str],
        use_browser: bool,
    ) -> str | None:
        """Get HTML via HTTP, with an optional browser fallback.

        athome renders prices client-side, so when ``use_browser`` is set and
        the HTTP response lacks listing markup we retry the page with a
        headless browser (Playwright). Degrades to a no-op without Playwright.
        """
        html = await AthomeSearchConnector._fetch_page_with_retry(
            client,
            url,
            page,
            errors,
        )

        if use_browser and (html is None or "bukkenList" not in html):
            from app.config import settings
            from app.connectors import browser_fetch

            rendered = await browser_fetch.fetch_html(
                url,
                wait_for_text="bukkenList",
                proxy=settings.scrape_proxy,
            )
            if rendered and "bukkenList" in rendered:
                return rendered

        return html

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
                "Fetching athome page %d (attempt %d): %s",
                page,
                attempt + 1,
                url,
            )
            headers = {**HEADERS, "Referer": "https://www.athome.co.jp/"}
            resp = await client.get(url, headers=headers)

            if resp.status_code == 200:
                return resp.text

            if resp.status_code in (202, 429, 503):
                logger.warning(
                    "athome page %d: HTTP %d, retrying in %.1fs",
                    page,
                    resp.status_code,
                    _RETRY_DELAY,
                )
                await asyncio.sleep(_RETRY_DELAY)
                continue

            errors.append(f"athome page {page}: HTTP {resp.status_code}")
            return None

        # All retries exhausted — try to parse last response anyway
        if resp.status_code in (200, 202):
            logger.info(
                "athome page %d: using response despite HTTP %d",
                page,
                resp.status_code,
            )
            return resp.text

        errors.append(f"athome page {page}: HTTP {resp.status_code} after {_MAX_RETRIES} retries")
        return None

    @staticmethod
    def _resolve_url(
        station_name: str = "",
        city_name: str = "",
        prefecture: str = "",
        property_type: str = "mansion",
    ) -> str | None:
        # 中古マンション → /mansion/chuko   中古戸建て → /kodate/chuko
        kind = "kodate" if property_type == "house" else "mansion"
        base = f"https://www.athome.co.jp/{kind}/chuko"

        # City lookup
        if city_name and city_name in _CITY_SLUGS:
            pref, city = _CITY_SLUGS[city_name]
            return f"{base}/{pref}/{city}/list/"

        # Prefecture + keyword
        pref_slug = _PREF_SLUGS.get(prefecture, "")
        keyword = station_name or city_name
        if pref_slug and keyword:
            return f"{base}/{pref_slug}/list/?keyword={quote(keyword)}"
        if pref_slug:
            return f"{base}/{pref_slug}/list/"
        if keyword:
            return f"{base}/list/?keyword={quote(keyword)}"
        return None


# -------------------------------------------------------------------
# Parsing
#
# athome is an Angular app: the listing data is server-rendered into an
# Angular TransferState <script type="application/json"> blob rather than
# into plain listing-card markup. We parse that JSON (works over plain HTTP,
# no browser needed). The relevant array lives at:
#     data.bukkenData.bukkenList[]
# with fields: bukkenNo, title, kakaku (万円), madori (間取り), location,
# kaiinAccess, bukkenAccess[].name, areaInfo.area, syumokuNm.
# -------------------------------------------------------------------

_ZEN_TO_HAN = str.maketrans(
    "０１２３４５６７８９ＬＤＫＳＲ",
    "0123456789LDKSR",
)


def _zen_to_han(text: str) -> str:
    return (text or "").translate(_ZEN_TO_HAN)


def _parse_athome_page(
    html: str,
    property_type: str = "mansion",
) -> list[dict[str, Any]]:
    """Parse an athome listing page from its TransferState JSON."""
    bukken_list = _extract_bukken_list(html)
    listings: list[dict[str, Any]] = []
    for item in bukken_list:
        parsed = _parse_bukken(item, property_type)
        if parsed:
            listings.append(parsed)
    return listings


def _extract_bukken_list(html: str) -> list[dict[str, Any]]:
    """Pull data.bukkenData.bukkenList out of the TransferState blob(s)."""
    for block in re.findall(
        r'<script[^>]*type="application/json"[^>]*>(.*?)</script>',
        html,
        re.DOTALL,
    ):
        try:
            state = json.loads(block)
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(state, dict):
            continue
        for entry in state.values():
            body = entry.get("body") if isinstance(entry, dict) else None
            if not isinstance(body, str) or "bukkenList" not in body:
                continue
            try:
                inner = json.loads(body)
            except (json.JSONDecodeError, ValueError):
                continue
            bl = inner.get("data", {}).get("bukkenData", {}).get("bukkenList")
            if isinstance(bl, list) and bl:
                return bl
    return []


def _parse_bukken(
    item: dict[str, Any],
    property_type: str,
) -> dict[str, Any] | None:
    """Map one bukkenList entry to the connector's listing dict."""
    info: dict[str, Any] = {
        "source": "athome",
        "parse_method": "json",
    }

    title = (item.get("title") or "").strip()
    if title:
        info["name"] = title

    # Detail URL from the property number.
    bukken_no = str(item.get("bukkenNo") or "").strip()
    if bukken_no:
        kind = "kodate" if property_type == "house" else "mansion"
        info["url"] = f"https://www.athome.co.jp/{kind}/{bukken_no}/"

    # Price: kakaku is in 万円 (e.g. "300", "2,980"); may be "応談" etc.
    kakaku = str(item.get("kakaku") or "")
    pm = re.search(r"([\d,]+)", kakaku)
    if pm:
        try:
            man = int(pm.group(1).replace(",", ""))
            info["price_jpy"] = man * 10_000
            info["price_text"] = f"{man:,}万円"
        except ValueError:
            pass

    # Layout (間取り), normalised from full-width.
    madori = _zen_to_han(item.get("madori") or "").strip()
    if madori:
        info["layout"] = madori

    # Address.
    loc = (item.get("location") or "").strip()
    if loc:
        info["address"] = loc

    # Access: combine the representative access with every listed route so
    # the walk-distance filter can see all stations (incl. both 塚口 lines).
    # athome's kaiinAccess uses a "路線名/駅名 徒歩N分" form — replace the
    # internal slash with a space so the line stays attached to the station,
    # and join entries with newlines (the filter splits on those).
    access_parts: list[str] = []
    kaiin = (item.get("kaiinAccess") or "").strip()
    if kaiin:
        access_parts.append(kaiin.replace("/", " "))
    for acc in item.get("bukkenAccess") or []:
        name = (acc.get("name") if isinstance(acc, dict) else "") or ""
        name = name.strip()
        if name:
            access_parts.append(name.replace("/", " "))
    if access_parts:
        info["access"] = "\n".join(access_parts)
        wm = re.search(r"徒歩(\d+)分", info["access"])
        if wm:
            info["walking_minutes"] = int(wm.group(1))

    # Floor area.
    area_info = item.get("areaInfo")
    if isinstance(area_info, dict):
        am = re.search(r"([\d.]+)\s*m", area_info.get("area", ""))
        if am:
            info["floor_area_sqm"] = float(am.group(1))

    if "price_jpy" in info or "name" in info:
        return info
    return None
