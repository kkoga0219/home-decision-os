"""SUUMO market data connector.

Fetches real market data from SUUMO's public 相場情報 pages:
1. 賃貸相場 (rental market prices) - by station
2. 中古マンション相場 (used condo prices) - by station

These pages are publicly accessible and don't require an API key.
Data is updated regularly by SUUMO based on their listing database.

Note: This is NOT scraping individual listings. These are SUUMO's own
aggregate statistics pages, similar to what Zillow or Redfin publish.
"""

from __future__ import annotations

import logging
import re
from typing import Any

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

# SUUMO rental market page URLs by station
# Format: https://suumo.jp/chintai/soba/hyogo/ek_{station_code}/
# We store the known station codes for our target area
RENTAL_SOBA_URLS: dict[str, str] = {
    "塚口": "https://suumo.jp/chintai/soba/hyogo/ek_33810/",      # JR塚口
    "武庫之荘": "https://suumo.jp/chintai/soba/hyogo/ek_34440/",
    "立花": "https://suumo.jp/chintai/soba/hyogo/ek_33440/",
    "尼崎": "https://suumo.jp/chintai/soba/hyogo/ek_33370/",       # JR尼崎
    "園田": "https://suumo.jp/chintai/soba/hyogo/ek_34420/",
    "西宮北口": "https://suumo.jp/chintai/soba/hyogo/ek_34460/",
    "夙川": "https://suumo.jp/chintai/soba/hyogo/ek_34350/",
    "芦屋": "https://suumo.jp/chintai/soba/hyogo/ek_33120/",
    "三宮": "https://suumo.jp/chintai/soba/hyogo/ek_33720/",
    "伊丹": "https://suumo.jp/chintai/soba/hyogo/ek_33180/",       # JR伊丹
}

# SUUMO used condo market page URLs by city
CONDO_SOBA_URLS: dict[str, str] = {
    "尼崎市": "https://suumo.jp/ms/chuko/hyogo/sc_amagasaki/soba/",
    "西宮市": "https://suumo.jp/ms/chuko/hyogo/sc_nishinomiya/soba/",
    "神戸市": "https://suumo.jp/ms/chuko/hyogo/sc_kobe/soba/",
    "伊丹市": "https://suumo.jp/ms/chuko/hyogo/sc_itami/soba/",
    "芦屋市": "https://suumo.jp/ms/chuko/hyogo/sc_ashiya/soba/",
}


class SuumoMarketConnector(BaseConnector):
    """Fetches real rental and sales market data from SUUMO public pages."""

    @property
    def name(self) -> str:
        return "SUUMO相場データ"

    async def fetch(
        self,
        station_name: str = "",
        city_name: str = "",
        **kwargs: Any,
    ) -> ConnectorResult:
        """Fetch market data for a station/city.

        Returns rental market data (by station) and/or
        condo price data (by city).
        """
        data: dict[str, Any] = {}
        errors: list[str] = []

        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            # --- Rental market data ---
            if station_name and station_name in RENTAL_SOBA_URLS:
                url = RENTAL_SOBA_URLS[station_name]
                try:
                    resp = await client.get(url, headers=HEADERS)
                    if resp.status_code == 200:
                        rental_data = _parse_rental_soba(resp.text, station_name)
                        if rental_data:
                            data["rental_market"] = rental_data
                            data["rental_source_url"] = url
                except Exception as e:
                    logger.warning("Rental soba fetch error: %s", e)
                    errors.append(f"賃貸相場取得エラー: {str(e)}")

            # --- Condo price data ---
            # Determine city from station
            city = city_name
            if not city and station_name:
                city = _station_to_city(station_name)

            if city and city in CONDO_SOBA_URLS:
                url = CONDO_SOBA_URLS[city]
                try:
                    resp = await client.get(url, headers=HEADERS)
                    if resp.status_code == 200:
                        condo_data = _parse_condo_soba(resp.text, city)
                        if condo_data:
                            data["condo_market"] = condo_data
                            data["condo_source_url"] = url
                except Exception as e:
                    logger.warning("Condo soba fetch error: %s", e)
                    errors.append(f"中古マンション相場取得エラー: {str(e)}")

        if not data:
            return ConnectorResult(
                success=False,
                source=self.name,
                errors=errors or [f"相場データが見つかりません: {station_name or city_name}"],
            )

        return ConnectorResult(success=True, source=self.name, data=data, errors=errors)


