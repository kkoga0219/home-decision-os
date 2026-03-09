"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import type { Property, LoanScenario, RentalScenario, ExitScore, LoanScenarioCreate, RentalScenarioCreate } from "@/lib/types";
import {
  getProperty, deleteProperty,
  listLoanScenarios, createLoanScenario,
  listRentalScenarios, createRentalScenario,
  getExitScore, calculateExitScore,
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
          <button onClick={() => setShowRentalForm(!showRentalForm)} className={btnPrimary}>
            {showRentalForm ? "閉じる" : "+ シナリオ追加"}
          </button>
        </div>

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
    </div>
  );
}
