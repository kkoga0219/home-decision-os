"""Tests for ML-calibrated rent estimation."""

from app.ml.data_pipeline import CleanRecord, MLDataset
from app.ml.rent_model import (
    CalibratedCapRates,
    MLRentEstimate,
    calibrate_cap_rates,
    estimate_rent_ml,
)


def _make_record(**overrides) -> CleanRecord:
    defaults = dict(
        trade_price=30_000_000,
        unit_price=461_538.0,
        floor_area=65.0,
        age_years=15.0,
        walking_minutes=7.0,
        layout_cat=6,
        station_name="塚口",
        district="塚口町",
        quarter_index=10,
        trade_period="2024年第2四半期",
    )
    defaults.update(overrides)
    return CleanRecord(**defaults)


def _make_dataset(records: list[CleanRecord]) -> MLDataset:
    return MLDataset(
        X=[[0] * 17 for _ in records],
        y=[r.unit_price for r in records],
        feature_names=["f"] * 17,
        records=records,
        station_popularity={"塚口": len(records)},
        quarter_labels=["Q1"],
    )


class TestCalibrateCapRates:
    def test_returns_calibrated_rates(self):
        records = [_make_record(age_years=i * 3) for i in range(20)]
        ds = _make_dataset(records)
        cap_rates = calibrate_cap_rates(ds)
        assert isinstance(cap_rates, CalibratedCapRates)
        assert cap_rates.base_cap_rate > 0
        assert len(cap_rates.age_coefficients) > 0

    def test_custom_prefecture_yield(self):
        records = [_make_record() for _ in range(20)]
        ds = _make_dataset(records)
        cap_rates = calibrate_cap_rates(
            ds,
            prefecture_base_yield=0.060,
        )
        assert cap_rates.base_cap_rate > 0


class TestEstimateRentML:
    def _get_cap_rates(self) -> CalibratedCapRates:
        records = [_make_record(age_years=5 + i * 2) for i in range(30)]
        ds = _make_dataset(records)
        return calibrate_cap_rates(ds)

    def test_returns_rent_estimate(self):
        cap_rates = self._get_cap_rates()
        result = estimate_rent_ml(
            cap_rates,
            price_jpy=30_000_000,
            floor_area=65.0,
            age_years=15.0,
            walking_minutes=7.0,
            layout="3LDK",
        )
        assert isinstance(result, MLRentEstimate)
        assert result.estimated_rent > 0
        assert result.low_estimate <= result.estimated_rent
        assert result.high_estimate >= result.estimated_rent
        assert result.gross_yield > 0

    def test_rent_positive_for_various_inputs(self):
        cap_rates = self._get_cap_rates()
        # Small 1R near station
        r1 = estimate_rent_ml(
            cap_rates,
            price_jpy=10_000_000,
            floor_area=25.0,
            age_years=5.0,
            walking_minutes=3.0,
            layout="1R",
        )
        assert r1.estimated_rent > 0

        # Large 4LDK far from station
        r2 = estimate_rent_ml(
            cap_rates,
            price_jpy=50_000_000,
            floor_area=90.0,
            age_years=30.0,
            walking_minutes=15.0,
            layout="4LDK",
        )
        assert r2.estimated_rent > 0

    def test_yield_reasonable(self):
        cap_rates = self._get_cap_rates()
        result = estimate_rent_ml(
            cap_rates,
            price_jpy=30_000_000,
            floor_area=65.0,
            age_years=15.0,
            walking_minutes=7.0,
        )
        # Gross yield should be between 1% and 15%
        assert 0.01 <= result.gross_yield <= 0.15
