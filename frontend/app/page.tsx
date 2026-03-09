"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import type { Property } from "@/lib/types";
import { listProperties } from "@/lib/api";
import PropertyCard from "@/components/PropertyCard";

export default function HomePage() {
  const [properties, setProperties] = useState<Property[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listProperties()
      .then(setProperties)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div>
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold">物件一覧</h1>
          <p className="text-sm text-gray-500 mt-1">登録済みの物件を管理・比較できます</p>
        </div>
        <Link
          href="/properties/new"
          className="inline-flex items-center gap-2 bg-primary-600 text-white px-4 py-2 rounded-lg hover:bg-primary-700 transition-colors text-sm font-medium"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
          </svg>
          物件を登録
        </Link>
      </div>

      {/* Content */}
      {loading && (
        <div className="text-center py-20 text-gray-400">読み込み中...</div>
      )}

      {error && (
        <div className="bg-red-50 text-red-700 rounded-lg p-4 text-sm">
          APIに接続できません: {error}
          <p className="mt-1 text-red-500">バックエンドが起動しているか確認してください (http://localhost:8000)</p>
        </div>
      )}

      {!loading && !error && properties.length === 0 && (
        <div className="text-center py-20">
          <p className="text-gray-400 mb-4">まだ物件が登録されていません</p>
          <Link
            href="/properties/new"
            className="text-primary-600 hover:text-primary-700 font-medium"
          >
            最初の物件を登録する →
          </Link>
        </div>
      )}

      {!loading && !error && properties.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {properties.map((p) => (
            <PropertyCard key={p.id} property={p} />
          ))}
        </div>
      )}
    </div>
  );
}
