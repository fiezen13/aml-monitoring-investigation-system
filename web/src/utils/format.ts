/** Định dạng số dùng chung — tabular numbers được bật ở tầng CSS. */

export function formatVnd(amount: number): string {
  return `${amount.toLocaleString("vi-VN")} VNĐ`;
}

export function formatUsd(amount: number): string {
  return amount.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

export function formatCompactVnd(amount: number): string {
  if (amount >= 1_000_000_000) {
    return `${(amount / 1_000_000_000).toLocaleString("vi-VN", { maximumFractionDigits: 2 })}B`;
  }
  if (amount >= 1_000_000) {
    return `${(amount / 1_000_000).toLocaleString("vi-VN", { maximumFractionDigits: 0 })}M`;
  }
  return amount.toLocaleString("vi-VN");
}

export function riskTone(score: number): "risk" | "warn" | "ok" {
  if (score >= 75) return "risk";
  if (score >= 50) return "warn";
  return "ok";
}
