"""Comparable Transaction Analysis Engine (取引事例比較法).

The "comps" (comparable sales) approach is the gold standard method
used by professional appraisers (不動産鑑定士) in Japan.

Approach:
  1. From the MLIT dataset, find transactions most similar to the
     subject property using a distance metric
  2. Weight recent transactions higher than older ones
  3. Return statistics (median, percentiles) of comp prices
  4. Compare subject property's listing price against comp range

Distance metric (weighted Euclidean):
  - Floor area difference (normalized)  : weight 0.25
  - Age difference                      : weight 0.30
  - Walking minutes difference          : weight 0.20
  - Layout category match               : weight 0.15
  - Same station bonus                  : weight 0.10

This is inspired by the actual 取引事例比較法 approach in Japanese
real estate appraisal (不動産鑑定評価基準).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.ml.data_pipeline import (
    LAYOUT_CAT_NAMES,
    LAYOUT_CATEGORIES,
    CleanRecord,
    MLDataset,
)

logger = logging.getLogger(__name__)


@dataclass
class CompTransaction:
    """A single comparable transaction with similarity score."""

    trade_price: int
    unit_price: int
    floor_area: float
    age_years: float
    walking_minutes: float
    layout: str
    station_name: str
    district: str
    trade_period: str
    similarity: float     # 0-1, higher is more similar
    time_weight: float    # Recency weight


@dataclass
class CompsResult:
    """Result of comparable transaction analysis."""

    n_comps: int               # Number of comparable transactions
    median_unit_price: int     # 中央値 ㎡単価
    p25_unit_price: int        # 25th percentile
    p75_unit_price: int        # 75th percentile
    weighted_avg_price: int    # 類似度加重平均 ㎡単価
    median_total_price: int    # 中央値 総額 (for subject area)
    price_range_low: int       # Estimated price range low
    price_range_high: int      # Estimated price range high
    deviation_pct: float | None  # Listing price vs comps median
    assessment: str            # 割安/適正/割高
    comps: list[CompTransaction]  # Top comparable transactions
    subject_area: float        # Subject property area (for display)
    search_criteria: str       # Human-readable search description


# ===================================================================
# Distance weights
# ===================================================================

W_AREA = 0.25
W_AGE = 0.30
W_WALK = 0.20
W_LAYOUT = 0.15
W_STATION = 0.10


# ===================================================================
# Public API
# ===================================================================

def find_comps(
    dataset: MLDataset,
    floor_area: float,
    age_years: float,
    walking_minutes: float,
    layout: str = "",
    station_name: str = "",
    listing_price: int | None = None,
    max_comps: int = 15,
    max_age_diff: float = 12.0,
    max_area_diff: float = 25.0,
) -> CompsResult | None:
    """Find comparable transactions for a subject property.

    Parameters
    ----------
    dataset : MLDataset
        MLIT transaction dataset.
    floor_area : float
        Subject property floor area (㎡).
    age_years : float
        Subject property age (years).
    walking_minutes : float
        Subject property walking minutes.
    layout : str
        Subject property layout (e.g. "3LDK").
    station_name : str
        Subject property nearest station.
    listing_price : int | None
        Listing price for comparison.
    max_comps : int
        Maximum number of comps to return.
    max_age_diff : float
        Maximum age difference to consider.
    max_area_diff : float
        Maximum area difference to consider.

    Returns
    -------
    CompsResult or None if insufficient comparable data.
    """
    if dataset.n_samples < 5:
        return None

    layout_upper = layout.upper().replace(" ", "") if layout else ""
    subject_layout_cat = LAYOUT_CATEGORIES.get(layout_upper, -1)

    # Max quarter index for recency weighting
    max_q = max(r.quarter_index for r in dataset.records) or 1

    # Score each record
    scored: list[tuple[float, float, CleanRecord]] = []
    for rec in dataset.records:
        # Hard filters: skip records too different
        area_diff = abs(rec.floor_area - floor_area)
        if area_diff > max_area_diff:
            continue
        age_diff = abs(rec.age_years - age_years)
        if age_diff > max_age_diff:
            continue

        # Distance components (normalized to ~0-1 range)
        d_area = area_diff / max(floor_area, 20)
        d_age = age_diff / 30.0
        d_walk = abs(rec.walking_minutes - walking_minutes) / 20.0

        # Layout distance: 0 if same cat, 0.5 if adjacent, 1.0 otherwise
        if subject_layout_cat >= 0:
            cat_diff = abs(rec.layout_cat - subject_layout_cat)
            d_layout = min(cat_diff / 3.0, 1.0)
        else:
            d_layout = 0.3  # Unknown layout, moderate penalty

        # Station bonus: 0 if same station, 0.5 if different
        if station_name and rec.station_name:
            same_station = (
                station_name in rec.station_name
                or rec.station_name in station_name
            )
            d_station = 0.0 if same_station else 0.5
        else:
            d_station = 0.3

        # Weighted distance
        distance = (
            W_AREA * d_area
            + W_AGE * d_age
            + W_WALK * d_walk
            + W_LAYOUT * d_layout
            + W_STATION * d_station
        )

        # Similarity (inverse of distance, 0-1)
        similarity = max(0.0, 1.0 - distance)

        # Time weight (more recent = higher weight)
        time_weight = 0.5 + 0.5 * (rec.quarter_index / max_q)

        # Combined score
        combined = similarity * time_weight

        scored.append((combined, similarity, rec))

    if len(scored) < 3:
        return None

    # Sort by combined score (descending)
    scored.sort(key=lambda x: x[0], reverse=True)

    # Take top comps
    top = scored[:max_comps]

    comps: list[CompTransaction] = []
    for combined, sim, rec in top:
        # Reconstruct layout string from category
        layout_str = LAYOUT_CAT_NAMES[rec.layout_cat]
        raw_layout = rec.raw.get("FloorPlan", layout_str)

        comps.append(CompTransaction(
            trade_price=rec.trade_price,
            unit_price=int(rec.unit_price),
            floor_area=rec.floor_area,
            age_years=rec.age_years,
            walking_minutes=rec.walking_minutes,
            layout=raw_layout,
            station_name=rec.station_name,
            district=rec.district,
            trade_period=rec.trade_period,
            similarity=round(sim, 3),
            time_weight=round(0.5 + 0.5 * (rec.quarter_index / max_q), 3),
        ))

    # Compute statistics using similarity-weighted values
    unit_prices = [c.unit_price for c in comps]
    weights = [c.similarity * c.time_weight for c in comps]
    total_w = sum(weights)

    weighted_avg = int(
        sum(up * w for up, w in zip(unit_prices, weights)) / total_w
    ) if total_w > 0 else int(sum(unit_prices) / len(unit_prices))

    sorted_prices = sorted(unit_prices)
    n = len(sorted_prices)
    median_up = sorted_prices[n // 2]
    p25 = sorted_prices[max(0, n // 4)]
    p75 = sorted_prices[min(n - 1, 3 * n // 4)]

    median_total = int(median_up * floor_area)
    range_low = int(p25 * floor_area)
    range_high = int(p75 * floor_area)

    # Deviation
    deviation = None
    assessment = "適正"
    if listing_price and listing_price > 0 and median_total > 0:
        deviation = round(
            (listing_price / median_total - 1) * 100, 1,
        )
        if deviation < -15:
            assessment = "かなり割安（類似取引比）"
        elif deviation < -8:
            assessment = "割安（類似取引比）"
        elif deviation < 8:
            assessment = "適正価格帯"
        elif deviation < 15:
            assessment = "やや割高（類似取引比）"
        else:
            assessment = "割高（類似取引比）"

    # Search criteria description
    criteria_parts = [f"{floor_area}㎡"]
    if age_years:
        criteria_parts.append(f"築{int(age_years)}年")
    if walking_minutes:
        criteria_parts.append(f"徒歩{int(walking_minutes)}分")
    if layout:
        criteria_parts.append(layout)
    criteria = " / ".join(criteria_parts)

    return CompsResult(
        n_comps=len(comps),
        median_unit_price=median_up,
        p25_unit_price=p25,
        p75_unit_price=p75,
        weighted_avg_price=weighted_avg,
        median_total_price=median_total,
        price_range_low=range_low,
        price_range_high=range_high,
        deviation_pct=deviation,
        assessment=assessment,
        comps=comps,
        subject_area=floor_area,
        search_criteria=criteria,
    )
