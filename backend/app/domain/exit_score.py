"""Exit-strategy score (出口スコア).

Weighted scoring to evaluate how easy it is to rent out or sell a property.
Each factor yields 0-10 points, then weighted and normalised to 0-100.

Weights are based on:
- 東京カンテイ「中古マンションの資産性評価」レポート
- 賃貸住宅市場レポート（各社公開データ）
- 一般社団法人不動産流通経営協会「既存住宅流通量」調査

Key insight: station distance is the #1 factor affecting both rental demand
and resale price retention. Age is #2 because it directly affects:
- 旧耐震 (pre-1981) vs 新耐震 classification
- Major renovation cycles (築12年, 築24年)
- Buyer psychology and bank loan approval difficulty
"""

from __future__ import annotations

from dataclasses import dataclass

# -------------------------------------------------------------------
# Factor weights (must sum to 1.0)
# Higher weight = more impact on total score
# -------------------------------------------------------------------
WEIGHTS = {
    "station": 0.25,    # 駅距離: 最重要。賃貸需要と資産価値に直結
    "age": 0.20,        # 築年数: 耐震基準・設備・銀行融資に影響
    "size": 0.15,       # 面積: 需要ボリュームゾーン (60-75㎡) が有利
    "layout": 0.12,     # 間取り: 2-3LDK のファミリー向けが流動性高い
    "liquidity": 0.10,  # 総戸数: 管理組合の安定性・修繕計画の実行力
    "hazard": 0.10,     # ハザード: 浸水・土砂災害リスクは融資と保険に影響
    "zoning": 0.08,     # 用途地域: 商業地域は利便性高いが騒音リスクも
}


@dataclass(frozen=True)
class ExitScoreResult:
    station_score: int
    size_score: int
    layout_score: int
    age_score: int
    zoning_score: int
    hazard_score: int
    liquidity_score: int
    total_score: int  # 0-100
    assessment: str   # 評価コメント


# ---------------------------------------------------------------------------
# Individual scoring functions (each returns 0-10)
# ---------------------------------------------------------------------------

def score_station(walking_minutes: int | None) -> int:
    """Closer to station = higher score.

    Based on: 東京カンテイ 駅距離と中古マンション価格の関係
    - 徒歩3分以内: 資産価値下落率が最も低い
    - 徒歩7分超: 賃貸需要が急激に低下
    - 徒歩15分超: バス便物件扱い、流動性大幅低下
    """
    if walking_minutes is None:
        return 5
    if walking_minutes <= 3:
        return 10
    if walking_minutes <= 5:
        return 9
    if walking_minutes <= 7:
        return 8
    if walking_minutes <= 10:
        return 6
    if walking_minutes <= 15:
        return 4
    return 2


def score_size(floor_area_sqm: float | None) -> int:
    """60-75㎡ is the sweet spot for both rental demand and resale.

    Based on: 賃貸住宅市場レポート + 中古マンション取引動向
    - 60-75㎡ (2-3LDK): 最大需要ボリュームゾーン
    - 40-55㎡: DINKS向け需要あり
    - 75㎡超: 賃料単価下がるが実需は安定
    - 30㎡未満: 投資用ワンルーム、出口戦略限定的
    """
    if floor_area_sqm is None:
        return 5
    if 60 <= floor_area_sqm <= 75:
        return 10
    if 50 <= floor_area_sqm < 60 or 75 < floor_area_sqm <= 85:
        return 8
    if 40 <= floor_area_sqm < 50 or 85 < floor_area_sqm <= 100:
        return 6
    if floor_area_sqm < 30:
        return 3
    return 4


def score_layout(layout: str | None) -> int:
    """2LDK/3LDK score highest for rental demand.

    Based on: SUUMO/LIFULL HOME'S 賃貸検索ボリューム分析
    - 3LDK: ファミリー需要No.1
    - 2LDK: DINKS + 小家族
    - 1LDK: 単身上位層
    - 4LDK: 需要限定的（賃料上限に当たりやすい）
    """
    if layout is None:
        return 5
    upper = layout.upper().replace(" ", "")
    if upper in ("3LDK", "2SLDK"):
        return 10
    if upper in ("2LDK", "3SLDK"):
        return 9
    if upper in ("1LDK",):
        return 7
    if upper in ("2DK", "3DK"):
        return 6
    if upper in ("4LDK",):
        return 5
    if upper in ("1DK", "1K"):
        return 4
    if upper in ("1R",):
        return 3
    return 5


