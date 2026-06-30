"""ML-Enhanced Exit Score (MLIT流動性データ活用版).

Enhances the existing rule-based exit score with actual MLIT
transaction data to compute:

1. **Real liquidity**: How many similar properties actually transacted
   in this area in the last N years? (Not a guess based on total units)

2. **Price retention curve**: What is the ACTUAL depreciation rate
   for properties of this age/type in this market?
   (Not a generic table, but market-specific data)

3. **Market momentum**: Is this station/city trending up or down?
   (Directly from quarterly price data)

4. **Comparable demand**: Among recent transactions, what % match
   this property's profile? (Layout, area, station distance)

These data-driven factors replace or supplement the rule-based
scores in exit_score.py.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.ml.data_pipeline import (
    LAYOUT_CATEGORIES,
    MLDataset,
)

logger = logging.getLogger(__name__)


@dataclass
class MLExitScoreResult:
    """Enhanced exit score with MLIT-backed factors."""

    # Overall
    total_score: int  # 0-100
    assessment: str

    # Data-driven factors
    liquidity_score: int  # 0-10: real transaction volume
    liquidity_detail: str  # Human-readable detail
    price_retention_score: int  # 0-10: actual depreciation curve
    price_retention_detail: str
    momentum_score: int  # 0-10: price trend
    momentum_detail: str
    demand_match_score: int  # 0-10: demand for this profile
    demand_match_detail: str

    # Traditional factors (kept from existing model)
    station_score: int
    size_score: int
    layout_score: int

    # Metadata
    n_transactions: int
    data_quality: str  # "MLIT実データ" or "推定"
    comparable_count: int  # Number of similar transactions found


def calc_ml_exit_score(
    dataset: MLDataset | None,
    walking_minutes: float | None = None,
    floor_area: float | None = None,
    layout: str | None = None,
    age_years: float | None = None,
    station_name: str = "",
) -> MLExitScoreResult:
    """Calculate exit score using MLIT data + rule-based factors.

    If dataset is None, falls back to pure rule-based scoring.
    """
    from app.domain.exit_score import (
        score_layout,
        score_size,
        score_station,
    )

    # Rule-based scores (always available)
    stn_score = score_station(
        int(walking_minutes) if walking_minutes else None,
    )
    size_score = score_size(floor_area)
    layout_score = score_layout(layout)

    if dataset is None or dataset.n_samples < 10:
        return _fallback_score(
            stn_score,
            size_score,
            layout_score,
            walking_minutes,
            floor_area,
            layout,
            age_years,
        )

    records = dataset.records
    n = len(records)

    # --- 1. Liquidity score ---
    # How many transactions per year in this area?
    n_quarters = len(dataset.quarter_labels)
    years_span = max(n_quarters / 4, 0.5)
    annual_volume = n / years_span

    if annual_volume >= 100:
        liq_score = 10
        liq_detail = f"年間{int(annual_volume)}件取引 → 流動性◎"
    elif annual_volume >= 50:
        liq_score = 9
        liq_detail = f"年間{int(annual_volume)}件取引 → 流動性○"
    elif annual_volume >= 20:
        liq_score = 7
        liq_detail = f"年間{int(annual_volume)}件取引 → 流動性やや良"
    elif annual_volume >= 10:
        liq_score = 5
        liq_detail = f"年間{int(annual_volume)}件取引 → 流動性普通"
    elif annual_volume >= 5:
        liq_score = 3
        liq_detail = f"年間{int(annual_volume)}件取引 → 流動性やや低"
    else:
        liq_score = 1
        liq_detail = f"年間{int(annual_volume)}件取引 → 流動性低"

    # --- 2. Price retention score ---
    # Compare unit prices of newer vs older properties in the data
    if age_years is not None:
        ret_score, ret_detail = _calc_price_retention(
            records,
            age_years,
        )
    else:
        ret_score = 5
        ret_detail = "築年数不明のため推定"

    # --- 3. Momentum score ---
    # Price trend from quarterly data
    mom_score, mom_detail = _calc_momentum(dataset)

    # --- 4. Demand match score ---
    # How many recent transactions match this property's profile?
    layout_upper = layout.upper().replace(" ", "") if layout else ""
    match_score, match_detail, comp_count = _calc_demand_match(
        records,
        floor_area,
        age_years,
        layout_upper,
        station_name,
    )

    # --- Weighted total ---
    # Weights reflecting real-world importance for exit strategy
    weights = {
        "station": 0.18,
        "size": 0.10,
        "layout": 0.08,
        "liquidity": 0.20,
        "retention": 0.18,
        "momentum": 0.14,
        "demand": 0.12,
    }
    scores = {
        "station": stn_score,
        "size": size_score,
        "layout": layout_score,
        "liquidity": liq_score,
        "retention": ret_score,
        "momentum": mom_score,
        "demand": match_score,
    }
    weighted_sum = sum(scores[k] * weights[k] for k in weights)
    total = int(weighted_sum * 10 + 0.5)
    total = min(max(total, 0), 100)

    if total >= 85:
        assessment = "出口戦略◎: 高い流動性と価格安定性（実データ裏付け）"
    elif total >= 70:
        assessment = "出口戦略○: 標準的な流動性（実データ裏付け）"
    elif total >= 55:
        assessment = "出口戦略△: 一部リスクあり"
    elif total >= 40:
        assessment = "出口戦略▲: 流動性に懸念あり"
    else:
        assessment = "出口戦略×: 売却困難が予想される"

    return MLExitScoreResult(
        total_score=total,
        assessment=assessment,
        liquidity_score=liq_score,
        liquidity_detail=liq_detail,
        price_retention_score=ret_score,
        price_retention_detail=ret_detail,
        momentum_score=mom_score,
        momentum_detail=mom_detail,
        demand_match_score=match_score,
        demand_match_detail=match_detail,
        station_score=stn_score,
        size_score=size_score,
        layout_score=layout_score,
        n_transactions=n,
        data_quality="MLIT実取引データ",
        comparable_count=comp_count,
    )


# ===================================================================
# Internal scoring functions
# ===================================================================


def _calc_price_retention(
    records: list,
    subject_age: float,
) -> tuple[int, str]:
    """Score based on actual price depreciation curve.

    Compare properties aged ±5 years of the subject
    vs properties 10 years newer to estimate retention rate.
    """
    # Subject-age bracket
    target_recs = [r for r in records if abs(r.age_years - subject_age) <= 5]
    # Newer reference bracket (0-10 years old)
    new_recs = [r for r in records if r.age_years <= 10]

    if not target_recs or not new_recs:
        return 5, "比較データ不足"

    target_avg = sum(r.unit_price for r in target_recs) / len(target_recs)
    new_avg = sum(r.unit_price for r in new_recs) / len(new_recs)

    if new_avg <= 0:
        return 5, "算出不可"

    retention = target_avg / new_avg
    retention_pct = round(retention * 100, 1)

    if retention >= 0.90:
        score = 10
        detail = f"価格維持率{retention_pct}% → 資産価値安定"
    elif retention >= 0.80:
        score = 8
        detail = f"価格維持率{retention_pct}% → 標準的な減価"
    elif retention >= 0.70:
        score = 6
        detail = f"価格維持率{retention_pct}% → やや減価"
    elif retention >= 0.55:
        score = 4
        detail = f"価格維持率{retention_pct}% → 減価大きい"
    else:
        score = 2
        detail = f"価格維持率{retention_pct}% → 大幅減価"

    return score, detail


def _calc_momentum(dataset: MLDataset) -> tuple[int, str]:
    """Score based on price trend direction and strength."""
    from collections import defaultdict

    by_q: dict[int, list[float]] = defaultdict(list)
    for r in dataset.records:
        by_q[r.quarter_index].append(r.unit_price)

    if len(by_q) < 4:
        return 5, "四半期データ不足"

    sorted_qs = sorted(by_q.keys())
    mid = len(sorted_qs) // 2
    older_qs = sorted_qs[:mid]
    recent_qs = sorted_qs[mid:]

    older_prices = []
    for q in older_qs:
        older_prices.extend(by_q[q])
    recent_prices = []
    for q in recent_qs:
        recent_prices.extend(by_q[q])

    if not older_prices or not recent_prices:
        return 5, "データ不足"

    older_avg = sum(older_prices) / len(older_prices)
    recent_avg = sum(recent_prices) / len(recent_prices)

    if older_avg <= 0:
        return 5, "算出不可"

    change_pct = round((recent_avg / older_avg - 1) * 100, 1)

    if change_pct > 10:
        score = 10
        detail = f"前期比+{change_pct}% → 強い上昇トレンド"
    elif change_pct > 5:
        score = 8
        detail = f"前期比+{change_pct}% → 上昇トレンド"
    elif change_pct > 0:
        score = 7
        detail = f"前期比+{change_pct}% → やや上昇"
    elif change_pct > -5:
        score = 5
        detail = f"前期比{change_pct}% → 横ばい"
    elif change_pct > -10:
        score = 3
        detail = f"前期比{change_pct}% → やや下落"
    else:
        score = 1
        detail = f"前期比{change_pct}% → 下落トレンド"

    return score, detail


def _calc_demand_match(
    records: list,
    floor_area: float | None,
    age_years: float | None,
    layout_cat_str: str,
    station_name: str,
) -> tuple[int, str, int]:
    """Score based on demand for similar properties.

    Returns (score, detail, comparable_count).
    """
    layout_cat = LAYOUT_CATEGORIES.get(layout_cat_str, -1)

    similar = []
    for r in records:
        match_count = 0
        # Area match (±15㎡)
        if floor_area and abs(r.floor_area - floor_area) <= 15:
            match_count += 1
        # Age match (±7 years)
        if age_years is not None and abs(r.age_years - age_years) <= 7:
            match_count += 1
        # Layout match
        if layout_cat >= 0 and abs(r.layout_cat - layout_cat) <= 1:
            match_count += 1
        # Station match
        if station_name and (station_name in r.station_name or r.station_name in station_name):
            match_count += 1

        if match_count >= 2:  # At least 2 criteria match
            similar.append(r)

    comp_count = len(similar)

    if comp_count >= 30:
        score = 10
        detail = f"類似取引{comp_count}件 → 需要◎"
    elif comp_count >= 15:
        score = 8
        detail = f"類似取引{comp_count}件 → 需要○"
    elif comp_count >= 8:
        score = 6
        detail = f"類似取引{comp_count}件 → 需要普通"
    elif comp_count >= 3:
        score = 4
        detail = f"類似取引{comp_count}件 → 需要やや低"
    else:
        score = 2
        detail = f"類似取引{comp_count}件 → 需要低"

    return score, detail, comp_count


def _fallback_score(
    stn_score: int,
    size_score: int,
    layout_score: int,
    walking_minutes: float | None,
    floor_area: float | None,
    layout: str | None,
    age_years: float | None,
) -> MLExitScoreResult:
    """Fallback when MLIT data is unavailable."""
    from app.domain.exit_score import score_age

    built_year = int(2026 - age_years) if age_years else None
    age_score = score_age(built_year)

    weighted = (
        stn_score * 0.25
        + size_score * 0.15
        + layout_score * 0.12
        + age_score * 0.20
        + 5 * 0.28  # Default for data-driven factors
    )
    total = int(weighted * 10 + 0.5)
    total = min(max(total, 0), 100)

    if total >= 70:
        assessment = "出口戦略○（データなし・ルールベース推定）"
    elif total >= 55:
        assessment = "出口戦略△（データなし・ルールベース推定）"
    else:
        assessment = "出口戦略▲（データなし・ルールベース推定）"

    return MLExitScoreResult(
        total_score=total,
        assessment=assessment,
        liquidity_score=5,
        liquidity_detail="MLIT APIキー未設定 → 推定",
        price_retention_score=5,
        price_retention_detail="取引データなし → 推定",
        momentum_score=5,
        momentum_detail="トレンドデータなし → 推定",
        demand_match_score=5,
        demand_match_detail="需要データなし → 推定",
        station_score=stn_score,
        size_score=size_score,
        layout_score=layout_score,
        n_transactions=0,
        data_quality="推定（MLIT APIキー未設定）",
        comparable_count=0,
    )
