"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { createProperty, enrichFromURL, enrichFromData } from "@/lib/api";
import type { PropertyCreate, EnrichmentResult } from "@/lib/types";
import { yen, pct } from "@/lib/format";

const INITIAL: PropertyCreate = {
  name: "",
  source_url: "",
  address_text: "",
  station_name: "",
  walking_minutes: undefined,
  price_jpy: 0,
  floor_area_sqm: undefined,
  layout: "",
  built_year: undefined,
  management_fee_jpy: 0,
  repair_reserve_jpy: 0,
  floor_number: undefined,
  total_floors: undefined,
  total_units: undefined,
  zoning_type: "",
  hazard_flag: false,
  memo: "",
};

interface FieldProps {
  label: string;
  required?: boolean;
  children: React.ReactNode;
  hint?: string;
}
function Field({ label, required, children, hint }: FieldProps) {
  return (
    <div>
      <label className="block text-sm font-medium text-gray-700 mb-1">
        {label}
        {required && <span className="text-red-500 ml-1">*</span>}
      </label>
      {children}
      {hint && <p className="text-xs text-gray-400 mt-1">{hint}</p>}
    </div>
  );
}

const inputClass = "w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none";

export default function NewPropertyPage() {
  const router = useRouter();
  const [form, setForm] = useState<PropertyCreate>(INITIAL);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [enriching, setEnriching] = useState(false);
  const [enrichResult, setEnrichResult] = useState<EnrichmentResult | null>(null);

  function set<K extends keyof PropertyCreate>(key: K, value: PropertyCreate[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  function numOrUndef(v: string): number | undefined {
    const n = Number(v);
    return v === "" || isNaN(n) ? undefined : n;
  }

  /** URL-based enrichment: paste URL → auto-fill + market data */
  async function handleEnrichFromURL() {
    const url = form.source_url;
    if (!url) return;
    setEnriching(true);
    setEnrichResult(null);
    try {
      const res = await enrichFromURL(url);
      setEnrichResult(res);

      // Auto-fill empty fields
      const updates: Partial<PropertyCreate> = {};
      if (res.title && !form.name) updates.name = res.title;
      if (res.hint_price_jpy && !form.price_jpy) updates.price_jpy = res.hint_price_jpy;
      if (res.hint_floor_area_sqm && !form.floor_area_sqm) updates.floor_area_sqm = res.hint_floor_area_sqm;
      if (res.hint_layout && !form.layout) updates.layout = res.hint_layout;
      if (res.hint_walking_minutes && !form.walking_minutes) updates.walking_minutes = res.hint_walking_minutes;
      if (res.hint_station_name && !form.station_name) updates.station_name = res.hint_station_name;
      if (res.hint_built_year && !form.built_year) updates.built_year = res.hint_built_year;
      if (res.hint_address_text && !form.address_text) updates.address_text = res.hint_address_text;
      if (res.hint_management_fee_jpy && !form.management_fee_jpy) updates.management_fee_jpy = res.hint_management_fee_jpy;
      if (res.hint_repair_reserve_jpy && !form.repair_reserve_jpy) updates.repair_reserve_jpy = res.hint_repair_reserve_jpy;
      if (res.hint_total_units && !form.total_units) updates.total_units = res.hint_total_units;
      if (res.hint_floor_number && !form.floor_number) updates.floor_number = res.hint_floor_number;
      if (res.hint_total_floors && !form.total_floors) updates.total_floors = res.hint_total_floors;

      if (Object.keys(updates).length > 0) {
        setForm((prev) => ({ ...prev, ...updates }));
      }
    } catch {
      setEnrichResult(null);
      setError("データ取得に失敗しました。URLを確認してください。");
    } finally {
      setEnriching(false);
    }
  }

  /** Manual enrichment: run market analysis on entered data */
  async function handleEnrichFromData() {
    if (!form.price_jpy) return;
    setEnriching(true);
    setEnrichResult(null);
    try {
      const res = await enrichFromData({
        price_jpy: form.price_jpy,
        station_name: form.station_name ?? "",
        address_text: form.address_text ?? "",
        floor_area_sqm: form.floor_area_sqm,
        built_year: form.built_year,
        walking_minutes: form.walking_minutes,
      });
      setEnrichResult(res);
    } catch {
      setError("市場分析に失敗しました。");
    } finally {
      setEnriching(false);
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const created = await createProperty(form);
      router.push(`/properties/${created.id}`);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="max-w-3xl mx-auto">
      <h1 className="text-2xl font-bold mb-6">物件を登録</h1>

      {error && (
        <div className="bg-red-50 text-red-700 rounded-lg p-4 text-sm mb-6">{error}</div>
      )}

      <form onSubmit={handleSubmit} className="space-y-8">
        {/* URL入力 + 統合データ取得 */}
        <section>
          <h2 className="text-lg font-semibold mb-4 pb-2 border-b">URLからデータ取得</h2>
          <div className="space-y-3">
            <Field label="物件URL" hint="SUUMO / LIFULL HOME'S などのURLを貼ると、物件情報 + エリア相場 + 賃料推定を一括取得します">
              <div className="flex gap-2">
                <input
                  className={inputClass}
                  value={form.source_url ?? ""}
                  onChange={(e) => set("source_url", e.target.value || null)}
                  placeholder="https://suumo.jp/ms/chuko/..."
                />
                <button
                  type="button"
                  onClick={handleEnrichFromURL}
                  disabled={!form.source_url || enriching}
                  className="shrink-0 bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 disabled:opacity-50 text-sm font-medium transition-colors"
                >
                  {enriching ? "取得中..." : "データ取得"}
                </button>
              </div>
            </Field>
          </div>
        </section>

        {/* Enrichment results panel */}
        {enrichResult && (
          <EnrichmentPanel result={enrichResult} />
        )}

        {/* 基本情報 */}
        <section>
          <h2 className="text-lg font-semibold mb-4 pb-2 border-b">基本情報</h2>
          <div className="space-y-4">
            <Field label="物件名" required>
              <input className={inputClass} value={form.name} onChange={(e) => set("name", e.target.value)} placeholder="例: プラウド塚口" required />
            </Field>
            <Field label="住所">
              <input className={inputClass} value={form.address_text ?? ""} onChange={(e) => set("address_text", e.target.value || null)} placeholder="例: 兵庫県尼崎市塚口本町1丁目" />
            </Field>
            <div className="grid grid-cols-2 gap-4">
              <Field label="最寄り駅">
                <input className={inputClass} value={form.station_name ?? ""} onChange={(e) => set("station_name", e.target.value || null)} placeholder="例: 塚口" />
              </Field>
              <Field label="徒歩（分）">
                <input className={inputClass} type="number" min={0} value={form.walking_minutes ?? ""} onChange={(e) => set("walking_minutes", numOrUndef(e.target.value))} placeholder="例: 5" />
              </Field>
            </div>
          </div>
        </section>

        {/* 物件スペック */}
        <section>
          <h2 className="text-lg font-semibold mb-4 pb-2 border-b">物件スペック</h2>
          <div className="space-y-4">
            <Field label="価格（円）" required>
              <input className={inputClass} type="number" min={1} value={form.price_jpy || ""} onChange={(e) => set("price_jpy", Number(e.target.value))} placeholder="例: 35000000" required />
            </Field>
            <div className="grid grid-cols-3 gap-4">
              <Field label="面積（㎡）">
                <input className={inputClass} type="number" step="0.1" min={0} value={form.floor_area_sqm ?? ""} onChange={(e) => set("floor_area_sqm", numOrUndef(e.target.value))} placeholder="65.5" />
              </Field>
              <Field label="間取り">
                <input className={inputClass} value={form.layout ?? ""} onChange={(e) => set("layout", e.target.value || null)} placeholder="3LDK" />
              </Field>
              <Field label="築年">
                <input className={inputClass} type="number" min={1950} max={2030} value={form.built_year ?? ""} onChange={(e) => set("built_year", numOrUndef(e.target.value))} placeholder="2015" />
              </Field>
            </div>
            <div className="grid grid-cols-3 gap-4">
              <Field label="階数">
                <input className={inputClass} type="number" min={1} value={form.floor_number ?? ""} onChange={(e) => set("floor_number", numOrUndef(e.target.value))} placeholder="5" />
              </Field>
              <Field label="総階数">
                <input className={inputClass} type="number" min={1} value={form.total_floors ?? ""} onChange={(e) => set("total_floors", numOrUndef(e.target.value))} placeholder="10" />
              </Field>
              <Field label="総戸数">
                <input className={inputClass} type="number" min={1} value={form.total_units ?? ""} onChange={(e) => set("total_units", numOrUndef(e.target.value))} placeholder="52" />
              </Field>
            </div>
          </div>
        </section>

        {/* コスト */}
        <section>
          <h2 className="text-lg font-semibold mb-4 pb-2 border-b">月額コスト</h2>
          <div className="grid grid-cols-2 gap-4">
            <Field label="管理費（円/月）">
              <input className={inputClass} type="number" min={0} value={form.management_fee_jpy ?? ""} onChange={(e) => set("management_fee_jpy", Number(e.target.value) || 0)} placeholder="12000" />
            </Field>
            <Field label="修繕積立金（円/月）">
              <input className={inputClass} type="number" min={0} value={form.repair_reserve_jpy ?? ""} onChange={(e) => set("repair_reserve_jpy", Number(e.target.value) || 0)} placeholder="10000" />
            </Field>
          </div>
        </section>

        {/* 立地条件 */}
        <section>
          <h2 className="text-lg font-semibold mb-4 pb-2 border-b">立地条件</h2>
          <div className="space-y-4">
            <Field label="用途地域">
              <select className={inputClass} value={form.zoning_type ?? ""} onChange={(e) => set("zoning_type", e.target.value || null)}>
                <option value="">選択してください</option>
                <option value="第一種低層住居専用地域">第一種低層住居専用地域</option>
                <option value="第二種低層住居専用地域">第二種低層住居専用地域</option>
                <option value="第一種中高層住居専用地域">第一種中高層住居専用地域</option>
                <option value="第二種中高層住居専用地域">第二種中高層住居専用地域</option>
                <option value="第一種住居地域">第一種住居地域</option>
                <option value="第二種住居地域">第二種住居地域</option>
                <option value="準住居地域">準住居地域</option>
                <option value="近隣商業地域">近隣商業地域</option>
                <option value="商業地域">商業地域</option>
                <option value="準工業地域">準工業地域</option>
                <option value="工業地域">工業地域</option>
                <option value="工業専用地域">工業専用地域</option>
              </select>
            </Field>
            <Field label="ハザード区域">
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" className="rounded" checked={form.hazard_flag ?? false} onChange={(e) => set("hazard_flag", e.target.checked)} />
                ハザードマップで浸水・土砂災害等の区域に該当する
              </label>
            </Field>
          </div>
        </section>

        {/* メモ */}
        <Field label="メモ">
          <textarea className={inputClass} rows={3} value={form.memo ?? ""} onChange={(e) => set("memo", e.target.value || null)} placeholder="気になる点、内覧の感想など..." />
        </Field>

        {/* 市場分析ボタン + Submit */}
        <div className="flex justify-between items-center pt-4 border-t">
          <button
            type="button"
            onClick={handleEnrichFromData}
            disabled={!form.price_jpy || enriching}
            className="bg-green-600 text-white px-4 py-2 rounded-lg hover:bg-green-700 disabled:opacity-50 text-sm font-medium transition-colors"
          >
            {enriching ? "分析中..." : "入力データで市場分析"}
          </button>
          <div className="flex gap-3">
            <button type="button" onClick={() => router.back()} className="px-4 py-2 text-sm text-gray-600 hover:text-gray-800">
              キャンセル
            </button>
            <button
              type="submit"
              disabled={submitting || !form.name || !form.price_jpy}
              className="bg-primary-600 text-white px-6 py-2 rounded-lg hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed text-sm font-medium transition-colors"
            >
              {submitting ? "登録中..." : "登録する"}
            </button>
          </div>
        </div>
      </form>
    </div>
  );
}


/** Enrichment results display panel */
function EnrichmentPanel({ result }: { result: EnrichmentResult }) {
  const { area_stats, rent_estimate, market_comparison, sources_used, errors } = result;

  return (
    <div className="bg-gray-50 border border-gray-200 rounded-lg p-5 space-y-4">
      {/* Sources */}
      <div className="flex flex-wrap gap-2">
        {sources_used.map((s, i) => (
          <span key={i} className="bg-blue-100 text-blue-700 px-2 py-0.5 rounded text-xs font-medium">
            {s}
          </span>
        ))}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Area stats */}
        {area_stats && (
          <div className="bg-white rounded-lg p-4 shadow-sm">
            <h3 className="text-sm font-semibold text-gray-600 mb-2">
              エリア相場: {area_stats.area_name}
            </h3>
            <div className="space-y-1 text-sm">
              <div className="flex justify-between">
                <span className="text-gray-500">平均㎡単価</span>
                <span className="font-medium">{yen(area_stats.avg_unit_price_sqm)}/㎡</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">70㎡換算</span>
                <span className="font-medium">{yen(area_stats.avg_price_70sqm)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">表面利回り</span>
                <span className="font-medium">{pct(area_stats.avg_gross_yield)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">価格動向</span>
                <span className={`font-medium ${area_stats.price_trend === "上昇" ? "text-green-600" : area_stats.price_trend === "下落" ? "text-red-600" : "text-gray-600"}`}>
                  {area_stats.price_trend}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">年間取引</span>
                <span className="font-medium">{area_stats.transaction_count_annual}件</span>
              </div>
            </div>
            {area_stats.note && (
              <p className="text-xs text-gray-400 mt-2">{area_stats.note}</p>
            )}
            <p className="text-xs text-gray-300 mt-1">出典: {area_stats.source}</p>
          </div>
        )}

        {/* Rent estimate */}
        {rent_estimate && (
          <div className="bg-white rounded-lg p-4 shadow-sm">
            <h3 className="text-sm font-semibold text-gray-600 mb-2">推定賃料</h3>
            <div className="text-center mb-3">
              <span className="text-2xl font-bold text-blue-600">{yen(rent_estimate.estimated_rent)}</span>
              <span className="text-sm text-gray-500">/月</span>
            </div>
            <div className="space-y-1 text-sm">
              <div className="flex justify-between">
                <span className="text-gray-500">下限</span>
                <span>{yen(rent_estimate.low_estimate)}/月</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">上限</span>
                <span>{yen(rent_estimate.high_estimate)}/月</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">利回り</span>
                <span>{pct(rent_estimate.gross_yield)}</span>
              </div>
            </div>
            <p className="text-xs text-gray-400 mt-2">{rent_estimate.method}</p>
          </div>
        )}

        {/* Market comparison */}
        {market_comparison && (
          <div className="bg-white rounded-lg p-4 shadow-sm">
            <h3 className="text-sm font-semibold text-gray-600 mb-2">相場比較</h3>
            <div className="text-center mb-3">
              <span className={`text-2xl font-bold ${
                market_comparison.assessment === "割安" ? "text-green-600" :
                market_comparison.assessment === "相場並み" ? "text-blue-600" :
                "text-red-600"
              }`}>
                {market_comparison.assessment}
              </span>
            </div>
            <div className="space-y-1 text-sm">
              <div className="flex justify-between">
                <span className="text-gray-500">この物件(70㎡換算)</span>
                <span className="font-medium">{yen(market_comparison.your_price_70sqm_normalized)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">エリア平均(70㎡)</span>
                <span className="font-medium">{yen(market_comparison.area_avg_70sqm)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">乖離率</span>
                <span className={`font-medium ${market_comparison.diff_percent < 0 ? "text-green-600" : "text-red-600"}`}>
                  {market_comparison.diff_percent > 0 ? "+" : ""}{market_comparison.diff_percent}%
                </span>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Errors */}
      {errors.length > 0 && (
        <div className="text-xs text-amber-600 bg-amber-50 rounded p-2">
          {errors.map((e, i) => <div key={i}>{e}</div>)}
        </div>
      )}
    </div>
  );
}
