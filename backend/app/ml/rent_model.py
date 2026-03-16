"""ML-Enhanced Rent Estimation Model.

Improves on the existing 3-tier rent estimator by adding a data-driven
layer that uses MLIT transaction data to calibrate the price-to-rent
relationship for the specific area.

Key insight: MLIT has *sale* prices but no *rent* data. However, we can
derive much better rent estimates by combining:
  1. MLIT sale prices → accurate ㎡ unit prices by area/age/layout
  2. SUUMO rental market data → actual rent levels by layout
  3. Cross-reference → calibrated cap rate by property attributes

The "ML" here is a calibrated regression that learns:
  - How cap rate varies with age, area, and station distance
  - The premium/discount for specific stations vs city average
  - The layout-specific rent multiplier from SUUMO data

This replaces the hardcoded AGE_DISCOUNT / STATION_PREMIUM / AREA_ADJUSTMENT
tables with data-driven coefficients.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Any

from app.ml.data_pipeline import (
    LAYOUT_CATEGORIES,
    MLDataset,
)

logger = logging.getLogger(__name__)


@dataclass
class MLRentEstimate:
    """ML-enhanced rent estimation result."""

    estimated_rent: int           # 推定月額賃料
    low_estimate: int
    high_estimate: int
    gross_yield: float            # 表面利回り
    confidence: str               # high / medium / low
    method: str
    cap_rate_used: float          # 使用した還元利回り
    adjustments: dict[str, float]  # 各種調整係数


@dataclass
class CalibratedCapRates:
    """Area-calibrated capitalization rates."""

    base_cap_rate: float          # Base cap rate for the area
    age_coefficients: list[float]  # Cap rate adjustment by age bracket
    station_premium: dict[str, float]  # Station → cap rate modifier
    layout_rents: dict[str, int]  # Layout → base rent from SUUMO
    avg_unit_price: float         # Average ㎡ unit price from MLIT
    n_transactions: int
    calibration_quality: str      # "high" / "medium" / "low"


def calibrate_cap_rates(
    dataset: MLDataset,
    rental_market_data: dict | None = None,
    area_avg_unit_price: int | None = None,
    prefecture_base_yield: float = 0.055,
) -> CalibratedCapRates:
    """Calibrate cap rates using MLIT data + SUUMO rents.

    This creates a data-driven mapping from property attributes
    to expected capitalization rate, replacing hardcoded tables.
    """
    records = dataset.records
    n = len(records)

    # --- Step 1: Compute actual ㎡ unit prices by age bracket ---
    # Age brackets: 0-5, 6-10, 11-15, 16-20, 21-25, 26-30, 31+
    age_brackets = [
        (0, 5), (6, 10), (11, 15), (16, 20),
        (21, 25), (26, 30), (31, 999),
    ]
    age_avg_prices: list[float] = []
    overall_avg = sum(r.unit_price for r in records) / n if n else 0

    for lo, hi in age_brackets:
        bracket_recs = [
            r for r in records if lo <= r.age_years <= hi
        ]
        if bracket_recs:
            avg = sum(r.unit_price for r in bracket_recs) / len(bracket_recs)
            age_avg_prices.append(avg)
        else:
            age_avg_prices.append(overall_avg)

    # Normalize: age_coefficient = age_bracket_avg / overall_avg
    # This tells us how much prices depreciate with age in THIS area
    age_coeffs = [
        round(avg / overall_avg, 4) if overall_avg > 0 else 1.0
        for avg in age_avg_prices
    ]

    # --- Step 2: Station-level premium/discount ---
    station_prices: dict[str, list[float]] = {}
    for r in records:
        stn = r.station_name
        if stn:
            station_prices.setdefault(stn, []).append(r.unit_price)

    station_premium: dict[str, float] = {}
    for stn, prices in station_prices.items():
        if len(prices) >= 3:
            stn_avg = sum(prices) / len(prices)
            station_premium[stn] = round(stn_avg / overall_avg, 4)

    # --- Step 3: Layout rents from SUUMO (if available) ---
    layout_rents: dict[str, int] = {}
    if rental_market_data:
        rbl = rental_market_data.get("rents_by_layout", {})
        for layout, rent in rbl.items():
            if isinstance(rent, (int, float)) and rent > 0:
                layout_rents[layout.upper()] = int(rent)

    # --- Step 4: Calibrate base cap rate ---
    # If we have both SUUMO rents and MLIT sale prices, compute
    # actual implied cap rate for the area
    base_cap = prefecture_base_yield
    if layout_rents and overall_avg > 0:
        # Average rent across available layouts
        avg_rent = sum(layout_rents.values()) / len(layout_rents)
        # Assume average condo ~65㎡
        avg_sale_price = overall_avg * 65
        if avg_sale_price > 0:
            implied_yield = (avg_rent * 12) / avg_sale_price
            # Blend with prefecture default (SUUMO data may not be perfect)
            base_cap = implied_yield * 0.7 + prefecture_base_yield * 0.3

    # Calibration quality
    if n >= 50 and layout_rents:
        quality = "high"
    elif n >= 20:
        quality = "medium"
    else:
        quality = "low"

    return CalibratedCapRates(
        base_cap_rate=round(base_cap, 5),
        age_coefficients=age_coeffs,
        station_premium=station_premium,
        layout_rents=layout_rents,
        avg_unit_price=overall_avg,
        n_transactions=n,
        calibration_quality=quality,
    )


def estimate_rent_ml(
    calibrated: CalibratedCapRates,
    price_jpy: int,
    floor_area: float = 65.0,
    age_years: float = 15.0,
    walking_minutes: float = 10.0,
    layout: str = "",
    station_name: str = "",
) -> MLRentEstimate:
    """Estimate rent using calibrated cap rates.

    This is the ML-enhanced replacement for the existing
    RentEstimatorConnector's 3-tier approach.
    """
    adjustments: dict[str, float] = {}

    # --- Step 1: Try direct SUUMO rent by layout ---
    layout_upper = layout.upper().replace(" ", "") if layout else ""
    if layout_upper and layout_upper in calibrated.layout_rents:
        base_rent = calibrated.layout_rents[layout_upper]

        # Adjust for property-specific attributes using MLIT-derived coeffs
        age_adj = _get_age_coefficient(
            calibrated.age_coefficients, age_years,
        )
        walk_adj = _walk_adjustment(walking_minutes)
        stn_adj = _station_adjustment(
            calibrated.station_premium, station_name,
        )

        # These adjustments are RELATIVE to the "average" property
        # that SUUMO rent data represents
        avg_age_adj = _get_age_coefficient(
            calibrated.age_coefficients, 15,
        )
        avg_walk_adj = _walk_adjustment(10)

        relative = (
            (age_adj / avg_age_adj)
            * (walk_adj / avg_walk_adj)
            * stn_adj
        )

        adjustments = {
            "age_factor": round(age_adj / avg_age_adj, 4),
            "walk_factor": round(walk_adj / avg_walk_adj, 4),
            "station_factor": round(stn_adj, 4),
            "combined": round(relative, 4),
        }

        estimated = int(base_rent * relative)
        implied_yield = (
            (estimated * 12) / price_jpy if price_jpy > 0 else 0
        )

        margin = 0.08 if calibrated.calibration_quality == "high" else 0.12

        return MLRentEstimate(
            estimated_rent=estimated,
            low_estimate=int(estimated * (1 - margin)),
            high_estimate=int(estimated * (1 + margin)),
            gross_yield=round(implied_yield, 4),
            confidence=(
                "high" if calibrated.calibration_quality == "high"
                else "medium"
            ),
            method=(
                f"SUUMO実賃料({layout_upper}:{base_rent:,}円)"
                f" + MLIT補正(×{relative:.3f})"
            ),
            cap_rate_used=round(implied_yield, 5),
            adjustments=adjustments,
        )

    # --- Step 2: Cap rate based estimation ---
    cap = calibrated.base_cap_rate
    age_adj = _get_age_coefficient(calibrated.age_coefficients, age_years)
    walk_adj = _walk_adjustment(walking_minutes)
    stn_adj = _station_adjustment(
        calibrated.station_premium, station_name,
    )

    # Adjust cap rate: older/farther properties have higher cap rates
    # (i.e., rent relative to price is higher = investors demand higher yield)
    # This is the inverse of price depreciation
    avg_age_adj = _get_age_coefficient(
        calibrated.age_coefficients, 15,
    )
    relative_quality = age_adj * walk_adj * stn_adj
    avg_quality = avg_age_adj * 1.0 * 1.0

    if relative_quality > 0 and avg_quality > 0:
        quality_ratio = relative_quality / avg_quality
        # Better property → lower cap rate (closer to avg)
        # Worse property → higher cap rate (investors need higher yield)
        adjusted_cap = cap / max(quality_ratio, 0.5)
        adjusted_cap = min(adjusted_cap, 0.10)  # Cap at 10%
        adjusted_cap = max(adjusted_cap, 0.025)  # Floor at 2.5%
    else:
        adjusted_cap = cap

    monthly_rent = int(price_jpy * adjusted_cap / 12)

    adjustments = {
        "age_factor": round(age_adj, 4),
        "walk_factor": round(walk_adj, 4),
        "station_factor": round(stn_adj, 4),
        "base_cap_rate": round(cap, 5),
        "adjusted_cap_rate": round(adjusted_cap, 5),
    }

    margin = 0.12 if calibrated.calibration_quality == "high" else 0.18

    return MLRentEstimate(
        estimated_rent=monthly_rent,
        low_estimate=int(monthly_rent * (1 - margin)),
        high_estimate=int(monthly_rent * (1 + margin)),
        gross_yield=round(adjusted_cap, 4),
        confidence=(
            "medium" if calibrated.calibration_quality != "low"
            else "low"
        ),
        method=(
            f"MLIT還元利回り({adjusted_cap:.2%})"
            f" [{calibrated.n_transactions}件calibrated]"
        ),
        cap_rate_used=round(adjusted_cap, 5),
        adjustments=adjustments,
    )


# ===================================================================
# Internal helpers
# ===================================================================

def _get_age_coefficient(coefficients: list[float], age: float) -> float:
    """Get age depreciation coefficient from calibrated data.

    Brackets: 0-5, 6-10, 11-15, 16-20, 21-25, 26-30, 31+
    """
    brackets = [5, 10, 15, 20, 25, 30, 999]
    for i, upper in enumerate(brackets):
        if age <= upper:
            return coefficients[i] if i < len(coefficients) else 1.0
    return coefficients[-1] if coefficients else 0.7


def _walk_adjustment(walking_minutes: float) -> float:
    """Walking distance adjustment (continuous, not bucketed).

    Uses a smooth curve instead of discrete buckets:
    f(w) = 1.05 - 0.015 * w  (clamped to [0.75, 1.08])

    This captures the well-documented non-linear effect
    where value drops more steeply after ~7 minutes.
    """
    if walking_minutes <= 3:
        return 1.05
    elif walking_minutes <= 7:
        return 1.05 - 0.01 * (walking_minutes - 3)
    elif walking_minutes <= 15:
        return 1.01 - 0.02 * (walking_minutes - 7)
    else:
        return max(0.75, 0.85 - 0.005 * (walking_minutes - 15))


def _station_adjustment(
    station_premium: dict[str, float],
    station_name: str,
) -> float:
    """Station-level premium/discount from MLIT data."""
    if not station_name or not station_premium:
        return 1.0

    # Exact match
    if station_name in station_premium:
        return station_premium[station_name]

    # Fuzzy match
    for stn, premium in station_premium.items():
        if station_name in stn or stn in station_name:
            return premium

    return 1.0
