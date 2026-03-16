"""Unified Valuation Engine (統合評価エンジン).

Orchestrates all ML modules to produce a comprehensive property
valuation using MLIT transaction data.

This is the single entry point that the API layer calls.
It handles:
  1. Fetching and caching MLIT data
  2. Training hedonic model on the fly
  3. Running comps analysis
  4. Price trend forecasting
  5. ML-enhanced rent estimation
  6. ML-enhanced exit score

The result is a rich valuation report that replaces the old
"simple area average comparison" approach.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from app.config import settings
from app.connectors.mlit_transaction import (
    CITY_CODES,
    PREFECTURE_CODES,
    city_name_to_code,
    prefecture_name_to_code,
)
from app.ml.comps_engine import CompsResult, find_comps
from app.ml.data_pipeline import (
    MLDataset,
    fetch_ml_dataset,
    fetch_ml_dataset_multi_city,
)
from app.ml.exit_score_ml import MLExitScoreResult, calc_ml_exit_score
from app.ml.hedonic_model import (
    HedonicModel,
    PricePrediction,
    train_hedonic_model,
)
from app.ml.rent_model import (
    CalibratedCapRates,
    MLRentEstimate,
    calibrate_cap_rates,
    estimate_rent_ml,
)
from app.ml.trend_forecast import (
    TrendForecastResult,
    forecast_price_trend,
)

logger = logging.getLogger(__name__)

# In-memory cache for datasets (keyed by prefecture+city+period)
_dataset_cache: dict[str, MLDataset] = {}
_model_cache: dict[str, HedonicModel] = {}


@dataclass
class ValuationReport:
    """Comprehensive ML-based property valuation."""

    # Hedonic price prediction
    hedonic: PricePrediction | None = None

    # Comparable transactions
    comps: CompsResult | None = None

    # Trend forecast
    trend: TrendForecastResult | None = None

    # ML rent estimate
    rent: MLRentEstimate | None = None
    cap_rates: CalibratedCapRates | None = None

    # ML exit score
    exit_score: MLExitScoreResult | None = None

    # Metadata
    mlit_available: bool = False
    dataset_size: int = 0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to API-friendly dict."""
        result: dict[str, Any] = {
            "mlit_available": self.mlit_available,
            "dataset_size": self.dataset_size,
            "errors": self.errors,
        }

        if self.hedonic:
            result["hedonic"] = {
                "predicted_unit_price": self.hedonic.predicted_unit_price,
                "predicted_total_price": self.hedonic.predicted_total_price,
                "confidence_low": self.hedonic.confidence_low,
                "confidence_high": self.hedonic.confidence_high,
                "deviation_pct": self.hedonic.deviation_pct,
                "assessment": self.hedonic.assessment,
                "model_r2": self.hedonic.model_r2,
                "model_mape": self.hedonic.model_mape,
                "training_samples": self.hedonic.training_samples,
                "top_features": self.hedonic.top_features,
                "method": self.hedonic.method,
            }

        if self.comps:
            result["comps"] = {
                "n_comps": self.comps.n_comps,
                "median_unit_price": self.comps.median_unit_price,
                "p25_unit_price": self.comps.p25_unit_price,
                "p75_unit_price": self.comps.p75_unit_price,
                "weighted_avg_price": self.comps.weighted_avg_price,
                "median_total_price": self.comps.median_total_price,
                "price_range_low": self.comps.price_range_low,
                "price_range_high": self.comps.price_range_high,
                "deviation_pct": self.comps.deviation_pct,
                "assessment": self.comps.assessment,
                "search_criteria": self.comps.search_criteria,
                "top_comps": [
                    {
                        "trade_price": c.trade_price,
                        "unit_price": c.unit_price,
                        "floor_area": c.floor_area,
                        "age_years": c.age_years,
                        "walking_minutes": c.walking_minutes,
                        "layout": c.layout,
                        "station_name": c.station_name,
                        "district": c.district,
                        "trade_period": c.trade_period,
                        "similarity": c.similarity,
                    }
                    for c in self.comps.comps[:8]
                ],
            }

        if self.trend:
            result["trend"] = {
                "current_unit_price": self.trend.current_unit_price,
                "trend_direction": self.trend.trend_direction,
                "trend_pct_annual": self.trend.trend_pct_annual,
                "acceleration": self.trend.acceleration,
                "volatility": self.trend.volatility,
                "n_quarters": self.trend.n_quarters,
                "n_transactions": self.trend.n_transactions,
                "confidence_note": self.trend.confidence_note,
                "forecasts": [
                    {
                        "period": f.period_label,
                        "predicted": f.predicted_unit_price,
                        "low": f.confidence_low,
                        "high": f.confidence_high,
                    }
                    for f in self.trend.forecasts
                ],
                "history": self.trend.quarterly_history,
            }

        if self.rent:
            result["ml_rent"] = {
                "estimated_rent": self.rent.estimated_rent,
                "low_estimate": self.rent.low_estimate,
                "high_estimate": self.rent.high_estimate,
                "gross_yield": self.rent.gross_yield,
                "confidence": self.rent.confidence,
                "method": self.rent.method,
                "cap_rate": self.rent.cap_rate_used,
                "adjustments": self.rent.adjustments,
            }

        if self.exit_score:
            result["ml_exit_score"] = {
                "total_score": self.exit_score.total_score,
                "assessment": self.exit_score.assessment,
                "liquidity": {
                    "score": self.exit_score.liquidity_score,
                    "detail": self.exit_score.liquidity_detail,
                },
                "price_retention": {
                    "score": self.exit_score.price_retention_score,
                    "detail": self.exit_score.price_retention_detail,
                },
                "momentum": {
                    "score": self.exit_score.momentum_score,
                    "detail": self.exit_score.momentum_detail,
                },
                "demand_match": {
                    "score": self.exit_score.demand_match_score,
                    "detail": self.exit_score.demand_match_detail,
                },
                "station_score": self.exit_score.station_score,
                "size_score": self.exit_score.size_score,
                "layout_score": self.exit_score.layout_score,
                "n_transactions": self.exit_score.n_transactions,
                "data_quality": self.exit_score.data_quality,
                "comparable_count": self.exit_score.comparable_count,
            }

        return result


