"""Built-in area statistics database.

Provides baseline market data for major Kansai / Tokyo metro areas
without requiring an external API key.

Data is sourced from publicly available aggregate statistics:
- 不動産経済研究所 (Real Estate Economic Institute) summaries
- 国交省 不動産情報ライブラリ public summaries
- 令和5年地価公示 (2023 Official Land Price)

This is a FALLBACK when MLIT API key is not configured.
When the API key is available, real transaction data takes precedence.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.connectors.base import BaseConnector, ConnectorResult


@dataclass
class AreaData:
    """Market statistics for an area."""
    area_name: str
    prefecture: str
    avg_unit_price_sqm: int       # 平均㎡単価 (中古マンション)
    avg_price_70sqm: int          # 70㎡換算平均価格
    avg_rent_per_sqm: int         # 平均賃料㎡単価
    avg_gross_yield: float        # 平均表面利回り
    transaction_count_annual: int  # 年間取引件数（推定）
    price_trend: str              # "上昇" / "横ばい" / "下落"
    population_trend: str         # "増加" / "横ばい" / "減少"
    source: str                   # データソース
    note: str = ""


# -------------------------------------------------------------------
# Built-in area database (key = city/station name)
# -------------------------------------------------------------------

AREA_DB: dict[str, AreaData] = {
    # --- 兵庫県尼崎市 (user's primary search area) ---
    "尼崎市": AreaData(
        area_name="尼崎市",
        prefecture="兵庫県",
        avg_unit_price_sqm=380_000,
        avg_price_70sqm=26_600_000,
        avg_rent_per_sqm=1_550,
        avg_gross_yield=0.055,
        transaction_count_annual=1200,
        price_trend="上昇",
        population_trend="横ばい",
        source="不動産経済研究所/国交省公示地価(2023-2024概算)",
        note="大阪へのアクセス良好。JR/阪急沿線で人気上昇中",
    ),
    "塚口": AreaData(
        area_name="塚口（JR/阪急）",
        prefecture="兵庫県",
        avg_unit_price_sqm=420_000,
        avg_price_70sqm=29_400_000,
        avg_rent_per_sqm=1_650,
        avg_gross_yield=0.053,
        transaction_count_annual=250,
        price_trend="上昇",
        population_trend="増加",
        source="MLIT取引価格集計(2023-2024概算)/SUUMO相場データ",
        note="再開発で注目エリア。阪急塚口駅周辺は特に人気",
    ),
    "武庫之荘": AreaData(
        area_name="武庫之荘",
        prefecture="兵庫県",
        avg_unit_price_sqm=400_000,
        avg_price_70sqm=28_000_000,
        avg_rent_per_sqm=1_600,
        avg_gross_yield=0.054,
        transaction_count_annual=180,
        price_trend="上昇",
        population_trend="横ばい",
        source="MLIT取引価格集計(2023-2024概算)",
    ),
    "立花": AreaData(
        area_name="立花",
        prefecture="兵庫県",
        avg_unit_price_sqm=350_000,
        avg_price_70sqm=24_500_000,
        avg_rent_per_sqm=1_450,
        avg_gross_yield=0.057,
        transaction_count_annual=150,
        price_trend="横ばい",
        population_trend="横ばい",
        source="MLIT取引価格集計(2023-2024概算)",
    ),
    # --- 大阪市 ---
    "大阪市": AreaData(
        area_name="大阪市",
        prefecture="大阪府",
        avg_unit_price_sqm=520_000,
        avg_price_70sqm=36_400_000,
        avg_rent_per_sqm=1_900,
        avg_gross_yield=0.050,
        transaction_count_annual=8000,
        price_trend="上昇",
        population_trend="横ばい",
        source="不動産経済研究所(2024概算)",
    ),
    "梅田": AreaData(
        area_name="梅田・北区",
        prefecture="大阪府",
        avg_unit_price_sqm=800_000,
        avg_price_70sqm=56_000_000,
        avg_rent_per_sqm=2_800,
        avg_gross_yield=0.042,
        transaction_count_annual=600,
        price_trend="上昇",
        population_trend="増加",
        source="不動産経済研究所(2024概算)",
    ),
    # --- 神戸市 ---
    "神戸市": AreaData(
        area_name="神戸市",
        prefecture="兵庫県",
        avg_unit_price_sqm=360_000,
        avg_price_70sqm=25_200_000,
        avg_rent_per_sqm=1_500,
        avg_gross_yield=0.056,
        transaction_count_annual=3000,
        price_trend="横ばい",
        population_trend="減少",
        source="不動産経済研究所(2024概算)",
    ),
    "三宮": AreaData(
        area_name="三宮・中央区",
        prefecture="兵庫県",
        avg_unit_price_sqm=500_000,
        avg_price_70sqm=35_000_000,
        avg_rent_per_sqm=1_900,
        avg_gross_yield=0.048,
        transaction_count_annual=400,
        price_trend="上昇",
        population_trend="横ばい",
        source="不動産経済研究所(2024概算)",
    ),
    # --- 西宮市 ---
    "西宮市": AreaData(
        area_name="西宮市",
        prefecture="兵庫県",
        avg_unit_price_sqm=450_000,
        avg_price_70sqm=31_500_000,
        avg_rent_per_sqm=1_700,
        avg_gross_yield=0.051,
        transaction_count_annual=800,
        price_trend="上昇",
        population_trend="増加",
        source="不動産経済研究所(2024概算)",
    ),
    # --- 東京 (reference) ---
    "東京23区": AreaData(
        area_name="東京23区",
        prefecture="東京都",
        avg_unit_price_sqm=1_050_000,
        avg_price_70sqm=73_500_000,
        avg_rent_per_sqm=3_500,
        avg_gross_yield=0.042,
        transaction_count_annual=25000,
        price_trend="上昇",
        population_trend="増加",
        source="不動産経済研究所(2024概算)",
    ),
}


class AreaStatsConnector(BaseConnector):
    """Look up built-in area statistics."""

    @property
    def name(self) -> str:
        return "エリア統計データベース"

    async def fetch(
        self,
        station_name: str = "",
        city_name: str = "",
        address_text: str = "",
        **kwargs: Any,
    ) -> ConnectorResult:
        """Find the best matching area data.

        Searches by station name first, then city name, then address substring.
        """
        # Try exact station match
        if station_name and station_name in AREA_DB:
            return self._ok(AREA_DB[station_name])

        # Try city match
        if city_name and city_name in AREA_DB:
            return self._ok(AREA_DB[city_name])

        # Try fuzzy match against all keys and area names
        search_terms = [station_name, city_name, address_text]
        for term in search_terms:
            if not term:
                continue
            for key, area in AREA_DB.items():
                if key in term or term in key or term in area.area_name:
                    return self._ok(area)

        # Try extracting city from address
        if address_text:
            import re
            m = re.search(r"(.{2,4}[市区町村])", address_text)
            if m:
                city = m.group(1)
                if city in AREA_DB:
                    return self._ok(AREA_DB[city])

        return ConnectorResult(
            success=False,
            source=self.name,
            errors=[f"エリアデータが見つかりません: station={station_name}, city={city_name}"],
            data={"available_areas": list(AREA_DB.keys())},
        )

    def _ok(self, area: AreaData) -> ConnectorResult:
        return ConnectorResult(
            success=True,
            source=self.name,
            data={
                "area_name": area.area_name,
                "prefecture": area.prefecture,
                "avg_unit_price_sqm": area.avg_unit_price_sqm,
                "avg_price_70sqm": area.avg_price_70sqm,
                "avg_rent_per_sqm": area.avg_rent_per_sqm,
                "avg_gross_yield": area.avg_gross_yield,
                "transaction_count_annual": area.transaction_count_annual,
                "price_trend": area.price_trend,
                "population_trend": area.population_trend,
                "source": area.source,
                "note": area.note,
            },
        )
