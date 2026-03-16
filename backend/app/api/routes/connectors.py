"""Connector API endpoints.

Exposes the data connectors as REST endpoints for:
- Enrichment: integrated pipeline (URL → area stats → rent estimate)
- URL preview (metadata extraction from property listing URLs)
- Area statistics (built-in market data)
- Market data (MLIT transaction prices)
- Rent estimation
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

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
        return await c.fetch(
            **search_kwargs,
            search_url=body.search_url,
            price_min=body.price_min,
            price_max=body.price_max,
            area_min=body.area_min,
            walking_max=body.walking_max,
            age_max=body.age_max,
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

    # --- 4. Enrich each listing with rent estimate + market comparison ---
    enriched_listings: list[dict] = []
    rent_connector = RentEstimatorConnector()

    area_ok = area_result and not isinstance(area_result, Exception)
    prefecture = (
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
            try:
                rent_result = await rent_connector.fetch(
                    price_jpy=price,
                    floor_area_sqm=listing.get("floor_area_sqm"),
                    built_year=listing.get("built_year"),
                    walking_minutes=listing.get("walking_minutes"),
                    prefecture=prefecture,
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

            if avg_70 > 0:
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
        "listings": enriched_listings,
        "area_stats": (
            area_result.data
            if area_ok and area_result.success else None
        ),
        "suumo_market": suumo_market_data,
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
