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
"""

from __future__ import annotations

import logging
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
}

# Area/city codes for key cities (subset)
CITY_CODES = {
    "尼崎市": "28202", "西宮市": "28204", "芦屋市": "28206",
    "神戸市中央区": "28110", "大阪市北区": "27127",
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
    floor_area: float | None # 面積 (㎡)
    built_year: int | None
    layout: str | None
    trade_period: str        # e.g. "2024年第3四半期"
    unit_price: int | None   # 坪単価 or ㎡単価


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
        params: dict[str, str] = {
            "from": from_period,
            "to": to_period,
            "area": prefecture_code,
        }
        if city_code:
            params["city"] = city_code

        headers = {"Ocp-Apim-Subscription-Key": self._api_key}

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    f"{MLIT_API_BASE}/XIT001",
                    params=params,
                    headers=headers,
                )
                resp.raise_for_status()
                raw = resp.json()
        except httpx.HTTPStatusError as e:
            logger.error("MLIT API HTTP error: %s", e)
            return ConnectorResult(success=False, source=self.name, errors=[str(e)])
        except Exception as e:
            logger.error("MLIT API error: %s", e)
            return ConnectorResult(success=False, source=self.name, errors=[str(e)])

        records = _parse_transactions(raw, property_type)
        summary = _summarize(records)

        return ConnectorResult(
            success=True,
            source=self.name,
            data={
                "record_count": len(records),
                "summary": summary,
                "records": [_record_to_dict(r) for r in records[:50]],  # cap at 50
            },
        )


def _parse_transactions(raw: dict, property_type_filter: str) -> list[TransactionRecord]:
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
        built = _parse_int(item.get("BuildingYear"))

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
    unit_prices = [r.unit_price for r in records if r.unit_price and r.unit_price > 0]
    areas = [r.floor_area for r in records if r.floor_area and r.floor_area > 0]

    return {
        "count": len(records),
        "price_min": min(prices) if prices else None,
        "price_max": max(prices) if prices else None,
        "price_median": _median(prices) if prices else None,
        "price_avg": int(sum(prices) / len(prices)) if prices else None,
        "unit_price_avg": int(sum(unit_prices) / len(unit_prices)) if unit_prices else None,
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
