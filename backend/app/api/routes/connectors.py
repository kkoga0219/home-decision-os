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
from app.connectors.mlit_transaction import MLITTransactionConnector
from app.connectors.rent_estimator import RentEstimatorConnector
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
    max_pages: int = Field(default=2, ge=1, le=5)


@router.post("/area-search")
async def area_search(body: AreaSearchRequest):
    """Search SUUMO for property listings in a given area.

    Returns a list of properties with basic info (price, area, layout, etc.)
    plus area market statistics for context.

    Example: station_name="塚口" → fetches all chuko mansion listings near 塚口
    """
    connector = SuumoSearchConnector()
    search_result = await connector.fetch(
        station_name=body.station_name,
        city_name=body.city_name,
        search_url=body.search_url,
        max_pages=body.max_pages,
    )

    # Also fetch area stats for context
    area_connector = AreaStatsConnector()
    area_result = await area_connector.fetch(
        station_name=body.station_name,
        city_name=body.city_name,
    )

    # Enrich listings with rent estimates if we have area data
    listings = search_result.data.get("listings", [])
    enriched_listings = []

    rent_connector = RentEstimatorConnector()
    prefecture = area_result.data.get("prefecture", "") if area_result.success else ""
    area_avg_unit = area_result.data.get("avg_unit_price_sqm") if area_result.success else None
    avg_70 = area_result.data.get("avg_price_70sqm", 0) if area_result.success else 0

    for listing in listings:
        price = listing.get("price_jpy")
        if price and price > 0:
            # Rent estimate
            try:
                rent_result = await rent_connector.fetch(
                    price_jpy=price,
                    floor_area_sqm=listing.get("floor_area_sqm"),
                    built_year=listing.get("built_year"),
                    walking_minutes=listing.get("walking_minutes"),
                    prefecture=prefecture,
                    area_avg_unit_price=area_avg_unit,
                )
                if rent_result.success:
                    listing["estimated_rent"] = rent_result.data["estimated_rent"]
                    listing["gross_yield"] = rent_result.data["gross_yield"]
            except Exception:
                pass

            # Market comparison
            if avg_70 > 0:
                area_sqm = listing.get("floor_area_sqm", 70)
                normalized = price * 70 / area_sqm if area_sqm else price
                diff = round((normalized / avg_70 - 1) * 100, 1)
                listing["vs_market_pct"] = diff
                listing["vs_market"] = (
                    "割安" if diff < -10
                    else "相場並み" if diff < 10
                    else "やや割高" if diff < 20
                    else "割高"
                )

        enriched_listings.append(listing)

    return {
        "success": search_result.success,
        "search_url": search_result.data.get("search_url", ""),
        "total_found": len(enriched_listings),
        "listings": enriched_listings,
        "area_stats": area_result.data if area_result.success else None,
        "errors": search_result.errors + (area_result.errors if not area_result.success else []),
    }


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
    """Look up built-in area market statistics."""
    connector = AreaStatsConnector()
    result = await connector.fetch(
        station_name=body.station_name,
        city_name=body.city_name,
        address_text=body.address_text,
    )
    return {"success": result.success, "data": result.data, "errors": result.errors}


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
    )
