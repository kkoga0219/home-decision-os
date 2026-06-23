"""Connector API endpoints.

Exposes the data connectors as REST endpoints for:
- Enrichment: integrated pipeline (URL → area stats → rent estimate)
- URL preview (metadata extraction from property listing URLs)
- Area statistics (built-in market data)
- Market data (MLIT transaction prices)
- Rent estimation
"""

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

from app.config import settings
from app.connectors.area_stats import AreaStatsConnector
from app.connectors.enrichment import enrich_from_property_data, enrich_from_url
from app.connectors.mlit_transaction import (
    MLITTransactionConnector,
    city_name_to_code,
    prefecture_name_to_code,
    station_stats_to_area_data,
)
from app.connectors.athome_search import AthomeSearchConnector
from app.connectors.homes_search import HomesSearchConnector
from app.connectors.rent_estimator import RentEstimatorConnector
from app.connectors.suumo_market import SuumoMarketConnector
from app.connectors.suumo_search import SuumoSearchConnector
from app.connectors.url_preview import URLPreviewConnector

router = APIRouter(prefix="/connectors", tags=["connectors"])


# ===================================================================
# Integrated Enrichment (main entry point for frontend)
# ===================================================================

class EnrichFromURLRequest(BaseModel):
    url: str = Field(..., min_length=1)


class EnrichFromDataRequest(BaseModel):
    price_jpy: int = Field(..., gt=0)
    station_name: str = ""
    address_text: str = ""
    floor_area_sqm: float | None = None
    built_year: int | None = None
    walking_minutes: int | None = None


@router.post("/enrich-url")
async def enrich_url(body: EnrichFromURLRequest):
    """Integrated enrichment: URL → property data → area stats → rent estimate.

    This is the primary endpoint the frontend should use.
    Chains all available data sources to build a complete picture.
    """
    return await enrich_from_url(body.url)


@router.post("/enrich-data")
async def enrich_data(body: EnrichFromDataRequest):
    """Enrichment from manually entered property data (no URL needed).

    Use this when the user enters data directly instead of pasting a URL.
    """
    return await enrich_from_property_data(
        price_jpy=body.price_jpy,
        station_name=body.station_name,
        address_text=body.address_text,
        floor_area_sqm=body.floor_area_sqm,
        built_year=body.built_year,
        walking_minutes=body.walking_minutes,
    )


# ===================================================================
# Area Search (SUUMO listings + enrichment)
# ===================================================================

class AreaSearchRequest(BaseModel):
    station_name: str = ""
    city_name: str = ""
    search_url: str = ""
    prefecture: str = ""
    max_pages: int = Field(default=3, ge=1, le=10)
    # Filters
    price_min: int | None = Field(default=None, description="最低価格(万円)")
    price_max: int | None = Field(default=None, description="最高価格(万円)")
    area_min: float | None = Field(default=None, description="最小面積(㎡)")
    area_max: float | None = Field(default=None, description="最大面積(㎡)")
    layouts: list[str] = Field(
        default_factory=list,
        description="間取り (1K,1LDK,2LDK,3LDK,4LDK など)",
    )
    walking_max: int | None = Field(
        default=None, description="徒歩分数上限",
    )
    age_max: int | None = Field(
        default=None, description="築年数上限",
    )
    stations: list[str] = Field(
        default_factory=list,
        description="複数駅検索 (station_name より優先)",
    )
    sources: list[str] = Field(
        default_factory=lambda: ["suumo", "homes", "athome"],
        description="検索ソース (suumo, homes, athome)",
    )


