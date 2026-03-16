"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import type { Property, LoanScenario, RentalScenario, ExitScore, LoanScenarioCreate, RentalScenarioCreate, RentEstimateResponse } from "@/lib/types";
import {
  getProperty, deleteProperty,
  listLoanScenarios, createLoanScenario,
  listRentalScenarios, createRentalScenario,
  getExitScore, calculateExitScore,
  fetchRentEstimate,
  simulateCashflowForProperty,
  runValuation,
} from "@/lib/api";
import type {
  CashflowSimulationResult, ExitScenarioData,
  ValuationResult, CompTransaction,
} from "@/lib/api";
import { yen, yenCompact, pct, signedYen } from "@/lib/format";
import KpiCard from "@/components/KpiCard";
import ScoreBar from "@/components/ScoreBar";

/* ── Loan form defaults ── */
const DEFAULT_LOAN: LoanScenarioCreate = {
  label: "",
  down_payment_jpy: 0,
  annual_interest_rate: 0.005,
  loan_years: 35,
};

/* ── Rental form defaults ── */
const DEFAULT_RENTAL: RentalScenarioCreate = {
  label: "",
  expected_rent_jpy: 0,
  vacancy_rate: 0.05,
  management_fee_rate: 0.05,
  fixed_asset_tax_annual_jpy: 100000,
  insurance_annual_jpy: 20000,
  other_cost_annual_jpy: 0,
};

const inputClass = "w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none";
const btnPrimary = "bg-primary-600 text-white px-4 py-2 rounded-lg hover:bg-primary-700 text-sm font-medium transition-colors disabled:opacity-50";

