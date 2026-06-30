"""Integrated property data enrichment pipeline.

Chains multiple data sources to build the most complete picture:

1. URL Preview → basic property info from listing page
2. MLIT API    → official transaction data → station-level area stats (if key configured)
3. Area Stats  → local market data (MLIT real data or built-in DB fallback)
4. SUUMO Market → real rental & condo market data (live fetch)
5. Rent Estimator → monthly rent estimate using all available data
6. Market Comparison → price vs area average

This is the main entry point the frontend should call.
"""

from __future__ import annotations

import logging
from typing import Any

from app.config import settings
from app.connectors.area_stats import AreaStatsConnector
from app.connectors.rent_estimator import RentEstimatorConnector
from app.connectors.url_preview import URLPreviewConnector

logger = logging.getLogger(__name__)


async def enrich_from_url(url: str) -> dict[str, Any]:
    """Full enrichment pipeline: URL → area data → market data → rent estimate."""
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

        for key, val in preview_result.data.items():
            if key.startswith("hint_"):
                result[key] = val
            elif key in ("title", "description", "image"):
                result[key] = val
    else:
        result["errors"].extend(preview_result.errors)

    # --- Steps 2-6: Shared enrichment ---
    await _enrich_with_market_data(result)

    return result


async def enrich_from_property_data(
    price_jpy: int,
    station_name: str = "",
    address_text: str = "",
    floor_area_sqm: float | None = None,
    built_year: int | None = None,
    walking_minutes: int | None = None,
    layout: str = "",
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
    if layout:
        result["hint_layout"] = layout

    await _enrich_with_market_data(result)

    return result


async def _enrich_with_market_data(result: dict[str, Any]) -> None:
    """Shared enrichment: MLIT → area stats → SUUMO → rent estimate → comparison."""

    station_name = result.get("hint_station_name", "")
    address_text = result.get("hint_address_text", "")
    price = result.get("hint_price_jpy")

    # --- Step 2: MLIT API → station-level real area stats ---
    mlit_area_data = None
    if settings.mlit_api_key:
        mlit_area_data = await _fetch_mlit_area_stats(result, station_name, address_text)

    # --- Step 3: Area Statistics (MLIT real data or built-in fallback) ---
    area_connector = AreaStatsConnector(mlit_override=mlit_area_data)
    area_result = await area_connector.fetch(
        station_name=station_name,
        address_text=address_text,
    )

    if area_result.success:
        source_label = area_result.data.get("data_quality", "エリア統計")
        area_name = area_result.data.get("area_name", "")
        result["sources_used"].append(f"エリア統計({area_name}) [{source_label}]")
        result["area_stats"] = area_result.data

    # --- Step 4: SUUMO Real Market Data (live fetch) ---
    rental_market_data = None
    try:
        from app.connectors.suumo_market import SuumoMarketConnector

        market_connector = SuumoMarketConnector()
        market_result = await market_connector.fetch(
            station_name=station_name,
        )
        if market_result.success:
            result["sources_used"].append("SUUMO相場データ")
            result["suumo_market"] = market_result.data
            rental_market_data = market_result.data.get("rental_market")

            # Update area stats with live condo data if available
            condo_data = market_result.data.get("condo_market")
            if condo_data and condo_data.get("avg_unit_price_sqm"):
                if "area_stats" not in result:
                    result["area_stats"] = {}
                result["area_stats"]["avg_unit_price_sqm_live"] = condo_data["avg_unit_price_sqm"]
                result["area_stats"]["live_data_source"] = "SUUMO相場ページ"
    except Exception as e:
        logger.warning("SUUMO market data error (non-fatal): %s", e)

    # --- Step 5: Rent Estimation (using best available data) ---
    if price and price > 0:
        rent_connector = RentEstimatorConnector()

        area_avg = None
        prefecture = ""
        if area_result.success:
            area_avg = area_result.data.get("avg_unit_price_sqm")
            prefecture = area_result.data.get("prefecture", "")

        rent_result = await rent_connector.fetch(
            price_jpy=price,
            floor_area_sqm=result.get("hint_floor_area_sqm"),
            built_year=result.get("hint_built_year"),
            walking_minutes=result.get("hint_walking_minutes"),
            prefecture=prefecture,
            area_avg_unit_price=area_avg,
            layout=result.get("hint_layout", ""),
            rental_market_data=rental_market_data,
        )

        if rent_result.success:
            result["sources_used"].append("賃料推定エンジン")
            result["rent_estimate"] = rent_result.data

    # --- Step 6: Market comparison (legacy rule-based) ---
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
                    "割安"
                    if price_vs_market < -10
                    else "相場並み"
                    if price_vs_market < 10
                    else "やや割高"
                    if price_vs_market < 20
                    else "割高"
                ),
            }

        # If MLIT data had quarterly trends, include them in the comparison
        if mlit_area_data and mlit_area_data.get("quarterly_prices"):
            result["market_comparison"]["price_trend"] = mlit_area_data.get("price_trend", "")
            result["market_comparison"]["price_trend_pct"] = mlit_area_data.get(
                "price_trend_pct", 0
            )
            result["market_comparison"]["quarterly_prices"] = mlit_area_data["quarterly_prices"]

    # --- Step 7: ML Valuation Engine (hedonic, comps, trend, rent, exit) ---
    if price and price > 0:
        await _enrich_with_ml_valuation(
            result,
            price_jpy=price,
            station_name=station_name,
            prefecture=area_result.data.get("prefecture", "") if area_result.success else "",
            rental_market_data=rental_market_data,
        )


