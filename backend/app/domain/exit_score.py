"""Exit-strategy score (出口スコア).

Rule-based scoring to evaluate how easy it is to rent out or sell a property.
Each factor yields 0-10 points.  Total is normalised to 0-100.
"""

from __future__ import annotations

from dataclasses import dataclass

FACTORS = [
    "station",
    "size",
    "layout",
    "age",
    "zoning",
    "hazard",
    "liquidity",
]


@dataclass(frozen=True)
class ExitScoreResult:
    station_score: int
    size_score: int
    layout_score: int
    age_score: int
    zoning_score: int
    hazard_score: int
    liquidity_score: int
    total_score: int  # 0-100


# ---------------------------------------------------------------------------
# Individual scoring functions (each returns 0-10)
# ---------------------------------------------------------------------------

def score_station(walking_minutes: int | None) -> int:
    """Closer to station = higher score."""
    if walking_minutes is None:
        return 5
    if walking_minutes <= 3:
        return 10
    if walking_minutes <= 5:
        return 9
    if walking_minutes <= 7:
        return 8
    if walking_minutes <= 10:
        return 6
    if walking_minutes <= 15:
        return 4
    return 2


def score_size(floor_area_sqm: float | None) -> int:
    """60-75 ㎡ is ideal for rental demand (2-3 LDK sweet spot)."""
    if floor_area_sqm is None:
        return 5
    if 60 <= floor_area_sqm <= 75:
        return 10
    if 50 <= floor_area_sqm < 60 or 75 < floor_area_sqm <= 85:
        return 8
    if 40 <= floor_area_sqm < 50 or 85 < floor_area_sqm <= 100:
        return 6
    if floor_area_sqm < 30:
        return 3
    return 4


def score_layout(layout: str | None) -> int:
    """2LDK/3LDK score highest for family rentals."""
    if layout is None:
        return 5
    upper = layout.upper().replace(" ", "")
    if upper in ("2LDK", "3LDK"):
        return 10
    if upper in ("1LDK", "2DK", "3DK"):
        return 7
    if upper in ("1DK", "1K", "4LDK"):
        return 5
    return 4


def score_age(built_year: int | None, current_year: int = 2026) -> int:
    """Newer is better for both rental demand and resale."""
    if built_year is None:
        return 5
    age = current_year - built_year
    if age <= 5:
        return 10
    if age <= 10:
        return 9
    if age <= 15:
        return 8
    if age <= 20:
        return 7
    if age <= 25:
        return 5
    if age <= 35:
        return 3
    return 1


def score_zoning(zoning_type: str | None) -> int:
    """Residential zones preferred; industrial deducted."""
    if zoning_type is None:
        return 5
    z = zoning_type.lower()
    if "商業" in z or "近隣商業" in z:
        return 9
    if "住居" in z:
        return 8
    if "準工業" in z:
        return 5
    if "工業" in z:
        return 3
    return 5


def score_hazard(hazard_flag: bool | None) -> int:
    """Simple binary: hazard area → deduction."""
    if hazard_flag is None:
        return 5
    return 3 if hazard_flag else 8


def score_liquidity(total_units: int | None) -> int:
    """Larger buildings have better long-term maintenance prospects."""
    if total_units is None:
        return 5
    if total_units >= 100:
        return 9
    if total_units >= 50:
        return 8
    if total_units >= 30:
        return 7
    if total_units >= 15:
        return 5
    return 3


# ---------------------------------------------------------------------------
# Aggregate
# ---------------------------------------------------------------------------

def calc_exit_score(
    walking_minutes: int | None = None,
    floor_area_sqm: float | None = None,
    layout: str | None = None,
    built_year: int | None = None,
    zoning_type: str | None = None,
    hazard_flag: bool | None = None,
    total_units: int | None = None,
    current_year: int = 2026,
) -> ExitScoreResult:
    """Calculate composite exit score (0-100)."""
    ss = score_station(walking_minutes)
    si = score_size(floor_area_sqm)
    sl = score_layout(layout)
    sa = score_age(built_year, current_year)
    sz = score_zoning(zoning_type)
    sh = score_hazard(hazard_flag)
    sq = score_liquidity(total_units)

    raw = ss + si + sl + sa + sz + sh + sq  # max 70
    total = int(raw / 70 * 100 + 0.5)

    return ExitScoreResult(
        station_score=ss,
        size_score=si,
        layout_score=sl,
        age_score=sa,
        zoning_score=sz,
        hazard_score=sh,
        liquidity_score=sq,
        total_score=min(total, 100),
    )
