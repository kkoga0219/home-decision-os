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

# All 47 prefecture codes (JIS X 0401)
PREFECTURE_CODES = {
    "北海道": "01",
    "青森県": "02",
    "岩手県": "03",
    "宮城県": "04",
    "秋田県": "05",
    "山形県": "06",
    "福島県": "07",
    "茨城県": "08",
    "栃木県": "09",
    "群馬県": "10",
    "埼玉県": "11",
    "千葉県": "12",
    "東京都": "13",
    "神奈川県": "14",
    "新潟県": "15",
    "富山県": "16",
    "石川県": "17",
    "福井県": "18",
    "山梨県": "19",
    "長野県": "20",
    "岐阜県": "21",
    "静岡県": "22",
    "愛知県": "23",
    "三重県": "24",
    "滋賀県": "25",
    "京都府": "26",
    "大阪府": "27",
    "兵庫県": "28",
    "奈良県": "29",
    "和歌山県": "30",
    "鳥取県": "31",
    "島根県": "32",
    "岡山県": "33",
    "広島県": "34",
    "山口県": "35",
    "徳島県": "36",
    "香川県": "37",
    "愛媛県": "38",
    "高知県": "39",
    "福岡県": "40",
    "佐賀県": "41",
    "長崎県": "42",
    "熊本県": "43",
    "大分県": "44",
    "宮崎県": "45",
    "鹿児島県": "46",
    "沖縄県": "47",
}

# Major city/ward codes (JIS X 0402) — covers all prefectural capitals + key cities
CITY_CODES = {
    # 北海道
    "札幌市中央区": "01101",
    "札幌市北区": "01102",
    "札幌市豊平区": "01105",
    "札幌市白石区": "01104",
    "札幌市西区": "01107",
    "札幌市厚別区": "01108",
    "旭川市": "01204",
    "函館市": "01202",
    # 東北
    "仙台市青葉区": "04101",
    "仙台市宮城野区": "04102",
    "仙台市太白区": "04104",
    "青森市": "02201",
    "盛岡市": "03201",
    "秋田市": "05201",
    "山形市": "06201",
    "福島市": "07201",
    "郡山市": "07203",
    # 関東 (東京23区)
    "千代田区": "13101",
    "中央区": "13102",
    "港区": "13103",
    "新宿区": "13104",
    "文京区": "13105",
    "台東区": "13106",
    "墨田区": "13107",
    "江東区": "13108",
    "品川区": "13109",
    "目黒区": "13110",
    "大田区": "13111",
    "世田谷区": "13112",
    "渋谷区": "13113",
    "中野区": "13114",
    "杉並区": "13115",
    "豊島区": "13116",
    "北区": "13117",
    "荒川区": "13118",
    "板橋区": "13119",
    "練馬区": "13120",
    "足立区": "13121",
    "葛飾区": "13122",
    "江戸川区": "13123",
    # 東京市部
    "八王子市": "13201",
    "立川市": "13202",
    "武蔵野市": "13203",
    "三鷹市": "13204",
    "府中市": "13206",
    "調布市": "13208",
    "町田市": "13209",
    "小金井市": "13210",
    "国分寺市": "13214",
    "国立市": "13215",
    "多摩市": "13224",
    # 神奈川
    "横浜市西区": "14103",
    "横浜市中区": "14104",
    "横浜市南区": "14105",
    "横浜市神奈川区": "14102",
    "横浜市港北区": "14109",
    "横浜市青葉区": "14117",
    "横浜市都筑区": "14118",
    "川崎市川崎区": "14131",
    "川崎市中原区": "14133",
    "川崎市高津区": "14134",
    "川崎市宮前区": "14135",
    "相模原市中央区": "14152",
    "藤沢市": "14205",
    "横須賀市": "14201",
    "鎌倉市": "14204",
    # 埼玉
    "さいたま市大宮区": "11103",
    "さいたま市浦和区": "11107",
    "さいたま市南区": "11109",
    "川口市": "11203",
    "川越市": "11201",
    "所沢市": "11208",
    "越谷市": "11222",
    # 千葉
    "千葉市中央区": "12101",
    "千葉市美浜区": "12106",
    "船橋市": "12204",
    "市川市": "12203",
    "松戸市": "12207",
    "柏市": "12217",
    "浦安市": "12227",
    # 北陸・甲信越
    "新潟市中央区": "15101",
    "富山市": "16201",
    "金沢市": "17201",
    "福井市": "18201",
    "甲府市": "19201",
    "長野市": "20201",
    # 東海
    "岐阜市": "21201",
    "静岡市葵区": "22101",
    "静岡市駿河区": "22102",
    "浜松市中区": "22131",
    "浜松市東区": "22132",
    "名古屋市千種区": "23101",
    "名古屋市東区": "23102",
    "名古屋市北区": "23103",
    "名古屋市中村区": "23105",
    "名古屋市中区": "23106",
    "名古屋市昭和区": "23107",
    "名古屋市瑞穂区": "23108",
    "名古屋市熱田区": "23109",
    "名古屋市名東区": "23115",
    "名古屋市天白区": "23116",
    "豊田市": "23211",
    "豊橋市": "23201",
    "岡崎市": "23202",
    "津市": "24201",
    # 近畿
    "大津市": "25201",
    "京都市北区": "26101",
    "京都市上京区": "26102",
    "京都市左京区": "26103",
    "京都市中京区": "26104",
    "京都市東山区": "26105",
    "京都市下京区": "26106",
    "京都市南区": "26107",
    "京都市右京区": "26108",
    "京都市西京区": "26111",
    "大阪市都島区": "27102",
    "大阪市福島区": "27103",
    "大阪市此花区": "27104",
    "大阪市西区": "27106",
    "大阪市港区": "27107",
    "大阪市天王寺区": "27109",
    "大阪市浪速区": "27111",
    "大阪市西淀川区": "27112",
    "大阪市淀川区": "27123",
    "大阪市東淀川区": "27114",
    "大阪市東成区": "27115",
    "大阪市生野区": "27116",
    "大阪市城東区": "27118",
    "大阪市住吉区": "27120",
    "大阪市東住吉区": "27121",
    "大阪市阿倍野区": "27118",
    "大阪市北区": "27127",
    "大阪市中央区": "27128",
    "堺市堺区": "27141",
    "堺市北区": "27146",
    "豊中市": "27203",
    "吹田市": "27205",
    "高槻市": "27207",
    "枚方市": "27210",
    "茨木市": "27211",
    "八尾市": "27212",
    "東大阪市": "27227",
    "神戸市東灘区": "28101",
    "神戸市灘区": "28102",
    "神戸市兵庫区": "28105",
    "神戸市長田区": "28106",
    "神戸市須磨区": "28107",
    "神戸市垂水区": "28108",
    "神戸市北区": "28109",
    "神戸市中央区": "28110",
    "神戸市西区": "28111",
    "尼崎市": "28202",
    "明石市": "28203",
    "西宮市": "28204",
    "芦屋市": "28206",
    "伊丹市": "28207",
    "宝塚市": "28214",
    "川西市": "28217",
    "三田市": "28219",
    "加古川市": "28210",
    "姫路市": "28201",
    "奈良市": "29201",
    "和歌山市": "30201",
    # 中国
    "鳥取市": "31201",
    "松江市": "32201",
    "岡山市北区": "33101",
    "岡山市中区": "33102",
    "倉敷市": "33202",
    "広島市中区": "34101",
    "広島市東区": "34102",
    "広島市南区": "34103",
    "広島市西区": "34104",
    "広島市安佐南区": "34105",
    "福山市": "34207",
    "下関市": "35201",
    "山口市": "35203",
    # 四国
    "徳島市": "36201",
    "高松市": "37201",
    "松山市": "38201",
    "高知市": "39201",
    # 九州
    "福岡市東区": "40131",
    "福岡市博多区": "40132",
    "福岡市中央区": "40133",
    "福岡市南区": "40134",
    "福岡市西区": "40135",
    "福岡市早良区": "40137",
    "北九州市小倉北区": "40106",
    "北九州市小倉南区": "40107",
    "久留米市": "40203",
    "佐賀市": "41201",
    "長崎市": "42201",
    "熊本市中央区": "43101",
    "熊本市東区": "43102",
    "大分市": "44201",
    "宮崎市": "45201",
    "鹿児島市": "46201",
    "那覇市": "47201",
}


