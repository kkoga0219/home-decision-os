"""Tests for ML-enhanced exit score."""

from app.ml.data_pipeline import CleanRecord, MLDataset
from app.ml.exit_score_ml import MLExitScoreResult, calc_ml_exit_score


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


class TestFallbackScore:
    """When no MLIT data, returns rule-based fallback."""

    def test_no_dataset(self):
        result = calc_ml_exit_score(
            dataset=None,
            walking_minutes=7.0,
            floor_area=65.0,
            layout="3LDK",
            age_years=15.0,
        )
        assert isinstance(result, MLExitScoreResult)
        assert result.data_quality.startswith("推定")
        assert result.n_transactions == 0
        assert 0 <= result.total_score <= 100

    def test_small_dataset_fallback(self):
        records = [_make_record() for _ in range(5)]
        ds = _make_dataset(records)
        result = calc_ml_exit_score(
            dataset=ds,
            walking_minutes=7.0,
            floor_area=65.0,
            layout="3LDK",
            age_years=15.0,
        )
        assert result.data_quality.startswith("推定")

    def test_close_station_high_score(self):
        result = calc_ml_exit_score(
            dataset=None,
            walking_minutes=3.0,
            floor_area=65.0,
            layout="3LDK",
            age_years=10.0,
        )
        assert result.station_score >= 8

    def test_far_station_low_score(self):
        result = calc_ml_exit_score(
            dataset=None,
            walking_minutes=20.0,
            floor_area=65.0,
            layout="3LDK",
            age_years=15.0,
        )
        assert result.station_score <= 4


class TestMLExitScore:
    """When MLIT data is available, uses data-driven scoring."""

    def _make_rich_dataset(self, n: int = 100) -> MLDataset:
        """Create a dataset with varied records for testing."""
        records = []
        for i in range(n):
            qi = i % 16
            records.append(
                _make_record(
                    trade_price=25_000_000 + (i % 10) * 1_000_000,
                    unit_price=(25_000_000 + (i % 10) * 1_000_000) / 65.0,
                    floor_area=55.0 + (i % 5) * 5,
                    age_years=5.0 + (i % 20),
                    walking_minutes=3.0 + (i % 10),
                    quarter_index=qi,
                )
            )
        return _make_dataset(records, n_quarters=16)

    def test_data_driven_quality(self):
        ds = self._make_rich_dataset()
        result = calc_ml_exit_score(
            dataset=ds,
            walking_minutes=7.0,
            floor_area=65.0,
            layout="3LDK",
            age_years=15.0,
        )
        assert "MLIT" in result.data_quality or "実" in result.data_quality
        assert result.n_transactions == 100

    def test_score_range(self):
        ds = self._make_rich_dataset()
        result = calc_ml_exit_score(
            dataset=ds,
            walking_minutes=7.0,
            floor_area=65.0,
            layout="3LDK",
            age_years=15.0,
        )
        assert 0 <= result.total_score <= 100

    def test_liquidity_high_volume(self):
        ds = self._make_rich_dataset(200)
        result = calc_ml_exit_score(
            dataset=ds,
            walking_minutes=7.0,
            floor_area=65.0,
            layout="3LDK",
            age_years=15.0,
        )
        assert result.liquidity_score >= 5

    def test_comparable_count(self):
        ds = self._make_rich_dataset()
        result = calc_ml_exit_score(
            dataset=ds,
            walking_minutes=7.0,
            floor_area=65.0,
            layout="3LDK",
            age_years=15.0,
            station_name="塚口",
        )
        assert result.comparable_count >= 0

    def test_momentum_scoring(self):
        """Rising prices should produce higher momentum score."""
        records = []
        for i in range(80):
            qi = i % 16
            # Prices increase with later quarters
            price = 25_000_000 + qi * 500_000
            records.append(
                _make_record(
                    trade_price=price,
                    unit_price=price / 65.0,
                    quarter_index=qi,
                )
            )
        ds = _make_dataset(records, n_quarters=16)
        result = calc_ml_exit_score(
            dataset=ds,
            walking_minutes=7.0,
            floor_area=65.0,
            layout="3LDK",
            age_years=15.0,
        )
        assert result.momentum_score >= 5  # Rising market

    def test_assessment_text(self):
        ds = self._make_rich_dataset()
        result = calc_ml_exit_score(
            dataset=ds,
            walking_minutes=7.0,
            floor_area=65.0,
            layout="3LDK",
            age_years=15.0,
        )
        assert "出口戦略" in result.assessment
