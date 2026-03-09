/** Formatting utilities for Japanese currency and numbers. */

export function yen(amount: number | null | undefined): string {
  if (amount == null) return "-";
  return amount.toLocaleString("ja-JP") + "円";
}

export function yenCompact(amount: number | null | undefined): string {
  if (amount == null) return "-";
  if (Math.abs(amount) >= 100_000_000) {
    return (amount / 100_000_000).toFixed(1) + "億円";
  }
  if (Math.abs(amount) >= 10_000) {
    return (amount / 10_000).toFixed(0) + "万円";
  }
  return yen(amount);
}

export function pct(rate: number | null | undefined, digits = 2): string {
  if (rate == null) return "-";
  return (rate * 100).toFixed(digits) + "%";
}

export function signedYen(amount: number | null | undefined): string {
  if (amount == null) return "-";
  const prefix = amount >= 0 ? "+" : "";
  return prefix + yen(amount);
}