def score_age(built_year: int | None, current_year: int = 2026) -> int:
    """Newer is better, with key breakpoints.

    Key thresholds:
    - 築5年以内: 新築プレミアム残存
    - 築12年前後: 第1回大規模修繕（修繕積立金の実績が見える）
    - 築20年前後: 設備の陳腐化が目立つ
    - 築25年 (2001年以前): 一部銀行で融資制限
    - 築40年 (1986年以前): 旧耐震の可能性（1981年基準）
    """
    if built_year is None:
        return 5
    age = current_year - built_year
    if age <= 5:
        return 10
    if age <= 10:
        return 9
    if age <= 15:
        return 8
    if age <= 20:
        return 7
    if age <= 25:
        return 5
    if age <= 30:
        return 4
    if age <= 40:
        return 2
    return 1  # 旧耐震: 融資困難・保険制限


def score_zoning(zoning_type: str | None) -> int:
    """Zoning affects noise, convenience, and future development risk.

    Based on: 用途地域と不動産価値の関係（一般的な傾向）
    """
    if zoning_type is None:
        return 5
    z = zoning_type
    if "近隣商業" in z:
        return 9   # 利便性◎、住環境○
    if "商業" in z:
        return 8   # 利便性◎、騒音リスクあり
    if "第一種住居" in z or "第二種住居" in z or "準住居" in z:
        return 8   # 住環境良好
    if "中高層" in z:
        return 7   # 良好だがマンション多い
    if "低層" in z:
        return 6   # 閑静だが利便性△
    if "準工業" in z:
        return 5
    if "工業" in z:
        return 3
    return 5


def score_hazard(hazard_flag: bool | None) -> int:
    """Hazard area designation affects insurance, loans, and resale.

    Based on: 宅地建物取引業法 重要事項説明義務
    - ハザード区域: 重要事項説明で告知義務あり
    - 保険料上昇、一部融資制限の可能性
    """
    if hazard_flag is None:
        return 5
    return 3 if hazard_flag else 9


def score_liquidity(total_units: int | None) -> int:
    """Larger buildings tend to have better management and maintenance.

    Based on: マンション管理適正化法 + 修繕積立金に関する調査
    - 50戸以上: 管理組合が機能しやすい、修繕計画が安定
    - 30戸未満: 一戸あたりの負担大、管理費滞納リスク
    - 15戸未満: 自主管理が多い、管理品質にバラつき
    """
    if total_units is None:
        return 5
    if total_units >= 100:
        return 9
    if total_units >= 50:
        return 8
    if total_units >= 30:
        return 7
    if total_units >= 15:
        return 5
    return 3


# ---------------------------------------------------------------------------
# Aggregate (weighted)
# ---------------------------------------------------------------------------

def calc_exit_score(
    walking_minutes: int | None = None,
    floor_area_sqm: float | None = None,
    layout: str | None = None,
    built_year: int | None = None,
    zoning_type: str | None = None,
    hazard_flag: bool | None = None,
    total_units: int | None = None,
    current_year: int = 2026,
) -> ExitScoreResult:
    """Calculate weighted composite exit score (0-100)."""
    scores = {
        "station": score_station(walking_minutes),
        "size": score_size(floor_area_sqm),
        "layout": score_layout(layout),
        "age": score_age(built_year, current_year),
        "zoning": score_zoning(zoning_type),
        "hazard": score_hazard(hazard_flag),
        "liquidity": score_liquidity(total_units),
    }

    # Weighted sum: each score is 0-10, weight sum is 1.0
    # So max weighted sum = 10, normalize to 100
    weighted_sum = sum(scores[k] * WEIGHTS[k] for k in WEIGHTS)
    total = int(weighted_sum * 10 + 0.5)
    total = min(max(total, 0), 100)

    # Assessment text
    if total >= 85:
        assessment = "出口戦略◎: 賃貸・売却とも有利。資産性の高い物件"
    elif total >= 70:
        assessment = "出口戦略○: 標準的な流動性。立地・築年数のバランス良好"
    elif total >= 55:
        assessment = "出口戦略△: 一部リスクあり。賃貸需要や融資条件を要確認"
    elif total >= 40:
        assessment = "出口戦略▲: 流動性に懸念。長期保有前提で検討を"
    else:
        assessment = "出口戦略×: 賃貸・売却とも困難が予想される"

    return ExitScoreResult(
        station_score=scores["station"],
        size_score=scores["size"],
        layout_score=scores["layout"],
        age_score=scores["age"],
        zoning_score=scores["zoning"],
        hazard_score=scores["hazard"],
        liquidity_score=scores["liquidity"],
        total_score=total,
        assessment=assessment,
    )
