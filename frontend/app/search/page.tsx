"use client";

import { useState } from "react";
import Link from "next/link";
import { searchArea, createProperty } from "@/lib/api";
import type { AreaSearchResult, AreaSearchListing, AreaSearchParams } from "@/lib/api";
import type { AreaStats } from "@/lib/types";
import { yen, yenCompact, pct } from "@/lib/format";
import { useRouter } from "next/navigation";

/* ------------------------------------------------------------------ */
/* Constants                                                           */
/* ------------------------------------------------------------------ */

const PRESET_AREAS = [
  { label: "塚口", station: "塚口", pref: "兵庫県" },
  { label: "武庫之荘", station: "武庫之荘", pref: "兵庫県" },
  { label: "立花", station: "立花", pref: "兵庫県" },
  { label: "西宮北口", station: "西宮北口", pref: "兵庫県" },
  { label: "尼崎市全域", city: "尼崎市", pref: "兵庫県" },
  { label: "西宮市全域", city: "西宮市", pref: "兵庫県" },
  { label: "梅田", station: "梅田", pref: "大阪府" },
  { label: "江坂", station: "江坂", pref: "大阪府" },
  { label: "豊中市", city: "豊中市", pref: "大阪府" },
];

const PREFECTURES = [
  "兵庫県", "大阪府", "京都府", "東京都", "神奈川県",
  "埼玉県", "千葉県", "愛知県", "福岡県", "広島県",
  "宮城県", "北海道", "奈良県", "滋賀県",
];

// Grouped by prefecture for multi-station filter
const STATION_GROUPS: Record<string, string[]> = {
  "兵庫県": [
    "塚口", "武庫之荘", "立花", "尼崎", "園田",
    "西宮北口", "夙川", "甲子園", "芦屋", "伊丹",
    "三宮", "六甲道", "住吉", "宝塚", "明石", "姫路",
  ],
  "大阪府": [
    "梅田", "難波", "天王寺", "新大阪", "本町", "心斎橋",
    "京橋", "十三", "江坂", "千里中央", "豊中", "池田",
    "箕面", "茨木", "高槻", "堺",
  ],
  "京都府": ["京都", "四条", "河原町", "烏丸", "宇治"],
};

const LAYOUT_OPTIONS = [
  "1K", "1DK", "1LDK", "2K", "2DK", "2LDK",
  "3K", "3DK", "3LDK", "4LDK",
];

const PRICE_MIN_OPTIONS = [
  { label: "下限なし", value: "" },
  { label: "300万円", value: "300" },
  { label: "500万円", value: "500" },
  { label: "800万円", value: "800" },
  { label: "1,000万円", value: "1000" },
  { label: "1,500万円", value: "1500" },
  { label: "2,000万円", value: "2000" },
  { label: "2,500万円", value: "2500" },
  { label: "3,000万円", value: "3000" },
];

const PRICE_MAX_OPTIONS = [
  { label: "上限なし", value: "" },
  { label: "500万円", value: "500" },
  { label: "800万円", value: "800" },
  { label: "1,000万円", value: "1000" },
  { label: "1,500万円", value: "1500" },
  { label: "2,000万円", value: "2000" },
  { label: "2,500万円", value: "2500" },
  { label: "3,000万円", value: "3000" },
  { label: "4,000万円", value: "4000" },
  { label: "5,000万円", value: "5000" },
];

const AREA_MIN_OPTIONS = [
  { label: "下限なし", value: "" },
  { label: "20㎡", value: "20" },
  { label: "30㎡", value: "30" },
  { label: "40㎡", value: "40" },
  { label: "50㎡", value: "50" },
  { label: "60㎡", value: "60" },
  { label: "70㎡", value: "70" },
  { label: "80㎡", value: "80" },
];

const AREA_MAX_OPTIONS = [
  { label: "上限なし", value: "" },
  { label: "30㎡", value: "30" },
  { label: "40㎡", value: "40" },
  { label: "50㎡", value: "50" },
  { label: "60㎡", value: "60" },
  { label: "70㎡", value: "70" },
  { label: "80㎡", value: "80" },
  { label: "100㎡", value: "100" },
];

