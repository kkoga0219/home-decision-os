"""Connector API endpoints.

Exposes the data connectors as REST endpoints for:
- URL preview (metadata extraction from property listing URLs)
- Market data (MLIT transaction prices)
- Rent estimation
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.config import settings
from app.connectors.mlit_transaction import MLITTransactionConnector
from app.connectors.rent_estimator import RentEstimatorConnector
from app.connectors.url_preview import URLPreviewConnector

router = APIRouter(prefix="/connectors", tags=["connectors"])


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
