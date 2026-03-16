"""MLIT Real Estate Transaction Price API connector (不動産情報ライブラリ).

Public API provided by the Ministry of Land, Infrastructure, Transport and Tourism.
Returns actual transaction prices for real estate in a specified area.

API docs: https://www.reinfolib.mlit.go.jp/api-manual/

Usage:
    connector = MLITTransactionConnector(api_key="YOUR_API_KEY")
    result = await connector.fetch(
        prefecture_code="28",       # 兵庫県
        city_code="28202",          # 尼崎市
        from_period="20231",        # 2023年第1四半期
        to_period="20254",          # 2025年第4四半期
    )

Station-level area stats:
    stats = await connector.fetch_station_stats(
        prefecture_code="28",
        city_code="28202",
        station_name="塚口",
    )
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

import httpx

from app.connectors.base import BaseConnector, ConnectorResult

logger = logging.getLogger(__name__)

# MLIT API base URL
MLIT_API_BASE = "https://www.reinfolib.mlit.go.jp/ex-api/external"

# Common prefecture codes
PREFECTURE_CODES = {
    "北海道": "01", "東京都": "13", "大阪府": "27", "兵庫県": "28",
    "京都府": "26", "神奈川県": "14", "愛知県": "23", "福岡県": "40",
    "埼玉県": "11", "千葉県": "12", "奈良県": "29",
}

# Area/city codes for key cities (subset)
CITY_CODES = {
    "尼崎市": "28202", "西宮市": "28204", "芦屋市": "28206",
    "伊丹市": "28207", "宝塚市": "28214", "川西市": "28217",
    "神戸市東灘区": "28101", "神戸市灘区": "28102",
    "神戸市中央区": "28110",
    "大阪市北区": "27127", "大阪市中央区": "27128",
    "豊中市": "27203", "吹田市": "27205",
}


@dataclass
class TransactionRecord:
    """One real estate transaction."""

    property_type: str       # マンション等, 宅地(土地と建物), etc.
    prefecture: str
    city: str
    district: str
    nearest_station: str
    walking_minutes: int | None
    trade_price: int         # 取引価格 (JPY)
    floor_area: float | None  # 面積 (㎡)
    built_year: int | None
    layout: str | None
    trade_period: str        # e.g. "2024年第3四半期"
    unit_price: int | None   # ㎡単価 (JPY/㎡)


@dataclass
class StationAreaStats:
    """MLIT-backed real area statistics for a station/city."""

    area_name: str
    prefecture: str
    avg_unit_price_sqm: int       # 平均㎡単価 (中古マンション)
    median_unit_price_sqm: int    # 中央値㎡単価
    avg_price_70sqm: int          # 70㎡換算平均価格
    avg_rent_per_sqm: int | None  # MLIT has no rent data; filled from other sources
    avg_gross_yield: float | None
    transaction_count: int        # 集計対象の取引件数
    price_trend: str              # "上昇" / "横ばい" / "下落" (computed from quarterly data)
    price_trend_pct: float        # 前年同期比 (%)
    quarterly_prices: list[dict[str, Any]]  # 四半期別㎡単価推移
    source: str
    period_range: str             # e.g. "2023Q1 - 2025Q4"


class MLITTransactionConnector(BaseConnector):
    """Fetches real estate transaction data from MLIT API."""

    def __init__(self, api_key: str):
        self._api_key = api_key

    @property
    def name(self) -> str:
        return "MLIT不動産取引価格情報"

    async def fetch(
        self,
        prefecture_code: str,
        city_code: str = "",
        from_period: str = "20231",
        to_period: str = "20254",
        property_type: str = "",
    ) -> ConnectorResult:
        """Fetch transaction data.

        Parameters
        ----------
        prefecture_code : str
            都道府県コード (e.g. "28" for 兵庫県)
        city_code : str
            市区町村コード (e.g. "28202" for 尼崎市). Empty = all cities.
        from_period : str
            開始期間 "YYYYQ" (e.g. "20231" = 2023年第1四半期)
        to_period : str
            終了期間 "YYYYQ"
        property_type : str
            物件種別フィルタ (empty = all). "マンション等" for condos.
        """
        records = await self._fetch_records(
            prefecture_code, city_code, from_period, to_period, property_type
        )
        if records is None:
            return ConnectorResult(
                success=False, source=self.name, errors=["API request failed"]
            )

        summary = _summarize(records)

        return ConnectorResult(
            success=True,
            source=self.name,
            data={
                "record_count": len(records),
                "summary": summary,
                "records": [_record_to_dict(r) for r in records[:50]],
            },
        )

    async def fetch_station_stats(
        self,
        prefecture_code: str,
        city_code: str = "",
        station_name: str = "",
        from_period: str = "20221",
        to_period: str = "20254",
    ) -> StationAreaStats | None:
        """Fetch condo transactions and compute station-level area statistics.

        This is the core function for TODO #1 and #2:
        - Aggregates ㎡ unit prices by station
        - Computes quarterly price trends
        - Returns real data to replace hardcoded area_stats

        Parameters
        ----------
        prefecture_code : str
            都道府県コード
        city_code : str
            市区町村コード (recommended for performance)
        station_name : str
            Target station name for filtering (e.g. "塚口")
        from_period : str
            Start period (default: 3 years back for trend analysis)
        to_period : str
            End period
        """
        records = await self._fetch_records(
            prefecture_code, city_code, from_period, to_period,
            property_type="マンション等",
        )
        if records is None or len(records) == 0:
            return None

        # Filter by station if specified
        if station_name:
            # Fuzzy match: "塚口" matches "塚口", "阪急塚口", "JR塚口" etc.
            station_records = [
                r for r in records
                if station_name in r.nearest_station or r.nearest_station in station_name
            ]
            # Fall back to all records if station filter yields too few
            if len(station_records) >= 5:
                records = station_records
                area_label = f"{station_name}駅周辺"
            else:
                area_label = city_code_to_name(city_code) or "指定エリア"
        else:
            area_label = city_code_to_name(city_code) or "指定エリア"

        # Only records with valid ㎡ unit price
        priced = [r for r in records if r.unit_price and r.unit_price > 0]
        if not priced:
            return None

        # --- Aggregate stats ---
        unit_prices = [r.unit_price for r in priced if r.unit_price]
        avg_up = int(sum(unit_prices) / len(unit_prices))
        median_up = _median(unit_prices)

        # --- Quarterly trend ---
        quarterly = _compute_quarterly_prices(priced)
        trend_label, trend_pct = _compute_trend(quarterly)

        # Prefecture name from code
        pref_name = _code_to_prefecture(prefecture_code)

        return StationAreaStats(
            area_name=area_label,
            prefecture=pref_name,
            avg_unit_price_sqm=avg_up,
            median_unit_price_sqm=median_up,
            avg_price_70sqm=avg_up * 70,
            avg_rent_per_sqm=None,  # MLIT has no rent data
            avg_gross_yield=None,
            transaction_count=len(priced),
            price_trend=trend_label,
            price_trend_pct=trend_pct,
            quarterly_prices=quarterly,
            source=f"国交省不動産取引価格API ({from_period}-{to_period})",
            period_range=f"{from_period}-{to_period}",
        )

    async def _fetch_records(
        self,
        prefecture_code: str,
        city_code: str,
        from_period: str,
        to_period: str,
        property_type: str,
    ) -> list[TransactionRecord] | None:
        """Internal: fetch and parse transaction records from MLIT API."""
        params: dict[str, str] = {
            "from": from_period,
            "to": to_period,
            "area": prefecture_code,
        }
        if city_code:
            params["city"] = city_code

        headers = {"Ocp-Apim-Subscription-Key": self._api_key}

        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.get(
                    f"{MLIT_API_BASE}/XIT001",
                    params=params,
                    headers=headers,
                )
                resp.raise_for_status()
                raw = resp.json()
        except httpx.HTTPStatusError as e:
            logger.error("MLIT API HTTP error: %s", e)
            return None
        except Exception as e:
            logger.error("MLIT API error: %s", e)
            return None

        return _parse_transactions(raw, property_type)


# ---------------------------------------------------------------------------
# Station-level aggregation helpers
# ---------------------------------------------------------------------------

def _compute_quarterly_prices(
    records: list[TransactionRecord],
) -> list[dict[str, Any]]:
    """Group records by trade_period and compute quarterly ㎡ unit prices.

    Returns a list of dicts sorted chronologically:
    [
        {"period": "2023年第1四半期", "sort_key": "20231",
         "avg_unit_price": 420000, "median_unit_price": 410000, "count": 12},
        ...
    ]
    """
    by_period: dict[str, list[int]] = defaultdict(list)
    for r in records:
        if r.unit_price and r.unit_price > 0 and r.trade_period:
            by_period[r.trade_period].append(r.unit_price)

    results = []
    for period, prices in by_period.items():
        sort_key = _period_to_sort_key(period)
        results.append({
            "period": period,
            "sort_key": sort_key,
            "avg_unit_price": int(sum(prices) / len(prices)),
            "median_unit_price": _median(prices),
            "count": len(prices),
        })

    results.sort(key=lambda x: x["sort_key"])
    return results


def _compute_trend(
    quarterly: list[dict[str, Any]],
) -> tuple[str, float]:
    """Compute price trend from quarterly data.

    Compares the most recent 4 quarters with the previous 4 quarters.
    Returns (label, yoy_percent).
    """
    if len(quarterly) < 4:
        return "データ不足", 0.0

    # Split into recent half and older half
    mid = len(quarterly) // 2
    older = quarterly[:mid]
    recent = quarterly[mid:]

    older_avg = sum(q["avg_unit_price"] for q in older) / len(older)
    recent_avg = sum(q["avg_unit_price"] for q in recent) / len(recent)

    if older_avg <= 0:
        return "算出不可", 0.0

    change_pct = round((recent_avg / older_avg - 1) * 100, 1)

    if change_pct > 5:
        label = "上昇"
    elif change_pct > 2:
        label = "やや上昇"
    elif change_pct > -2:
        label = "横ばい"
    elif change_pct > -5:
        label = "やや下落"
    else:
        label = "下落"

    return label, change_pct


def _period_to_sort_key(period: str) -> str:
    """Convert '2024年第3四半期' to '20243' for sorting."""
    m = re.search(r"(\d{4})年第(\d)四半期", period)
    if m:
        return f"{m.group(1)}{m.group(2)}"
    # Fallback: try to extract any year+quarter pattern
    m2 = re.search(r"(\d{4}).*?(\d)", period)
    if m2:
        return f"{m2.group(1)}{m2.group(2)}"
    return period


def station_stats_to_area_data(stats: StationAreaStats) -> dict[str, Any]:
    """Convert StationAreaStats to a dict compatible with area_stats format.

    This allows seamless integration with the existing enrichment pipeline.
    """
    return {
        "area_name": stats.area_name,
        "prefecture": stats.prefecture,
        "avg_unit_price_sqm": stats.avg_unit_price_sqm,
        "median_unit_price_sqm": stats.median_unit_price_sqm,
        "avg_price_70sqm": stats.avg_price_70sqm,
        "avg_rent_per_sqm": stats.avg_rent_per_sqm,
        "avg_gross_yield": stats.avg_gross_yield,
        "transaction_count": stats.transaction_count,
        "price_trend": stats.price_trend,
        "price_trend_pct": stats.price_trend_pct,
        "quarterly_prices": stats.quarterly_prices,
        "source": stats.source,
        "period_range": stats.period_range,
        "data_quality": "MLIT実取引データ",
    }


# ---------------------------------------------------------------------------
# City code helpers
# ---------------------------------------------------------------------------

# Reverse lookup: city code → name
_CITY_CODE_TO_NAME = {v: k for k, v in CITY_CODES.items()}


def city_code_to_name(code: str) -> str:
    """Convert city code to city name."""
    return _CITY_CODE_TO_NAME.get(code, "")


def city_name_to_code(name: str) -> str:
    """Convert city name to city code. Supports fuzzy matching."""
    if name in CITY_CODES:
        return CITY_CODES[name]
    # Partial match
    for city, code in CITY_CODES.items():
        if name in city or city in name:
            return code
    return ""


def prefecture_name_to_code(name: str) -> str:
    """Convert prefecture name to 2-digit code."""
    return PREFECTURE_CODES.get(name, "")


def _code_to_prefecture(code: str) -> str:
    """Convert 2-digit code to prefecture name."""
    for name, c in PREFECTURE_CODES.items():
        if c == code:
            return name
    return ""


# ---------------------------------------------------------------------------
# Parsing / summarization (existing)
# ---------------------------------------------------------------------------

def _parse_transactions(
    raw: dict, property_type_filter: str,
) -> list[TransactionRecord]:
    """Parse MLIT API response into typed records."""
    records: list[TransactionRecord] = []
    for item in raw.get("data", []):
        ptype = item.get("Type", "")
        if property_type_filter and property_type_filter not in ptype:
            continue

        walking = item.get("TimeToNearestStation")
        walking_int = _parse_int(walking) if walking else None

        price = _parse_int(item.get("TradePrice", "0"))
        area = _parse_float(item.get("Area"))
        built = _parse_built_year(item.get("BuildingYear"))

        unit_price = None
        if price and area and area > 0:
            unit_price = int(price / area)

        records.append(TransactionRecord(
            property_type=ptype,
            prefecture=item.get("Prefecture", ""),
            city=item.get("Municipality", ""),
            district=item.get("DistrictName", ""),
            nearest_station=item.get("NearestStation", ""),
            walking_minutes=walking_int,
            trade_price=price or 0,
            floor_area=area,
            built_year=built,
            layout=item.get("FloorPlan"),
            trade_period=item.get("Period", ""),
            unit_price=unit_price,
        ))
    return records


def _summarize(records: list[TransactionRecord]) -> dict[str, Any]:
    """Compute aggregate statistics."""
    if not records:
        return {"count": 0}

    prices = [r.trade_price for r in records if r.trade_price > 0]
    unit_prices = [
        r.unit_price for r in records if r.unit_price and r.unit_price > 0
    ]
    areas = [r.floor_area for r in records if r.floor_area and r.floor_area > 0]

    return {
        "count": len(records),
        "price_min": min(prices) if prices else None,
        "price_max": max(prices) if prices else None,
        "price_median": _median(prices) if prices else None,
        "price_avg": int(sum(prices) / len(prices)) if prices else None,
        "unit_price_avg": (
            int(sum(unit_prices) / len(unit_prices)) if unit_prices else None
        ),
        "area_avg": round(sum(areas) / len(areas), 1) if areas else None,
    }


def _median(values: list[int]) -> int:
    s = sorted(values)
    n = len(s)
    if n % 2 == 1:
        return s[n // 2]
    return (s[n // 2 - 1] + s[n // 2]) // 2


def _record_to_dict(r: TransactionRecord) -> dict[str, Any]:
    return {
        "property_type": r.property_type,
        "city": r.city,
        "district": r.district,
        "nearest_station": r.nearest_station,
        "walking_minutes": r.walking_minutes,
        "trade_price": r.trade_price,
        "floor_area": r.floor_area,
        "built_year": r.built_year,
        "layout": r.layout,
        "trade_period": r.trade_period,
        "unit_price": r.unit_price,
    }


def _parse_int(v: Any) -> int | None:
    if v is None:
        return None
    try:
        return int(str(v).replace(",", ""))
    except (ValueError, TypeError):
        return None


def _parse_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(str(v).replace(",", ""))
    except (ValueError, TypeError):
        return None


def _parse_built_year(v: Any) -> int | None:
    """Parse BuildingYear which can be '2018年', '令和5年', '平成30年', etc."""
    if v is None:
        return None
    s = str(v)

    # Try direct year: "2018年" or "2018"
    m = re.search(r"((?:19|20)\d{2})", s)
    if m:
        return int(m.group(1))

    # Japanese era conversion
    era_map = {
        "令和": 2018,   # 令和1年 = 2019年
        "平成": 1988,   # 平成1年 = 1989年
        "昭和": 1925,   # 昭和1年 = 1926年
    }
    for era, base in era_map.items():
        m2 = re.search(rf"{era}(\d+)年?", s)
        if m2:
            return base + int(m2.group(1))

    return None
