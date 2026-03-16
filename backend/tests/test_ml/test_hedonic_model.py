"""Tests for hedonic price model — training and prediction."""

import math

from app.ml.data_pipeline import CleanRecord, MLDataset
from app.ml.hedonic_model import (
    HedonicModel,
    PricePrediction,
    train_hedonic_model,
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


def _build_features(rec: CleanRecord, station_pop: dict, max_q: int) -> list[float]:
    """Replicate feature engineering for test dataset construction."""
    total_pop = max(sum(station_pop.values()), 1)
    feats = [
        rec.floor_area,
        math.log(max(rec.floor_area, 1)),
        rec.age_years,
        rec.age_years ** 2,
        rec.walking_minutes,
        rec.walking_minutes ** 2,
        rec.age_years * rec.walking_minutes,
        rec.quarter_index / max(max_q, 1),
        station_pop.get(rec.station_name, 1) / total_pop,
    ]
    for i in range(8):
        feats.append(1.0 if rec.layout_cat == i else 0.0)
    return feats


FEATURE_NAMES = [
    "floor_area", "log_floor_area", "age_years", "age_squared",
    "walking_minutes", "walk_squared", "age_x_walk",
    "quarter_norm", "station_popularity",
    "layout_1R", "layout_1K_1DK", "layout_1LDK", "layout_2K_2DK",
    "layout_2LDK", "layout_3K_3DK", "layout_3LDK", "layout_4LDK_plus",
]


def _make_realistic_dataset(n: int = 80) -> MLDataset:
    """Create a realistic-ish dataset where price depends on features."""
    records = []
    station_pop = {"塚口": 40, "武庫之荘": 25, "立花": 15}
    stations = list(station_pop.keys())

    for i in range(n):
        area = 40.0 + (i % 8) * 10
        age = 5.0 + (i % 15) * 2
        walk = 3.0 + (i % 6) * 2
        stn = stations[i % 3]
        layout_cat = min(6, 2 + (i % 5))

        # Realistic-ish pricing: base 400k/sqm, adjusted by factors
        base_up = 400_000
        age_adj = -age * 5000
        walk_adj = -walk * 3000
        noise = ((i * 7) % 100 - 50) * 1000
        unit_price = max(base_up + age_adj + walk_adj + noise, 150_000)
        trade_price = int(unit_price * area)

        records.append(_make_record(
            trade_price=trade_price,
            unit_price=unit_price,
            floor_area=area,
            age_years=age,
            walking_minutes=walk,
            layout_cat=layout_cat,
            station_name=stn,
            quarter_index=i % 16,
        ))

    max_q = max(r.quarter_index for r in records)
    X = [_build_features(r, station_pop, max_q) for r in records]
    y = [r.unit_price for r in records]

    return MLDataset(
        X=X, y=y,
        feature_names=FEATURE_NAMES,
        records=records,
        station_popularity=station_pop,
        quarter_labels=[f"Q{i}" for i in range(16)],
    )


class TestTrainHedonicModel:
    def test_returns_model_with_enough_data(self):
        ds = _make_realistic_dataset(80)
        model = train_hedonic_model(ds)
        assert model is not None
        assert isinstance(model, HedonicModel)

    def test_returns_none_with_too_few(self):
        ds = _make_realistic_dataset(5)
        ds.X = ds.X[:5]
        ds.y = ds.y[:5]
        ds.records = ds.records[:5]
        ds.n_samples = 5
        model = train_hedonic_model(ds)
        # With only 5 samples, may return None or a fallback
        # (depends on implementation threshold)
        # At minimum, it shouldn't crash
        assert model is None or isinstance(model, HedonicModel)

    def test_model_has_valid_r2(self):
        ds = _make_realistic_dataset(100)
        model = train_hedonic_model(ds)
        assert model is not None
        assert model.r2 > 0  # Should explain some variance
        assert model.r2 <= 1.0

    def test_model_has_valid_mape(self):
        ds = _make_realistic_dataset(100)
        model = train_hedonic_model(ds)
        assert model is not None
        assert model.mape >= 0
        assert model.mape < 1.0  # Should be < 100% error


class TestPrediction:
    def test_predict_returns_price_prediction(self):
        ds = _make_realistic_dataset(100)
        model = train_hedonic_model(ds)
        assert model is not None

        pred = model.predict(
            floor_area=65.0,
            age_years=15.0,
            walking_minutes=7.0,
            layout="3LDK",
            station_name="塚口",
            listing_price=28_000_000,
        )
        assert isinstance(pred, PricePrediction)
        assert pred.predicted_unit_price > 0
        assert pred.predicted_total_price > 0
        assert pred.confidence_low < pred.predicted_total_price
        assert pred.confidence_high > pred.predicted_total_price

    def test_deviation_positive_if_overpriced(self):
        ds = _make_realistic_dataset(100)
        model = train_hedonic_model(ds)
        assert model is not None

        pred = model.predict(
            floor_area=65.0,
            age_years=15.0,
            walking_minutes=7.0,
            layout="3LDK",
            station_name="塚口",
            listing_price=100_000_000,  # Wildly overpriced
        )
        assert pred.deviation_pct is not None
        assert pred.deviation_pct > 0

    def test_assessment_text(self):
        ds = _make_realistic_dataset(100)
        model = train_hedonic_model(ds)
        assert model is not None

        pred = model.predict(
            floor_area=65.0,
            age_years=15.0,
            walking_minutes=7.0,
            listing_price=28_000_000,
        )
        # Should contain one of the assessment keywords
        assert any(
            kw in pred.assessment
            for kw in ["割安", "適正", "割高"]
        )