@router.post("/area-search")
async def area_search(body: AreaSearchRequest):
    """Search multiple listing sites for properties in a given area.

    Searches SUUMO, LIFULL HOME'S, and athome concurrently,
    merges results, and enriches with rent/market data.
    """
    import asyncio
    import datetime

    sources = [s.lower() for s in body.sources] if body.sources else [
        "suumo", "homes", "athome",
    ]

    # --- 1. Fetch listings from all requested sources concurrently ---
    search_kwargs: dict = dict(
        station_name=body.station_name,
        city_name=body.city_name,
        prefecture=body.prefecture,
        max_pages=body.max_pages,
    )

    async def _fetch_suumo():
        c = SuumoSearchConnector()
        # Note: filter params are NOT passed to SUUMO URL construction.
        # Filtering is handled post-fetch by _apply_filters() and also
        # client-side. This avoids SUUMO returning 0 results when filter
        # query params produce an unrecognized URL format.
        return await c.fetch(
            **search_kwargs,
            search_url=body.search_url,
            stations=body.stations,
        )

    async def _fetch_homes():
        c = HomesSearchConnector()
        return await c.fetch(**search_kwargs)

    async def _fetch_athome():
        c = AthomeSearchConnector()
        return await c.fetch(**search_kwargs)

    connector_tasks: list = []
    connector_names: list[str] = []
    if "suumo" in sources:
        connector_tasks.append(_fetch_suumo())
        connector_names.append("suumo")
    if "homes" in sources:
        connector_tasks.append(_fetch_homes())
        connector_names.append("homes")
    if "athome" in sources:
        connector_tasks.append(_fetch_athome())
        connector_names.append("athome")

    results = await asyncio.gather(*connector_tasks, return_exceptions=True)

    # Merge listings + collect errors / search_urls
    all_raw_listings: list[dict] = []
    all_errors: list[str] = []
    search_urls: dict[str, str] = {}
    any_success = False

    for name, res in zip(connector_names, results):
        if isinstance(res, Exception):
            all_errors.append(f"{name}: {res!s}")
            continue
        if res.success:
            any_success = True
        all_errors.extend(res.errors)
        search_urls[name] = res.data.get("search_url", "")
        all_raw_listings.extend(res.data.get("listings", []))

    # --- 2. Area stats + market data (concurrent) ---
    area_connector = AreaStatsConnector()
    area_coro = area_connector.fetch(
        station_name=body.station_name,
        city_name=body.city_name,
    )

    async def _fetch_market():
        mc = SuumoMarketConnector()
        return await mc.fetch(
            station_name=body.station_name,
            city_name=body.city_name,
        )

    area_result, market_raw = await asyncio.gather(
        area_coro, _fetch_market(), return_exceptions=True,
    )

    rental_market_data = None
    suumo_market_data = None
    if not isinstance(market_raw, Exception):
        if market_raw.success:
            suumo_market_data = market_raw.data
            rental_market_data = market_raw.data.get("rental_market")
        all_errors.extend(market_raw.errors)

    if isinstance(area_result, Exception):
        area_result = None

    # --- 3. Post-filter ---
    total_before_filter = len(all_raw_listings)
    listings = _apply_filters(
        all_raw_listings,
        price_min=body.price_min,
        price_max=body.price_max,
        area_min=body.area_min,
        area_max=body.area_max,
        layouts=body.layouts,
        walking_max=body.walking_max,
        age_max=body.age_max,
        current_year=datetime.date.today().year,
    )
    logger.info(
        "Post-filter: %d → %d listings", total_before_filter, len(listings),
    )

    # --- 4. ML Valuation (MLIT-based, if API key available) ---
    ml_valuation_data = None
    hedonic_model = None
    ml_dataset = None
    ml_cap_rates = None
    try:
        if settings.mlit_api_key:
            from app.ml.valuation_engine import run_valuation
            from app.ml.data_pipeline import fetch_ml_dataset
            from app.ml.hedonic_model import train_hedonic_model
            from app.ml.rent_model import calibrate_cap_rates
            from app.connectors.mlit_transaction import (
                prefecture_name_to_code as _pnc,
                city_name_to_code as _cnc,
            )
            pref_code = _pnc(body.prefecture)
            city_code = _cnc(body.city_name) if body.city_name else ""
            # Infer from station name if not resolved
            if not pref_code and body.station_name:
                from app.connectors.enrichment import (
                    _infer_location_from_station,
                )
                inferred = _infer_location_from_station(body.station_name)
                if inferred:
                    pref_code = inferred[0]
                    if not city_code:
                        city_code = inferred[1]
            if not pref_code:
                pref_code = ""  # Skip ML if we can't determine location
            if pref_code:
                ml_dataset = await fetch_ml_dataset(
                    settings.mlit_api_key, pref_code, city_code,
                    station_name=body.station_name,
                )
            if ml_dataset and ml_dataset.n_samples >= 15:
                hedonic_model = train_hedonic_model(ml_dataset)
                pref_yield = {
                    "東京都": 0.042, "神奈川県": 0.048,
                    "大阪府": 0.050, "京都府": 0.050,
                    "愛知県": 0.052, "兵庫県": 0.055,
                    "千葉県": 0.055, "埼玉県": 0.055,
                    "福岡県": 0.055, "北海道": 0.060,
                    "宮城県": 0.058, "広島県": 0.056,
                }.get(body.prefecture, 0.058)
                ml_cap_rates = calibrate_cap_rates(
                    ml_dataset,
                    rental_market_data=rental_market_data,
                    prefecture_base_yield=pref_yield,
                )
    except Exception as exc:
        all_errors.append(f"ML valuation init: {exc!s}")

    # --- 5. Enrich each listing ---
    enriched_listings: list[dict] = []
    rent_connector = RentEstimatorConnector()

    area_ok = area_result and not isinstance(area_result, Exception)
    pref_str = (
        area_result.data.get("prefecture", "")
        if area_ok and area_result.success else ""
    )
    area_avg_unit = (
        area_result.data.get("avg_unit_price_sqm")
        if area_ok and area_result.success else None
    )
    avg_70 = (
        area_result.data.get("avg_price_70sqm", 0)
        if area_ok and area_result.success else 0
    )

    for listing in listings:
        price = listing.get("price_jpy")
        if price and price > 0:
            # --- ML rent estimate (if available) ---
            used_ml_rent = False
            if ml_cap_rates:
                try:
                    from app.ml.rent_model import estimate_rent_ml
                    built_yr = listing.get("built_year")
                    age = (
                        datetime.date.today().year - built_yr
                        if built_yr else 15
                    )
                    ml_rent = estimate_rent_ml(
                        ml_cap_rates,
                        price_jpy=price,
                        floor_area=listing.get("floor_area_sqm", 65),
                        age_years=float(age),
                        walking_minutes=float(
                            listing.get("walking_minutes", 10),
                        ),
                        layout=listing.get("layout", ""),
                        station_name=listing.get(
                            "station_name", "",
                        ),
                    )
                    listing["estimated_rent"] = ml_rent.estimated_rent
                    listing["gross_yield"] = ml_rent.gross_yield
                    listing["rent_confidence"] = ml_rent.confidence
                    listing["rent_method"] = ml_rent.method
                    used_ml_rent = True
                except Exception:
                    pass

            # Fallback: original rent estimator
            if not used_ml_rent:
                try:
                    rent_result = await rent_connector.fetch(
                        price_jpy=price,
                        floor_area_sqm=listing.get("floor_area_sqm"),
                        built_year=listing.get("built_year"),
                        walking_minutes=listing.get("walking_minutes"),
                        prefecture=pref_str,
                        area_avg_unit_price=area_avg_unit,
                        layout=listing.get("layout", ""),
                        rental_market_data=rental_market_data,
                    )
                    if rent_result.success:
                        listing["estimated_rent"] = (
                            rent_result.data["estimated_rent"]
                        )
                        listing["gross_yield"] = (
                            rent_result.data["gross_yield"]
                        )
                        listing["rent_confidence"] = (
                            rent_result.data.get("confidence", "low")
                        )
                except Exception:
                    pass

            # --- ML hedonic price assessment (if available) ---
            if hedonic_model:
                try:
                    built_yr = listing.get("built_year")
                    age = (
                        datetime.date.today().year - built_yr
                        if built_yr else 15
                    )
                    pred = hedonic_model.predict(
                        floor_area=listing.get("floor_area_sqm", 65),
                        age_years=float(age),
                        walking_minutes=float(
                            listing.get("walking_minutes", 10),
                        ),
                        layout=listing.get("layout", ""),
                        station_name=listing.get(
                            "station_name", "",
                        ),
                        listing_price=price,
                    )
                    listing["ml_fair_price"] = (
                        pred.predicted_total_price
                    )
                    listing["ml_deviation_pct"] = pred.deviation_pct
                    listing["ml_assessment"] = pred.assessment
                    listing["vs_market_pct"] = pred.deviation_pct
                    listing["vs_market"] = pred.assessment
                except Exception:
                    pass

            # Fallback: simple area average comparison
            if "vs_market_pct" not in listing and avg_70 > 0:
                area_sqm = listing.get("floor_area_sqm", 70)
                normalized = (
                    price * 70 / area_sqm if area_sqm else price
                )
                diff = round((normalized / avg_70 - 1) * 100, 1)
                listing["vs_market_pct"] = diff
                listing["vs_market"] = (
                    "割安" if diff < -10
                    else "相場並み" if diff < 10
                    else "やや割高" if diff < 20
                    else "割高"
                )

        enriched_listings.append(listing)

    if area_ok and not area_result.success:
        all_errors.extend(area_result.errors)

    # Primary search URL: prefer SUUMO, fallback to first available
    primary_url = (
        search_urls.get("suumo")
        or next(iter(search_urls.values()), "")
    )

    return {
        "success": any_success,
        "search_url": primary_url,
        "search_urls": search_urls,
        "total_found": len(enriched_listings),
        "total_before_filter": total_before_filter,
        "listings": enriched_listings,
        "area_stats": (
            area_result.data
            if area_ok and area_result.success else None
        ),
        "suumo_market": suumo_market_data,
        "ml_model_info": {
            "hedonic_available": hedonic_model is not None,
            "hedonic_r2": (
                hedonic_model.r2_score if hedonic_model else None
            ),
            "hedonic_mape": (
                hedonic_model.mape if hedonic_model else None
            ),
            "dataset_size": (
                ml_dataset.n_samples if ml_dataset else 0
            ),
            "rent_calibration": (
                ml_cap_rates.calibration_quality
                if ml_cap_rates else None
            ),
        },
        "errors": all_errors,
    }


