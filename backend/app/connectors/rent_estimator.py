"""Rent estimation connector.

Estimates expected monthly rent based on:
1. MLIT transaction data (actual trade prices in the area)
2. Simple yield-based model as fallback

This is a rule-based estimator for the MVP.
A future version could use ML regression trained on rental listing data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.connectors.base import BaseConnector, ConnectorResult

# Tokyo-metro and Kansai area average gross rental yields (from public data)
# Source: 不動産投資家調査 (Japan Real Estate Institute)
DEFAULT_GROSS_YIELDS = {
    "東京都": 0.042,   # 4.2%
    "大阪府": 0.050,   # 5.0%
    "兵庫県": 0.055,   # 5.5%
    "京都府": 0.050,
    "神奈川県": 0.048,
    "愛知県": 0.052,
    "福岡県": 0.053,
    "default": 0.055,
}

# Adjustment factors for property attributes
AGE_DISCOUNT = {
    (0, 5): 1.00,
    (6, 10): 0.97,
    (11, 15): 0.93,
    (16, 20): 0.88,
    (21, 25): 0.82,
    (26, 30): 0.75,
    (31, 999): 0.68,
}

STATION_PREMIUM = {
    (0, 3): 1.05,     # 駅3分以内: +5%
    (4, 5): 1.02,     # 駅5分以内: +2%
    (6, 7): 1.00,
    (8, 10): 0.97,
    (11, 15): 0.93,
    (16, 999): 0.88,
}


@dataclass
class RentEstimate:
    """Estimated monthly rent with confidence range."""
    estimated_rent: int      # 推定月額賃料
    low_estimate: int        # 悲観シナリオ
    high_estimate: int       # 楽観シナリオ
    gross_yield: float       # 使用した表面利回り
    method: str              # 推定方法の説明


class RentEstimatorConnector(BaseConnector):
    """Estimates monthly rent from property attributes + area data."""

    @property
    def name(self) -> str:
        return "賃料推定エンジン"

    async def fetch(
        self,
        price_jpy: int,
        floor_area_sqm: float | None = None,
        built_year: int | None = None,
        walking_minutes: int | None = None,
        prefecture: str = "",
        area_avg_unit_price: int | None = None,
    ) -> ConnectorResult:
        """Estimate rent based on property attributes.

        Parameters
        ----------
        price_jpy : int
            Property purchase price.
        floor_area_sqm : float | None
            Floor area in square meters.
        built_year : int | None
            Year the building was constructed.
        walking_minutes : int | None
            Minutes walk to nearest station.
        prefecture : str
            Prefecture name for yield lookup.
        area_avg_unit_price : int | None
            Average ㎡ unit price in the area (from MLIT data).
            If provided, used for cross-validation.
        """
        # Base gross yield for the area
        base_yield = DEFAULT_GROSS_YIELDS.get(prefecture, DEFAULT_GROSS_YIELDS["default"])

        # Adjust for building age
        current_year = 2026
        age = (current_year - built_year) if built_year else 15  # assume 15 if unknown
        age_factor = _lookup_range(AGE_DISCOUNT, age)

        # Adjust for station proximity
        walk = walking_minutes if walking_minutes is not None else 10
        station_factor = _lookup_range(STATION_PREMIUM, walk)

        # Adjusted yield
        adjusted_yield = base_yield * age_factor * station_factor

        # Monthly rent = price × annual_yield / 12
        annual_rent = int(price_jpy * adjusted_yield)
        monthly_rent = annual_rent // 12

        # Confidence range (±15%)
        low = int(monthly_rent * 0.85)
        high = int(monthly_rent * 1.15)

        # Cross-validate with area unit price if available
        method = f"利回りベース推定 (表面利回り {adjusted_yield:.1%})"
        if area_avg_unit_price and floor_area_sqm:
            market_based = int(area_avg_unit_price * floor_area_sqm * adjusted_yield / 12)
            # Blend: 60% yield-based, 40% market-based
            monthly_rent = int(monthly_rent * 0.6 + market_based * 0.4)
            low = int(monthly_rent * 0.85)
            high = int(monthly_rent * 1.15)
            method += f" + 相場補正 (㎡単価{area_avg_unit_price:,}円)"

        estimate = RentEstimate(
            estimated_rent=monthly_rent,
            low_estimate=low,
            high_estimate=high,
            gross_yield=adjusted_yield,
            method=method,
        )

        return ConnectorResult(
            success=True,
            source=self.name,
            data={
                "estimated_rent": estimate.estimated_rent,
                "low_estimate": estimate.low_estimate,
                "high_estimate": estimate.high_estimate,
                "gross_yield": round(estimate.gross_yield, 4),
                "method": estimate.method,
            },
        )


def _lookup_range(table: dict[tuple[int, int], float], value: int) -> float:
    """Look up a value in a range-keyed dict."""
    for (lo, hi), factor in table.items():
        if lo <= value <= hi:
            return factor
    return 1.0
