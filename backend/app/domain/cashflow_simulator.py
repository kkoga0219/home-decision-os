"""年次キャッシュフローシミュレーター.

住宅購入から N年間のキャッシュフローを年次で算出する。
自己居住シナリオと投資（賃貸運用）シナリオの両方に対応。

含まれる項目:
- 初期費用 (諸費用・仲介手数料・登記費用・不動産取得税)
- ローン返済 (元利均等)
- 住宅ローン控除 (0.7%/年、最大13年or10年)
- 管理費・修繕積立金
- 固定資産税・都市計画税
- 火災保険
- 賃貸収入 (投資シナリオのみ)
- 減価償却 (投資シナリオ・節税効果)
- 売却想定 (出口シナリオ)

参考資料:
- 住宅ローン控除: 国税庁 https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/1211-1.htm
- 固定資産税: 標準税率1.4% (評価額ベース)
- 都市計画税: 上限0.3%
- 仲介手数料: 宅建業法上限 price*3%+6万+消費税
- 不動産取得税: 土地3% + 建物3% (住宅用軽減)
- 登記費用: 所有権移転0.3%(軽減), 抵当権0.1%(軽減) + 司法書士報酬
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from app.domain.mortgage import (
    approximate_outstanding_balance,
    calc_monthly_payment,
    calc_tax_credit_annual,
)


# ---------------------------------------------------------------------------
# 諸費用パラメータ (デフォルト値)
# ---------------------------------------------------------------------------

# 仲介手数料率 (400万超: 3% + 6万)
BROKER_FEE_RATE = 0.03
BROKER_FEE_BASE = 60_000
CONSUMPTION_TAX = 0.10

# 登記費用 (概算: 物件価格の 0.7~1.0%)
REGISTRATION_COST_RATE = 0.008

# 不動産取得税 (概算: 固定資産税評価額の約3%、評価額≒市場価格の70%)
ACQUISITION_TAX_RATE_ON_ASSESSED = 0.03
ASSESSED_VALUE_RATIO = 0.70

# 固定資産税 (評価額×1.4%) + 都市計画税 (評価額×0.3%)
PROPERTY_TAX_RATE = 0.014
CITY_PLANNING_TAX_RATE = 0.003

# 新築マンション: 固定資産税は5年間半額特例
# 中古は適用なし (ここでは中古前提)

# 火災保険 (年額概算: マンションの場合)
DEFAULT_INSURANCE_ANNUAL = 15_000  # 5年一括 ÷ 5 ≈ 1.5万/年

# 減価償却 (RC造マンション: 耐用年数47年)
RC_USEFUL_LIFE = 47

# 賃貸管理手数料 (賃料の5%)
DEFAULT_PM_FEE_RATE = 0.05
DEFAULT_VACANCY_RATE = 0.05

# 住宅ローン控除
DEFAULT_TAX_CREDIT_RATE = 0.007  # 0.7%
DEFAULT_TAX_CREDIT_YEARS_NEW = 13  # 新築
DEFAULT_TAX_CREDIT_YEARS_USED = 10  # 中古
DEFAULT_TAX_CREDIT_MAX = 210_000  # 年間上限 (一般住宅)


# ---------------------------------------------------------------------------
# データクラス
# ---------------------------------------------------------------------------

@dataclass
class InitialCosts:
    """購入時の諸費用."""

    down_payment: int = 0
    broker_fee: int = 0          # 仲介手数料
    registration_cost: int = 0   # 登記費用
    acquisition_tax: int = 0     # 不動産取得税
    loan_guarantee_fee: int = 0  # ローン保証料
    other_initial: int = 0       # その他
    total: int = 0


@dataclass
class AnnualCashflow:
    """1年分のキャッシュフロー."""

    year: int

    # 支出
    loan_payment: int = 0           # ローン返済 (年間)
    management_fee: int = 0         # 管理費 (年間)
    repair_reserve: int = 0         # 修繕積立金 (年間)
    property_tax: int = 0           # 固定資産税+都市計画税
    insurance: int = 0              # 火災保険
    total_expense: int = 0

    # 減税・控除
    tax_credit: int = 0             # 住宅ローン控除
    depreciation_benefit: int = 0   # 減価償却による節税効果

    # 収入 (投資シナリオ)
    gross_rent: int = 0             # 賃料収入 (満室想定)
    vacancy_loss: int = 0           # 空室損
    pm_fee: int = 0                 # 賃貸管理費
    net_rent: int = 0               # 手取り賃料

    # キャッシュフロー
    cashflow: int = 0               # 年間CF (収入 - 支出 + 控除)
    cumulative_cashflow: int = 0    # 累積CF

    # ローン残高
    outstanding_balance: int = 0


@dataclass
class ExitScenario:
    """売却時のシナリオ."""

    year: int
    sale_price: int = 0           # 想定売却価格
    outstanding_balance: int = 0  # ローン残高
    selling_costs: int = 0        # 売却諸費用 (仲介手数料等)
    capital_gain: int = 0         # 売却益 (税引前)
    cumulative_cashflow: int = 0  # それまでの累積CF
    total_return: int = 0         # トータルリターン
    annual_roi_pct: float = 0.0   # 年利換算ROI


@dataclass
class CashflowSimulationResult:
    """シミュレーション結果."""

    # 入力パラメータ
    price_jpy: int = 0
    scenario_type: str = "self_use"  # "self_use" or "investment"

    # 初期費用
    initial_costs: InitialCosts = field(default_factory=InitialCosts)

    # 年次CF
    annual_cashflows: list[AnnualCashflow] = field(default_factory=list)

    # 出口シナリオ
    exit_scenarios: list[ExitScenario] = field(default_factory=list)

    # サマリー
    total_cost_10yr: int = 0       # 10年間の総支出
    total_benefit_10yr: int = 0    # 10年間の総控除+収入
    net_cost_10yr: int = 0         # 10年間の実質負担


# ---------------------------------------------------------------------------
# メイン関数
# ---------------------------------------------------------------------------

def simulate_cashflow(
    # 物件情報
    price_jpy: int,
    floor_area_sqm: float = 70.0,
    built_year: int | None = None,
    management_fee_jpy: int = 0,
    repair_reserve_jpy: int = 0,

    # ローン条件
    down_payment_jpy: int = 0,
    annual_interest_rate: float = 0.005,
    loan_years: int = 35,

    # 住宅ローン控除
    tax_credit_rate: float = DEFAULT_TAX_CREDIT_RATE,
    tax_credit_years: int | None = None,  # None → 中古10年/新築13年
    tax_credit_max: int = DEFAULT_TAX_CREDIT_MAX,

    # コスト
    property_tax_annual: int | None = None,  # None → 自動推定
    insurance_annual: int = DEFAULT_INSURANCE_ANNUAL,

    # 投資シナリオ
    scenario_type: str = "self_use",  # "self_use" or "investment"
    expected_rent_jpy: int = 0,       # 投資の場合の月額賃料
    vacancy_rate: float = DEFAULT_VACANCY_RATE,
    pm_fee_rate: float = DEFAULT_PM_FEE_RATE,
    marginal_tax_rate: float = 0.20,  # 所得税率 (減価償却の節税効果計算用)

    # シミュレーション期間
    simulation_years: int = 35,

    # 売却想定
    annual_price_decline_rate: float = 0.015,  # 年間下落率 (1.5%)

    # 諸費用カスタム
    broker_fee_jpy: int | None = None,
    registration_cost_jpy: int | None = None,
    acquisition_tax_jpy: int | None = None,
    other_initial_jpy: int = 0,
) -> CashflowSimulationResult:
    """N年間のキャッシュフローを年次でシミュレーションする."""

    import datetime
    current_year = datetime.date.today().year

    # --- 築年数判定 ---
    building_age = (current_year - built_year) if built_year else 15
    is_new = building_age <= 2

    if tax_credit_years is None:
        tax_credit_years = DEFAULT_TAX_CREDIT_YEARS_NEW if is_new else DEFAULT_TAX_CREDIT_YEARS_USED

    # --- ローン計算 ---
    loan_amount = price_jpy - down_payment_jpy
    monthly_payment = calc_monthly_payment(loan_amount, annual_interest_rate, loan_years)
    annual_payment = monthly_payment * 12

    # --- 初期費用 ---
    if broker_fee_jpy is None:
        broker_fee_jpy = int(
            (price_jpy * BROKER_FEE_RATE + BROKER_FEE_BASE) * (1 + CONSUMPTION_TAX)
        )

    if registration_cost_jpy is None:
        registration_cost_jpy = int(price_jpy * REGISTRATION_COST_RATE)

    if acquisition_tax_jpy is None:
        assessed_value = int(price_jpy * ASSESSED_VALUE_RATIO)
        acquisition_tax_jpy = int(assessed_value * ACQUISITION_TAX_RATE_ON_ASSESSED)
        # 住宅用軽減: 建物は評価額-1200万(新築)、中古は築年数による
        # 簡略化: 実効税率を半額程度に
        if floor_area_sqm >= 50:
            acquisition_tax_jpy = acquisition_tax_jpy // 2

    # ローン保証料 (概算: 借入額の2%)
    loan_guarantee = int(loan_amount * 0.02) if loan_amount > 0 else 0

    initial = InitialCosts(
        down_payment=down_payment_jpy,
        broker_fee=broker_fee_jpy,
        registration_cost=registration_cost_jpy,
        acquisition_tax=acquisition_tax_jpy,
        loan_guarantee_fee=loan_guarantee,
        other_initial=other_initial_jpy,
        total=(
            down_payment_jpy
            + broker_fee_jpy
            + registration_cost_jpy
            + acquisition_tax_jpy
            + loan_guarantee
            + other_initial_jpy
        ),
    )

    # --- 固定資産税 ---
    # マンションの固定資産税は戸建てより大幅に安い。理由:
    #   1. 土地: マンション全体の敷地を戸数で按分 → 持分はごく小さい
    #   2. 建物: 経年で評価額が下がる (RC造は築20年で新築時の60%程度)
    #   3. 小規模住宅用地の特例: 固定資産税1/6, 都市計画税1/3
    # 実態: 5000万の中古マンション → 年額10〜18万程度が一般的
    #
    # 概算ロジック:
    #   建物評価額 ≒ 市場価格 × 40% × 経年減価 (築年数で按分)
    #   土地評価額 ≒ 市場価格 × 15% (マンション按分後)
    #   土地は小規模住宅用地の特例で固定1/6, 都計1/3
    if property_tax_annual is None:
        # 建物部分
        # RC造マンションの建物評価額: 市場価格の30%程度(新築時)
        # 経年で逓減: 築20年で新築時の約50%, 下限は新築時の30%
        age_factor = max(1.0 - building_age * 0.025, 0.30)
        building_assessed = int(price_jpy * 0.30 * age_factor)
        building_tax = int(building_assessed * (PROPERTY_TAX_RATE + CITY_PLANNING_TAX_RATE))

        # 土地部分 (マンション按分後 + 小規模住宅用地の特例)
        # マンションの土地持分は非常に小さい: 市場価格の10%程度
        land_assessed = int(price_jpy * 0.10)
        land_fixed_tax = int(land_assessed * PROPERTY_TAX_RATE / 6)     # 特例1/6
        land_city_tax = int(land_assessed * CITY_PLANNING_TAX_RATE / 3)  # 特例1/3
        land_tax = land_fixed_tax + land_city_tax

        property_tax_annual = building_tax + land_tax

    # --- 減価償却 (投資シナリオ) ---
    annual_depreciation = 0
    if scenario_type == "investment" and floor_area_sqm > 0:
        # 建物部分の取得費 (マンション: 物件価格の約60%が建物)
        building_cost = int(price_jpy * 0.60)
        # 中古RC: 残耐用年数 = (47 - 経過年数) + 経過年数*0.2
        remaining_life = max(
            (RC_USEFUL_LIFE - building_age) + int(building_age * 0.2),
            2,
        )
        annual_depreciation = building_cost // remaining_life

    # --- 年次キャッシュフロー ---
    cashflows: list[AnnualCashflow] = []
    cumulative_cf = -initial.total  # 初期費用をマイナスからスタート

    annual_mgmt = management_fee_jpy * 12
    annual_repair = repair_reserve_jpy * 12

    for yr in range(1, simulation_years + 1):
        cf = AnnualCashflow(year=yr)

        # ローン返済 (完済後はゼロ)
        if yr <= loan_years:
            cf.loan_payment = annual_payment
        else:
            cf.loan_payment = 0

        cf.management_fee = annual_mgmt
        cf.repair_reserve = annual_repair
        cf.property_tax = property_tax_annual
        cf.insurance = insurance_annual

        cf.total_expense = (
            cf.loan_payment
            + cf.management_fee
            + cf.repair_reserve
            + cf.property_tax
            + cf.insurance
        )

        # 住宅ローン控除
        if yr <= tax_credit_years and yr <= loan_years:
            balance = approximate_outstanding_balance(
                loan_amount, annual_interest_rate, loan_years, yr
            )
            cf.tax_credit = calc_tax_credit_annual(
                balance, tax_credit_rate, tax_credit_max
            )
        else:
            cf.tax_credit = 0

        # 減価償却の節税効果 (投資シナリオ)
        if scenario_type == "investment" and annual_depreciation > 0:
            # 経過年数が残耐用年数を超えたら0
            total_age = building_age + yr
            remaining = max(
                (RC_USEFUL_LIFE - building_age) + int(building_age * 0.2), 2
            )
            if yr <= remaining:
                cf.depreciation_benefit = int(annual_depreciation * marginal_tax_rate)

        # 賃料収入 (投資シナリオ)
        if scenario_type == "investment" and expected_rent_jpy > 0:
            cf.gross_rent = expected_rent_jpy * 12
            cf.vacancy_loss = int(cf.gross_rent * vacancy_rate)
            cf.pm_fee = int(cf.gross_rent * pm_fee_rate)
            cf.net_rent = cf.gross_rent - cf.vacancy_loss - cf.pm_fee

        # 年間CF
        cf.cashflow = (
            cf.net_rent
            + cf.tax_credit
            + cf.depreciation_benefit
            - cf.total_expense
        )
        cumulative_cf += cf.cashflow
        cf.cumulative_cashflow = cumulative_cf

        # ローン残高
        if yr <= loan_years:
            cf.outstanding_balance = approximate_outstanding_balance(
                loan_amount, annual_interest_rate, loan_years, yr
            )
        else:
            cf.outstanding_balance = 0

        cashflows.append(cf)

    # --- 出口シナリオ ---
    exit_scenarios: list[ExitScenario] = []
    for exit_yr in [5, 10, 15, 20, 25, 30]:
        if exit_yr > simulation_years:
            break

        # 想定売却価格 (年率下落)
        sale_price = int(price_jpy * (1 - annual_price_decline_rate) ** exit_yr)

        # ローン残高
        if exit_yr <= loan_years:
            balance = approximate_outstanding_balance(
                loan_amount, annual_interest_rate, loan_years, exit_yr
            )
        else:
            balance = 0

        # 売却諸費用 (仲介手数料 + 印紙代等 ≒ 売却額の4%)
        selling_costs = int(sale_price * 0.04)

        # 売却手取り (= 売却価格 - ローン残高 - 売却費用)
        net_sale = sale_price - balance - selling_costs

        # 累積CF (該当年のcashflow含む)
        cum_cf = cashflows[exit_yr - 1].cumulative_cashflow if exit_yr <= len(cashflows) else 0

        # トータルリターン = 売却手取り + 累積CF
        total_return = net_sale + cum_cf

        # 年利ROI:
        # 総投入額 (初期費用 + 年間支出総額)
        total_cash_out = initial.total + sum(
            c.total_expense for c in cashflows[:exit_yr]
        )
        # 総回収額 (控除 + 収入 + 売却手取り)
        total_cash_in = sum(
            c.tax_credit + c.depreciation_benefit + c.net_rent
            for c in cashflows[:exit_yr]
        ) + max(net_sale, 0)

        if total_cash_out > 0 and exit_yr > 0:
            # Simple annualized ROI
            net_gain = total_cash_in - total_cash_out
            annual_roi = (net_gain / total_cash_out) / exit_yr
        else:
            annual_roi = 0.0

        exit_scenarios.append(ExitScenario(
            year=exit_yr,
            sale_price=sale_price,
            outstanding_balance=balance,
            selling_costs=selling_costs,
            capital_gain=net_sale,
            cumulative_cashflow=cum_cf,
            total_return=total_return,
            annual_roi_pct=round(annual_roi * 100, 2),
        ))

    # --- サマリー (10年) ---
    cf_10 = cashflows[:10] if len(cashflows) >= 10 else cashflows
    total_cost = sum(c.total_expense for c in cf_10) + initial.total
    total_benefit = sum(c.net_rent + c.tax_credit + c.depreciation_benefit for c in cf_10)
    net_cost = total_cost - total_benefit

    return CashflowSimulationResult(
        price_jpy=price_jpy,
        scenario_type=scenario_type,
        initial_costs=initial,
        annual_cashflows=cashflows,
        exit_scenarios=exit_scenarios,
        total_cost_10yr=total_cost,
        total_benefit_10yr=total_benefit,
        net_cost_10yr=net_cost,
    )


def result_to_dict(result: CashflowSimulationResult) -> dict[str, Any]:
    """シミュレーション結果をJSON化可能な辞書に変換."""
    return {
        "price_jpy": result.price_jpy,
        "scenario_type": result.scenario_type,
        "initial_costs": {
            "down_payment": result.initial_costs.down_payment,
            "broker_fee": result.initial_costs.broker_fee,
            "registration_cost": result.initial_costs.registration_cost,
            "acquisition_tax": result.initial_costs.acquisition_tax,
            "loan_guarantee_fee": result.initial_costs.loan_guarantee_fee,
            "other_initial": result.initial_costs.other_initial,
            "total": result.initial_costs.total,
        },
        "annual_cashflows": [
            {
                "year": c.year,
                "loan_payment": c.loan_payment,
                "management_fee": c.management_fee,
                "repair_reserve": c.repair_reserve,
                "property_tax": c.property_tax,
                "insurance": c.insurance,
                "total_expense": c.total_expense,
                "tax_credit": c.tax_credit,
                "depreciation_benefit": c.depreciation_benefit,
                "gross_rent": c.gross_rent,
                "vacancy_loss": c.vacancy_loss,
                "pm_fee": c.pm_fee,
                "net_rent": c.net_rent,
                "cashflow": c.cashflow,
                "cumulative_cashflow": c.cumulative_cashflow,
                "outstanding_balance": c.outstanding_balance,
            }
            for c in result.annual_cashflows
        ],
        "exit_scenarios": [
            {
                "year": e.year,
                "sale_price": e.sale_price,
                "outstanding_balance": e.outstanding_balance,
                "selling_costs": e.selling_costs,
                "capital_gain": e.capital_gain,
                "cumulative_cashflow": e.cumulative_cashflow,
                "total_return": e.total_return,
                "annual_roi_pct": e.annual_roi_pct,
            }
            for e in result.exit_scenarios
        ],
        "summary_10yr": {
            "total_cost": result.total_cost_10yr,
            "total_benefit": result.total_benefit_10yr,
            "net_cost": result.net_cost_10yr,
        },
    }
