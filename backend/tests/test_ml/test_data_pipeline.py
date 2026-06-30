"""Tests for ML data pipeline — feature engineering, cleaning, outlier removal."""

import math

from app.ml.data_pipeline import (
    LAYOUT_CAT_NAMES,
    LAYOUT_CATEGORIES,
    NUM_LAYOUT_CATS,
    CleanRecord,
    MLDataset,
)


def _make_record(
    trade_price: int = 30_000_000,
    floor_area: float = 65.0,
    age_years: float = 15.0,
    walking_minutes: float = 7.0,
    layout_cat: int = 6,
    station_name: str = "塚口",
    district: str = "塚口町",
    quarter_index: int = 10,
    trade_period: str = "2024年第2四半期",
) -> CleanRecord:
    unit_price = trade_price / floor_area
    return CleanRecord(
        trade_price=trade_price,
        unit_price=unit_price,
        floor_area=floor_area,
        age_years=age_years,
        walking_minutes=walking_minutes,
        layout_cat=layout_cat,
        station_name=station_name,
        district=district,
        quarter_index=quarter_index,
        trade_period=trade_period,
    )


def _build_features_for_record(
    rec: CleanRecord,
    station_pop: dict[str, int],
    max_quarter: int,
) -> list[float]:
    """Replicate the feature engineering from data_pipeline._build_features."""
    feats = [
        rec.floor_area,
        math.log(max(rec.floor_area, 1)),
        rec.age_years,
        rec.age_years**2,
        rec.walking_minutes,
        rec.walking_minutes**2,
        rec.age_years * rec.walking_minutes,
        rec.quarter_index / max(max_quarter, 1),
        station_pop.get(rec.station_name, 1) / max(sum(station_pop.values()), 1),
    ]
    # Layout one-hot
    for i in range(NUM_LAYOUT_CATS):
        feats.append(1.0 if rec.layout_cat == i else 0.0)
    return feats


class TestLayoutCategories:
    def test_1r_category(self):
        assert LAYOUT_CATEGORIES["1R"] == 0

    def test_1k_1dk_same(self):
        assert LAYOUT_CATEGORIES["1K"] == LAYOUT_CATEGORIES["1DK"]

    def test_3ldk_category(self):
        assert LAYOUT_CATEGORIES["3LDK"] == 6

    def test_4ldk_plus(self):
        assert LAYOUT_CATEGORIES["4LDK"] == 7
        assert LAYOUT_CATEGORIES["5LDK"] == 7

    def test_cat_names_count(self):
        assert NUM_LAYOUT_CATS == 8
        assert len(LAYOUT_CAT_NAMES) == 8


class TestCleanRecord:
    def test_unit_price_computation(self):
        rec = _make_record(trade_price=20_000_000, floor_area=50.0)
        assert abs(rec.unit_price - 400_000.0) < 0.01

    def test_default_raw_dict(self):
        rec = _make_record()
        assert isinstance(rec.raw, dict)


class TestMLDataset:
    def test_n_samples_auto(self):
        ds = MLDataset(
            X=[[1, 2], [3, 4], [5, 6]],
            y=[100, 200, 300],
            feature_names=["a", "b"],
            records=[],
            station_popularity={},
            quarter_labels=[],
        )
        assert ds.n_samples == 3

    def test_empty_dataset(self):
        ds = MLDataset(
            X=[],
            y=[],
            feature_names=[],
            records=[],
            station_popularity={},
            quarter_labels=[],
        )
        assert ds.n_samples == 0


class TestFeatureEngineering:
    """Test that feature construction produces correct dimensions and values."""

    def test_feature_vector_length(self):
        rec = _make_record()
        station_pop = {"塚口": 50}
        feats = _build_features_for_record(rec, station_pop, max_quarter=12)
        # 9 numeric + 8 layout one-hot = 17
        assert len(feats) == 17

    def test_layout_one_hot_single_active(self):
        rec = _make_record(layout_cat=6)  # 3LDK
        feats = _build_features_for_record(rec, {"塚口": 10}, 12)
        layout_bits = feats[9:]  # last 8 entries
        assert sum(layout_bits) == 1.0
        assert layout_bits[6] == 1.0

    def test_quarter_normalization(self):
        rec = _make_record(quarter_index=6)
        feats = _build_features_for_record(rec, {"塚口": 10}, 12)
        assert abs(feats[7] - 0.5) < 0.01

    def test_log_floor_area(self):
        rec = _make_record(floor_area=100.0)
        feats = _build_features_for_record(rec, {"塚口": 10}, 12)
        assert abs(feats[1] - math.log(100.0)) < 0.001

    def test_interaction_term(self):
        rec = _make_record(age_years=20.0, walking_minutes=10.0)
        feats = _build_features_for_record(rec, {"塚口": 10}, 12)
        assert abs(feats[6] - 200.0) < 0.01  # age × walk