export default function PropertyDetailPage() {
  const { id } = useParams();
  const router = useRouter();
  const propertyId = Number(id);

  const [property, setProperty] = useState<Property | null>(null);
  const [loans, setLoans] = useState<LoanScenario[]>([]);
  const [rentals, setRentals] = useState<RentalScenario[]>([]);
  const [exitScore, setExitScore] = useState<ExitScore | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Forms
  const [showLoanForm, setShowLoanForm] = useState(false);
  const [loanForm, setLoanForm] = useState<LoanScenarioCreate>(DEFAULT_LOAN);
  const [showRentalForm, setShowRentalForm] = useState(false);
  const [rentalForm, setRentalForm] = useState<RentalScenarioCreate>(DEFAULT_RENTAL);
  const [rentEstimate, setRentEstimate] = useState<RentEstimateResponse | null>(null);

  // ML Valuation
  const [valuation, setValuation] = useState<ValuationResult | null>(null);
  const [valLoading, setValLoading] = useState(false);

  // Cashflow simulation
  const [cfResult, setCfResult] = useState<CashflowSimulationResult | null>(null);
  const [cfLoading, setCfLoading] = useState(false);
  const [cfScenario, setCfScenario] = useState<"self_use" | "investment">("self_use");
  const [cfParams, setCfParams] = useState({
    down_payment_jpy: 0,
    annual_interest_rate: 0.005,
    loan_years: 35,
    simulation_years: 35,
  });

  async function handleSimulateCF() {
    setCfLoading(true);
    try {
      const res = await simulateCashflowForProperty(propertyId, {
        ...cfParams,
        scenario_type: cfScenario,
      });
      setCfResult(res);
    } catch (err: any) {
      console.error("CF simulation failed:", err);
    } finally {
      setCfLoading(false);
    }
  }

  async function handleRunValuation() {
    if (!property) return;
    setValLoading(true);
    try {
      const prefMatch = property.address_text?.match(
        /(東京都|大阪府|京都府|兵庫県|神奈川県|愛知県|福岡県|北海道|.{2,3}県)/
      );
      const builtYear = property.built_year;
      const ageYears = builtYear ? new Date().getFullYear() - builtYear : undefined;
      const res = await runValuation({
        price_jpy: property.price_jpy,
        floor_area_sqm: property.floor_area_sqm ?? undefined,
        age_years: ageYears,
        walking_minutes: property.walking_minutes ?? undefined,
        layout: property.layout ?? undefined,
        station_name: property.station_name ?? undefined,
        prefecture: prefMatch?.[1] ?? "",
      });
      setValuation(res);
    } catch (err: any) {
      console.error("Valuation failed:", err);
    } finally {
      setValLoading(false);
    }
  }

  async function loadAll() {
    try {
      const [p, l, r, e] = await Promise.all([
        getProperty(propertyId),
        listLoanScenarios(propertyId),
        listRentalScenarios(propertyId),
        getExitScore(propertyId),
      ]);
      setProperty(p);
      setLoans(l);
      setRentals(r);
      setExitScore(e);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { loadAll(); }, [propertyId]);

  async function handleCreateLoan(e: React.FormEvent) {
    e.preventDefault();
    await createLoanScenario(propertyId, loanForm);
    setShowLoanForm(false);
    setLoanForm(DEFAULT_LOAN);
    const updated = await listLoanScenarios(propertyId);
    setLoans(updated);
  }

  async function handleCreateRental(e: React.FormEvent) {
    e.preventDefault();
    await createRentalScenario(propertyId, rentalForm);
    setShowRentalForm(false);
    setRentalForm(DEFAULT_RENTAL);
    const updated = await listRentalScenarios(propertyId);
    setRentals(updated);
  }

  async function handleCalcExitScore() {
    const score = await calculateExitScore(propertyId);
    setExitScore(score);
  }

  async function handleEstimateRent() {
    if (!property) return;
    try {
      const est = await fetchRentEstimate({
        price_jpy: property.price_jpy,
        floor_area_sqm: property.floor_area_sqm,
        built_year: property.built_year,
        walking_minutes: property.walking_minutes,
        prefecture: property.address_text?.match(/(東京都|大阪府|兵庫県|京都府|神奈川県|愛知県|福岡県)/)?.[1] ?? "",
      });
      setRentEstimate(est);
      // Pre-fill the rental form with estimated rent
      setRentalForm((prev) => ({ ...prev, expected_rent_jpy: est.estimated_rent, label: "AI推定" }));
      setShowRentalForm(true);
    } catch (err: any) {
      console.error("Rent estimate failed:", err);
    }
  }

  async function handleDelete() {
    if (!confirm("この物件を削除しますか？関連するシナリオも全て削除されます。")) return;
    await deleteProperty(propertyId);
    router.push("/");
  }

  if (loading) return <div className="text-center py-20 text-gray-400">読み込み中...</div>;
  if (error) return <div className="bg-red-50 text-red-700 rounded-lg p-4">{error}</div>;
  if (!property) return <div className="text-center py-20 text-gray-400">物件が見つかりません</div>;

  const p = property;

  return (
    <div className="space-y-8">
      {/* ── Header ── */}
      <div className="flex items-start justify-between">
        <div>
          <Link href="/" className="text-sm text-gray-400 hover:text-primary-600">← 物件一覧</Link>
          <h1 className="text-2xl font-bold mt-1">{p.name}</h1>
          <p className="text-sm text-gray-500 mt-1">{p.address_text}</p>
        </div>
        <div className="flex items-center gap-2">
          {p.source_url && (
            <a href={p.source_url} target="_blank" rel="noopener noreferrer" className="text-sm text-primary-600 hover:underline">
              物件ページ ↗
            </a>
          )}
          <button onClick={handleDelete} className="text-sm text-red-500 hover:text-red-700">削除</button>
        </div>
      </div>

      {/* ── Property Info ── */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <KpiCard title="価格" value={yenCompact(p.price_jpy)} />
        <KpiCard title="面積" value={p.floor_area_sqm ? `${p.floor_area_sqm}㎡` : "-"} sub={p.layout ?? undefined} />
        <KpiCard title="最寄り駅" value={p.station_name ?? "-"} sub={p.walking_minutes != null ? `徒歩${p.walking_minutes}分` : undefined} />
        <KpiCard title="築年数" value={p.built_year ? `${new Date().getFullYear() - p.built_year}年` : "-"} sub={p.built_year ? `${p.built_year}年築` : undefined} />
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <KpiCard title="管理費" value={yen(p.management_fee_jpy)} sub="/月" />
        <KpiCard title="修繕積立金" value={yen(p.repair_reserve_jpy)} sub="/月" />
        <KpiCard title="総戸数" value={p.total_units ? `${p.total_units}戸` : "-"} />
        <KpiCard title="用途地域" value={p.zoning_type ?? "-"} />
      </div>

      {p.memo && (
        <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4 text-sm text-yellow-800">
          <span className="font-medium">メモ:</span> {p.memo}
        </div>
      )}

      {/* ── ML Valuation Panel ── */}
      <section>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-bold">ML バリュエーション</h2>
          <button onClick={handleRunValuation} disabled={valLoading} className={btnPrimary}>
            {valLoading ? "分析中..." : valuation ? "再分析" : "ML分析を実行"}
          </button>
        </div>

        {!valuation && !valLoading && (
          <p className="text-sm text-gray-400">
            「ML分析を実行」で国交省取引データに基づく機械学習評価を行います
          </p>
        )}

        {valuation && (
          <div className="space-y-4">
            {/* Dataset info banner */}
            <div className={`rounded-lg p-3 text-sm ${valuation.mlit_available ? "bg-purple-50 border border-purple-200 text-purple-800" : "bg-gray-50 border border-gray-200 text-gray-600"}`}>
              {valuation.mlit_available
                ? `MLIT実取引データ ${valuation.dataset_size}件を使用`
                : "MLITデータ未取得（ルールベース推定）"}
              {valuation.errors.length > 0 && (
                <span className="ml-2 text-xs text-orange-600">
                  ({valuation.errors.length}件の警告あり)
                </span>
              )}
            </div>

            {/* Hedonic Price Prediction */}
            {valuation.hedonic && (
              <div className="bg-white border border-gray-200 rounded-lg p-5">
                <h3 className="text-sm font-bold text-gray-700 mb-3">ヘドニック価格モデル</h3>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-3">
                  <div>
                    <span className="text-xs text-gray-500">予測価格</span>
                    <div className="text-lg font-bold text-purple-700">
                      {yenCompact(valuation.hedonic.predicted_total_price)}
                    </div>
                  </div>
                  <div>
                    <span className="text-xs text-gray-500">㎡単価</span>
                    <div className="font-bold">
                      {Math.round(valuation.hedonic.predicted_unit_price).toLocaleString()}円/㎡
                    </div>
                  </div>
                  <div>
                    <span className="text-xs text-gray-500">信頼区間</span>
                    <div className="text-sm">
                      {yenCompact(valuation.hedonic.confidence_low)} 〜 {yenCompact(valuation.hedonic.confidence_high)}
                    </div>
                  </div>
                  <div>
                    <span className="text-xs text-gray-500">乖離率</span>
                    <div className={`font-bold ${
                      (valuation.hedonic.deviation_pct ?? 0) < -8 ? "text-green-600"
                        : (valuation.hedonic.deviation_pct ?? 0) > 8 ? "text-red-600"
                        : "text-gray-700"
                    }`}>
                      {valuation.hedonic.deviation_pct != null
                        ? `${valuation.hedonic.deviation_pct > 0 ? "+" : ""}${valuation.hedonic.deviation_pct.toFixed(1)}%`
                        : "-"}
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-4 text-xs text-gray-500">
                  <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                    valuation.hedonic.assessment.includes("割安") ? "bg-green-100 text-green-700"
                      : valuation.hedonic.assessment.includes("割高") ? "bg-red-100 text-red-700"
                      : "bg-gray-100 text-gray-700"
                  }`}>
                    {valuation.hedonic.assessment}
                  </span>
                  <span>R²: {valuation.hedonic.model_r2.toFixed(3)}</span>
                  <span>MAPE: {(valuation.hedonic.model_mape * 100).toFixed(1)}%</span>
                  <span>{valuation.hedonic.training_samples}件で学習</span>
                </div>
              </div>
            )}

            {/* Comparable Transactions */}
            {valuation.comps && (
              <div className="bg-white border border-gray-200 rounded-lg p-5">
                <h3 className="text-sm font-bold text-gray-700 mb-3">
                  取引事例比較法（{valuation.comps.n_comps}件）
                </h3>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-3">
                  <div>
                    <span className="text-xs text-gray-500">中央値総額</span>
                    <div className="text-lg font-bold">{yenCompact(valuation.comps.median_total_price)}</div>
                  </div>
                  <div>
                    <span className="text-xs text-gray-500">価格帯</span>
                    <div className="text-sm">
                      {yenCompact(valuation.comps.price_range_low)} 〜 {yenCompact(valuation.comps.price_range_high)}
                    </div>
                  </div>
                  <div>
                    <span className="text-xs text-gray-500">加重平均㎡単価</span>
                    <div className="font-bold">{valuation.comps.weighted_avg_price.toLocaleString()}円</div>
                  </div>
                  <div>
                    <span className="text-xs text-gray-500">判定</span>
                    <div className={`font-bold ${
                      valuation.comps.assessment.includes("割安") ? "text-green-600"
                        : valuation.comps.assessment.includes("割高") ? "text-red-600"
                        : "text-gray-700"
                    }`}>
                      {valuation.comps.assessment}
                    </div>
                  </div>
                </div>
                {/* Top comps table */}
                {valuation.comps.top_comps.length > 0 && (
                  <CompsTable comps={valuation.comps.top_comps} />
                )}
              </div>
            )}

            {/* Trend + ML Rent + Exit Score row */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {/* Price Trend */}
              {valuation.trend && (
                <div className="bg-white border border-gray-200 rounded-lg p-4">
                  <h3 className="text-sm font-bold text-gray-700 mb-2">価格トレンド</h3>
                  <div className={`text-2xl font-bold mb-1 ${
                    valuation.trend.trend_pct_annual > 0 ? "text-green-600" : "text-red-600"
                  }`}>
                    {valuation.trend.trend_pct_annual > 0 ? "+" : ""}
                    {valuation.trend.trend_pct_annual.toFixed(1)}%/年
                  </div>
                  <div className="text-xs text-gray-500 space-y-1">
                    <div>方向: {valuation.trend.trend_direction}</div>
                    <div>加速度: {valuation.trend.acceleration}</div>
                    <div>ボラティリティ: {valuation.trend.volatility}</div>
                    <div>{valuation.trend.n_transactions}件 / {valuation.trend.n_quarters}四半期</div>
                  </div>
                </div>
              )}

              {/* ML Rent */}
              {valuation.ml_rent && (
                <div className="bg-white border border-gray-200 rounded-lg p-4">
                  <h3 className="text-sm font-bold text-gray-700 mb-2">ML賃料推定</h3>
                  <div className="text-2xl font-bold text-blue-700 mb-1">
                    {valuation.ml_rent.estimated_rent.toLocaleString()}円/月
                  </div>
                  <div className="text-xs text-gray-500 space-y-1">
                    <div>レンジ: {valuation.ml_rent.low_estimate.toLocaleString()} 〜 {valuation.ml_rent.high_estimate.toLocaleString()}</div>
                    <div>表面利回り: {(valuation.ml_rent.gross_yield * 100).toFixed(2)}%</div>
                    <div>Cap Rate: {(valuation.ml_rent.cap_rate * 100).toFixed(2)}%</div>
                    <div>信頼度: {valuation.ml_rent.confidence}</div>
                  </div>
                </div>
              )}

              {/* ML Exit Score */}
              {valuation.ml_exit_score && (
                <div className="bg-white border border-gray-200 rounded-lg p-4">
                  <h3 className="text-sm font-bold text-gray-700 mb-2">ML出口スコア</h3>
                  <div className={`text-3xl font-bold mb-1 ${
                    valuation.ml_exit_score.total_score >= 70 ? "text-green-600"
                      : valuation.ml_exit_score.total_score >= 50 ? "text-yellow-600"
                      : "text-red-600"
                  }`}>
                    {valuation.ml_exit_score.total_score}
                    <span className="text-sm text-gray-400 font-normal ml-1">/100</span>
                  </div>
                  <div className="text-xs text-gray-500 space-y-1">
                    <div>{valuation.ml_exit_score.assessment}</div>
                    <div>流動性: {valuation.ml_exit_score.liquidity.detail}</div>
                    <div>価格維持: {valuation.ml_exit_score.price_retention.detail}</div>
                    <div>勢い: {valuation.ml_exit_score.momentum.detail}</div>
                    <div>需要: {valuation.ml_exit_score.demand_match.detail}</div>
                    <div className="text-purple-600">{valuation.ml_exit_score.n_transactions}件の実取引データ</div>
                  </div>
                </div>
              )}
            </div>

            {/* Warnings */}
            {valuation.errors.length > 0 && (
              <div className="bg-orange-50 border border-orange-200 rounded-lg p-3 text-xs text-orange-700">
                <span className="font-medium">警告:</span>
                {valuation.errors.map((e, i) => <div key={i}>・{e}</div>)}
              </div>
            )}
          </div>
        )}
      </section>

      {/* ── Loan Scenarios ── */}
      <section>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-bold">住宅ローンシナリオ</h2>
          <button onClick={() => setShowLoanForm(!showLoanForm)} className={btnPrimary}>
            {showLoanForm ? "閉じる" : "+ シナリオ追加"}
          </button>
        </div>

        {showLoanForm && (
          <form onSubmit={handleCreateLoan} className="bg-gray-50 rounded-lg p-4 mb-4 space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs text-gray-500">ラベル</label>
                <input className={inputClass} placeholder="例: 変動0.5%" value={loanForm.label ?? ""} onChange={(e) => setLoanForm({ ...loanForm, label: e.target.value })} />
              </div>
              <div>
                <label className="text-xs text-gray-500">頭金（円）</label>
                <input className={inputClass} type="number" min={0} value={loanForm.down_payment_jpy} onChange={(e) => setLoanForm({ ...loanForm, down_payment_jpy: Number(e.target.value) })} />
              </div>
              <div>
                <label className="text-xs text-gray-500">年利（例: 0.005 = 0.5%）</label>
                <input className={inputClass} type="number" step="0.001" min={0} max={0.2} value={loanForm.annual_interest_rate} onChange={(e) => setLoanForm({ ...loanForm, annual_interest_rate: Number(e.target.value) })} />
              </div>
              <div>
                <label className="text-xs text-gray-500">返済年数</label>
                <input className={inputClass} type="number" min={1} max={50} value={loanForm.loan_years} onChange={(e) => setLoanForm({ ...loanForm, loan_years: Number(e.target.value) })} />
              </div>
            </div>
            <button type="submit" className={btnPrimary}>計算して保存</button>
          </form>
        )}

        {loans.length === 0 ? (
          <p className="text-sm text-gray-400">ローンシナリオがまだありません</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-gray-500">
                  <th className="pb-2 font-medium">ラベル</th>
                  <th className="pb-2 font-medium text-right">頭金</th>
                  <th className="pb-2 font-medium text-right">借入額</th>
                  <th className="pb-2 font-medium text-right">金利</th>
                  <th className="pb-2 font-medium text-right">年数</th>
                  <th className="pb-2 font-medium text-right">月額返済</th>
                  <th className="pb-2 font-medium text-right">総返済額</th>
                </tr>
              </thead>
              <tbody>
                {loans.map((l) => (
                  <tr key={l.id} className="border-b border-gray-100">
                    <td className="py-2">{l.label || "-"}</td>
                    <td className="py-2 text-right">{yenCompact(l.down_payment_jpy)}</td>
                    <td className="py-2 text-right">{yenCompact(l.loan_amount_jpy)}</td>
                    <td className="py-2 text-right">{pct(l.annual_interest_rate)}</td>
                    <td className="py-2 text-right">{l.loan_years}年</td>
                    <td className="py-2 text-right font-bold">{yen(l.monthly_payment_jpy)}</td>
                    <td className="py-2 text-right">{yenCompact(l.total_payment_jpy)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* ── Rental Scenarios ── */}
      <section>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-bold">賃貸シナリオ</h2>
          <div className="flex gap-2">
            <button onClick={handleEstimateRent} className="bg-accent-600 text-white px-4 py-2 rounded-lg hover:bg-accent-500 text-sm font-medium transition-colors">
              賃料を自動推定
            </button>
            <button onClick={() => setShowRentalForm(!showRentalForm)} className={btnPrimary}>
              {showRentalForm ? "閉じる" : "+ シナリオ追加"}
            </button>
          </div>
        </div>

        {rentEstimate && (
          <div className="bg-green-50 border border-green-200 rounded-lg p-4 mb-4 text-sm">
            <div className="font-medium text-green-800 mb-2">賃料推定結果</div>
            <div className="grid grid-cols-3 gap-4 text-green-700">
              <div>
                <span className="text-green-500 text-xs">悲観</span>
                <div className="font-bold">{rentEstimate.low_estimate.toLocaleString()}円</div>
              </div>
              <div>
                <span className="text-green-500 text-xs">標準（推定値）</span>
                <div className="font-bold text-lg">{rentEstimate.estimated_rent.toLocaleString()}円</div>
              </div>
              <div>
                <span className="text-green-500 text-xs">楽観</span>
                <div className="font-bold">{rentEstimate.high_estimate.toLocaleString()}円</div>
              </div>
            </div>
            <p className="text-xs text-green-600 mt-2">{rentEstimate.method}</p>
          </div>
        )}

        {showRentalForm && (
          <form onSubmit={handleCreateRental} className="bg-gray-50 rounded-lg p-4 mb-4 space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs text-gray-500">ラベル</label>
                <input className={inputClass} placeholder="例: 標準シナリオ" value={rentalForm.label ?? ""} onChange={(e) => setRentalForm({ ...rentalForm, label: e.target.value })} />
              </div>
              <div>
                <label className="text-xs text-gray-500">想定月額家賃（円）</label>
                <input className={inputClass} type="number" min={0} value={rentalForm.expected_rent_jpy} onChange={(e) => setRentalForm({ ...rentalForm, expected_rent_jpy: Number(e.target.value) })} required />
              </div>
              <div>
                <label className="text-xs text-gray-500">空室率（例: 0.05 = 5%）</label>
                <input className={inputClass} type="number" step="0.01" min={0} max={1} value={rentalForm.vacancy_rate} onChange={(e) => setRentalForm({ ...rentalForm, vacancy_rate: Number(e.target.value) })} />
              </div>
              <div>
                <label className="text-xs text-gray-500">管理委託率（例: 0.05 = 5%）</label>
                <input className={inputClass} type="number" step="0.01" min={0} max={1} value={rentalForm.management_fee_rate} onChange={(e) => setRentalForm({ ...rentalForm, management_fee_rate: Number(e.target.value) })} />
              </div>
              <div>
                <label className="text-xs text-gray-500">固定資産税（年額）</label>
                <input className={inputClass} type="number" min={0} value={rentalForm.fixed_asset_tax_annual_jpy} onChange={(e) => setRentalForm({ ...rentalForm, fixed_asset_tax_annual_jpy: Number(e.target.value) })} />
              </div>
              <div>
                <label className="text-xs text-gray-500">保険料（年額）</label>
                <input className={inputClass} type="number" min={0} value={rentalForm.insurance_annual_jpy} onChange={(e) => setRentalForm({ ...rentalForm, insurance_annual_jpy: Number(e.target.value) })} />
              </div>
            </div>
            <button type="submit" className={btnPrimary}>計算して保存</button>
          </form>
        )}

        {rentals.length === 0 ? (
          <p className="text-sm text-gray-400">賃貸シナリオがまだありません</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-gray-500">
                  <th className="pb-2 font-medium">ラベル</th>
                  <th className="pb-2 font-medium text-right">想定家賃</th>
                  <th className="pb-2 font-medium text-right">空室率</th>
                  <th className="pb-2 font-medium text-right">管理率</th>
                  <th className="pb-2 font-medium text-right">月次CF</th>
                </tr>
              </thead>
              <tbody>
                {rentals.map((r) => (
                  <tr key={r.id} className="border-b border-gray-100">
                    <td className="py-2">{r.label || "-"}</td>
                    <td className="py-2 text-right">{yen(r.expected_rent_jpy)}</td>
                    <td className="py-2 text-right">{pct(r.vacancy_rate)}</td>
                    <td className="py-2 text-right">{pct(r.management_fee_rate)}</td>
                    <td className={`py-2 text-right font-bold ${(r.monthly_net_cashflow_jpy ?? 0) >= 0 ? "text-green-600" : "text-red-600"}`}>
                      {signedYen(r.monthly_net_cashflow_jpy)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* ── Exit Score ── */}
      <section>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-bold">出口スコア</h2>
          <button onClick={handleCalcExitScore} className={btnPrimary}>
            {exitScore ? "再計算" : "計算する"}
          </button>
        </div>

        {exitScore ? (
          <div className="bg-white border border-gray-200 rounded-lg p-6">
            <div className="flex items-center gap-4 mb-6">
              <div className={`text-4xl font-bold ${exitScore.total_score >= 70 ? "text-green-600" : exitScore.total_score >= 50 ? "text-yellow-600" : "text-red-600"}`}>
                {exitScore.total_score}
              </div>
              <div className="text-sm text-gray-500">/ 100点</div>
              <div className="text-sm">
                {exitScore.total_score >= 80 && "出口戦略: 非常に良好"}
                {exitScore.total_score >= 60 && exitScore.total_score < 80 && "出口戦略: 良好"}
                {exitScore.total_score >= 40 && exitScore.total_score < 60 && "出口戦略: 注意が必要"}
                {exitScore.total_score < 40 && "出口戦略: リスクあり"}
              </div>
            </div>
            {exitScore.assessment && (
              <p className="text-sm text-gray-600 mb-4 bg-gray-50 rounded p-3">{exitScore.assessment}</p>
            )}
            <div className="space-y-3">
              <ScoreBar label="駅距離" score={exitScore.station_score} />
              <ScoreBar label="面積" score={exitScore.size_score} />
              <ScoreBar label="間取り" score={exitScore.layout_score} />
              <ScoreBar label="築年数" score={exitScore.age_score} />
              <ScoreBar label="用途地域" score={exitScore.zoning_score} />
              <ScoreBar label="ハザード" score={exitScore.hazard_score} />
              <ScoreBar label="流動性" score={exitScore.liquidity_score} />
            </div>
          </div>
        ) : (
          <p className="text-sm text-gray-400">「計算する」ボタンを押すと出口スコアが算出されます</p>
        )}
      </section>

      {/* ── Cashflow Simulation ── */}
      <section>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-bold">キャッシュフロー分析</h2>
          <Link
            href={`/cashflow?price=${p.price_jpy}&area=${p.floor_area_sqm ?? ""}&year=${p.built_year ?? ""}&mgmt=${p.management_fee_jpy ?? 0}&repair=${p.repair_reserve_jpy ?? 0}`}
            className="text-sm text-primary-600 hover:underline"
          >
            詳細CF分析ページへ →
          </Link>
        </div>

        {/* Quick simulation form */}
        <div className="bg-gray-50 rounded-lg p-4 mb-4">
          <div className="flex items-center gap-3 mb-3">
            <span className="text-sm font-medium text-gray-700">シナリオ:</span>
            <button
              onClick={() => setCfScenario("self_use")}
              className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${cfScenario === "self_use" ? "bg-blue-600 text-white" : "bg-gray-200 text-gray-600"}`}
            >
              自己居住
            </button>
            <button
              onClick={() => setCfScenario("investment")}
              className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${cfScenario === "investment" ? "bg-blue-600 text-white" : "bg-gray-200 text-gray-600"}`}
            >
              投資（賃貸）
            </button>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div>
              <label className="text-xs text-gray-500">頭金（万円）</label>
              <input
                className={inputClass}
                type="number"
                min={0}
                value={Math.round(cfParams.down_payment_jpy / 10000)}
                onChange={(e) => setCfParams({ ...cfParams, down_payment_jpy: Number(e.target.value) * 10000 })}
              />
            </div>
            <div>
              <label className="text-xs text-gray-500">金利（%）</label>
              <input
                className={inputClass}
                type="number"
                step="0.1"
                min={0}
                max={20}
                value={(cfParams.annual_interest_rate * 100).toFixed(1)}
                onChange={(e) => setCfParams({ ...cfParams, annual_interest_rate: Number(e.target.value) / 100 })}
              />
            </div>
            <div>
              <label className="text-xs text-gray-500">返済年数</label>
              <input
                className={inputClass}
                type="number"
                min={1}
                max={50}
                value={cfParams.loan_years}
                onChange={(e) => setCfParams({ ...cfParams, loan_years: Number(e.target.value) })}
              />
            </div>
            <div className="flex items-end">
              <button
                onClick={handleSimulateCF}
                disabled={cfLoading}
                className={btnPrimary + " w-full"}
              >
                {cfLoading ? "計算中..." : "CF分析を実行"}
              </button>
            </div>
          </div>
        </div>

        {/* CF Results */}
        {cfResult && (
          <div className="space-y-4">
            {/* Initial costs + 10yr summary */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <KpiCard title="初期費用合計" value={yenCompact(cfResult.initial_costs.total)} />
              <KpiCard title="10年総コスト" value={yenCompact(cfResult.summary_10yr.total_cost)} />
              <KpiCard
                title={cfScenario === "investment" ? "10年総収入" : "10年控除等"}
                value={yenCompact(cfResult.summary_10yr.total_benefit)}
              />
              <KpiCard
                title="10年純コスト"
                value={yenCompact(cfResult.summary_10yr.net_cost)}
                sub={`月平均 ${yen(Math.round(cfResult.summary_10yr.net_cost / 120))}`}
              />
            </div>

            {/* Exit scenarios */}
            <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
              <h3 className="px-4 py-3 bg-gray-50 text-sm font-bold border-b">売却シミュレーション</h3>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-gray-500 text-xs">
                      <th className="px-3 py-2 text-left">年数</th>
                      <th className="px-3 py-2 text-right">想定売却額</th>
                      <th className="px-3 py-2 text-right">ローン残高</th>
                      <th className="px-3 py-2 text-right">累計CF</th>
                      <th className="px-3 py-2 text-right">トータルリターン</th>
                      <th className="px-3 py-2 text-right">年利回り</th>
                    </tr>
                  </thead>
                  <tbody>
                    {cfResult.exit_scenarios.map((ex: ExitScenarioData) => (
                      <tr key={ex.year} className="border-b border-gray-50 hover:bg-gray-50">
                        <td className="px-3 py-2">{ex.year}年後</td>
                        <td className="px-3 py-2 text-right">{yenCompact(ex.sale_price)}</td>
                        <td className="px-3 py-2 text-right">{yenCompact(ex.outstanding_balance)}</td>
                        <td className={`px-3 py-2 text-right ${ex.cumulative_cashflow >= 0 ? "text-green-600" : "text-red-600"}`}>
                          {signedYen(ex.cumulative_cashflow)}
                        </td>
                        <td className={`px-3 py-2 text-right font-bold ${ex.total_return >= 0 ? "text-green-600" : "text-red-600"}`}>
                          {signedYen(ex.total_return)}
                        </td>
                        <td className={`px-3 py-2 text-right ${ex.annual_roi_pct >= 0 ? "text-green-600" : "text-red-600"}`}>
                          {ex.annual_roi_pct.toFixed(1)}%
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Annual cashflow table (collapsible) */}
            <CashflowDetailTable cashflows={cfResult.annual_cashflows} scenario={cfScenario} />
          </div>
        )}
      </section>
    </div>
  );
}


/* ── Comparable Transactions Table ── */
function CompsTable({ comps }: { comps: CompTransaction[] }) {
  const [open, setOpen] = useState(false);
  const shown = open ? comps : comps.slice(0, 3);
  return (
    <div>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b text-gray-500">
              <th className="px-2 py-1 text-left">駅</th>
              <th className="px-2 py-1 text-right">取引価格</th>
              <th className="px-2 py-1 text-right">㎡単価</th>
              <th className="px-2 py-1 text-right">面積</th>
              <th className="px-2 py-1 text-right">築年</th>
              <th className="px-2 py-1 text-left">間取り</th>
              <th className="px-2 py-1 text-right">類似度</th>
              <th className="px-2 py-1 text-left">時期</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((c, i) => (
              <tr key={i} className="border-b border-gray-50 hover:bg-gray-50">
                <td className="px-2 py-1">{c.station_name}</td>
                <td className="px-2 py-1 text-right">{yenCompact(c.trade_price)}</td>
                <td className="px-2 py-1 text-right">{c.unit_price.toLocaleString()}</td>
                <td className="px-2 py-1 text-right">{c.floor_area}㎡</td>
                <td className="px-2 py-1 text-right">{Math.round(c.age_years)}年</td>
                <td className="px-2 py-1">{c.layout}</td>
                <td className="px-2 py-1 text-right">{(c.similarity * 100).toFixed(0)}%</td>
                <td className="px-2 py-1">{c.trade_period}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {comps.length > 3 && (
        <button
          onClick={() => setOpen(!open)}
          className="text-xs text-primary-600 hover:underline mt-1"
        >
          {open ? "閉じる" : `他${comps.length - 3}件を表示`}
        </button>
      )}
    </div>
  );
}

/* ── Collapsible Annual Cashflow Table ── */
function CashflowDetailTable({
  cashflows,
  scenario,
}: {
  cashflows: CashflowSimulationResult["annual_cashflows"];
  scenario: string;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full px-4 py-3 bg-gray-50 text-sm font-bold border-b flex justify-between items-center hover:bg-gray-100 transition-colors"
      >
        <span>年間キャッシュフロー詳細</span>
        <span className="text-gray-400">{open ? "▲ 閉じる" : "▼ 展開"}</span>
      </button>
      {open && (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b text-gray-500">
                <th className="px-2 py-2 text-left">年</th>
                <th className="px-2 py-2 text-right">ローン返済</th>
                <th className="px-2 py-2 text-right">管理費+修繕</th>
                <th className="px-2 py-2 text-right">固定資産税</th>
                <th className="px-2 py-2 text-right">住宅ローン控除</th>
                {scenario === "investment" && <>
                  <th className="px-2 py-2 text-right">賃料収入</th>
                  <th className="px-2 py-2 text-right">減価償却益</th>
                </>}
                <th className="px-2 py-2 text-right">年間CF</th>
                <th className="px-2 py-2 text-right">累計CF</th>
              </tr>
            </thead>
            <tbody>
              {cashflows.map((cf) => (
                <tr key={cf.year} className="border-b border-gray-50 hover:bg-gray-50">
                  <td className="px-2 py-1.5">{cf.year}年目</td>
                  <td className="px-2 py-1.5 text-right">{yenCompact(cf.loan_payment)}</td>
                  <td className="px-2 py-1.5 text-right">{yenCompact(cf.management_fee + cf.repair_reserve)}</td>
                  <td className="px-2 py-1.5 text-right">{yenCompact(cf.property_tax)}</td>
                  <td className="px-2 py-1.5 text-right text-green-600">{cf.tax_credit > 0 ? `+${yenCompact(cf.tax_credit)}` : "-"}</td>
                  {scenario === "investment" && <>
                    <td className="px-2 py-1.5 text-right text-blue-600">{yenCompact(cf.net_rent)}</td>
                    <td className="px-2 py-1.5 text-right text-blue-600">{cf.depreciation_benefit > 0 ? `+${yenCompact(cf.depreciation_benefit)}` : "-"}</td>
                  </>}
                  <td className={`px-2 py-1.5 text-right font-bold ${cf.cashflow >= 0 ? "text-green-600" : "text-red-600"}`}>
                    {signedYen(cf.cashflow)}
                  </td>
                  <td className={`px-2 py-1.5 text-right ${cf.cumulative_cashflow >= 0 ? "text-green-600" : "text-red-600"}`}>
                    {signedYen(cf.cumulative_cashflow)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