def _apply_filters(
    listings: list[dict],
    *,
    price_min: int | None = None,
    price_max: int | None = None,
    area_min: float | None = None,
    area_max: float | None = None,
    layouts: list[str] | None = None,
    walking_max: int | None = None,
    age_max: int | None = None,
    current_year: int = 2026,
) -> list[dict]:
    """Filter scraped listings by user criteria."""
    result = []
    # Normalise layout filter: e.g. ["2LDK","3LDK"] → {"2LDK","3LDK"}
    layout_set: set[str] | None = None
    if layouts:
        layout_set = set(layouts)

    for ls in listings:
        price = ls.get("price_jpy")
        # price filters are in 万円 units from the frontend
        if price_min is not None and price is not None:
            if price < price_min * 10_000:
                continue
        if price_max is not None and price is not None:
            if price > price_max * 10_000:
                continue

        area = ls.get("floor_area_sqm")
        if area_min is not None and area is not None:
            if area < area_min:
                continue
        if area_max is not None and area is not None:
            if area > area_max:
                continue

        if layout_set:
            layout = ls.get("layout", "")
            if layout and layout not in layout_set:
                continue

        walk = ls.get("walking_minutes")
        if walking_max is not None and walk is not None:
            if walk > walking_max:
                continue

        built = ls.get("built_year")
        if age_max is not None and built is not None:
            if (current_year - built) > age_max:
                continue

        result.append(ls)
    return result


