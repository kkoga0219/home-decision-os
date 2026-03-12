"""Rent estimation connector.

Three-tier estimation approach (uses the best available data):

Tier 1: SUUMO実賃料データ (if rental_market_data provided)
  → Uses actual average rents by layout from SUUMO相場ページ
  → Adjusts for property-specific attributes (age, area, station distance)
  → Confidence: HIGH (±10%)

Tier 2: 相場ベース推定 (if area_avg_unit_price provided)
  → Blends yield-based model with area ㎡ unit price
  → Confidence: MEDIUM (±15%)

Tier 3: 利回りベース推定 (fallback)
  → Uses prefecture-level gross yield × price
  → Adjusts for age, station distance
  → Confidence: LOW (±20%)
"""

from __future__ import annotations

from dataclasses import dataclass

from app.connectors.base import BaseConnector, ConnectorResult

# -------------------------------------------------------------------
# Prefecture-level gross yields
# Source: 不動産投資家調査 (Japan Real Estate Institute, 2024)
# -------------------------------------------------------------------
DEFAULT_GROSS_YIELDS = {
    "東京都": 0.042,
    "大阪府": 0.050,
    "兵庫県": 0.055,
    "京都府": 0.050,
    "神奈川県": 0.048,
    "愛知県": 0.052,
    "福岡県": 0.053,
    "default": 0.055,
}

# -------------------------------------------------------------------
# Age discount factors
# Source: 三井不動産リアルティ「中古マンション築年数と価格・賃料の関係」
# These represent the rent retention rate vs. new construction
# -------------------------------------------------------------------
AGE_DISCOUNT = {
    (0, 3): 1.00,    # 新築同等
    (4, 7): 0.97,    # 築浅
    (8, 12): 0.93,   # 築10年前後: 大規模修繕前
    (13, 17): 0.88,  # 築15年前後: 大規模修繕後なら維持
    (18, 22): 0.82,  # 築20年前後: 設備の古さが影響
    (23, 27): 0.76,  # 築25年前後: 旧耐震基準ボーダー
    (28, 32): 0.70,  # 築30年前後: リノベ物件は例外
    (33, 40): 0.64,  # 築35年前後
    (41, 999): 0.58, # 築40年超
}

# -------------------------------------------------------------------
# Station proximity premium/discount
# Source: 東京カンテイ「駅距離と資産性」レポート (2023)
# -------------------------------------------------------------------
STATION_PREMIUM = {
    (0, 3): 1.05,     # 駅3分以内: +5%
    (4, 5): 1.02,     # 駅5分以内: +2%
    (6, 7): 1.00,     # 基準
    (8, 10): 0.97,    # 徒歩10分まで: -3%
    (11, 15): 0.92,   # バス便距離: -8%
    (16, 20): 0.87,   # バス必須: -13%
    (21, 999): 0.82,  # 遠距離: -18%
}

# -------------------------------------------------------------------
# Floor area adjustment (larger units → lower ㎡ rent)
# Source: 賃貸住宅市場レポート 一般的な傾向値
# -------------------------------------------------------------------
AREA_ADJUSTMENT = {
    (0, 25): 1.10,    # コンパクト: ㎡単価高い
    (26, 40): 1.05,   # 単身向け
    (41, 55): 1.00,   # 基準 (DINKS)
    (56, 70): 0.97,   # ファミリー
    (71, 85): 0.94,   # 広めファミリー
    (86, 999): 0.90,  # 大型: ㎡単価下がる
}


@dataclass
class RentEstimate:
    """Estimated monthly rent with confidence range."""
    estimated_rent: int
    low_estimate: int
    high_estimate: int
    gross_yield: float
    method: str
    confidence: str  # "high", "medium", "low"


