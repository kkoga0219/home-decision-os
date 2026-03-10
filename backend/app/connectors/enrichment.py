"""Integrated property data enrichment pipeline.

Chains multiple data sources to build the most complete picture:

1. URL Preview → basic property info from listing page
2. Area Stats  → local market data (built-in DB or MLIT API)
3. Rent Estimator → monthly rent estimate using all available data
4. Combine everything into a single enriched result

This is the main entry point the frontend should call.
"""

from __future__ import annotations

import logging
from typing import Any

from app.connectors.area_stats import AreaStatsConnector
from app.connectors.base import ConnectorResult
from app.connectors.rent_estimator import RentEstimatorConnector
from app.connectors.url_preview import URLPreviewConnector
from app.config import settings

logger = logging.getLogger(__name__)


async def enrich_from_url(url: str) -> dict[str, Any]:
    """Full enrichment pipeline: URL → area data → rent estimate.

    Returns a unified dict with all extracted and computed data.
    """
    result: dict[str, Any] = {
        "url": url,
        "sources_used": [],
        "errors": [],
    }

    # --- Step 1: URL Preview ---
    preview = URLPreviewConnector()
    preview_result = await preview.fetch(url=url)

    if preview_result.success:
        result["sources_used"].append("URL Preview")
        result["url_preview"] = preview_result.data

        # Copy hints to top level for easy access
        for key, val in preview_result.data.items():
            if key.startswith("hint_"):
                result[key] = val
            elif key in ("title", "description", "image"):
                result[key] = val
    else:
        result["errors"].extend(preview_result.errors)

    # --- Step 2: Area Statistics ---
    area_connector = AreaStatsConnector()
    area_result = await area_connector.fetch(
        station_name=result.get("hint_station_name", ""),
        address_text=result.get("hint_address_text", ""),
    )

    if area_result.success:
        result["sources_used"].append(f"エリア統計({area_result.data.get('area_name', '')})")
        result["area_stats"] = area_result.data
    else:
        result["errors"].extend(area_result.errors)

    # --- Step 2b: MLIT API (if key is configured) ---
    if settings.mlit_api_key:
        try:
            from app.connectors.mlit_transaction import MLITTransactionConnector
            mlit = MLITTransactionConnector(api_key=settings.mlit_api_key)
            # Try to determine prefecture code from area stats or hints
            prefecture = ""
            if area_result.success:
                prefecture = area_result.data.get("prefecture", "")
            pref_code = _prefecture_to_code(prefecture)
            if pref_code:
                mlit_result = await mlit.fetch(prefecture_code=pref_code)
                if mlit_result.success:
                    result["sources_used"].append("国交省不動産取引API")
                    result["mlit_data"] = mlit_result.data
        except Exception as e:
            logger.warning("MLIT API error (non-fatal): %s", e)

    # --- Step 3: Rent Estimation ---
    price = result.get("hint_price_jpy")
    if price and price > 0:
        rent_connector = RentEstimatorConnector()

        # Use area stats to improve estimation
        area_avg = None
        if area_result.success:
            area_avg = area_result.data.get("avg_unit_price_sqm")

        prefecture = ""
        if area_result.success:
            prefecture = area_result.data.get("prefecture", "")

        rent_result = await rent_connector.fetch(
            price_jpy=price,
            floor_area_sqm=result.get("hint_floor_area_sqm"),
            built_year=result.get("hint_built_year"),
            walking_minutes=result.get("hint_walking_minutes"),
            prefecture=prefecture,
            area_avg_unit_price=area_avg,
        )

        if rent_result.success:
            result["sources_used"].append("賃料推定エンジン")
            result["rent_estimate"] = rent_result.data
    else:
        result["rent_estimate"] = None

    # --- Step 4: Market comparison ---
    if price and area_result.success:
        avg_70 = area_result.data.get("avg_price_70sqm", 0)
        if avg_70 > 0:
            area_sqm = result.get("hint_floor_area_sqm", 70)
            normalized_price = price * 70 / area_sqm if area_sqm else price
            price_vs_market = round((normalized_price / avg_70 - 1) * 100, 1)
            result["market_comparison"] = {
                "your_price_70sqm_normalized": int(normalized_price),
                "area_avg_70sqm": avg_70,
                "diff_percent": price_vs_market,
                "assessment": (
                    "割安" if price_vs_market < -10
                    else "相場並み" if price_vs_market < 10
                    else "やや割高" if price_vs_market < 20
                    else "割高"
                ),
            }

    return result


async def enrich_from_property_data(
    price_jpy: int,
    station_name: str = "",
    address_text: str = "",
    floor_area_sqm: float | None = None,
    built_year: int | None = None,
    walking_minutes: int | None = None,
) -> dict[str, Any]:
    """Enrich from manually entered property data (no URL needed)."""
    result: dict[str, Any] = {
        "sources_used": [],
        "errors": [],
        "hint_price_jpy": price_jpy,
    }
    if station_name:
        result["hint_station_name"] = station_name
    if address_text:
        result["hint_address_text"] = address_text
    if floor_area_sqm:
        result["hint_floor_area_sqm"] = floor_area_sqm
    if built_year:
        result["hint_built_year"] = built_year
    if walking_minutes:
        result["hint_walking_minutes"] = walking_minutes

    # Area stats
    area_connector = AreaStatsConnector()
    area_result = await area_connector.fetch(
        station_name=station_name,
        address_text=address_text,
    )
    if area_result.success:
        result["sources_used"].append(f"エリア統計({area_result.data.get('area_name', '')})")
        result["area_stats"] = area_result.data

    # Rent estimation
    rent_connector = RentEstimatorConnector()
    prefecture = area_result.data.get("prefecture", "") if area_result.success else ""
    area_avg = area_result.data.get("avg_unit_price_sqm") if area_result.success else None

    rent_result = await rent_connector.fetch(
        price_jpy=price_jpy,
        floor_area_sqm=floor_area_sqm,
        built_year=built_year,
        walking_minutes=walking_minutes,
        prefecture=prefecture,
        area_avg_unit_price=area_avg,
    )
    if rent_result.success:
        result["sources_used"].append("賃料推定エンジン")
        result["rent_estimate"] = rent_result.data

    # Market comparison
    if area_result.success:
        avg_70 = area_result.data.get("avg_price_70sqm", 0)
        if avg_70 > 0:
            area = floor_area_sqm or 70
            normalized = price_jpy * 70 / area
            diff = round((normalized / avg_70 - 1) * 100, 1)
            result["market_comparison"] = {
                "your_price_70sqm_normalized": int(normalized),
                "area_avg_70sqm": avg_70,
                "diff_percent": diff,
                "assessment": (
                    "割安" if diff < -10
                    else "相場並み" if diff < 10
                    else "やや割高" if diff < 20
                    else "割高"
                ),
            }

    return result


# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------

_PREF_CODES = {
    "北海道": "01", "東京都": "13", "神奈川県": "14",
    "大阪府": "27", "兵庫県": "28", "京都府": "26",
    "愛知県": "23", "福岡県": "40", "埼玉県": "11",
    "千葉県": "12", "奈良県": "29",
}


def _prefecture_to_code(prefecture: str) -> str:
    """Convert prefecture name to 2-digit code."""
    return _PREF_CODES.get(prefecture, "")