# ===================================================================
# Individual connector endpoints (for direct access / debugging)
# ===================================================================

# --- URL Preview ---

class URLPreviewRequest(BaseModel):
    url: str = Field(..., min_length=1)


class URLPreviewResponse(BaseModel):
    success: bool
    data: dict
    errors: list[str] = []


@router.post("/url-preview", response_model=URLPreviewResponse)
async def url_preview(body: URLPreviewRequest):
    """Extract metadata from a property listing URL."""
    connector = URLPreviewConnector()
    result = await connector.fetch(url=body.url)
    return URLPreviewResponse(success=result.success, data=result.data, errors=result.errors)


# --- Area Statistics ---

class AreaStatsRequest(BaseModel):
    station_name: str = ""
    city_name: str = ""
    address_text: str = ""


@router.post("/area-stats")
async def area_stats(body: AreaStatsRequest):
    """Look up area market statistics.

    If MLIT API key is configured, returns real transaction data.
    Otherwise falls back to built-in estimates.
    """
    # Try MLIT real data first
    mlit_data = None
    if settings.mlit_api_key and (body.station_name or body.address_text):
        try:
            import re

            pref_code = ""
            city_code = ""
            if body.address_text:
                m = re.search(
                    r"(東京都|北海道|(?:大阪|京都)府|.{2,3}県)",
                    body.address_text,
                )
                if m:
                    pref_code = prefecture_name_to_code(m.group(1))
                m2 = re.search(r"(.{2,4}[市区町村])", body.address_text)
                if m2:
                    city_code = city_name_to_code(m2.group(1))
            if body.city_name:
                city_code = city_name_to_code(body.city_name)
            if not pref_code:
                pref_code = "28"  # Default: 兵庫県

            mlit = MLITTransactionConnector(api_key=settings.mlit_api_key)
            stats = await mlit.fetch_station_stats(
                prefecture_code=pref_code,
                city_code=city_code,
                station_name=body.station_name,
            )
            if stats:
                mlit_data = station_stats_to_area_data(stats)
        except Exception:
            pass

    connector = AreaStatsConnector(mlit_override=mlit_data)
    result = await connector.fetch(
        station_name=body.station_name,
        city_name=body.city_name,
        address_text=body.address_text,
    )
    return {"success": result.success, "data": result.data, "errors": result.errors}


