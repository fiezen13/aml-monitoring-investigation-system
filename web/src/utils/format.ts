/** Định dạng số dùng chung — tabular numbers được bật ở tầng CSS. */

export function formatCompactVnd(amount: number): string {
  if (amount >= 1_000_000_000) {
    return `${(amount / 1_000_000_000).toLocaleString("vi-VN", { maximumFractionDigits: 2 })}B`;
  }
  if (amount >= 1_000_000) {
    return `${(amount / 1_000_000).toLocaleString("vi-VN", { maximumFractionDigits: 0 })}M`;
  }
  return amount.toLocaleString("vi-VN");
}