async def _enrich_with_ml_valuation(
    result: dict[str, Any],
    price_jpy: int,
    station_name: str,
    prefecture: str,
    rental_market_data: dict | None = None,
) -> None:
    """Run ML valuation engine and merge results into enrichment output.

    Adds hedonic pricing, comparable transaction analysis, price trend
    forecasting, ML-calibrated rent estimation, and data-driven exit score.
    Non-fatal: errors are logged and enrichment continues without ML data.
    """
    try:
        from app.ml.valuation_engine import run_valuation

        floor_area = result.get("hint_floor_area_sqm") or 65.0
        built_year = result.get("hint_built_year")
        age_years = (2026 - built_year) if built_year else 15.0
        walking_minutes = result.get("hint_walking_minutes") or 10.0
        layout = result.get("hint_layout", "")

        # Infer city name from address text
        city_name = ""
        address_text = result.get("hint_address_text", "")
        if address_text:
            import re

            m = re.search(r"(.{2,4}[市区町村])", address_text)
            if m:
                city_name = m.group(1)

        report = await run_valuation(
            price_jpy=price_jpy,
            floor_area=float(floor_area),
            age_years=float(age_years),
            walking_minutes=float(walking_minutes),
            layout=layout,
            station_name=station_name,
            city_name=city_name,
            prefecture=prefecture,
            rental_market_data=rental_market_data,
        )

        ml_data = report.to_dict()
        result["ml_valuation"] = ml_data

        if report.mlit_available:
            result["sources_used"].append(f"ML評価エンジン (MLIT {report.dataset_size}件)")

        # Override market comparison with hedonic model if available
        if report.hedonic:
            result["market_comparison_ml"] = {
                "method": "hedonic_model",
                "predicted_total_price": report.hedonic.predicted_total_price,
                "predicted_unit_price": report.hedonic.predicted_unit_price,
                "confidence_low": report.hedonic.confidence_low,
                "confidence_high": report.hedonic.confidence_high,
                "deviation_pct": report.hedonic.deviation_pct,
                "assessment": report.hedonic.assessment,
                "model_r2": report.hedonic.model_r2,
                "model_mape": report.hedonic.model_mape,
            }

        # Override rent estimate with ML-calibrated version if available
        if report.rent:
            result["rent_estimate_ml"] = {
                "estimated_rent": report.rent.estimated_rent,
                "low_estimate": report.rent.low_estimate,
                "high_estimate": report.rent.high_estimate,
                "gross_yield": report.rent.gross_yield,
                "confidence": report.rent.confidence,
                "method": report.rent.method,
                "cap_rate": report.rent.cap_rate_used,
            }

        # Add ML exit score (replaces or supplements rule-based)
        if report.exit_score:
            result["exit_score_ml"] = {
                "total_score": report.exit_score.total_score,
                "assessment": report.exit_score.assessment,
                "liquidity": report.exit_score.liquidity_detail,
                "price_retention": report.exit_score.price_retention_detail,
                "momentum": report.exit_score.momentum_detail,
                "demand_match": report.exit_score.demand_match_detail,
                "data_quality": report.exit_score.data_quality,
            }

        if report.errors:
            result["ml_warnings"] = report.errors

    except Exception as e:
        logger.warning("ML valuation error (non-fatal): %s", e)
        result.setdefault("errors", []).append(f"ML評価エンジンエラー: {e!s}")


