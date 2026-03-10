"use client";

import { useState } from "react";
import Link from "next/link";
import { searchArea, createProperty } from "@/lib/api";
import type { AreaSearchResult, AreaSearchListing } from "@/lib/api";
import type { AreaStats } from "@/lib/types";
import { yen, yenCompact, pct } from "@/lib/format";
import { useRouter } from "next/navigation";

const PRESET_AREAS = [
  { label: "塚口", station: "塚口" },
  { label: "武庫之荘", station: "武庫之荘" },
  { label: "立花", station: "立花" },
  { label: "西宮北口", station: "西宮北口" },
  { label: "尼崎市全域", city: "尼崎市" },
  { label: "西宮市全域", city: "西宮市" },
];

export default function AreaSearchPage() {
  const router = useRouter();
  const [station, setStation] = useState("");
  const [city, setCity] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AreaSearchResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sortKey, setSortKey] = useState<string>("price");
  const [registeringUrl, setRegisteringUrl] = useState<string | null>(null);

  async function handleSearch(stationOverride?: string, cityOverride?: string) {
    const s = stationOverride ?? station;
    const c = cityOverride ?? city;
    if (!s && !c) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await searchArea({
        station_name: s,
        city_name: c,
        max_pages: 2,
      });
      setResult(res);
      if (!res.success) {
        setError("検索結果の取得に失敗しました。");
      }
    } catch (err: any) {
      setError(err.message || "検索に失敗しました。");
    } finally {
      setLoading(false);
    }
  }

  function handlePreset(preset: typeof PRESET_AREAS[0]) {
    setStation(preset.station ?? "");
    setCity(preset.city ?? "");
    handleSearch(preset.station, preset.city);
  }

  async function handleRegister(listing: AreaSearchListing) {
    if (!listing.price_jpy) return;
    setRegisteringUrl(listing.url);
    try {
      const created = await createProperty({
        name: listing.name || `物件 (${listing.layout || "不明"})`,
        source_url: listing.url,
        price_jpy: listing.price_jpy,
        floor_area_sqm: listing.floor_area_sqm,
        layout: listing.layout,
        station_name: listing.station_name,
        walking_minutes: listing.walking_minutes,
        built_year: listing.built_year,
      });
      router.push(`/properties/${created.id}`);
    } catch (err: any) {
      setError(`登録エラー: ${err.message}`);
    } finally {
      setRegisteringUrl(null);
    }
  }

  // Sort listings
  const listings = result?.listings ?? [];
  const sorted = [...listings].sort((a, b) => {
    if (sortKey === "price") return (a.price_jpy ?? 0) - (b.price_jpy ?? 0);
    if (sortKey === "price_desc") return (b.price_jpy ?? 0) - (a.price_jpy ?? 0);
    if (sortKey === "area") return (b.floor_area_sqm ?? 0) - (a.floor_area_sqm ?? 0);
    if (sortKey === "yield") return (b.gross_yield ?? 0) - (a.gross_yield ?? 0);
    if (sortKey === "market") return (a.vs_market_pct ?? 999) - (b.vs_market_pct ?? 999);
    return 0;
  });

  return (
    <div className="max-w-6xl mx-auto">
      <h1 className="text-2xl font-bold mb-6">エリア物件検索</h1>

      {/* Search bar */}
      <div className="bg-white rounded-lg shadow-sm p-5 mb-6">
        <div className="flex gap-3 mb-4">
          <div className="flex-1">
            <label className="block text-sm font-medium text-gray-600 mb-1">駅名</label>
            <input
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
              value={station}
              onChange={(e) => setStation(e.target.value)}
              placeholder="例: 塚口"
              onKeyDown={(e) => e.key === "Enter" && handleSearch()}
            />
          </div>
          <div className="flex-1">
            <label className="block text-sm font-medium text-gray-600 mb-1">市区町村</label>
            <input
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
              value={city}
              onChange={(e) => setCity(e.target.value)}
              placeholder="例: 尼崎市"
              onKeyDown={(e) => e.key === "Enter" && handleSearch()}
            />
          </div>
          <div className="flex items-end">
            <button
              onClick={() => handleSearch()}
              disabled={loading || (!station && !city)}
              className="bg-blue-600 text-white px-6 py-2 rounded-lg hover:bg-blue-700 disabled:opacity-50 text-sm font-medium transition-colors"
            >
              {loading ? "検索中..." : "検索"}
            </button>
          </div>
        </div>

        {/* Preset area buttons */}
        <div className="flex flex-wrap gap-2">
          <span className="text-xs text-gray-400 self-center mr-1">よく使うエリア:</span>
          {PRESET_AREAS.map((p) => (
            <button
              key={p.label}
              onClick={() => handlePreset(p)}
              disabled={loading}
              className="bg-gray-100 hover:bg-gray-200 text-gray-700 px-3 py-1 rounded-full text-xs font-medium transition-colors disabled:opacity-50"
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      {error && (
        <div className="bg-red-50 text-red-700 rounded-lg p-4 text-sm mb-6">{error}</div>
      )}

      {/* Area stats summary */}
      {result?.area_stats && <AreaStatsBar stats={result.area_stats} />}

      {/* Results */}
      {result && (
        <div className="mb-4">
          <div className="flex justify-between items-center mb-3">
            <p className="text-sm text-gray-600">
              <span className="font-bold text-lg text-gray-900">{result.total_found}</span> 件の物件
            </p>
            <div className="flex gap-2 items-center">
              <span className="text-xs text-gray-400">並び替え:</span>
              <select
                className="border border-gray-300 rounded px-2 py-1 text-xs"
                value={sortKey}
                onChange={(e) => setSortKey(e.target.value)}
              >
                <option value="price">価格 安い順</option>
                <option value="price_desc">価格 高い順</option>
                <option value="area">面積 広い順</option>
                <option value="yield">利回り 高い順</option>
                <option value="market">割安度 順</option>
              </select>
            </div>
          </div>

          {/* Listings grid */}
          <div className="space-y-3">
            {sorted.map((listing, i) => (
              <ListingRow
                key={listing.url + i}
                listing={listing}
                onRegister={() => handleRegister(listing)}
                registering={registeringUrl === listing.url}
              />
            ))}
          </div>

          {result.errors.length > 0 && (
            <div className="mt-4 text-xs text-amber-600 bg-amber-50 rounded p-2">
              {result.errors.map((e, i) => <div key={i}>{e}</div>)}
            </div>
          )}
        </div>
      )}

      {loading && (
        <div className="text-center py-12 text-gray-500">
          <div className="inline-block w-8 h-8 border-4 border-blue-200 border-t-blue-600 rounded-full animate-spin mb-3" />
          <p className="text-sm">SUUMOから物件データを取得中...</p>
          <p className="text-xs text-gray-400">エリア相場・賃料推定も同時に計算しています</p>
        </div>
      )}
    </div>
  );
}


function AreaStatsBar({ stats }: { stats: AreaStats }) {
  return (
    <div className="bg-gradient-to-r from-blue-50 to-indigo-50 border border-blue-200 rounded-lg p-4 mb-6">
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <span className="text-sm font-semibold text-blue-800">{stats.area_name}</span>
          <span className="text-xs text-blue-600 ml-2">エリア相場</span>
        </div>
        <div className="flex gap-6 text-sm">
          <div>
            <span className="text-gray-500">平均㎡単価</span>
            <span className="font-bold text-gray-800 ml-2">{yen(stats.avg_unit_price_sqm)}</span>
          </div>
          <div>
            <span className="text-gray-500">70㎡換算</span>
            <span className="font-bold text-gray-800 ml-2">{yenCompact(stats.avg_price_70sqm)}</span>
          </div>
          <div>
            <span className="text-gray-500">利回り</span>
            <span className="font-bold text-gray-800 ml-2">{pct(stats.avg_gross_yield)}</span>
          </div>
          <div>
            <span className="text-gray-500">動向</span>
            <span className={`font-bold ml-2 ${stats.price_trend === "上昇" ? "text-green-600" : stats.price_trend === "下落" ? "text-red-600" : "text-gray-600"}`}>
              {stats.price_trend}
            </span>
          </div>
        </div>
      </div>
      {stats.note && <p className="text-xs text-blue-500 mt-2">{stats.note}</p>}
    </div>
  );
}


function ListingRow({
  listing,
  onRegister,
  registering,
}: {
  listing: AreaSearchListing;
  onRegister: () => void;
  registering: boolean;
}) {
  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-100 p-4 hover:shadow-md transition-shadow">
      <div className="flex justify-between items-start gap-4">
        {/* Main info */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            {listing.name && (
              <span className="font-semibold text-gray-900 truncate">{listing.name}</span>
            )}
            {listing.vs_market && (
              <span className={`px-2 py-0.5 rounded text-xs font-bold ${
                listing.vs_market === "割安" ? "bg-green-100 text-green-700" :
                listing.vs_market === "相場並み" ? "bg-blue-100 text-blue-700" :
                listing.vs_market === "やや割高" ? "bg-amber-100 text-amber-700" :
                "bg-red-100 text-red-700"
              }`}>
                {listing.vs_market}
                {listing.vs_market_pct != null && ` ${listing.vs_market_pct > 0 ? "+" : ""}${listing.vs_market_pct}%`}
              </span>
            )}
          </div>

          <div className="flex flex-wrap gap-x-4 gap-y-1 text-sm text-gray-600">
            {listing.price_jpy && (
              <span className="font-bold text-lg text-gray-900">{yenCompact(listing.price_jpy)}</span>
            )}
            {listing.layout && <span>{listing.layout}</span>}
            {listing.floor_area_sqm && <span>{listing.floor_area_sqm}㎡</span>}
            {listing.station_name && (
              <span>{listing.station_name}駅 {listing.walking_minutes ? `徒歩${listing.walking_minutes}分` : ""}</span>
            )}
            {listing.built_year && <span>築{new Date().getFullYear() - listing.built_year}年</span>}
            {listing.age_years != null && !listing.built_year && <span>築{listing.age_years}年</span>}
            {listing.floor && <span>{listing.floor}</span>}
          </div>
        </div>

        {/* Rent & yield */}
        <div className="text-right shrink-0">
          {listing.estimated_rent && (
            <div>
              <span className="text-xs text-gray-400">推定賃料</span>
              <p className="text-sm font-bold text-blue-600">{yen(listing.estimated_rent)}<span className="text-xs font-normal">/月</span></p>
            </div>
          )}
          {listing.gross_yield && (
            <p className="text-xs text-gray-500">利回り {pct(listing.gross_yield)}</p>
          )}
        </div>

        {/* Actions */}
        <div className="shrink-0 flex flex-col gap-1.5">
          <button
            onClick={onRegister}
            disabled={!listing.price_jpy || registering}
            className="bg-primary-600 text-white px-3 py-1.5 rounded-lg hover:bg-primary-700 disabled:opacity-50 text-xs font-medium transition-colors"
          >
            {registering ? "登録中..." : "登録"}
          </button>
          {listing.price_jpy && (
            <Link
              href={`/cashflow?price=${listing.price_jpy}&area=${listing.floor_area_sqm ?? ""}&year=${listing.built_year ?? ""}`}
              className="bg-blue-50 text-blue-600 hover:bg-blue-100 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors text-center"
            >
              CF分析
            </Link>
          )}
        </div>
      </div>
    </div>
  );
}