const WALK_OPTIONS = [
  { label: "指定なし", value: "" },
  { label: "1分以内", value: "1" },
  { label: "3分以内", value: "3" },
  { label: "5分以内", value: "5" },
  { label: "7分以内", value: "7" },
  { label: "10分以内", value: "10" },
  { label: "15分以内", value: "15" },
  { label: "20分以内", value: "20" },
];

const AGE_OPTIONS = [
  { label: "指定なし", value: "" },
  { label: "新築", value: "1" },
  { label: "3年以内", value: "3" },
  { label: "5年以内", value: "5" },
  { label: "10年以内", value: "10" },
  { label: "15年以内", value: "15" },
  { label: "20年以内", value: "20" },
  { label: "25年以内", value: "25" },
  { label: "30年以内", value: "30" },
];


/* ------------------------------------------------------------------ */
/* Filter state type                                                   */
/* ------------------------------------------------------------------ */

const SOURCE_OPTIONS = [
  { key: "suumo", label: "SUUMO", color: "bg-green-100 text-green-700 border-green-300" },
  { key: "homes", label: "HOME'S", color: "bg-purple-100 text-purple-700 border-purple-300" },
  { key: "athome", label: "athome", color: "bg-orange-100 text-orange-700 border-orange-300" },
] as const;

function sourceLabel(src: string): string {
  if (src === "suumo") return "SUUMO";
  if (src === "homes") return "HOME'S";
  if (src === "athome") return "athome";
  return src;
}

function sourceBadgeClass(src: string): string {
  if (src === "suumo") return "bg-green-100 text-green-700";
  if (src === "homes") return "bg-purple-100 text-purple-700";
  if (src === "athome") return "bg-orange-100 text-orange-700";
  return "bg-gray-100 text-gray-700";
}

interface Filters {
  priceMin: string;
  priceMax: string;
  areaMin: string;
  areaMax: string;
  layouts: string[];
  walkMax: string;
  ageMax: string;
  stations: string[];
  sources: string[];
}

const INITIAL_FILTERS: Filters = {
  priceMin: "",
  priceMax: "",
  areaMin: "",
  areaMax: "",
  layouts: [],
  walkMax: "",
  ageMax: "",
  stations: [],
  sources: ["suumo", "homes", "athome"],
};


/* ------------------------------------------------------------------ */
/* Page component                                                      */
/* ------------------------------------------------------------------ */

// --------------- Client-side filter utility ---------------
function applyLocalFilters(
  listings: AreaSearchListing[],
  f: Filters,
): AreaSearchListing[] {
  const currentYear = new Date().getFullYear();
  return listings.filter((ls) => {
    const price = ls.price_jpy;
    if (f.priceMin && price != null && price < parseInt(f.priceMin) * 10_000)
      return false;
    if (f.priceMax && price != null && price > parseInt(f.priceMax) * 10_000)
      return false;

    const area = ls.floor_area_sqm;
    if (f.areaMin && area != null && area < parseFloat(f.areaMin)) return false;
    if (f.areaMax && area != null && area > parseFloat(f.areaMax)) return false;

    if (f.layouts.length > 0) {
      const layout = ls.layout || "";
      if (layout && !f.layouts.includes(layout)) return false;
    }

    const walk = ls.walking_minutes;
    if (f.walkMax && walk != null && walk > parseInt(f.walkMax)) return false;

    const built = ls.built_year;
    if (f.ageMax && built != null && currentYear - built > parseInt(f.ageMax))
      return false;

    return true;
  });
}

