"""Tests for price trend forecasting."""

from app.ml.data_pipeline import CleanRecord, MLDataset
from app.ml.trend_forecast import TrendForecastResult, forecast_price_trend


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


def _make_dataset(records: list[CleanRecord], n_quarters: int = 16) -> MLDataset:
    return MLDataset(
        X=[[0] * 17 for _ in records],
        y=[r.unit_price for r in records],
        feature_names=["f"] * 17,
        records=records,
        station_popularity={"塚口": len(records)},
        quarter_labels=[f"Q{i}" for i in range(n_quarters)],
    )


class TestTrendForecast:
    def test_returns_none_for_insufficient_data(self):
        """Too few quarters should return None."""
        records = [
            _make_record(quarter_index=0),
            _make_record(quarter_index=1),
        ]
        ds = _make_dataset(records, n_quarters=2)
        result = forecast_price_trend(ds)
        assert result is None

    def test_rising_market(self):
        """Prices increasing each quarter."""
        records = []
        for qi in range(12):
            for _ in range(5):
                price = 300_000 + qi * 10_000
                records.append(_make_record(
                    unit_price=price,
                    trade_price=int(price * 65),
                    quarter_index=qi,
                ))
        ds = _make_dataset(records, n_quarters=12)
        result = forecast_price_trend(ds)
        assert result is not None
        assert isinstance(result, TrendForecastResult)
        assert result.trend_pct_annual > 0
        assert "上昇" in result.trend_direction or result.trend_pct_annual > 0

    def test_declining_market(self):
        """Prices decreasing each quarter."""
        records = []
        for qi in range(12):
            for _ in range(5):
                price = 500_000 - qi * 15_000
                records.append(_make_record(
                    unit_price=price,
                    trade_price=int(price * 65),
                    quarter_index=qi,
                ))
        ds = _make_dataset(records, n_quarters=12)
        result = forecast_price_trend(ds)
        assert result is not None
        assert result.trend_pct_annual < 0

    def test_forecasts_exist(self):
        records = []
        for qi in range(12):
            for _ in range(5):
                records.append(_make_record(
                    unit_price=400_000 + qi * 5_000,
                    quarter_index=qi,
                ))
        ds = _make_dataset(records, n_quarters=12)
        result = forecast_price_trend(ds)
        assert result is not None
        assert len(result.forecasts) > 0

    def test_quarterly_history(self):
        records = []
        for qi in range(8):
            for _ in range(5):
                records.append(_make_record(quarter_index=qi))
        ds = _make_dataset(records, n_quarters=8)
        result = forecast_price_trend(ds)
        assert result is not None
        assert len(result.quarterly_history) > 0
