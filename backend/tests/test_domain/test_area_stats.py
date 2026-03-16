"""Tests for area stats connector with MLIT override support."""

import asyncio

from app.connectors.area_stats import AreaStatsConnector


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class TestAreaStatsConnectorFallback:
    """Tests for hardcoded fallback data."""

    def test_exact_station_match(self):
        c = AreaStatsConnector()
        result = _run(c.fetch(station_name="塚口"))
        assert result.success
        assert result.data["area_name"] == "塚口（JR/阪急）"
        assert result.data["avg_unit_price_sqm"] > 0

    def test_city_match(self):
        c = AreaStatsConnector()
        result = _run(c.fetch(city_name="尼崎市"))
        assert result.success
        assert result.data["area_name"] == "尼崎市"

    def test_fuzzy_match_from_address(self):
        c = AreaStatsConnector()
        result = _run(c.fetch(address_text="兵庫県尼崎市塚口本町1丁目"))
        assert result.success

    def test_not_found(self):
        c = AreaStatsConnector()
        result = _run(c.fetch(station_name="存在しない駅"))
        assert not result.success
        assert "available_areas" in result.data

    def test_fallback_has_data_quality_label(self):
        c = AreaStatsConnector()
        result = _run(c.fetch(station_name="塚口"))
        assert result.data.get("data_quality") == "フォールバック（概算値）"


class TestAreaStatsConnectorMLITOverride:
    """Tests for MLIT real data override."""

    def test_mlit_override_takes_precedence(self):
        mlit_data = {
            "area_name": "塚口駅周辺(実データ)",
            "prefecture": "兵庫県",
            "avg_unit_price_sqm": 450_000,
            "median_unit_price_sqm": 440_000,
            "avg_price_70sqm": 31_500_000,
            "avg_rent_per_sqm": None,
            "avg_gross_yield": None,
            "transaction_count": 80,
            "price_trend": "上昇",
            "price_trend_pct": 3.5,
            "quarterly_prices": [],
            "source": "国交省API",
            "data_quality": "MLIT実取引データ",
        }
        c = AreaStatsConnector(mlit_override=mlit_data)
        result = _run(c.fetch(station_name="塚口"))
        assert result.success
        # Should use MLIT data, not fallback
        assert result.data["area_name"] == "塚口駅周辺(実データ)"
        assert result.data["avg_unit_price_sqm"] == 450_000

    def test_mlit_override_fills_rent_defaults(self):
        mlit_data = {
            "area_name": "テスト",
            "prefecture": "兵庫県",
            "avg_unit_price_sqm": 400_000,
            "avg_rent_per_sqm": None,
            "avg_gross_yield": None,
        }
        c = AreaStatsConnector(mlit_override=mlit_data)
        result = _run(c.fetch())
        assert result.success
        # Should fill in defaults for rent and yield
        assert result.data["avg_rent_per_sqm"] > 0
        assert result.data["avg_gross_yield"] > 0
        assert "推定値" in result.data.get("rent_source", "")

    def test_no_override_uses_fallback(self):
        c = AreaStatsConnector(mlit_override=None)
        result = _run(c.fetch(station_name="塚口"))
        assert result.success
        assert "フォールバック" in result.data.get("data_quality", "")
