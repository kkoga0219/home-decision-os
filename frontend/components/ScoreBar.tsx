"use client";

interface ScoreBarProps {
  label: string;
  score: number;
  max?: number;
}

function barColor(score: number, max: number): string {
  const ratio = score / max;
  if (ratio >= 0.8) return "bg-green-500";
  if (ratio >= 0.6) return "bg-yellow-500";
  if (ratio >= 0.4) return "bg-orange-500";
  return "bg-red-500";
}

export default function ScoreBar({ label, score, max = 10 }: ScoreBarProps) {
  const pct = Math.min((score / max) * 100, 100);
  return (
    <div className="flex items-center gap-3">
      <span className="text-sm text-gray-600 w-20 shrink-0">{label}</span>
      <div className="flex-1 bg-gray-200 rounded-full h-2.5">
        <div className={`h-2.5 rounded-full ${barColor(score, max)}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-sm font-medium w-8 text-right">{score}</span>
    </div>
  );
}