class RentEstimatorConnector(BaseConnector):
    """Estimates monthly rent from property attributes + market data."""

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
        layout: str = "",
        rental_market_data: dict | None = None,
    ) -> ConnectorResult:
        """Estimate rent using the best available data tier.

        Parameters
        ----------
        price_jpy : int
            Property purchase price.
        floor_area_sqm : float | None
            Floor area in square meters.
        built_year : int | None
            Year built.
        walking_minutes : int | None
            Minutes walk to nearest station.
        prefecture : str
            Prefecture name for yield lookup.
        area_avg_unit_price : int | None
            Average ㎡ unit price in the area.
        layout : str
            Layout string (e.g. "3LDK") for SUUMO rent lookup.
        rental_market_data : dict | None
            Real rental market data from SuumoMarketConnector.
            Contains rents_by_layout, family_avg_rent, etc.
        """
        current_year = 2026
        age = (current_year - built_year) if built_year else 15
        walk = walking_minutes if walking_minutes is not None else 10
        area = floor_area_sqm if floor_area_sqm else 65

        age_factor = _lookup_range(AGE_DISCOUNT, age)
        station_factor = _lookup_range(STATION_PREMIUM, walk)
        area_factor = _lookup_range(AREA_ADJUSTMENT, int(area))

        # -------------------------------------------------------
        # Tier 1: SUUMO real rent data
        # -------------------------------------------------------
        if rental_market_data and rental_market_data.get("rents_by_layout"):
            estimate = self._tier1_suumo(
                rental_market_data, layout, area,
                age_factor, station_factor, area_factor, price_jpy,
            )
            if estimate:
                return self._to_result(estimate)

        # -------------------------------------------------------
        # Tier 2: Area unit price blend
        # -------------------------------------------------------
        if area_avg_unit_price and floor_area_sqm:
            estimate = self._tier2_blend(
                price_jpy, area_avg_unit_price, floor_area_sqm,
                age_factor, station_factor, area_factor, prefecture,
            )
            return self._to_result(estimate)

        # -------------------------------------------------------
        # Tier 3: Yield-based fallback
        # -------------------------------------------------------
        estimate = self._tier3_yield(
            price_jpy, age_factor, station_factor, area_factor, prefecture,
        )
        return self._to_result(estimate)

    def _tier1_suumo(
        self,
        rental_data: dict,
        layout: str,
        area: float,
        age_factor: float,
        station_factor: float,
        area_factor: float,
        price_jpy: int,
    ) -> RentEstimate | None:
        """Tier 1: Use actual SUUMO rent data by layout."""
        rents = rental_data.get("rents_by_layout", {})

        # Try exact layout match
        base_rent = None
        if layout and layout.upper() in rents:
            base_rent = rents[layout.upper()]

        # Try family average
        if not base_rent:
            base_rent = rental_data.get("family_avg_rent")

        # Try area average
        if not base_rent:
            base_rent = rental_data.get("area_avg_rent")

        if not base_rent:
            return None

        # Adjust for property-specific attributes
        # SUUMO rents are "market average" so we adjust relative to average conditions
        # Average property: ~15 years old, 7 min walk, 60㎡
        avg_age_factor = _lookup_range(AGE_DISCOUNT, 15)
        avg_station_factor = _lookup_range(STATION_PREMIUM, 7)
        avg_area_factor = _lookup_range(AREA_ADJUSTMENT, 60)

        relative_adjustment = (
            (age_factor / avg_age_factor)
            * (station_factor / avg_station_factor)
            * (area_factor / avg_area_factor)
        )
        adjusted_rent = int(base_rent * relative_adjustment)

        # Compute implied yield
        implied_yield = (adjusted_rent * 12) / price_jpy if price_jpy > 0 else 0

        method_parts = [f"SUUMO実賃料データ (基準: {base_rent:,}円/月)"]
        if abs(relative_adjustment - 1.0) > 0.02:
            method_parts.append(f"物件調整 ×{relative_adjustment:.2f}")

        return RentEstimate(
            estimated_rent=adjusted_rent,
            low_estimate=int(adjusted_rent * 0.90),
            high_estimate=int(adjusted_rent * 1.10),
            gross_yield=round(implied_yield, 4),
            method=" → ".join(method_parts),
            confidence="high",
        )

    def _tier2_blend(
        self,
        price_jpy: int,
        area_avg_unit_price: int,
        floor_area_sqm: float,
        age_factor: float,
        station_factor: float,
        area_factor: float,
        prefecture: str,
    ) -> RentEstimate:
        """Tier 2: Blend yield-based with area market data."""
        base_yield = DEFAULT_GROSS_YIELDS.get(prefecture, DEFAULT_GROSS_YIELDS["default"])
        adjusted_yield = base_yield * age_factor * station_factor * area_factor

        # Yield-based estimate
        yield_rent = int(price_jpy * adjusted_yield / 12)

        # Market-based estimate (area ㎡ unit price × area × yield)
        market_rent = int(area_avg_unit_price * floor_area_sqm * adjusted_yield / 12)

        # Blend: 50/50 (both have similar reliability at this tier)
        blended = int(yield_rent * 0.5 + market_rent * 0.5)

        return RentEstimate(
            estimated_rent=blended,
            low_estimate=int(blended * 0.85),
            high_estimate=int(blended * 1.15),
            gross_yield=round(adjusted_yield, 4),
            method=f"相場ブレンド推定 (利回り{adjusted_yield:.1%} + ㎡単価{area_avg_unit_price:,}円)",
            confidence="medium",
        )

    def _tier3_yield(
        self,
        price_jpy: int,
        age_factor: float,
        station_factor: float,
        area_factor: float,
        prefecture: str,
    ) -> RentEstimate:
        """Tier 3: Pure yield-based fallback."""
        base_yield = DEFAULT_GROSS_YIELDS.get(prefecture, DEFAULT_GROSS_YIELDS["default"])
        adjusted_yield = base_yield * age_factor * station_factor * area_factor
        monthly_rent = int(price_jpy * adjusted_yield / 12)

        return RentEstimate(
            estimated_rent=monthly_rent,
            low_estimate=int(monthly_rent * 0.80),
            high_estimate=int(monthly_rent * 1.20),
            gross_yield=round(adjusted_yield, 4),
            method=f"利回りベース推定 (表面利回り {adjusted_yield:.1%}) ※精度低",
            confidence="low",
        )

    def _to_result(self, estimate: RentEstimate) -> ConnectorResult:
        return ConnectorResult(
            success=True,
            source=self.name,
            data={
                "estimated_rent": estimate.estimated_rent,
                "low_estimate": estimate.low_estimate,
                "high_estimate": estimate.high_estimate,
                "gross_yield": estimate.gross_yield,
                "method": estimate.method,
                "confidence": estimate.confidence,
            },
        )


def _lookup_range(table: dict[tuple[int, int], float], value: int) -> float:
    """Look up a value in a range-keyed dict."""
    for (lo, hi), factor in table.items():
        if lo <= value <= hi:
            return factor
    return 1.0