async def _fetch_mlit_area_stats(
    result: dict[str, Any],
    station_name: str,
    address_text: str,
) -> dict[str, Any] | None:
    """Fetch real area stats from MLIT API.

    Determines prefecture/city from address or station name,
    then fetches condo transaction data and computes station-level stats.
    """
    try:
        from app.connectors.mlit_transaction import (
            MLITTransactionConnector,
            station_stats_to_area_data,
        )

        # Determine prefecture and city from available data
        pref_code, city_code = _resolve_location_codes(
            station_name,
            address_text,
            hint_prefecture=result.get("hint_prefecture", ""),
            hint_city=result.get("hint_city", ""),
        )
        if not pref_code:
            logger.info("MLIT: Could not determine prefecture code")
            return None

        mlit = MLITTransactionConnector(api_key=settings.mlit_api_key)
        stats = await mlit.fetch_station_stats(
            prefecture_code=pref_code,
            city_code=city_code,
            station_name=station_name,
            from_period="20221",  # 3 years for trend analysis
            to_period="20254",
        )

        if stats is None:
            logger.info("MLIT: No condo transactions found")
            return None

        result["sources_used"].append(f"国交省不動産取引API ({stats.transaction_count}件)")
        result["mlit_data"] = {
            "transaction_count": stats.transaction_count,
            "avg_unit_price_sqm": stats.avg_unit_price_sqm,
            "median_unit_price_sqm": stats.median_unit_price_sqm,
            "price_trend": stats.price_trend,
            "price_trend_pct": stats.price_trend_pct,
            "quarterly_prices": stats.quarterly_prices,
        }

        return station_stats_to_area_data(stats)

    except Exception as e:
        logger.warning("MLIT area stats error (non-fatal): %s", e)
        return None


def _resolve_location_codes(
    station_name: str,
    address_text: str,
    hint_prefecture: str = "",
    hint_city: str = "",
) -> tuple[str, str]:
    """Resolve prefecture code and city code from station/address.

    Strategy:
    1. Use explicit hints (from frontend or search params) first
    2. Extract from address text (regex for all 47 prefectures + cities)
    3. Infer from station name using station→city lookup table
    4. Return whatever we have (prefecture-only is OK for MLIT API)

    Returns (prefecture_code, city_code) tuple.
    """
    import re

    from app.connectors.mlit_transaction import (
        city_name_to_code,
        prefecture_name_to_code,
    )

    pref_code = ""
    city_code = ""

    # --- 1. Explicit hints ---
    if hint_prefecture:
        pref_code = prefecture_name_to_code(hint_prefecture)
    if hint_city:
        city_code = city_name_to_code(hint_city)

    # --- 2. Extract from address text ---
    if address_text:
        if not pref_code:
            m = re.search(r"(東京都|北海道|(?:大阪|京都)府|.{2,3}県)", address_text)
            if m:
                pref_code = prefecture_name_to_code(m.group(1))

        if not city_code:
            # Try "政令市+区" pattern first (e.g. "横浜市中区", "名古屋市中区")
            m_ward = re.search(r"(.{2,4}市)(.{1,3}区)", address_text)
            if m_ward:
                combined = m_ward.group(1).replace("市", "") + "市" + m_ward.group(2)
                city_code = city_name_to_code(combined)
                if not city_code:
                    # Try just the city part
                    city_code = city_name_to_code(m_ward.group(1))

            if not city_code:
                # Try "XX区" alone (for Tokyo 23 wards)
                m_ku = re.search(r"([^\s市]{2,4}区)", address_text)
                if m_ku:
                    city_code = city_name_to_code(m_ku.group(1))

            if not city_code:
                # General city/town/village
                m_city = re.search(r"(.{2,4}[市町村])", address_text)
                if m_city:
                    city_code = city_name_to_code(m_city.group(1))

    # --- 3. Infer from station name ---
    if not pref_code and station_name:
        inferred = _infer_location_from_station(station_name)
        if inferred:
            pref_code = inferred[0]
            if not city_code:
                city_code = inferred[1]

    return pref_code, city_code


