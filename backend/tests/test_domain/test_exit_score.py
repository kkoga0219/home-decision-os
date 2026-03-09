"""Tests for exit score calculation."""

from app.domain.exit_score import (
    calc_exit_score,
    score_age,
    score_layout,
    score_liquidity,
    score_size,
    score_station,
)


class TestIndividualScores:
    def test_station_close(self):
        assert score_station(3) == 10

    def test_station_far(self):
        assert score_station(20) == 2

    def test_station_none(self):
        assert score_station(None) == 5

    def test_size_sweet_spot(self):
        assert score_size(65.0) == 10

    def test_size_small(self):
        assert score_size(25.0) == 3

    def test_layout_family(self):
        assert score_layout("3LDK") == 10

    def test_layout_single(self):
        assert score_layout("1K") == 5

    def test_age_new(self):
        assert score_age(2024, 2026) == 10

    def test_age_old(self):
        assert score_age(1980, 2026) == 1

    def test_liquidity_large(self):
        assert score_liquidity(150) == 9

    def test_liquidity_small(self):
        assert score_liquidity(10) == 3


class TestCalcExitScore:
    def test_ideal_property(self):
        result = calc_exit_score(
            walking_minutes=3,
            floor_area_sqm=65.0,
            layout="3LDK",
            built_year=2022,
            zoning_type="近隣商業地域",
            hazard_flag=False,
            total_units=100,
        )
        assert result.total_score >= 90

    def test_poor_property(self):
        result = calc_exit_score(
            walking_minutes=25,
            floor_area_sqm=25.0,
            layout="ワンルーム",
            built_year=1975,
            zoning_type="工業地域",
            hazard_flag=True,
            total_units=8,
        )
        assert result.total_score <= 30

    def test_all_none(self):
        result = calc_exit_score()
        assert result.total_score == 50  # all defaults to 5 → 35/70 = 50%

    def test_score_range(self):
        result = calc_exit_score(walking_minutes=5, floor_area_sqm=70.0)
        assert 0 <= result.total_score <= 100
