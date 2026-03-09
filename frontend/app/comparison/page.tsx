"use client";

import { useEffect, useState } from "react";
import type { Property, PropertySummary } from "@/lib/types";
import { listProperties, compareProperties } from "@/lib/api";
import { yen, yenCompact, pct, signedYen } from "@/lib/format";

export default function ComparisonPage() {
  const [allProperties, setAllProperties] = useState<Property[]>([]);
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [results, setResults] = useState<PropertySummary[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listProperties().then(setAllProperties).catch((e) => setError(e.message));
  }, []);

  function toggleId(id: number) {
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );
    setResults(null);
  }

  async function handleCompare() {
    if (selectedIds.length < 2) return;
    setLoading(true);
    setError(null);
    try {
      const res = await compareProperties(selectedIds);
      setResults(res.properties);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <h1 className="text-2xl font-bold mb-2">物件比較</h1>
      <p className="text-sm text-gray-500 mb-6">
        比較したい物件を2件以上選択してください
      </p>

      {error && (
        <div className="bg-red-50 text-red-700 rounded-lg p-4 text-sm mb-4">{error}</div>
      )}

      {/* Property selector */}
      <div className="bg-white border border-gray-200 rounded-lg p-4 mb-6">
        <div className="flex flex-wrap gap-2">
          {allProperties.map((p) => (
            <button
              key={p.id}
              onClick={() => toggleId(p.id)}
              className={`px-3 py-1.5 rounded-full text-sm border transition-colors ${
                selectedIds.includes(p.id)
                  ? "bg-primary-600 text-white border-primary-600"
                  : "bg-white text-gray-700 border-gray-300 hover:border-primary-400"
              }`}
            >
              {p.name}
            </button>
          ))}
        </div>
        {allProperties.length === 0 && (
          <p className="text-sm text-gray-400">物件が登録されていません</p>
        )}
        <div className="mt-4">
          <button
            onClick={handleCompare}
            disabled={selectedIds.length < 2 || loading}
            className="bg-primary-600 text-white px-6 py-2 rounded-lg hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed text-sm font-medium transition-colors"
          >
            {loading ? "比較中..." : `${selectedIds.length}件を比較する`}
          </button>
        </div>
      </div>

      {/* Comparison table */}
      {results && results.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm bg-white border border-gray-200 rounded-lg overflow-hidden">
            <thead>
              <tr className="bg-gray-50 border-b">
                <th className="text-left p-3 font-medium text-gray-500 w-40">項目</th>
                {results.map((s) => (
                  <th key={s.property.id} className="text-center p-3 font-bold">
                    {s.property.name}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {/* 基本情報 */}
              <Row label="価格" values={results.map((s) => yenCompact(s.property.price_jpy))} />
              <Row label="面積" values={results.map((s) => s.property.floor_area_sqm ? `${s.property.floor_area_sqm}㎡` : "-")} />
              <Row label="間取り" values={results.map((s) => s.property.layout ?? "-")} />
              <Row label="最寄り駅" values={results.map((s) => s.property.station_name ? `${s.property.station_name} ${s.property.walking_minutes}分` : "-")} />
              <Row label="築年数" values={results.map((s) => s.property.built_year ? `${new Date().getFullYear() - s.property.built_year}年` : "-")} />
              <Row label="管理費+修繕" values={results.map((s) => yen((s.property.management_fee_jpy ?? 0) + (s.property.repair_reserve_jpy ?? 0)))} />

              {/* Separator */}
              <tr><td colSpan={results.length + 1} className="bg-gray-100 p-1" /></tr>

              {/* ローン（最初のシナリオ） */}
              <Row
                label="月額ローン返済"
                values={results.map((s) => s.loan_scenarios[0] ? yen(s.loan_scenarios[0].monthly_payment_jpy) : "-")}
                bold
              />
              <Row
                label="借入額"
                values={results.map((s) => s.loan_scenarios[0] ? yenCompact(s.loan_scenarios[0].loan_amount_jpy) : "-")}
              />
              <Row
                label="金利"
                values={results.map((s) => s.loan_scenarios[0] ? pct(s.loan_scenarios[0].annual_interest_rate) : "-")}
              />
              <Row
                label="総返済額"
                values={results.map((s) => s.loan_scenarios[0] ? yenCompact(s.loan_scenarios[0].total_payment_jpy) : "-")}
              />

              {/* Separator */}
              <tr><td colSpan={results.length + 1} className="bg-gray-100 p-1" /></tr>

              {/* 賃貸CF（最初のシナリオ） */}
              <Row
                label="月次賃貸CF"
                values={results.map((s) => {
                  const cf = s.rental_scenarios[0]?.monthly_net_cashflow_jpy;
                  return cf != null ? signedYen(cf) : "-";
                })}
                colorize
                bold
              />
              <Row
                label="想定家賃"
                values={results.map((s) => s.rental_scenarios[0] ? yen(s.rental_scenarios[0].expected_rent_jpy) : "-")}
              />

              {/* Separator */}
              <tr><td colSpan={results.length + 1} className="bg-gray-100 p-1" /></tr>

              {/* 出口スコア */}
              <Row
                label="出口スコア"
                values={results.map((s) => s.exit_score ? `${s.exit_score.total_score}/100` : "-")}
                colorizeScore
                bold
              />
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

/* ── Row component ── */
interface RowProps {
  label: string;
  values: string[];
  bold?: boolean;
  colorize?: boolean;
  colorizeScore?: boolean;
}

function Row({ label, values, bold, colorize, colorizeScore }: RowProps) {
  function cellColor(val: string): string {
    if (colorize) {
      if (val.startsWith("+")) return "text-green-600";
      if (val.startsWith("-") && val !== "-") return "text-red-600";
    }
    if (colorizeScore) {
      const num = parseInt(val);
      if (!isNaN(num)) {
        if (num >= 70) return "text-green-600";
        if (num >= 50) return "text-yellow-600";
        return "text-red-600";
      }
    }
    return "";
  }

  return (
    <tr className="border-b border-gray-100 hover:bg-gray-50">
      <td className="p-3 text-gray-500 font-medium">{label}</td>
      {values.map((v, i) => (
        <td key={i} className={`p-3 text-center ${bold ? "font-bold" : ""} ${cellColor(v)}`}>
          {v}
        </td>
      ))}
    </tr>
  );
}