def _parse_rental_soba(html: str, station_name: str) -> dict[str, Any] | None:
    """Parse SUUMO rental market (相場) page.

    SUUMO's rental soba pages typically show:
    - Average rent by layout (1K, 1LDK, 2LDK, 3LDK, etc.)
    - Rent ranges
    """
    text = _strip_tags(html)
    result: dict[str, Any] = {"station": station_name, "rents_by_layout": {}}

    # Look for rent by layout patterns
    # SUUMO format: "1K / 5.2万円" or "3LDK / 10.5万円" etc.
    # Also: "1K　5.2万円〜5.8万円" or similar table formats

    # Pattern 1: layout + rent in 万円
    layout_rents: dict[str, int] = {}

    # Try to find rent table data
    # Common patterns: "1R 4.5万円" "1K 5.3万円" "2LDK 8.2万円" "3LDK 10.5万円"
    for m in re.finditer(
        r"(\d[RLDK]{1,4})\s*[/／\s]*(\d+\.?\d*)\s*万円",
        text,
    ):
        layout = m.group(1).upper()
        rent_man = float(m.group(2))
        rent_yen = int(rent_man * 10_000)
        # Keep the first (usually most prominent) value per layout
        if layout not in layout_rents:
            layout_rents[layout] = rent_yen

    if layout_rents:
        result["rents_by_layout"] = layout_rents

        # Calculate useful aggregates
        all_rents = list(layout_rents.values())
        result["rent_min"] = min(all_rents)
        result["rent_max"] = max(all_rents)

        # Family-type rent (2LDK-3LDK) for comparison
        family_rents = [
            v for k, v in layout_rents.items()
            if k in ("2LDK", "3LDK", "2DK", "3DK", "2SLDK", "3SLDK")
        ]
        if family_rents:
            result["family_avg_rent"] = int(sum(family_rents) / len(family_rents))

    # Try to find average rent for the area
    m = re.search(r"平均.*?(\d+\.?\d*)\s*万円", text)
    if m:
        result["area_avg_rent"] = int(float(m.group(1)) * 10_000)

    return result if layout_rents else None


def _parse_condo_soba(html: str, city_name: str) -> dict[str, Any] | None:
    """Parse SUUMO used condo market (相場) page.

    Shows average prices, ㎡ unit prices, etc.
    """
    text = _strip_tags(html)
    result: dict[str, Any] = {"city": city_name}

    # Average price pattern: "平均価格 2,800万円" or "相場 2,800万円"
    m = re.search(r"(?:平均価格|相場|平均)\s*[：:]*\s*([\d,]+)\s*万円", text)
    if m:
        result["avg_price_manyen"] = int(m.group(1).replace(",", ""))
        result["avg_price_jpy"] = result["avg_price_manyen"] * 10_000

    # ㎡ unit price: "㎡単価 42万円" or "42.5万円/㎡"
    m = re.search(r"(?:㎡単価|平米単価)\s*[：:]*\s*([\d.]+)\s*万円", text)
    if m:
        result["avg_unit_price_manyen_sqm"] = float(m.group(1))
        result["avg_unit_price_sqm"] = int(float(m.group(1)) * 10_000)

    # Price by layout
    prices_by_layout: dict[str, int] = {}
    for m_layout in re.finditer(
        r"(\d[RLDK]{1,4})\s*[/／\s]*([\d,]+)\s*万円",
        text,
    ):
        layout = m_layout.group(1).upper()
        price_man = int(m_layout.group(2).replace(",", ""))
        if layout not in prices_by_layout:
            prices_by_layout[layout] = price_man * 10_000

    if prices_by_layout:
        result["prices_by_layout"] = prices_by_layout

    # Average area
    m = re.search(r"(?:平均面積|平均専有面積)\s*[：:]*\s*([\d.]+)\s*[㎡m²]", text)
    if m:
        result["avg_floor_area_sqm"] = float(m.group(1))

    return result if result.get("avg_price_jpy") or prices_by_layout else None


def _station_to_city(station: str) -> str:
    """Map station name to city."""
    amagasaki_stations = {"塚口", "武庫之荘", "立花", "尼崎", "園田"}
    nishinomiya_stations = {"西宮北口", "夙川", "甲子園"}
    kobe_stations = {"三宮", "六甲道", "住吉"}

    if station in amagasaki_stations:
        return "尼崎市"
    if station in nishinomiya_stations:
        return "西宮市"
    if station in kobe_stations:
        return "神戸市"
    if station == "芦屋":
        return "芦屋市"
    if station == "伊丹":
        return "伊丹市"
    return ""


def _strip_tags(html: str) -> str:
    """Remove HTML tags, collapse whitespace."""
    text = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()