# --- MLIT Station Stats (detailed) ---

class MLITStationStatsRequest(BaseModel):
    station_name: str = ""
    city_name: str = ""
    prefecture_code: str = ""
    from_period: str = "20221"
    to_period: str = "20254"


@router.post("/mlit-station-stats")
async def mlit_station_stats(body: MLITStationStatsRequest):
    """Fetch detailed station-level area statistics from MLIT API.

    Returns real transaction data aggregated by station, including
    quarterly price trends.
    """
    api_key = settings.mlit_api_key
    if not api_key:
        raise HTTPException(
            503,
            "MLIT API key not configured. Set HDOS_MLIT_API_KEY.",
        )

    pref_code = body.prefecture_code
    city_code = ""
    if body.city_name:
        city_code = city_name_to_code(body.city_name)
    if not pref_code:
        pref_code = "28"  # Default: 兵庫県

    mlit = MLITTransactionConnector(api_key=api_key)
    stats = await mlit.fetch_station_stats(
        prefecture_code=pref_code,
        city_code=city_code,
        station_name=body.station_name,
        from_period=body.from_period,
        to_period=body.to_period,
    )

    if stats is None:
        return {
            "success": False,
            "data": None,
            "errors": ["取引データが見つかりませんでした"],
        }

    return {
        "success": True,
        "data": station_stats_to_area_data(stats),
        "errors": [],
    }


# --- Market Data (MLIT) ---

class MarketDataRequest(BaseModel):
    prefecture_code: str = Field(..., min_length=2, max_length=2)
    city_code: str = ""
    from_period: str = "20231"
    to_period: str = "20254"
    property_type: str = ""


class MarketDataResponse(BaseModel):
    success: bool
    source: str
    data: dict
    errors: list[str] = []


@router.post("/market-data", response_model=MarketDataResponse)
async def market_data(body: MarketDataRequest):
    """Fetch real estate transaction data from MLIT API.

    Requires HDOS_MLIT_API_KEY environment variable.
    Get your free API key at: https://www.reinfolib.mlit.go.jp/
    """
    api_key = settings.mlit_api_key
    if not api_key:
        raise HTTPException(
            503,
            "MLIT API key not configured. Set HDOS_MLIT_API_KEY environment variable. "
            "Get a free key at https://www.reinfolib.mlit.go.jp/",
        )
    connector = MLITTransactionConnector(api_key=api_key)
    result = await connector.fetch(
        prefecture_code=body.prefecture_code,
        city_code=body.city_code,
        from_period=body.from_period,
        to_period=body.to_period,
        property_type=body.property_type,
    )
    return MarketDataResponse(
        success=result.success,
        source=result.source,
        data=result.data,
        errors=result.errors,
    )


# --- Rent Estimation ---

class RentEstimateRequest(BaseModel):
    price_jpy: int = Field(..., gt=0)
    floor_area_sqm: float | None = None
    built_year: int | None = None
    walking_minutes: int | None = None
    prefecture: str = ""
    area_avg_unit_price: int | None = None


class RentEstimateResponse(BaseModel):
    success: bool
    estimated_rent: int
    low_estimate: int
    high_estimate: int
    gross_yield: float
    method: str
    confidence: str = "low"