@dataclass
class TransactionRecord:
    """One real estate transaction."""

    property_type: str  # マンション等, 宅地(土地と建物), etc.
    prefecture: str
    city: str
    district: str
    nearest_station: str
    walking_minutes: int | None
    trade_price: int  # 取引価格 (JPY)
    floor_area: float | None  # 面積 (㎡)
    built_year: int | None
    layout: str | None
    trade_period: str  # e.g. "2024年第3四半期"
    unit_price: int | None  # ㎡単価 (JPY/㎡)


@dataclass
class StationAreaStats:
    """MLIT-backed real area statistics for a station/city."""

    area_name: str
    prefecture: str
    avg_unit_price_sqm: int  # 平均㎡単価 (中古マンション)
    median_unit_price_sqm: int  # 中央値㎡単価
    avg_price_70sqm: int  # 70㎡換算平均価格
    avg_rent_per_sqm: int | None  # MLIT has no rent data; filled from other sources
    avg_gross_yield: float | None
    transaction_count: int  # 集計対象の取引件数
    price_trend: str  # "上昇" / "横ばい" / "下落" (computed from quarterly data)
    price_trend_pct: float  # 前年同期比 (%)
    quarterly_prices: list[dict[str, Any]]  # 四半期別㎡単価推移
    source: str
    period_range: str  # e.g. "2023Q1 - 2025Q4"


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
            return ConnectorResult(success=False, source=self.name, errors=["API request failed"])

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
            prefecture_code,
            city_code,
            from_period,
            to_period,
            property_type="マンション等",
        )
        if records is None or len(records) == 0:
            return None

        # Filter by station if specified
        if station_name:
            # Fuzzy match: "塚口" matches "塚口", "阪急塚口", "JR塚口" etc.
            station_records = [
                r
                for r in records
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
        results.append(
            {
                "period": period,
                "sort_key": sort_key,
                "avg_unit_price": int(sum(prices) / len(prices)),
                "median_unit_price": _median(prices),
                "count": len(prices),
            }
        )

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
    raw: dict,
    property_type_filter: str,
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

        records.append(
            TransactionRecord(
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
            )
        )
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
        "unit_price_avg": (int(sum(unit_prices) / len(unit_prices)) if unit_prices else None),
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
        "令和": 2018,  # 令和1年 = 2019年
        "平成": 1988,  # 平成1年 = 1989年
        "昭和": 1925,  # 昭和1年 = 1926年
    }
    for era, base in era_map.items():
        m2 = re.search(rf"{era}(\d+)年?", s)
        if m2:
            return base + int(m2.group(1))

    return None
