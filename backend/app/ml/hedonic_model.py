"""Hedonic Price Model (ヘドニック価格モデル).

Predicts the *fair market unit price* (㎡単価) of a condo based on
its physical attributes and location, using actual MLIT transaction
data as training examples.

Model choice: **Gradient Boosting Regressor**
- Handles non-linear relationships naturally (age depreciation curve,
  distance premium cliff at ~7 min, etc.)
- Robust to outliers (Huber loss)
- Feature importance is interpretable
- Trains in <500ms on typical dataset sizes (200-2000 rows)
- No GPU or heavy dependencies needed

Alternative considered: LightGBM would be ~3x faster on >5k rows,
but sklearn GBR is sufficient for our typical 200-2000 row datasets
and avoids an extra dependency.

Usage flow:
    1. fetch_ml_dataset() → MLDataset
    2. train_hedonic_model(dataset) → HedonicModel
    3. model.predict(floor_area, age, walk, layout, station) → fair price
    4. model.evaluate(listing_price) → % deviation from fair price
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Any

from app.ml.data_pipeline import (
    LAYOUT_CATEGORIES,
    NUM_LAYOUT_CATS,
    CleanRecord,
    MLDataset,
)

logger = logging.getLogger(__name__)

# Use pure Python implementations to avoid sklearn dependency issues
# in environments where it may not be installed yet.
# We provide a GBR wrapper that falls back to a ridge regression
# implemented from scratch if sklearn is unavailable.

_HAS_SKLEARN = False
try:
    from sklearn.ensemble import GradientBoostingRegressor
    from sklearn.model_selection import cross_val_score
    _HAS_SKLEARN = True
except ImportError:
    pass


@dataclass
class PricePrediction:
    """Result of a hedonic price prediction."""

    predicted_unit_price: int     # 予測㎡単価 (JPY/㎡)
    predicted_total_price: int    # 予測適正価格 (JPY)
    confidence_low: int           # 下限 (JPY)
    confidence_high: int          # 上限 (JPY)
    deviation_pct: float | None   # 実勢価格との乖離率 (%, +means overpriced)
    assessment: str               # "割安" / "適正" / "やや割高" / "割高"
    model_r2: float               # モデルの決定係数
    model_mape: float             # Mean Absolute Percentage Error
    training_samples: int         # 学習データ件数
    top_features: list[dict]      # 重要特徴量 Top-5
    method: str                   # モデル名


@dataclass
class HedonicModel:
    """Trained hedonic price model with prediction capabilities."""

    _model: Any
    _feature_names: list[str]
    _dataset: MLDataset
    r2_score: float
    mape: float
    residual_std: float  # 残差の標準偏差 (for confidence interval)
    method: str

    def predict(
        self,
        floor_area: float,
        age_years: float,
        walking_minutes: float,
        layout: str = "",
        station_name: str = "",
        listing_price: int | None = None,
    ) -> PricePrediction:
        """Predict fair market price for a property.

        Parameters
        ----------
        floor_area : float
            Floor area in ㎡.
        age_years : float
            Building age in years.
        walking_minutes : float
            Walking minutes to nearest station.
        layout : str
            Layout string (e.g. "3LDK").
        station_name : str
            Nearest station name (for popularity feature).
        listing_price : int | None
            Actual listing price for deviation calculation.
        """
        features = self._make_features(
            floor_area, age_years, walking_minutes, layout, station_name,
        )

        pred_unit = float(self._model.predict([features])[0])
        pred_unit = max(pred_unit, 50_000)  # Floor at 5万/㎡

        pred_total = int(pred_unit * floor_area)

        # Confidence interval using residual std
        margin = self.residual_std * 1.5  # ~87% CI
        conf_low = int((pred_unit - margin) * floor_area)
        conf_high = int((pred_unit + margin) * floor_area)
        conf_low = max(conf_low, 0)

        # Deviation from listing price
        deviation = None
        assessment = "適正"
        if listing_price and listing_price > 0:
            deviation = round(
                (listing_price / pred_total - 1) * 100, 1,
            )
            if deviation < -15:
                assessment = "かなり割安"
            elif deviation < -8:
                assessment = "割安"
            elif deviation < 8:
                assessment = "適正"
            elif deviation < 15:
                assessment = "やや割高"
            else:
                assessment = "割高"

        # Feature importance
        top_feats = self._get_feature_importance()

        return PricePrediction(
            predicted_unit_price=int(pred_unit),
            predicted_total_price=pred_total,
            confidence_low=conf_low,
            confidence_high=conf_high,
            deviation_pct=deviation,
            assessment=assessment,
            model_r2=self.r2_score,
            model_mape=self.mape,
            training_samples=self._dataset.n_samples,
            top_features=top_feats,
            method=self.method,
        )

    def _make_features(
        self,
        floor_area: float,
        age_years: float,
        walking_minutes: float,
        layout: str,
        station_name: str,
    ) -> list[float]:
        """Build feature vector matching training format."""
        log_area = math.log(max(floor_area, 1.0))
        layout_upper = layout.upper().replace(" ", "") if layout else ""
        layout_cat = LAYOUT_CATEGORIES.get(layout_upper, 3)

        stn_pop = self._dataset.station_popularity.get(station_name, 0)
        if stn_pop == 0 and station_name:
            # Fuzzy match
            for stn, cnt in self._dataset.station_popularity.items():
                if station_name in stn or stn in station_name:
                    stn_pop = cnt
                    break
        if stn_pop == 0:
            # Use median popularity
            counts = list(self._dataset.station_popularity.values())
            stn_pop = sorted(counts)[len(counts) // 2] if counts else 10

        # Use latest quarter for prediction
        max_q = max(r.quarter_index for r in self._dataset.records)
        q_norm = 1.0  # Predict at current time

        row = [
            floor_area,
            log_area,
            age_years,
            age_years ** 2,
            walking_minutes,
            walking_minutes ** 2,
            age_years * walking_minutes,
            q_norm,
            float(stn_pop),
        ]

        # One-hot layout
        for cat_idx in range(NUM_LAYOUT_CATS):
            row.append(1.0 if layout_cat == cat_idx else 0.0)

        return row

    def _get_feature_importance(self) -> list[dict]:
        """Get top-5 feature importances."""
        if hasattr(self._model, "feature_importances_"):
            importances = self._model.feature_importances_
        else:
            return []

        pairs = list(zip(self._feature_names, importances))
        pairs.sort(key=lambda x: x[1], reverse=True)

        name_map = {
            "floor_area": "面積",
            "log_floor_area": "面積(log)",
            "age_years": "築年数",
            "age_squared": "築年数²",
            "walking_minutes": "駅徒歩",
            "walk_squared": "徒歩²",
            "age_x_walk": "築年×徒歩",
            "quarter_norm": "市場トレンド",
            "station_popularity": "駅人気度",
        }
        for name in LAYOUT_CATEGORIES:
            name_map[f"layout_{name}"] = f"間取り({name})"

        return [
            {
                "feature": name_map.get(name, name),
                "importance": round(float(imp), 4),
            }
            for name, imp in pairs[:5]
        ]


# ===================================================================
# Training
# ===================================================================

def train_hedonic_model(dataset: MLDataset) -> HedonicModel | None:
    """Train a hedonic price model on MLIT transaction data.

    Returns None if insufficient data or training fails.
    """
    if dataset.n_samples < 15:
        logger.warning(
            "Too few samples for hedonic model: %d", dataset.n_samples,
        )
        return None

    if _HAS_SKLEARN:
        return _train_sklearn_gbr(dataset)
    else:
        return _train_fallback_ridge(dataset)


def _train_sklearn_gbr(dataset: MLDataset) -> HedonicModel:
    """Train using sklearn GradientBoostingRegressor."""
    X = dataset.X
    y = dataset.y

    # Hyperparameters tuned for typical 200-2000 sample real estate data
    n_estimators = min(200, max(50, dataset.n_samples // 3))
    max_depth = 4 if dataset.n_samples > 200 else 3
    min_samples_leaf = max(3, dataset.n_samples // 50)

    model = GradientBoostingRegressor(
        n_estimators=n_estimators,
        max_depth=max_depth,
        learning_rate=0.08,
        min_samples_leaf=min_samples_leaf,
        subsample=0.8,
        loss="huber",       # Robust to outliers
        alpha=0.9,          # Huber quantile
        random_state=42,
    )

    model.fit(X, y)

    # Evaluate with 5-fold CV (if enough data)
    n_folds = min(5, max(2, dataset.n_samples // 20))
    if n_folds >= 2 and dataset.n_samples >= 30:
        cv_scores = cross_val_score(
            model, X, y, cv=n_folds, scoring="r2",
        )
        r2 = float(cv_scores.mean())
    else:
        # Simple train R²
        from sklearn.metrics import r2_score
        r2 = float(r2_score(y, model.predict(X)))

    # MAPE
    predictions = model.predict(X)
    abs_pct_errors = [
        abs(pred - actual) / actual
        for pred, actual in zip(predictions, y)
        if actual > 0
    ]
    mape = (
        sum(abs_pct_errors) / len(abs_pct_errors)
        if abs_pct_errors else 0.5
    )

    # Residual std for confidence intervals
    residuals = [pred - actual for pred, actual in zip(predictions, y)]
    mean_resid = sum(residuals) / len(residuals)
    resid_std = (
        sum((r - mean_resid) ** 2 for r in residuals) / len(residuals)
    ) ** 0.5

    return HedonicModel(
        _model=model,
        _feature_names=dataset.feature_names,
        _dataset=dataset,
        r2_score=round(r2, 4),
        mape=round(mape, 4),
        residual_std=resid_std,
        method=f"GradientBoosting(n={n_estimators},d={max_depth})",
    )


def _train_fallback_ridge(dataset: MLDataset) -> HedonicModel:
    """Pure-Python ridge regression fallback (no sklearn needed).

    Uses closed-form solution: w = (X'X + λI)^{-1} X'y
    Less accurate than GBR but still much better than fixed multipliers.
    """
    X_raw = dataset.X
    y = dataset.y
    n = len(y)
    p = len(X_raw[0])

    # Standardize features
    means = [0.0] * p
    stds = [1.0] * p
    for j in range(p):
        col = [X_raw[i][j] for i in range(n)]
        m = sum(col) / n
        means[j] = m
        var = sum((v - m) ** 2 for v in col) / n
        stds[j] = var ** 0.5 if var > 0 else 1.0

    X_std = []
    for i in range(n):
        row = [(X_raw[i][j] - means[j]) / stds[j] for j in range(p)]
        X_std.append(row)

    y_mean = sum(y) / n
    y_centered = [yi - y_mean for yi in y]

    # X'X
    xtx = [[0.0] * p for _ in range(p)]
    for i in range(n):
        for j in range(p):
            for k in range(p):
                xtx[j][k] += X_std[i][j] * X_std[i][k]

    # Add ridge penalty
    lam = 1.0 * n  # λ = 1.0 per sample
    for j in range(p):
        xtx[j][j] += lam

    # X'y
    xty = [0.0] * p
    for i in range(n):
        for j in range(p):
            xty[j] += X_std[i][j] * y_centered[i]

    # Solve via Gaussian elimination
    weights = _solve_linear(xtx, xty)

    # Build a simple predictor object
    class RidgePredictor:
        def __init__(self, w, means, stds, y_mean):
            self.w = w
            self.means = means
            self.stds = stds
            self.y_mean = y_mean
            # Approximate feature importances from |weights|
            total = sum(abs(wi) for wi in w)
            self.feature_importances_ = [
                abs(wi) / total if total > 0 else 0 for wi in w
            ]

        def predict(self, X_new):
            results = []
            for row in X_new:
                std_row = [
                    (row[j] - self.means[j]) / self.stds[j]
                    for j in range(len(row))
                ]
                pred = self.y_mean + sum(
                    std_row[j] * self.w[j] for j in range(len(self.w))
                )
                results.append(pred)
            return results

        def fit(self, X, y):
            pass  # Already fitted

    model = RidgePredictor(weights, means, stds, y_mean)

    # Compute metrics
    predictions = model.predict(X_raw)
    ss_res = sum((p - a) ** 2 for p, a in zip(predictions, y))
    ss_tot = sum((a - y_mean) ** 2 for a in y)
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0

    abs_pct_errors = [
        abs(p - a) / a for p, a in zip(predictions, y) if a > 0
    ]
    mape = (
        sum(abs_pct_errors) / len(abs_pct_errors)
        if abs_pct_errors else 0.5
    )

    residuals = [p - a for p, a in zip(predictions, y)]
    mean_r = sum(residuals) / len(residuals)
    resid_std = (
        sum((r - mean_r) ** 2 for r in residuals) / len(residuals)
    ) ** 0.5

    return HedonicModel(
        _model=model,
        _feature_names=dataset.feature_names,
        _dataset=dataset,
        r2_score=round(r2, 4),
        mape=round(mape, 4),
        residual_std=resid_std,
        method="Ridge(fallback,λ=1.0)",
    )


def _solve_linear(A: list[list[float]], b: list[float]) -> list[float]:
    """Solve Ax = b using Gaussian elimination with partial pivoting."""
    n = len(b)
    # Augmented matrix
    M = [A[i][:] + [b[i]] for i in range(n)]

    for col in range(n):
        # Partial pivoting
        max_row = col
        for row in range(col + 1, n):
            if abs(M[row][col]) > abs(M[max_row][col]):
                max_row = row
        M[col], M[max_row] = M[max_row], M[col]

        if abs(M[col][col]) < 1e-12:
            continue

        # Eliminate below
        for row in range(col + 1, n):
            factor = M[row][col] / M[col][col]
            for j in range(col, n + 1):
                M[row][j] -= factor * M[col][j]

    # Back substitution
    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        if abs(M[i][i]) < 1e-12:
            continue
        x[i] = M[i][n]
        for j in range(i + 1, n):
            x[i] -= M[i][j] * x[j]
        x[i] /= M[i][i]

    return x
