/**
 * Thang rủi ro — nguồn duy nhất của toàn hệ thống.
 *
 * Trước đây có ba thang song song cho cùng một điểm số 0–100:
 *
 *   - `fc/primitives.RiskScore`  → 80 / 60
 *   - `common/Badges.RiskBadge`  → 75 / 50
 *   - `AlertsPage.RISK_BANDS`    → 75 / 50, và tô bằng ba mã hex ngoài bảng màu
 *
 * Nghĩa là cùng một cảnh báo 78 điểm hiện màu đỏ ở Trung tâm cảnh báo và màu hổ
 * phách ở Tổng quan. Đó là lỗi nghiệp vụ chứ không phải lỗi thẩm mỹ: analyst
 * phân loại việc theo màu.
 *
 * Quyết định: giữ hệ 80/60 của `fc`. Lý do — 80 là ngưỡng đang được dùng ở phía
 * máy chủ và ở chính các trang (`high_risk_alerts` đếm theo ≥ 80, WorldPage suy
 * mức độ hành lang theo 80/60, Dashboard lọc "rủi ro cao" theo ≥ 80). Đổi sang
 * 75/50 sẽ khiến con số trong KPI không khớp với màu của hàng trong bảng.
 *
 * Bổ sung bậc thứ tư `low` (< 40). Bản cũ tô xanh lá cho mọi điểm dưới 60 và
 * gọi tất cả là "TRUNG BÌNH", nên một tài khoản 12 điểm và một tài khoản 58
 * điểm nhìn giống hệt nhau. Xanh lá vẫn giữ nghĩa "dưới ngưỡng", còn dải rất
 * thấp lùi về màu trung tính để không chiếm sự chú ý trong một bảng dài.
 */

import type { Tone } from "./semantic";
import { toneColor } from "./semantic";

export type RiskLevel = "critical" | "high" | "medium" | "low";

/** Ngưỡng dưới của từng bậc, xét từ cao xuống thấp. */
export const RISK_THRESHOLDS = {
  critical: 80,
  high: 60,
  medium: 40,
} as const;

interface RiskSpec {
  level: RiskLevel;
  tone: Tone;
  label: string;
  /** Nhãn viết hoa dùng trong HUD bản đồ và đồ thị. */
  shortLabel: string;
}

const SPEC: Record<RiskLevel, RiskSpec> = {
  critical: { level: "critical", tone: "risk", label: "Nghiêm trọng", shortLabel: "NGHIÊM TRỌNG" },
  high: { level: "high", tone: "warn", label: "Cao", shortLabel: "CAO" },
  medium: { level: "medium", tone: "ok", label: "Trung bình", shortLabel: "TRUNG BÌNH" },
  low: { level: "low", tone: "neutral", label: "Thấp", shortLabel: "THẤP" },
};

export function getRiskLevel(score: number): RiskLevel {
  if (score >= RISK_THRESHOLDS.critical) return "critical";
  if (score >= RISK_THRESHOLDS.high) return "high";
  if (score >= RISK_THRESHOLDS.medium) return "medium";
  return "low";
}

export function getRiskTone(score: number): Tone {
  return SPEC[getRiskLevel(score)].tone;
}

export function getRiskColor(score: number): string {
  return toneColor(getRiskTone(score));
}

export function getRiskLabel(score: number): string {
  return SPEC[getRiskLevel(score)].label;
}

export function getRiskShortLabel(score: number): string {
  return SPEC[getRiskLevel(score)].shortLabel;
}

/**
 * Mức độ ba bậc mà engine bản đồ và đồ thị dùng.
 *
 * Giữ đúng ba giá trị `crit | warn | ok` vì adapter Cesium/MapLibre và bộ test
 * của chúng đã nói bằng ngôn ngữ này; hàm chỉ bảo đảm ngưỡng đến từ cùng một
 * chỗ với phần còn lại của console.
 */
export type Severity = "crit" | "warn" | "ok";

export function severityOf(score: number): Severity {
  const level = getRiskLevel(score);
  if (level === "critical") return "crit";
  if (level === "high") return "warn";
  return "ok";
}

export function severityLabel(severity: Severity): string {
  return severity === "crit" ? "Nghiêm trọng" : severity === "warn" ? "Đáng ngờ" : "Bình thường";
}

/**
 * Màu cho biến động. Tách riêng khỏi thang rủi ro vì "tăng" không mặc định là
 * xấu: số vụ việc đã đóng tăng là tốt, số cảnh báo tồn đọng tăng là xấu.
 */
export function deltaColor(delta: number, higherIsWorse = true): string {
  if (delta === 0) return toneColor("neutral");
  const bad = higherIsWorse ? delta > 0 : delta < 0;
  return bad ? toneColor("risk") : toneColor("ok");
}
