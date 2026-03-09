"""Tests for rent estimation connector."""

import asyncio

from app.connectors.rent_estimator import RentEstimatorConnector


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class TestRentEstimator:
    def test_basic_estimate(self):
        c = RentEstimatorConnector()
        result = _run(c.fetch(price_jpy=35_000_000, prefecture="兵庫県"))
        assert result.success
        rent = result.data["estimated_rent"]
        assert 100_000 < rent < 250_000  # reasonable range for 35M property

    def test_new_building_higher_rent(self):
        c = RentEstimatorConnector()
        new = _run(c.fetch(price_jpy=35_000_000, built_year=2024, prefecture="兵庫県"))
        old = _run(c.fetch(price_jpy=35_000_000, built_year=1990, prefecture="兵庫県"))
        assert new.data["estimated_rent"] > old.data["estimated_rent"]

    def test_station_close_premium(self):
        c = RentEstimatorConnector()
        close = _run(c.fetch(price_jpy=35_000_000, walking_minutes=3))
        far = _run(c.fetch(price_jpy=35_000_000, walking_minutes=20))
        assert close.data["estimated_rent"] > far.data["estimated_rent"]

    def test_confidence_range(self):
        c = RentEstimatorConnector()
        result = _run(c.fetch(price_jpy=30_000_000))
        assert result.data["low_estimate"] < result.data["estimated_rent"]
        assert result.data["high_estimate"] > result.data["estimated_rent"]

    def test_tokyo_lower_yield(self):
        c = RentEstimatorConnector()
        tokyo = _run(c.fetch(price_jpy=50_000_000, prefecture="東京都"))
        hyogo = _run(c.fetch(price_jpy=50_000_000, prefecture="兵庫県"))
        # Tokyo has lower yield → lower rent relative to price
        assert tokyo.data["gross_yield"] < hyogo.data["gross_yield"]
