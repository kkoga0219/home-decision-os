"use client";

import { useState, useEffect } from "react";
import { useSearchParams } from "next/navigation";
import type {
  CashflowSimulationParams,
  CashflowSimulationResult,
  CashflowYearData,
  ExitScenarioData,
} from "@/lib/api";
import { simulateCashflow } from "@/lib/api";

// ---------------------------------------------------------------------------
// Helper
// ---------------------------------------------------------------------------

function yen(n: number): string {
  if (Math.abs(n) >= 100_000_000) return `${(n / 100_000_000).toFixed(1)}億円`;
  if (Math.abs(n) >= 10_000) return `${Math.round(n / 10_000).toLocaleString()}万円`;
  return `${n.toLocaleString()}円`;
}

function pct(n: number, digits = 1): string {
  return `${n.toFixed(digits)}%`;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function CashflowPage() {
  const searchParams = useSearchParams();

  // --- Input state (pre-filled from URL params if available) ---
  const qPrice = searchParams.get("price");
  const qArea = searchParams.get("area");
  const qYear = searchParams.get("year");
  const qMgmt = searchParams.get("mgmt");
  const qRepair = searchParams.get("repair");

  const [priceMan, setPriceMan] = useState(qPrice ? String(Math.round(Number(qPrice) / 10000)) : "3000");
  const [areaSqm, setAreaSqm] = useState(qArea || "68");
  const [builtYear, setBuiltYear] = useState(qYear || "2010");
  const [mgmtFee, setMgmtFee] = useState(qMgmt || "12000");
  const [repairRes, setRepairRes] = useState(qRepair || "8000");

  const [downPaymentMan, setDownPaymentMan] = useState("300");
  const [rate, setRate] = useState("0.5");
  const [loanYears, setLoanYears] = useState("35");

  const [scenarioType, setScenarioType] = useState<"self_use" | "investment">("self_use");
  const [rentMan, setRentMan] = useState("12");
  const [vacancyRate, setVacancyRate] = useState("5");
  const [taxRate, setTaxRate] = useState("20");
  const [declineRate, setDeclineRate] = useState("1.5");

  // --- Result state ---
  const [result, setResult] = useState<CashflowSimulationResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // --- Submit ---
  async function handleSimulate() {
    setLoading(true);
    setError("");
    try {
      const params: CashflowSimulationParams = {
        price_jpy: Number(priceMan) * 10_000,
        floor_area_sqm: Number(areaSqm),
        built_year: builtYear ? Number(builtYear) : null,
        management_fee_jpy: Number(mgmtFee),
        repair_reserve_jpy: Number(repairRes),
        down_payment_jpy: Number(downPaymentMan) * 10_000,
        annual_interest_rate: Number(rate) / 100,
        loan_years: Number(loanYears),
        scenario_type: scenarioType,
        expected_rent_jpy: scenarioType === "investment" ? Number(rentMan) * 10_000 : 0,
        vacancy_rate: Number(vacancyRate) / 100,
        marginal_tax_rate: Number(taxRate) / 100,
        annual_price_decline_rate: Number(declineRate) / 100,
        simulation_years: Number(loanYears),
      };
      const res = await simulateCashflow(params);
      setResult(res);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "エラーが発生しました");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="max-w-7xl mx-auto p-4">
      <h1 className="text-2xl font-bold mb-6">キャッシュフローシミュレーション</h1>

      {/* ====== Input Form ====== */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
        {/* Property Info */}
        <div className="bg-white border rounded-lg p-4">
          <h2 className="font-semibold text-lg mb-3">物件情報</h2>
          <div className="grid grid-cols-2 gap-3">
            <label className="block">
              <span className="text-sm text-gray-600">価格（万円）</span>
              <input type="number" value={priceMan} onChange={e => setPriceMan(e.target.value)}
                className="mt-1 w-full border rounded px-2 py-1" />
            </label>
            <label className="block">
              <span className="text-sm text-gray-600">面積（㎡）</span>
              <input type="number" value={areaSqm} onChange={e => setAreaSqm(e.target.value)}
                className="mt-1 w-full border rounded px-2 py-1" />
            </label>
            <label className="block">
              <span className="text-sm text-gray-600">築年</span>
              <input type="number" value={builtYear} onChange={e => setBuiltYear(e.target.value)}
                className="mt-1 w-full border rounded px-2 py-1" />
            </label>
            <label className="block">
              <span className="text-sm text-gray-600">管理費（円/月）</span>
              <input type="number" value={mgmtFee} onChange={e => setMgmtFee(e.target.value)}
                className="mt-1 w-full border rounded px-2 py-1" />
            </label>
            <label className="block col-span-2">
              <span className="text-sm text-gray-600">修繕積立金（円/月）</span>
              <input type="number" value={repairRes} onChange={e => setRepairRes(e.target.value)}
                className="mt-1 w-full border rounded px-2 py-1" />
            </label>
          </div>
        </div>

        {/* Loan Conditions */}
        <div className="bg-white border rounded-lg p-4">
          <h2 className="font-semibold text-lg mb-3">ローン条件</h2>
          <div className="grid grid-cols-2 gap-3">
            <label className="block">
              <span className="text-sm text-gray-600">頭金（万円）</span>
              <input type="number" value={downPaymentMan} onChange={e => setDownPaymentMan(e.target.value)}
                className="mt-1 w-full border rounded px-2 py-1" />
            </label>
            <label className="block">
              <span className="text-sm text-gray-600">金利（%）</span>
              <input type="number" step="0.01" value={rate} onChange={e => setRate(e.target.value)}
                className="mt-1 w-full border rounded px-2 py-1" />
            </label>
            <label className="block">
              <span className="text-sm text-gray-600">返済期間（年）</span>
              <input type="number" value={loanYears} onChange={e => setLoanYears(e.target.value)}
                className="mt-1 w-full border rounded px-2 py-1" />
            </label>
            <label className="block">
              <span className="text-sm text-gray-600">年間下落率（%）</span>
              <input type="number" step="0.1" value={declineRate} onChange={e => setDeclineRate(e.target.value)}
                className="mt-1 w-full border rounded px-2 py-1" />
            </label>
          </div>

          {/* Scenario Type */}
          <div className="mt-4">
            <span className="text-sm text-gray-600 block mb-1">シナリオ</span>
            <div className="flex gap-4">
              <label className="flex items-center gap-1">
                <input type="radio" name="scenario" value="self_use"
                  checked={scenarioType === "self_use"}
                  onChange={() => setScenarioType("self_use")} />
                <span className="text-sm">自己居住</span>
              </label>
              <label className="flex items-center gap-1">
                <input type="radio" name="scenario" value="investment"
                  checked={scenarioType === "investment"}
                  onChange={() => setScenarioType("investment")} />
                <span className="text-sm">投資（賃貸運用）</span>
              </label>
            </div>
          </div>

          {scenarioType === "investment" && (
            <div className="grid grid-cols-3 gap-3 mt-3">
              <label className="block">
                <span className="text-sm text-gray-600">想定賃料（万円/月）</span>
                <input type="number" step="0.1" value={rentMan} onChange={e => setRentMan(e.target.value)}
                  className="mt-1 w-full border rounded px-2 py-1" />
              </label>
              <label className="block">
                <span className="text-sm text-gray-600">空室率（%）</span>
                <input type="number" step="1" value={vacancyRate} onChange={e => setVacancyRate(e.target.value)}
                  className="mt-1 w-full border rounded px-2 py-1" />
              </label>
              <label className="block">
                <span className="text-sm text-gray-600">所得税率（%）</span>
                <input type="number" step="1" value={taxRate} onChange={e => setTaxRate(e.target.value)}
                  className="mt-1 w-full border rounded px-2 py-1" />
              </label>
            </div>
          )}
        </div>
      </div>

      {/* Submit */}
      <div className="mb-8 text-center">
        <button onClick={handleSimulate} disabled={loading}
          className="bg-blue-600 text-white px-8 py-2 rounded-lg hover:bg-blue-700 disabled:opacity-50">
          {loading ? "計算中..." : "シミュレーション実行"}
        </button>
      </div>
      {error && <p className="text-red-600 text-center mb-4">{error}</p>}

      {/* ====== Results ====== */}
      {result && (
        <div className="space-y-6">
          {/* Initial Costs */}
          <InitialCostCard costs={result.initial_costs} />

          {/* 10yr Summary */}
          <SummaryCard result={result} />

          {/* Exit Scenarios */}
          <ExitScenarioTable scenarios={result.exit_scenarios} />

          {/* Annual Cashflow Table */}
          <AnnualCashflowTable
            cashflows={result.annual_cashflows}
            scenarioType={result.scenario_type}
          />
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub components
// ---------------------------------------------------------------------------

function InitialCostCard({ costs }: { costs: CashflowSimulationResult["initial_costs"] }) {
  return (
    <div className="bg-white border rounded-lg p-4">
      <h2 className="font-semibold text-lg mb-3">購入時諸費用</h2>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <Stat label="頭金" value={yen(costs.down_payment)} />
        <Stat label="仲介手数料" value={yen(costs.broker_fee)} />
        <Stat label="登記費用" value={yen(costs.registration_cost)} />
        <Stat label="不動産取得税" value={yen(costs.acquisition_tax)} />
        <Stat label="ローン保証料" value={yen(costs.loan_guarantee_fee)} />
        <Stat label="その他" value={yen(costs.other_initial)} />
        <Stat label="合計" value={yen(costs.total)} highlight />
      </div>
    </div>
  );
}

function SummaryCard({ result }: { result: CashflowSimulationResult }) {
  const s = result.summary_10yr;
  return (
    <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
      <h2 className="font-semibold text-lg mb-3">10年間サマリー</h2>
      <div className="grid grid-cols-3 gap-4">
        <Stat label="総支出（諸費用含む）" value={yen(s.total_cost)} />
        <Stat label="総控除・収入" value={yen(s.total_benefit)} />
        <Stat label="実質負担" value={yen(s.net_cost)} highlight />
      </div>
      {result.scenario_type === "self_use" && (
        <p className="text-sm text-gray-500 mt-2">
          ※ 住宅ローン控除による節税効果を含む。月額実質負担: 約{yen(Math.round(s.net_cost / 120))}/月
        </p>
      )}
    </div>
  );
}

function ExitScenarioTable({ scenarios }: { scenarios: ExitScenarioData[] }) {
  return (
    <div className="bg-white border rounded-lg p-4 overflow-x-auto">
      <h2 className="font-semibold text-lg mb-3">売却シナリオ（出口戦略）</h2>
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b text-left text-gray-500">
            <th className="py-2 px-2">売却年</th>
            <th className="py-2 px-2 text-right">想定売却価格</th>
            <th className="py-2 px-2 text-right">ローン残高</th>
            <th className="py-2 px-2 text-right">売却諸費用</th>
            <th className="py-2 px-2 text-right">売却手取り</th>
            <th className="py-2 px-2 text-right">累積CF</th>
            <th className="py-2 px-2 text-right">トータルリターン</th>
            <th className="py-2 px-2 text-right">年利ROI</th>
          </tr>
        </thead>
        <tbody>
          {scenarios.map(e => (
            <tr key={e.year} className="border-b hover:bg-gray-50">
              <td className="py-2 px-2">{e.year}年後</td>
              <td className="py-2 px-2 text-right">{yen(e.sale_price)}</td>
              <td className="py-2 px-2 text-right">{yen(e.outstanding_balance)}</td>
              <td className="py-2 px-2 text-right">{yen(e.selling_costs)}</td>
              <td className="py-2 px-2 text-right">{yen(e.capital_gain)}</td>
              <td className="py-2 px-2 text-right">{yen(e.cumulative_cashflow)}</td>
              <td className={`py-2 px-2 text-right font-medium ${e.total_return >= 0 ? "text-green-700" : "text-red-600"}`}>
                {yen(e.total_return)}
              </td>
              <td className={`py-2 px-2 text-right ${e.annual_roi_pct >= 0 ? "text-green-700" : "text-red-600"}`}>
                {pct(e.annual_roi_pct)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function AnnualCashflowTable({
  cashflows,
  scenarioType,
}: {
  cashflows: CashflowYearData[];
  scenarioType: string;
}) {
  const isInvestment = scenarioType === "investment";
  // Show first 15 years + every 5th year after
  const display = cashflows.filter(
    (c) => c.year <= 15 || c.year % 5 === 0,
  );

  return (
    <div className="bg-white border rounded-lg p-4 overflow-x-auto">
      <h2 className="font-semibold text-lg mb-3">年次キャッシュフロー詳細</h2>
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b text-left text-gray-500">
            <th className="py-1 px-1">年</th>
            <th className="py-1 px-1 text-right">ローン返済</th>
            <th className="py-1 px-1 text-right">管理費+修繕</th>
            <th className="py-1 px-1 text-right">固定資産税</th>
            <th className="py-1 px-1 text-right">総支出</th>
            <th className="py-1 px-1 text-right">ローン控除</th>
            {isInvestment && <th className="py-1 px-1 text-right">賃料収入(税)</th>}
            {isInvestment && <th className="py-1 px-1 text-right">減価償却節税</th>}
            <th className="py-1 px-1 text-right">年間CF</th>
            <th className="py-1 px-1 text-right">累積CF</th>
            <th className="py-1 px-1 text-right">ローン残高</th>
          </tr>
        </thead>
        <tbody>
          {display.map(c => (
            <tr key={c.year} className="border-b hover:bg-gray-50">
              <td className="py-1 px-1">{c.year}</td>
              <td className="py-1 px-1 text-right">{yen(c.loan_payment)}</td>
              <td className="py-1 px-1 text-right">{yen(c.management_fee + c.repair_reserve)}</td>
              <td className="py-1 px-1 text-right">{yen(c.property_tax)}</td>
              <td className="py-1 px-1 text-right">{yen(c.total_expense)}</td>
              <td className="py-1 px-1 text-right text-green-700">{c.tax_credit > 0 ? `+${yen(c.tax_credit)}` : "-"}</td>
              {isInvestment && (
                <td className="py-1 px-1 text-right text-green-700">
                  {c.net_rent > 0 ? `+${yen(c.net_rent)}` : "-"}
                </td>
              )}
              {isInvestment && (
                <td className="py-1 px-1 text-right text-green-700">
                  {c.depreciation_benefit > 0 ? `+${yen(c.depreciation_benefit)}` : "-"}
                </td>
              )}
              <td className={`py-1 px-1 text-right font-medium ${c.cashflow >= 0 ? "text-green-700" : "text-red-600"}`}>
                {yen(c.cashflow)}
              </td>
              <td className={`py-1 px-1 text-right ${c.cumulative_cashflow >= 0 ? "text-green-700" : "text-red-600"}`}>
                {yen(c.cumulative_cashflow)}
              </td>
              <td className="py-1 px-1 text-right text-gray-500">{yen(c.outstanding_balance)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Stat({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div>
      <p className="text-xs text-gray-500">{label}</p>
      <p className={`text-base font-medium ${highlight ? "text-blue-700" : ""}`}>{value}</p>
    </div>
  );
}
