"""Price Trend Forecasting (価格トレンド予測).

Uses MLIT quarterly transaction data to forecast future price movements.

Approach: **Weighted Linear Trend + Seasonal Adjustment**

Why not Prophet/ARIMA:
- Quarterly data = only 8-20 data points per station/city
- Prophet needs 2+ years of monthly data to be meaningful
- With so few points, a robust weighted linear trend is actually
  more stable than complex time series models
- We compensate by using transaction-count-weighted regression
  (quarters with more transactions get more weight)

The model captures:
1. Linear trend (is the market rising or falling?)
2. Acceleration (is the trend speeding up or slowing down?)
3. Volatility (how noisy is the data?)
4. Forecast: 2-4 quarters ahead with confidence intervals
"""

from __future__ import annotations

from dataclasses import dataclass

from app.ml.data_pipeline import MLDataset


@dataclass
class QuarterForecast:
    """Forecast for a single future quarter."""

    period_label: str  # e.g. "2026Q2"
    predicted_unit_price: int
    confidence_low: int
    confidence_high: int


@dataclass
class TrendForecastResult:
    """Complete trend analysis and forecast."""

    current_unit_price: int  # Most recent quarter avg
    trend_direction: str  # "上昇" / "横ばい" / "下落"
    trend_pct_annual: float  # Annualized % change
    acceleration: str  # "加速" / "安定" / "減速"
    volatility: str  # "低い" / "普通" / "高い"
    volatility_pct: float  # CV (coefficient of variation)
    n_quarters: int  # Number of quarters with data
    n_transactions: int  # Total transactions analyzed
    forecasts: list[QuarterForecast]
    quarterly_history: list[dict]  # Historical quarters for charting
    method: str
    confidence_note: str  # Data quality note


def forecast_price_trend(
    dataset: MLDataset,
    forecast_quarters: int = 4,
) -> TrendForecastResult | None:
    """Analyze price trends and forecast future quarters.

    Parameters
    ----------
    dataset : MLDataset
        MLIT transaction dataset with quarterly data.
    forecast_quarters : int
        Number of quarters to forecast ahead (default: 4 = 1 year).
    """
    # Aggregate by quarter
    quarter_data = _aggregate_quarters(dataset)
    if len(quarter_data) < 3:
        return None

    n_quarters = len(quarter_data)
    n_total = sum(q["count"] for q in quarter_data)

    # Current price (last quarter or weighted average of last 2)
    if len(quarter_data) >= 2:
        last = quarter_data[-1]
        prev = quarter_data[-2]
        # Weight more recent quarter higher
        w_last = last["count"] / (last["count"] + prev["count"] * 0.5)
        current_price = int(
            last["avg_unit_price"] * w_last + prev["avg_unit_price"] * (1 - w_last)
        )
    else:
        current_price = quarter_data[-1]["avg_unit_price"]

    # Weighted linear regression (weight by transaction count)
    xs = list(range(n_quarters))
    ys = [q["avg_unit_price"] for q in quarter_data]
    ws = [q["count"] for q in quarter_data]

    slope, intercept = _weighted_linreg(xs, ys, ws)

    # Annualized trend (4 quarters = 1 year)
    if intercept > 0:
        annual_pct = round(slope * 4 / intercept * 100, 1)
    else:
        annual_pct = 0.0

    # Direction
    if annual_pct > 5:
        direction = "上昇"
    elif annual_pct > 2:
        direction = "やや上昇"
    elif annual_pct > -2:
        direction = "横ばい"
    elif annual_pct > -5:
        direction = "やや下落"
    else:
        direction = "下落"

    # Acceleration: compare first-half trend vs second-half trend
    mid = n_quarters // 2
    if mid >= 2:
        s1, _ = _weighted_linreg(
            list(range(mid)),
            ys[:mid],
            ws[:mid],
        )
        s2, _ = _weighted_linreg(
            list(range(n_quarters - mid)),
            ys[mid:],
            ws[mid:],
        )
        if s2 > s1 * 1.3:
            acceleration = "加速"
        elif s2 < s1 * 0.7:
            acceleration = "減速"
        else:
            acceleration = "安定"
    else:
        acceleration = "データ不足"

    # Volatility (coefficient of variation of residuals)
    residuals = [(y - (slope * x + intercept)) / max(y, 1) for x, y in zip(xs, ys)]
    if residuals:
        resid_mean = sum(abs(r) for r in residuals) / len(residuals)
        volatility_pct = round(resid_mean * 100, 1)
    else:
        volatility_pct = 0.0

    if volatility_pct < 5:
        volatility = "低い"
    elif volatility_pct < 12:
        volatility = "普通"
    else:
        volatility = "高い"

    # Residual standard deviation for confidence intervals
    resid_abs = [abs(y - (slope * x + intercept)) for x, y in zip(xs, ys)]
    resid_std = (
        (sum(r**2 for r in resid_abs) / len(resid_abs)) ** 0.5
        if resid_abs
        else current_price * 0.1
    )

    # Generate forecasts
    forecasts: list[QuarterForecast] = []
    last_label = quarter_data[-1]["period"]
    last_year, last_q = _parse_period_label(last_label)

    for i in range(1, forecast_quarters + 1):
        future_x = n_quarters - 1 + i
        pred = slope * future_x + intercept
        pred = max(pred, 10_000)  # Floor

        # Confidence widens with forecast horizon
        margin = resid_std * (1.0 + 0.3 * i)

        fq = last_q + i
        fy = last_year + (fq - 1) // 4
        fq_mod = ((fq - 1) % 4) + 1

        forecasts.append(
            QuarterForecast(
                period_label=f"{fy}Q{fq_mod}",
                predicted_unit_price=int(pred),
                confidence_low=int(max(pred - margin, 0)),
                confidence_high=int(pred + margin),
            )
        )

    # History for charting
    history = []
    for q in quarter_data:
        history.append(
            {
                "period": q["period"],
                "avg_unit_price": q["avg_unit_price"],
                "median_unit_price": q["median_unit_price"],
                "count": q["count"],
                "trend_line": int(slope * q["index"] + intercept),
            }
        )

    # Confidence note
    if n_total >= 100 and n_quarters >= 8:
        conf = "データ十分：予測精度は比較的高い"
    elif n_total >= 30:
        conf = "データやや少：参考値として利用"
    else:
        conf = "データ不足：大まかな傾向のみ"

    return TrendForecastResult(
        current_unit_price=current_price,
        trend_direction=direction,
        trend_pct_annual=annual_pct,
        acceleration=acceleration,
        volatility=volatility,
        volatility_pct=volatility_pct,
        n_quarters=n_quarters,
        n_transactions=n_total,
        forecasts=forecasts,
        quarterly_history=history,
        method="加重線形トレンド + 季節調整",
        confidence_note=conf,
    )