# Major station → (prefecture_code, city_code) lookup
# Covers all major metro areas plus key stations
_STATION_LOCATION_MAP: dict[str, tuple[str, str]] = {
    # 関西 (兵庫)
    "塚口": ("28", "28202"),
    "武庫之荘": ("28", "28202"),
    "立花": ("28", "28202"),
    "尼崎": ("28", "28202"),
    "園田": ("28", "28202"),
    "伊丹": ("28", "28207"),
    "西宮": ("28", "28204"),
    "芦屋": ("28", "28206"),
    "甲子園": ("28", "28204"),
    "鳴尾": ("28", "28204"),
    "宝塚": ("28", "28214"),
    "川西": ("28", "28217"),
    "三田": ("28", "28219"),
    "三宮": ("28", "28110"),
    "元町": ("28", "28110"),
    "神戸": ("28", "28110"),
    "住吉": ("28", "28101"),
    "岡本": ("28", "28101"),
    "御影": ("28", "28101"),
    "六甲道": ("28", "28102"),
    "灘": ("28", "28102"),
    "明石": ("28", "28203"),
    "姫路": ("28", "28201"),
    "加古川": ("28", "28210"),
    # 関西 (大阪)
    "梅田": ("27", "27127"),
    "大阪": ("27", "27127"),
    "難波": ("27", "27111"),
    "なんば": ("27", "27111"),
    "天王寺": ("27", "27109"),
    "新大阪": ("27", "27123"),
    "心斎橋": ("27", "27128"),
    "本町": ("27", "27128"),
    "淀屋橋": ("27", "27128"),
    "天満橋": ("27", "27128"),
    "京橋": ("27", "27118"),
    "鶴橋": ("27", "27115"),
    "豊中": ("27", "27203"),
    "吹田": ("27", "27205"),
    "高槻": ("27", "27207"),
    "枚方": ("27", "27210"),
    "茨木": ("27", "27211"),
    "堺": ("27", "27141"),
    "東大阪": ("27", "27227"),
    # 関西 (京都)
    "京都": ("26", "26106"),
    "四条": ("26", "26104"),
    "烏丸": ("26", "26104"),
    "河原町": ("26", "26104"),
    # 関西 (奈良)
    "奈良": ("29", "29201"),
    # 首都圏 (東京)
    "東京": ("13", "13102"),
    "新宿": ("13", "13104"),
    "渋谷": ("13", "13113"),
    "池袋": ("13", "13116"),
    "品川": ("13", "13109"),
    "目黒": ("13", "13110"),
    "恵比寿": ("13", "13113"),
    "中目黒": ("13", "13110"),
    "自由が丘": ("13", "13110"),
    "三軒茶屋": ("13", "13112"),
    "二子玉川": ("13", "13112"),
    "下北沢": ("13", "13112"),
    "吉祥寺": ("13", "13203"),
    "中野": ("13", "13114"),
    "荻窪": ("13", "13115"),
    "赤羽": ("13", "13117"),
    "上野": ("13", "13106"),
    "秋葉原": ("13", "13101"),
    "六本木": ("13", "13103"),
    "表参道": ("13", "13103"),
    "銀座": ("13", "13102"),
    "八王子": ("13", "13201"),
    "立川": ("13", "13202"),
    "町田": ("13", "13209"),
    "府中": ("13", "13206"),
    "調布": ("13", "13208"),
    "国分寺": ("13", "13214"),
    "三鷹": ("13", "13204"),
    "武蔵小金井": ("13", "13210"),
    # 首都圏 (神奈川)
    "横浜": ("14", "14104"),
    "川崎": ("14", "14131"),
    "武蔵小杉": ("14", "14133"),
    "溝の口": ("14", "14134"),
    "たまプラーザ": ("14", "14117"),
    "藤沢": ("14", "14205"),
    "鎌倉": ("14", "14204"),
    "横須賀": ("14", "14201"),
    "新横浜": ("14", "14109"),
    "日吉": ("14", "14109"),
    "センター北": ("14", "14118"),
    "センター南": ("14", "14118"),
    # 首都圏 (埼玉)
    "大宮": ("11", "11103"),
    "浦和": ("11", "11107"),
    "川口": ("11", "11203"),
    "川越": ("11", "11201"),
    "所沢": ("11", "11208"),
    # 首都圏 (千葉)
    "千葉": ("12", "12101"),
    "船橋": ("12", "12204"),
    "市川": ("12", "12203"),
    "松戸": ("12", "12207"),
    "柏": ("12", "12217"),
    "浦安": ("12", "12227"),
    # 中部
    "名古屋": ("23", "23106"),
    "栄": ("23", "23106"),
    "金山": ("23", "23109"),
    "豊田": ("23", "23211"),
    "静岡": ("22", "22101"),
    "浜松": ("22", "22131"),
    "岐阜": ("21", "21201"),
    "津": ("24", "24201"),
    "金沢": ("17", "17201"),
    "新潟": ("15", "15101"),
    "富山": ("16", "16201"),
    "長野": ("20", "20201"),
    "甲府": ("19", "19201"),
    # 中国
    "広島": ("34", "34101"),
    "岡山": ("33", "33101"),
    "倉敷": ("33", "33202"),
    "福山": ("34", "34207"),
    "松江": ("32", "32201"),
    "鳥取": ("31", "31201"),
    "下関": ("35", "35201"),
    "山口": ("35", "35203"),
    # 四国
    "高松": ("37", "37201"),
    "松山": ("38", "38201"),
    "徳島": ("36", "36201"),
    "高知": ("39", "39201"),
    # 九州
    "博多": ("40", "40132"),
    "天神": ("40", "40133"),
    "福岡": ("40", "40133"),
    "北九州": ("40", "40106"),
    "小倉": ("40", "40106"),
    "久留米": ("40", "40203"),
    "熊本": ("43", "43101"),
    "大分": ("44", "44201"),
    "長崎": ("42", "42201"),
    "佐賀": ("41", "41201"),
    "鹿児島": ("46", "46201"),
    "宮崎": ("45", "45201"),
    "那覇": ("47", "47201"),
    # 北海道・東北
    "札幌": ("01", "01101"),
    "旭川": ("01", "01204"),
    "函館": ("01", "01202"),
    "仙台": ("04", "04101"),
    "盛岡": ("03", "03201"),
    "青森": ("02", "02201"),
    "秋田": ("05", "05201"),
    "山形": ("06", "06201"),
    "福島": ("07", "07201"),
    "郡山": ("07", "07203"),
}


def _infer_location_from_station(station_name: str) -> tuple[str, str] | None:
    """Infer prefecture and city code from station name.

    Supports exact match and partial/fuzzy matching.
    """
    # Exact match
    if station_name in _STATION_LOCATION_MAP:
        return _STATION_LOCATION_MAP[station_name]

    # Partial match: station_name contains or is contained in a known station
    for known, codes in _STATION_LOCATION_MAP.items():
        if known in station_name or station_name in known:
            return codes

    return None