# ===================================================================
# Public API
# ===================================================================

async def run_valuation(
    price_jpy: int,
    floor_area: float = 65.0,
    age_years: float = 15.0,
    walking_minutes: float = 10.0,
    layout: str = "",
    station_name: str = "",
    city_name: str = "",
    prefecture: str = "兵庫県",
    rental_market_data: dict | None = None,
) -> ValuationReport:
    """Run full ML valuation pipeline.

    This is the main entry point for the API layer.
    Gracefully handles missing MLIT API key by returning
    a report with only rule-based scores.
    """
    report = ValuationReport()
    api_key = settings.mlit_api_key

    if not api_key:
        report.errors.append(
            "MLIT APIキー未設定: ML評価にはHDOS_MLIT_API_KEYが必要です"
        )
        # Return rule-based exit score at minimum
        report.exit_score = calc_ml_exit_score(
            dataset=None,
            walking_minutes=walking_minutes,
            floor_area=floor_area,
            layout=layout,
            age_years=age_years,
            station_name=station_name,
        )
        return report

    # Resolve codes
    pref_code = prefecture_name_to_code(prefecture)
    if not pref_code:
        pref_code = "28"  # Default: Hyogo
    city_code = city_name_to_code(city_name) if city_name else ""

    # If no city code, try to infer from station name
    if not city_code and station_name:
        city_code = _infer_city_code(station_name, pref_code)

    # --- Fetch MLIT data (with caching) ---
    cache_key = f"{pref_code}:{city_code}:20201:20254"
    dataset = _dataset_cache.get(cache_key)

    if dataset is None:
        try:
            if city_code:
                # Try primary city + neighboring cities for more data
                neighboring = _get_neighboring_cities(city_code)
                if neighboring:
                    dataset = await fetch_ml_dataset_multi_city(
                        api_key, pref_code, [city_code] + neighboring,
                        station_name=station_name,
                    )
                else:
                    dataset = await fetch_ml_dataset(
                        api_key, pref_code, city_code,
                        station_name=station_name,
                    )
            else:
                # Prefecture-wide (slower, more data)
                dataset = await fetch_ml_dataset(
                    api_key, pref_code, "",
                    station_name=station_name,
                )

            if dataset:
                _dataset_cache[cache_key] = dataset
        except Exception as e:
            report.errors.append(f"MLIT data fetch error: {e!s}")

    if dataset is None:
        report.errors.append("MLIT取引データを取得できませんでした")
        report.exit_score = calc_ml_exit_score(
            dataset=None,
            walking_minutes=walking_minutes,
            floor_area=floor_area,
            layout=layout,
            age_years=age_years,
            station_name=station_name,
        )
        return report

    report.mlit_available = True
    report.dataset_size = dataset.n_samples

    # --- Run all analyses concurrently ---
    # 1. Train hedonic model (or use cached)
    model_key = cache_key
    model = _model_cache.get(model_key)
    if model is None:
        model = train_hedonic_model(dataset)
        if model:
            _model_cache[model_key] = model

    # Run analyses
    try:
        if model:
            report.hedonic = model.predict(
                floor_area=floor_area,
                age_years=age_years,
                walking_minutes=walking_minutes,
                layout=layout,
                station_name=station_name,
                listing_price=price_jpy,
            )
    except Exception as e:
        report.errors.append(f"Hedonic model error: {e!s}")

    try:
        report.comps = find_comps(
            dataset,
            floor_area=floor_area,
            age_years=age_years,
            walking_minutes=walking_minutes,
            layout=layout,
            station_name=station_name,
            listing_price=price_jpy,
        )
    except Exception as e:
        report.errors.append(f"Comps error: {e!s}")

    try:
        report.trend = forecast_price_trend(dataset)
    except Exception as e:
        report.errors.append(f"Trend forecast error: {e!s}")

    try:
        pref_yield = {
            "兵庫県": 0.055, "大阪府": 0.050, "東京都": 0.042,
            "京都府": 0.050, "神奈川県": 0.048,
        }.get(prefecture, 0.055)

        cap_rates = calibrate_cap_rates(
            dataset,
            rental_market_data=rental_market_data,
            prefecture_base_yield=pref_yield,
        )
        report.cap_rates = cap_rates

        report.rent = estimate_rent_ml(
            cap_rates,
            price_jpy=price_jpy,
            floor_area=floor_area,
            age_years=age_years,
            walking_minutes=walking_minutes,
            layout=layout,
            station_name=station_name,
        )
    except Exception as e:
        report.errors.append(f"Rent model error: {e!s}")

    try:
        report.exit_score = calc_ml_exit_score(
            dataset,
            walking_minutes=walking_minutes,
            floor_area=floor_area,
            layout=layout,
            age_years=age_years,
            station_name=station_name,
        )
    except Exception as e:
        report.errors.append(f"Exit score error: {e!s}")

    return report


