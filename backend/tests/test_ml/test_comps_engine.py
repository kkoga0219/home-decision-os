"""Tests for comparable transaction analysis engine."""

from app.ml.comps_engine import CompsResult, find_comps
from app.ml.data_pipeline import CleanRecord, MLDataset


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
        quarter_labels=["2024Q1"],
    )


class TestFindComps:
    def test_returns_none_if_too_few(self):
        records = [_make_record() for _ in range(3)]
        ds = _make_dataset(records)
        result = find_comps(ds, floor_area=65.0, age_years=15.0, walking_minutes=7.0)
        # Fewer than the minimum sample size (5) → not enough data → None.
        assert result is None

    def test_insufficient_data(self):
        records = [_make_record() for _ in range(2)]
        ds = _make_dataset(records)
        result = find_comps(ds, floor_area=65.0, age_years=15.0, walking_minutes=7.0)
        assert result is None

    def test_basic_comps(self):
        records = [
            _make_record(
                trade_price=25_000_000 + i * 1_000_000,
                unit_price=(25_000_000 + i * 1_000_000) / 65.0,
                floor_area=60.0 + i * 2,
                age_years=12.0 + i,
                quarter_index=8 + i,
            )
            for i in range(10)
        ]
        ds = _make_dataset(records)
        result = find_comps(
            ds,
            floor_area=65.0,
            age_years=15.0,
            walking_minutes=7.0,
            layout="3LDK",
            station_name="塚口",
            listing_price=28_000_000,
        )
        assert result is not None
        assert isinstance(result, CompsResult)
        assert result.n_comps > 0
        assert result.median_unit_price > 0
        assert result.median_total_price > 0
        assert result.price_range_low <= result.median_total_price
        assert result.price_range_high >= result.median_total_price

    def test_deviation_assessment(self):
        # All comps at ~400k/sqm → listing at 30M for 65sqm = 461k/sqm = ~15% above
        records = [
            _make_record(
                trade_price=26_000_000,
                unit_price=400_000.0,
                floor_area=65.0,
                age_years=15.0,
            )
            for _ in range(10)
        ]
        ds = _make_dataset(records)
        result = find_comps(
            ds,
            floor_area=65.0,
            age_years=15.0,
            walking_minutes=7.0,
            listing_price=30_000_000,
        )
        assert result is not None
        assert result.deviation_pct is not None
        assert result.deviation_pct > 0  # listing above market

    def test_hard_filter_area(self):
        """Records too far in area should be excluded."""
        records = [_make_record(floor_area=120.0, unit_price=300_000.0) for _ in range(10)]
        ds = _make_dataset(records)
        result = find_comps(
            ds,
            floor_area=30.0,  # Very different from 120㎡
            age_years=15.0,
            walking_minutes=7.0,
            max_area_diff=25.0,
        )
        assert result is None  # All filtered out

    def test_similarity_ordering(self):
        """More similar records should rank higher."""
        records = [
            _make_record(
                floor_area=65.0, age_years=15.0, walking_minutes=7.0, quarter_index=12
            ),  # Identical
            _make_record(
                floor_area=80.0, age_years=25.0, walking_minutes=15.0, quarter_index=1
            ),  # Very different
        ] * 3  # Need at least 3 records after filtering
        ds = _make_dataset(records)
        result = find_comps(
            ds,
            floor_area=65.0,
            age_years=15.0,
            walking_minutes=7.0,
        )
        assert result is not None
        # First comp should be more similar
        assert result.comps[0].similarity >= result.comps[-1].similarity