@router.post("/rent-estimate", response_model=RentEstimateResponse)
async def rent_estimate(body: RentEstimateRequest):
    """Estimate monthly rent for a property."""
    connector = RentEstimatorConnector()
    result = await connector.fetch(
        price_jpy=body.price_jpy,
        floor_area_sqm=body.floor_area_sqm,
        built_year=body.built_year,
        walking_minutes=body.walking_minutes,
        prefecture=body.prefecture,
        area_avg_unit_price=body.area_avg_unit_price,
    )
    if not result.success:
        raise HTTPException(500, result.errors)
    return RentEstimateResponse(
        success=True,
        estimated_rent=result.data["estimated_rent"],
        low_estimate=result.data["low_estimate"],
        high_estimate=result.data["high_estimate"],
        gross_yield=result.data["gross_yield"],
        method=result.data["method"],
        confidence=result.data.get("confidence", "low"),
    )


# ===================================================================
# ML Valuation Engine (MLIT-based)
# ===================================================================

class ValuationRequest(BaseModel):
    price_jpy: int = Field(..., gt=0, description="物件価格 (円)")
    floor_area_sqm: float = Field(default=65.0, description="面積 (㎡)")
    age_years: float = Field(default=15.0, description="築年数")
    walking_minutes: float = Field(default=10.0, description="駅徒歩")
    layout: str = Field(default="", description="間取り (3LDK等)")
    station_name: str = Field(default="", description="最寄駅")
    city_name: str = Field(default="", description="市区町村")
    prefecture: str = Field(default="", description="都道府県")


# ===================================================================
# 塚口 New-Listing Alert (LINE notification)
# ===================================================================

class TsukaguchiAlertRequest(BaseModel):
    sources: list[str] = Field(
        default_factory=lambda: ["suumo", "homes", "athome"],
        description="検索ソース (suumo, homes, athome)",
    )
    max_pages: int = Field(default=1, ge=1, le=5)
    assume_unknown_is_hankyu: bool = Field(
        default=True,
        description="路線不明の「塚口」を阪急塚口とみなすか",
    )
    use_browser: bool = Field(
        default=True,
        description="Playwrightヘッドレスブラウザで取得（アンチボット回避）",
    )
    dry_run: bool = Field(
        default=False,
        description="LINE送信せず判定結果のみ返す（既読状態は更新）",
    )


@router.post("/alerts/tsukaguchi/run")
async def run_tsukaguchi_alert_endpoint(body: TsukaguchiAlertRequest):
    """Run the 塚口 new-listing alert and push matches to LINE.

    Searches 中古マンション + 中古戸建て around 塚口, keeps listings within
    the configured walk distance (阪急塚口 ≤10分、または 阪急・JR両塚口 ≤15分),
    skips already-seen listings, and notifies via the LINE Messaging API.

    Requires HDOS_LINE_CHANNEL_TOKEN (and optionally HDOS_LINE_TARGET_ID).
    """
    from app.services.listing_alert import run_tsukaguchi_alert

    if not body.dry_run and not settings.line_channel_token:
        raise HTTPException(
            503,
            "LINE channel token not configured. Set HDOS_LINE_CHANNEL_TOKEN "
            "(or call with dry_run=true to preview matches).",
        )

    return await run_tsukaguchi_alert(
        channel_token=settings.line_channel_token,
        target_id=settings.line_target_id,
        state_path=settings.alert_state_path,
        sources=body.sources,
        max_pages=body.max_pages,
        assume_unknown_is_hankyu=body.assume_unknown_is_hankyu,
        use_browser=body.use_browser,
        dry_run=body.dry_run,
    )


@router.post("/valuation")
async def ml_valuation(body: ValuationRequest):
    """ML-based property valuation using MLIT transaction data.

    Returns comprehensive analysis:
    - Hedonic fair price prediction
    - Comparable transaction analysis
    - Price trend forecast
    - ML-calibrated rent estimate
    - Data-driven exit score
    """
    from app.ml.valuation_engine import run_valuation

    report = await run_valuation(
        price_jpy=body.price_jpy,
        floor_area=body.floor_area_sqm,
        age_years=body.age_years,
        walking_minutes=body.walking_minutes,
        layout=body.layout,
        station_name=body.station_name,
        city_name=body.city_name,
        prefecture=body.prefecture,
    )
    return report.to_dict()