# ===================================================================
# Helpers
# ===================================================================

# Neighboring city clusters for data augmentation
_CITY_NEIGHBORS: dict[str, list[str]] = {
    "28202": ["28204", "28207"],  # 尼崎 → 西宮, 伊丹
    "28204": ["28202", "28206"],  # 西宮 → 尼崎, 芦屋
    "28206": ["28204", "28101"],  # 芦屋 → 西宮, 神戸東灘
    "28207": ["28202", "28214"],  # 伊丹 → 尼崎, 宝塚
    "28214": ["28207", "28217"],  # 宝塚 → 伊丹, 川西
    "28101": ["28102", "28206"],  # 神戸東灘 → 神戸灘, 芦屋
    "27203": ["27205", "28202"],  # 豊中 → 吹田, 尼崎
    "27205": ["27203"],           # 吹田 → 豊中
}


def _get_neighboring_cities(city_code: str) -> list[str]:
    """Get neighboring city codes for data augmentation."""
    return _CITY_NEIGHBORS.get(city_code, [])


# Station → city code mapping for inference
_STATION_CITY_MAP = {
    "塚口": "28202", "武庫之荘": "28202", "立花": "28202",
    "尼崎": "28202", "園田": "28202",
    "西宮北口": "28204", "夙川": "28204", "甲子園": "28204",
    "芦屋": "28206", "伊丹": "28207",
    "三宮": "28110", "六甲道": "28101", "住吉": "28101",
    "宝塚": "28214", "梅田": "27127", "新大阪": "27127",
    "江坂": "27205", "千里中央": "27205",
    "豊中": "27203",
}


def _infer_city_code(station_name: str, pref_code: str) -> str:
    """Try to infer city code from station name."""
    if station_name in _STATION_CITY_MAP:
        return _STATION_CITY_MAP[station_name]
    # Fuzzy match
    for stn, code in _STATION_CITY_MAP.items():
        if stn in station_name or station_name in stn:
            return code
    return ""
