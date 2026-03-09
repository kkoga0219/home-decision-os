interface KpiCardProps {
  title: string;
  value: string;
  sub?: string;
  accent?: "default" | "positive" | "negative";
}

export default function KpiCard({ title, value, sub, accent = "default" }: KpiCardProps) {
  const colorMap = {
    default: "text-gray-900",
    positive: "text-green-600",
    negative: "text-red-600",
  };
  return (
    <div className="bg-white rounded-lg border border-gray-200 p-4">
      <p className="text-xs text-gray-500 mb-1">{title}</p>
      <p className={`text-xl font-bold ${colorMap[accent]}`}>{value}</p>
      {sub && <p className="text-xs text-gray-400 mt-1">{sub}</p>}
    </div>
  );
}
