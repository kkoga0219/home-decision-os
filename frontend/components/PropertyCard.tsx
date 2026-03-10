import Link from "next/link";
import type { Property } from "@/lib/types";
import { yen, yenCompact } from "@/lib/format";

interface PropertyCardProps {
  property: Property;
}

export default function PropertyCard({ property: p }: PropertyCardProps) {
  return (
    <Link
      href={`/properties/${p.id}`}
      className="block bg-white rounded-lg border border-gray-200 hover:border-primary-500 hover:shadow-md transition-all p-5"
    >
      <div className="flex items-start justify-between mb-3">
        <h3 className="font-bold text-lg leading-tight">{p.name}</h3>
        <span className="text-lg font-bold text-primary-600 whitespace-nowrap ml-4">
          {yenCompact(p.price_jpy)}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm text-gray-600">
        {p.station_name && (
          <div>
            <span className="text-gray-400">駅 </span>
            {p.station_name} 徒歩{p.walking_minutes}分
          </div>
        )}
        {p.layout && (
          <div>
            <span className="text-gray-400">間取り </span>
            {p.layout}
          </div>
        )}
        {p.floor_area_sqm && (
          <div>
            <span className="text-gray-400">面積 </span>
            {p.floor_area_sqm}㎡
          </div>
        )}
        {p.built_year && (
          <div>
            <span className="text-gray-400">築年 </span>
            {p.built_year}年（築{new Date().getFullYear() - p.built_year}年）
          </div>
        )}
        {(p.management_fee_jpy || p.repair_reserve_jpy) && (
          <div className="col-span-2">
            <span className="text-gray-400">管理費+修繕 </span>
            {yen((p.management_fee_jpy ?? 0) + (p.repair_reserve_jpy ?? 0))}/月
          </div>
        )}
      </div>

      <div className="flex items-center justify-between mt-3">
        {p.address_text && (
          <p className="text-xs text-gray-400 truncate flex-1">{p.address_text}</p>
        )}
        <Link
          href={`/cashflow?price=${p.price_jpy}&area=${p.floor_area_sqm ?? ""}&year=${p.built_year ?? ""}&mgmt=${p.management_fee_jpy ?? 0}&repair=${p.repair_reserve_jpy ?? 0}`}
          onClick={(e) => e.stopPropagation()}
          className="shrink-0 ml-2 bg-blue-50 text-blue-600 hover:bg-blue-100 px-2 py-1 rounded text-xs font-medium transition-colors"
        >
          CF分析
        </Link>
      </div>
    </Link>
  );
}