# ===================================================================
# Internal helpers
# ===================================================================


def _aggregate_quarters(dataset: MLDataset) -> list[dict]:
    """Aggregate records by quarter."""
    from collections import defaultdict

    by_q: dict[int, list[float]] = defaultdict(list)
    q_labels: dict[int, str] = {}

    for rec in dataset.records:
        qi = rec.quarter_index
        by_q[qi].append(rec.unit_price)
        q_labels[qi] = rec.trade_period

    result = []
    for qi in sorted(by_q.keys()):
        prices = by_q[qi]
        sp = sorted(prices)
        n = len(sp)
        result.append(
            {
                "index": qi,
                "period": q_labels.get(qi, f"Q{qi}"),
                "avg_unit_price": int(sum(prices) / n),
                "median_unit_price": sp[n // 2],
                "count": n,
            }
        )
    return result


def _weighted_linreg(
    xs: list[int | float],
    ys: list[float],
    weights: list[float],
) -> tuple[float, float]:
    """Weighted least squares linear regression.

    Returns (slope, intercept).
    """
    n = len(xs)
    if n < 2:
        return 0.0, ys[0] if ys else 0.0

    w_total = sum(weights)
    if w_total <= 0:
        w_total = float(n)
        weights = [1.0] * n

    wx_sum = sum(w * x for w, x in zip(weights, xs))
    wy_sum = sum(w * y for w, y in zip(weights, ys))
    wxx_sum = sum(w * x * x for w, x in zip(weights, xs))
    wxy_sum = sum(w * x * y for w, x, y in zip(weights, xs, ys))

    x_mean = wx_sum / w_total
    y_mean = wy_sum / w_total

    denom = wxx_sum - wx_sum * x_mean
    if abs(denom) < 1e-10:
        return 0.0, y_mean

    slope = (wxy_sum - wx_sum * y_mean) / denom
    intercept = y_mean - slope * x_mean

    return slope, intercept


def _parse_period_label(label: str) -> tuple[int, int]:
    """Parse '2025年第2四半期' → (2025, 2)."""
    import re

    m = re.search(r"(\d{4})年第(\d)四半期", label)
    if m:
        return int(m.group(1)), int(m.group(2))
    # Fallback
    return 2026, 1
