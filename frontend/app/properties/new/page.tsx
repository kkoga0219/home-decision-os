"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { createProperty, fetchURLPreview } from "@/lib/api";
import type { PropertyCreate } from "@/lib/types";

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
  const [urlLoading, setUrlLoading] = useState(false);
  const [urlHint, setUrlHint] = useState<string | null>(null);

  function set<K extends keyof PropertyCreate>(key: K, value: PropertyCreate[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  function numOrUndef(v: string): number | undefined {
    const n = Number(v);
    return v === "" || isNaN(n) ? undefined : n;
  }

  async function handleURLPreview() {
    const url = form.source_url;
    if (!url) return;
    setUrlLoading(true);
    setUrlHint(null);
    try {
      const res = await fetchURLPreview(url);
      if (res.success && res.data) {
        const d = res.data;
        const updates: Partial<PropertyCreate> = {};
        if (d.title && !form.name) updates.name = d.title;
        if (d.hint_price_jpy && !form.price_jpy) updates.price_jpy = d.hint_price_jpy;
        if (d.hint_floor_area_sqm && !form.floor_area_sqm) updates.floor_area_sqm = d.hint_floor_area_sqm;
        if (d.hint_layout && !form.layout) updates.layout = d.hint_layout;
        if (d.hint_walking_minutes && !form.walking_minutes) updates.walking_minutes = d.hint_walking_minutes;
        if (d.hint_station_name && !form.station_name) updates.station_name = d.hint_station_name;

        if (Object.keys(updates).length > 0) {
          setForm((prev) => ({ ...prev, ...updates }));
          const fields = Object.keys(updates).join(", ");
          setUrlHint(`自動取得しました: ${fields}`);
        } else {
          setUrlHint("URLからの情報取得を試みましたが、新たに取得できるデータはありませんでした");
        }
      } else {
        setUrlHint("URLからの情報取得に失敗しました");
      }
    } catch {
      setUrlHint("URLへの接続に失敗しました");
    } finally {
      setUrlLoading(false);
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
    <div className="max-w-2xl mx-auto">
      <h1 className="text-2xl font-bold mb-6">物件を登録</h1>

      {error && (
        <div className="bg-red-50 text-red-700 rounded-lg p-4 text-sm mb-6">{error}</div>
      )}

      <form onSubmit={handleSubmit} className="space-y-8">
        {/* URL入力 + 自動取得 */}
        <section>
          <h2 className="text-lg font-semibold mb-4 pb-2 border-b">URLから自動取得</h2>
          <div className="space-y-3">
            <Field label="物件URL" hint="SUUMO / LIFULL HOME'S などのURLを貼ると情報を自動取得します">
              <div className="flex gap-2">
                <input
                  className={inputClass}
                  value={form.source_url ?? ""}
                  onChange={(e) => set("source_url", e.target.value || null)}
                  placeholder="https://suumo.jp/ms/chuko/..."
                />
                <button
                  type="button"
                  onClick={handleURLPreview}
                  disabled={!form.source_url || urlLoading}
                  className="shrink-0 bg-gray-700 text-white px-4 py-2 rounded-lg hover:bg-gray-800 disabled:opacity-50 text-sm font-medium transition-colors"
                >
                  {urlLoading ? "取得中..." : "自動取得"}
                </button>
              </div>
            </Field>
            {urlHint && (
              <div className="bg-blue-50 border border-blue-200 text-blue-700 rounded-lg p-3 text-sm">
                {urlHint}
              </div>
            )}
          </div>
        </section>

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

        {/* Submit */}
        <div className="flex justify-end gap-3 pt-4 border-t">
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
      </form>
    </div>
  );
}