export default function AreaSearchPage() {
  const router = useRouter();
  const [station, setStation] = useState("");
  const [city, setCity] = useState("");
  const [prefecture, setPrefecture] = useState("兵庫県");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AreaSearchResult | null>(null);
  // Cache: stores all listings from the last fetch (before client-side filtering)
  const [cachedAllListings, setCachedAllListings] = useState<AreaSearchListing[]>([]);
  // Track the search params that produced the cached results
  const [cachedSearchKey, setCachedSearchKey] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [sortKey, setSortKey] = useState<string>("price");
  const [registeringUrl, setRegisteringUrl] = useState<string | null>(null);
  const [showFilters, setShowFilters] = useState(false);
  const [filters, setFilters] = useState<Filters>(INITIAL_FILTERS);

  function updateFilter<K extends keyof Filters>(key: K, val: Filters[K]) {
    setFilters((prev) => ({ ...prev, [key]: val }));
  }

  function toggleLayout(layout: string) {
    setFilters((prev) => ({
      ...prev,
      layouts: prev.layouts.includes(layout)
        ? prev.layouts.filter((l) => l !== layout)
        : [...prev.layouts, layout],
    }));
  }

  function toggleStation(stn: string) {
    setFilters((prev) => ({
      ...prev,
      stations: prev.stations.includes(stn)
        ? prev.stations.filter((s) => s !== stn)
        : [...prev.stations, stn],
    }));
  }

  function toggleSource(src: string) {
    setFilters((prev) => {
      const next = prev.sources.includes(src)
        ? prev.sources.filter((s) => s !== src)
        : [...prev.sources, src];
      // Keep at least one source selected
      return next.length > 0 ? { ...prev, sources: next } : prev;
    });
  }

  function resetFilters() {
    setFilters(INITIAL_FILTERS);
    // Immediately restore all cached listings (unfiltered)
    if (result && cachedAllListings.length > 0) {
      setResult({
        ...result,
        listings: cachedAllListings,
        total_found: cachedAllListings.length,
      });
    }
  }

  function hasActiveFilters() {
    return (
      filters.priceMin !== "" ||
      filters.priceMax !== "" ||
      filters.areaMin !== "" ||
      filters.areaMax !== "" ||
      filters.layouts.length > 0 ||
      filters.walkMax !== "" ||
      filters.ageMax !== "" ||
      filters.stations.length > 0 ||
      filters.sources.length < 3
    );
  }

  // Build a cache key from the "location" params (station/city/prefecture/sources)
  // When only filters change, we can re-filter cached results locally
  function buildSearchKey(s: string, c: string, p: string, srcs: string[], stns: string[]): string {
    return JSON.stringify({ s, c, p, srcs: [...srcs].sort(), stns: [...stns].sort() });
  }

  async function handleSearch(
    stationOverride?: string,
    cityOverride?: string,
    prefOverride?: string,
    forceRefetch?: boolean,
  ) {
    // Use explicit overrides; fallback to current state only when override
    // is truly not provided (undefined). Empty string "" IS a valid override.
    const s = stationOverride !== undefined ? stationOverride : station;
    const c = cityOverride !== undefined ? cityOverride : city;
    const p = prefOverride !== undefined ? prefOverride : prefecture;
    // Allow search if we have station/city OR multi-station filter
    if (!s && !c && filters.stations.length === 0) return;

    const searchKey = buildSearchKey(
      filters.stations.length > 0 ? "" : s,
      c, p, filters.sources, filters.stations,
    );

    // --- Client-side re-filtering (no network request needed) ---
    // Use cache when the location/source params haven't changed
    if (!forceRefetch && cachedSearchKey === searchKey && cachedSearchKey !== "") {
      const filtered = applyLocalFilters(cachedAllListings, filters);
      if (result) {
        setResult({
          ...result,
          listings: filtered,
          total_found: filtered.length,
        });
      }
      return;
    }

    // --- Full fetch from backend ---
    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const params: AreaSearchParams = {
        station_name: filters.stations.length > 0 ? "" : s,
        city_name: c,
        prefecture: p,
        max_pages: 3,
      };

      // Only pass filters that constrain the scraping source (SUUMO URL-level)
      // Post-fetch filtering is done client-side for instant re-filtering
      if (filters.stations.length > 0) params.stations = filters.stations;
      if (filters.sources.length < 3) params.sources = filters.sources;

      const res = await searchArea(params);

      // Cache ALL listings (before client-side filtering)
      const allListings = res.listings ?? [];
      setCachedAllListings(allListings);
      setCachedSearchKey(searchKey);

      // Apply client-side filters
      const filtered = applyLocalFilters(allListings, filters);
      setResult({
        ...res,
        listings: filtered,
        total_found: filtered.length,
        total_before_filter: allListings.length,
      });

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
    const s = preset.station ?? "";
    const c = preset.city ?? "";
    const p = preset.pref ?? prefecture;
    setStation(s);
    setCity(c);
    if (preset.pref) setPrefecture(preset.pref);
    // Pass explicit values (NOT undefined) to avoid stale state leakage
    handleSearch(s, c, p);
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
      <div className="bg-white rounded-lg shadow-sm p-5 mb-4">
        <div className="flex gap-3 mb-4">
          <div className="w-32 shrink-0">
            <label className="block text-sm font-medium text-gray-600 mb-1">都道府県</label>
            <select
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
              value={prefecture}
              onChange={(e) => setPrefecture(e.target.value)}
            >
              {PREFECTURES.map((p) => (
                <option key={p} value={p}>{p}</option>
              ))}
            </select>
          </div>
          <div className="flex-1">
            <label className="block text-sm font-medium text-gray-600 mb-1">駅名</label>
            <input
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
              value={station}
              onChange={(e) => setStation(e.target.value)}
              placeholder="例: 塚口、梅田、渋谷..."
              onKeyDown={(e) => e.key === "Enter" && handleSearch()}
              disabled={filters.stations.length > 0}
            />
          </div>
          <div className="flex-1">
            <label className="block text-sm font-medium text-gray-600 mb-1">市区町村</label>
            <input
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
              value={city}
              onChange={(e) => setCity(e.target.value)}
              placeholder="例: 尼崎市、大阪市、世田谷区..."
              onKeyDown={(e) => e.key === "Enter" && handleSearch()}
            />
          </div>
          <div className="flex items-end">
            <button
              onClick={() => handleSearch()}
              disabled={loading || (!station && !city && filters.stations.length === 0)}
              className="bg-blue-600 text-white px-6 py-2 rounded-lg hover:bg-blue-700 disabled:opacity-50 text-sm font-medium transition-colors"
            >
              {loading ? "検索中..." : "検索"}
            </button>
          </div>
        </div>

        {/* Preset area buttons */}
        <div className="flex flex-wrap gap-2 items-center">
          <span className="text-xs text-gray-400 mr-1">よく使うエリア:</span>
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
          <div className="ml-auto">
            <button
              onClick={() => setShowFilters(!showFilters)}
              className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium transition-colors ${
                showFilters || hasActiveFilters()
                  ? "bg-blue-100 text-blue-700"
                  : "bg-gray-100 text-gray-600 hover:bg-gray-200"
              }`}
            >
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2.586a1 1 0 01-.293.707l-6.414 6.414a1 1 0 00-.293.707V17l-4 4v-6.586a1 1 0 00-.293-.707L3.293 7.293A1 1 0 013 6.586V4z" />
              </svg>
              絞り込み
              {hasActiveFilters() && (
                <span className="bg-blue-600 text-white rounded-full w-4 h-4 text-[10px] flex items-center justify-center">
                  {[filters.priceMin, filters.priceMax, filters.areaMin, filters.areaMax, filters.walkMax, filters.ageMax].filter(Boolean).length + (filters.layouts.length > 0 ? 1 : 0) + (filters.stations.length > 0 ? 1 : 0)}
                </span>
              )}
            </button>
          </div>
        </div>
      </div>

      {/* Filters panel */}
      {showFilters && (
        <div className="bg-white rounded-lg shadow-sm p-5 mb-4 border border-blue-100">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-bold text-gray-700">検索条件</h3>
            {hasActiveFilters() && (
              <button onClick={resetFilters} className="text-xs text-red-500 hover:text-red-700">
                条件をリセット
              </button>
            )}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Price range */}
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1.5">価格帯</label>
              <div className="flex items-center gap-2">
                <select
                  className="flex-1 border border-gray-300 rounded px-2 py-1.5 text-sm"
                  value={filters.priceMin}
                  onChange={(e) => updateFilter("priceMin", e.target.value)}
                >
                  {PRICE_MIN_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>{o.label}</option>
                  ))}
                </select>
                <span className="text-gray-400 text-xs">〜</span>
                <select
                  className="flex-1 border border-gray-300 rounded px-2 py-1.5 text-sm"
                  value={filters.priceMax}
                  onChange={(e) => updateFilter("priceMax", e.target.value)}
                >
                  {PRICE_MAX_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>{o.label}</option>
                  ))}
                </select>
              </div>
            </div>

            {/* Area range */}
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1.5">専有面積</label>
              <div className="flex items-center gap-2">
                <select
                  className="flex-1 border border-gray-300 rounded px-2 py-1.5 text-sm"
                  value={filters.areaMin}
                  onChange={(e) => updateFilter("areaMin", e.target.value)}
                >
                  {AREA_MIN_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>{o.label}</option>
                  ))}
                </select>
                <span className="text-gray-400 text-xs">〜</span>
                <select
                  className="flex-1 border border-gray-300 rounded px-2 py-1.5 text-sm"
                  value={filters.areaMax}
                  onChange={(e) => updateFilter("areaMax", e.target.value)}
                >
                  {AREA_MAX_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>{o.label}</option>
                  ))}
                </select>
              </div>
            </div>

            {/* Walking minutes */}
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1.5">駅徒歩</label>
              <select
                className="w-full border border-gray-300 rounded px-2 py-1.5 text-sm"
                value={filters.walkMax}
                onChange={(e) => updateFilter("walkMax", e.target.value)}
              >
                {WALK_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            </div>

            {/* Building age */}
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1.5">築年数</label>
              <select
                className="w-full border border-gray-300 rounded px-2 py-1.5 text-sm"
                value={filters.ageMax}
                onChange={(e) => updateFilter("ageMax", e.target.value)}
              >
                {AGE_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            </div>
          </div>

          {/* Layout chips */}
          <div className="mt-4">
            <label className="block text-xs font-medium text-gray-500 mb-1.5">間取り</label>
            <div className="flex flex-wrap gap-2">
              {LAYOUT_OPTIONS.map((l) => (
                <button
                  key={l}
                  onClick={() => toggleLayout(l)}
                  className={`px-3 py-1 rounded-full text-xs font-medium transition-colors border ${
                    filters.layouts.includes(l)
                      ? "bg-blue-600 text-white border-blue-600"
                      : "bg-white text-gray-600 border-gray-300 hover:border-blue-400"
                  }`}
                >
                  {l}
                </button>
              ))}
            </div>
          </div>

          {/* Source selection */}
          <div className="mt-4">
            <label className="block text-xs font-medium text-gray-500 mb-1.5">検索サイト</label>
            <div className="flex flex-wrap gap-2">
              {SOURCE_OPTIONS.map((s) => (
                <button
                  key={s.key}
                  onClick={() => toggleSource(s.key)}
                  className={`px-3 py-1 rounded-full text-xs font-medium transition-colors border ${
                    filters.sources.includes(s.key)
                      ? s.color
                      : "bg-gray-50 text-gray-400 border-gray-200"
                  }`}
                >
                  {s.label}
                </button>
              ))}
            </div>
            <p className="text-[11px] text-gray-400 mt-1">複数サイトを横断検索してお宝物件を発見</p>
          </div>

          {/* Multi-station chips (grouped by prefecture) */}
          <div className="mt-4">
            <label className="block text-xs font-medium text-gray-500 mb-1.5">
              駅を複数選択
              {filters.stations.length > 0 && (
                <span className="ml-2 text-blue-600">({filters.stations.length}駅)</span>
              )}
            </label>
            {Object.entries(STATION_GROUPS).map(([pref, stns]) => (
              <div key={pref} className="mb-2">
                <span className="text-[11px] text-gray-400 mr-2">{pref}:</span>
                <div className="inline-flex flex-wrap gap-1.5">
                  {stns.map((stn) => (
                    <button
                      key={stn}
                      onClick={() => toggleStation(stn)}
                      className={`px-2.5 py-0.5 rounded-full text-xs font-medium transition-colors border ${
                        filters.stations.includes(stn)
                          ? "bg-blue-600 text-white border-blue-600"
                          : "bg-white text-gray-600 border-gray-300 hover:border-blue-400"
                      }`}
                    >
                      {stn}
                    </button>
                  ))}
                </div>
              </div>
            ))}
            {filters.stations.length > 0 && (
              <p className="text-[11px] text-gray-400 mt-1">複数駅を選択すると、それぞれの駅の結果を統合して表示します</p>
            )}
          </div>

          {/* Search with filters */}
          <div className="mt-4 flex justify-end gap-2">
            <button
              onClick={() => handleSearch()}
              disabled={loading || (!station && !city && filters.stations.length === 0)}
              className="bg-blue-600 text-white px-6 py-2 rounded-lg hover:bg-blue-700 disabled:opacity-50 text-sm font-medium transition-colors"
            >
              {loading ? "検索中..." : cachedAllListings.length > 0 ? "絞り込み適用" : "この条件で検索"}
            </button>
            {cachedAllListings.length > 0 && (
              <button
                onClick={() => handleSearch(undefined, undefined, undefined, true)}
                disabled={loading}
                className="bg-gray-100 text-gray-600 px-4 py-2 rounded-lg hover:bg-gray-200 disabled:opacity-50 text-xs font-medium transition-colors"
              >
                再取得
              </button>
            )}
          </div>
        </div>
      )}

      {error && (
        <div className="bg-red-50 text-red-700 rounded-lg p-4 text-sm mb-6">{error}</div>
      )}

      {/* Area stats summary */}
      {result?.area_stats && <AreaStatsBar stats={result.area_stats} />}

      {/* ML Model info banner */}
      {result?.ml_model_info?.hedonic_available && (
        <div className="bg-gradient-to-r from-purple-50 to-pink-50 border border-purple-200 rounded-lg p-3 mb-4 flex items-center gap-3">
          <span className="bg-purple-600 text-white text-[10px] font-bold px-2 py-0.5 rounded">ML</span>
          <span className="text-xs text-purple-800">
            MLIT実取引データ {result.ml_model_info.dataset_size}件で学習済み
            {result.ml_model_info.hedonic_r2 != null && (
              <span className="ml-2 text-purple-600">
                (R²={result.ml_model_info.hedonic_r2.toFixed(2)}, MAPE={((result.ml_model_info.hedonic_mape ?? 0) * 100).toFixed(1)}%)
              </span>
            )}
          </span>
          <span className="text-[10px] text-purple-500 ml-auto">適正価格・賃料はMLモデルで算出</span>
        </div>
      )}

      {/* Results */}
      {result && (
        <div className="mb-4">
          <div className="flex justify-between items-center mb-3">
            <div className="flex items-center gap-3">
              <p className="text-sm text-gray-600">
                <span className="font-bold text-lg text-gray-900">{result.total_found}</span> 件の物件
                {cachedAllListings.length > 0 && result.total_found < cachedAllListings.length && (
                  <span className="text-xs text-gray-400 ml-2">
                    (全{cachedAllListings.length}件中 絞り込み)
                  </span>
                )}
              </p>
              {result.search_urls && Object.entries(result.search_urls as Record<string, string>).map(([src, url]) => url ? (
                <a
                  key={src}
                  href={url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs text-blue-500 hover:text-blue-700 hover:underline inline-flex items-center gap-1"
                >
                  {sourceLabel(src)}で見る
                  <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" /></svg>
                </a>
              ) : null)}
              {!(result.search_urls) && result.search_url && (
                <a
                  href={result.search_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs text-blue-500 hover:text-blue-700 hover:underline inline-flex items-center gap-1"
                >
                  SUUMOで全件表示
                  <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" /></svg>
                </a>
              )}
            </div>
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

          {sorted.length === 0 && (
            <div className="text-center py-8 text-gray-400 text-sm">
              {cachedAllListings.length > 0 ? (
                <>
                  <p>絞り込み条件に一致する物件がありません。</p>
                  <p className="mt-1">全{cachedAllListings.length}件取得済み — <button onClick={resetFilters} className="text-blue-500 hover:underline">条件をリセット</button>して再表示できます。</p>
                </>
              ) : (
                "条件に一致する物件が見つかりませんでした。条件を変更してお試しください。"
              )}
            </div>
          )}

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
          <p className="text-sm">複数サイトから物件データを取得中...</p>
          <p className="text-xs text-gray-400">SUUMO・HOME&apos;S・athomeを横断検索しています</p>
        </div>
      )}
    </div>
  );
}


/* ------------------------------------------------------------------ */
/* Sub-components                                                      */
/* ------------------------------------------------------------------ */

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
            {listing.source && (
              <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold shrink-0 ${sourceBadgeClass(listing.source)}`}>
                {sourceLabel(listing.source)}
              </span>
            )}
            {listing.name ? (
              listing.url ? (
                <a href={listing.url} target="_blank" rel="noopener noreferrer" className="font-semibold text-blue-700 hover:text-blue-900 hover:underline truncate">
                  {listing.name}
                </a>
              ) : (
                <span className="font-semibold text-gray-900 truncate">{listing.name}</span>
              )
            ) : listing.headline ? (
              listing.url ? (
                <a href={listing.url} target="_blank" rel="noopener noreferrer" className="font-semibold text-blue-700 hover:text-blue-900 hover:underline truncate text-sm">
                  {listing.headline}
                </a>
              ) : (
                <span className="font-semibold text-gray-900 truncate text-sm">{listing.headline}</span>
              )
            ) : listing.url ? (
              <a href={listing.url} target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:text-blue-800 hover:underline text-sm">
                物件詳細ページ
              </a>
            ) : null}
            {listing.vs_market && (
              <span className={`px-2 py-0.5 rounded text-xs font-bold shrink-0 ${
                listing.vs_market.includes("割安") ? "bg-green-100 text-green-700" :
                listing.vs_market.includes("適正") || listing.vs_market === "相場並み" ? "bg-blue-100 text-blue-700" :
                listing.vs_market.includes("割高") ? "bg-amber-100 text-amber-700" :
                "bg-red-100 text-red-700"
              }`}>
                {listing.ml_fair_price ? "ML:" : ""}{listing.vs_market}
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
              <span>
                {listing.line_name ? `${listing.line_name} ` : ""}
                {listing.station_name}駅
                {listing.walking_minutes ? ` 徒歩${listing.walking_minutes}分` : ""}
              </span>
            )}
            {listing.built_year && <span>築{new Date().getFullYear() - listing.built_year}年</span>}
            {listing.age_years != null && !listing.built_year && <span>築{listing.age_years}年</span>}
            {listing.floor && <span>{listing.floor}</span>}
          </div>
          {listing.address && (
            <p className="text-xs text-gray-400 mt-1 truncate">{listing.address}</p>
          )}
          {listing.url && (
            <a
              href={listing.url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-xs text-blue-500 hover:text-blue-700 mt-1"
            >
              {sourceLabel(listing.source || "suumo")}で見る
              <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" /></svg>
            </a>
          )}
        </div>

        {/* Rent & yield + ML fair price */}
        <div className="text-right shrink-0 space-y-1">
          {listing.ml_fair_price && listing.price_jpy && (
            <div>
              <span className="text-[10px] text-purple-500">ML適正価格</span>
              <p className="text-sm font-bold text-purple-700">{yenCompact(listing.ml_fair_price)}</p>
            </div>
          )}
          {listing.estimated_rent && (
            <div>
              <span className="text-[10px] text-gray-400">
                推定賃料
                {listing.rent_confidence === "high" && (
                  <span className="ml-1 text-green-500">&#9679;</span>
                )}
                {listing.rent_confidence === "medium" && (
                  <span className="ml-1 text-yellow-500">&#9679;</span>
                )}
                {listing.rent_confidence === "low" && (
                  <span className="ml-1 text-gray-300">&#9679;</span>
                )}
              </span>
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
